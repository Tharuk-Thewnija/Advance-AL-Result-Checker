from pathlib import Path
import tempfile
import threading
import unittest
import time
import tracemalloc
from unittest.mock import patch
import pandas as pd
from selenium.common.exceptions import TimeoutException
from al_results.collector import collect, StopRequested, SkipCurrentRow, open_search_form
from al_results.checkpoints import CheckpointStore
from al_results.models import InputWorkbook, RunConfig, RowResult
from tests.test_parsing import CARD
from al_results.events import EventBuffer


class BrowserStub:
    calls = []
    failure = None
    closed = False
    stop_after = None

    def fetch(self, nic, config, stop_event, skip_event, captcha_ready):
        self.calls.append(nic)
        captcha_ready()
        if self.failure:
            raise self.failure
        if self.stop_after and len(self.calls) >= self.stop_after:
            stop_event.set()
        return CARD

    def close(self):
        type(self).closed = True


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path_patch = patch('al_results.checkpoints.checkpoint_path', return_value=self.root / 'current.sqlite3')
        self.path_patch.start(); self.addCleanup(self.path_patch.stop)
        self.browser_patch = patch('al_results.collector.BrowserSession', BrowserStub)
        self.browser_patch.start(); self.addCleanup(self.browser_patch.stop)
        BrowserStub.calls = []; BrowserStub.failure = None; BrowserStub.closed = False; BrowserStub.stop_after = None
        self.book = InputWorkbook(self.root / 'a.xlsx', 'hash', 'First', pd.DataFrame({'NIC': ['900000000V', '200000000001', 'bad']}))
        self.config = RunConfig(self.book.path, ('20',), (), '2025', 1, self.root)
        self.stop = threading.Event(); self.skip = threading.Event(); self.events = []

    def run_worker(self, store=None):
        store = store or CheckpointStore.open(self.book, self.config)
        collect(self.config, self.book, store, self.events.append, self.stop, self.skip)
        return store

    def test_pending_only_and_commit_before_progress(self):
        store = CheckpointStore.open(self.book, self.config)
        store.save(RowResult(0, 'Completed', {'subject:20': 'B'}))
        def emit(event):
            if event.kind == 'progress':
                reader = CheckpointStore.open(self.book, self.config)
                self.assertEqual(len(reader.results()), event.payload['processed']); reader.close()
            self.events.append(event)
        collect(self.config, self.book, store, emit, self.stop, self.skip)
        self.assertEqual(BrowserStub.calls, ['200000000001'])
        reader = CheckpointStore.open(self.book, self.config)
        self.assertEqual([r.status for r in reader.results()], ['Completed', 'Completed', 'Skipped'])
        self.assertEqual(reader.results()[0].values['subject:20'], 'B'); reader.close()
        self.assertTrue(store.closed); self.assertTrue(BrowserStub.closed)
        self.assertEqual(self.events[-1].kind, 'finished')

    def test_timeout_and_skip_are_recorded(self):
        for error, status in [(TimeoutException('captcha timeout'), 'Error'), (SkipCurrentRow('Skipped'), 'Skipped')]:
            with self.subTest(status=status):
                BrowserStub.failure = error
                self.run_worker()
                reader = CheckpointStore.open(self.book, self.config)
                self.assertEqual(reader.results()[0].status, status); reader.discard()

    def test_stop_preserves_committed_rows(self):
        BrowserStub.stop_after = 1
        self.run_worker()
        reader = CheckpointStore.open(self.book, self.config)
        self.assertEqual(reader.pending_positions(), [1, 2]); reader.close()
        self.assertEqual(self.events[-1].kind, 'stopped')

    def test_navigation_and_database_failure_close_resources(self):
        BrowserStub.failure = RuntimeError('Site form unavailable')
        self.run_worker()
        self.assertEqual(self.events[-1].kind, 'fatal')
        self.assertTrue(BrowserStub.closed)
        BrowserStub.failure = None
        store = CheckpointStore.open(self.book, self.config)
        with patch.object(store, 'save', side_effect=OSError('Disk full')):
            self.run_worker(store)
        self.assertEqual(self.events[-1].kind, 'fatal')
        self.assertNotIn('progress', [event.kind for event in self.events])
        self.assertTrue(store.closed)

    def test_stop_before_form_navigation(self):
        self.stop.set()
        with self.assertRaises(StopRequested):
            open_search_form(None, '2025', self.stop, self.skip)

    def test_1000_rows_bounded_handoff_and_no_automatic_export(self):
        self.book = InputWorkbook(self.book.path, 'large', 'First',
                                  pd.DataFrame({'NIC': ['900000000V'] * 1000}))
        buffer = EventBuffer()
        start = time.perf_counter()
        tracemalloc.start()
        store = CheckpointStore.open(self.book, self.config)
        with patch('al_results.excel_io.export_results', side_effect=AssertionError('Unexpected export')):
            collect(self.config, self.book, store, buffer.put, self.stop, self.skip)
        _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
        events = buffer.drain()
        self.assertLessEqual(len(events), 503)
        self.assertEqual(events[-1].kind, 'finished')
        self.assertEqual(events[-1].payload['processed'], 1000)
        reader = CheckpointStore.open(self.book, self.config)
        self.assertEqual(len(reader.results()), 1000); reader.close()
        print(f'\nSynthetic 1000-row parse/checkpoint: {time.perf_counter()-start:.2f}s, traced peak {peak/1024/1024:.2f} MiB')
