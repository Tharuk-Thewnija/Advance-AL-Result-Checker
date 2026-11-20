"""Failure evidence from source runs, using only simulated network responses."""
import io
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import socket
import ssl
import tempfile
import threading
import time
import unittest
import urllib.error
from unittest.mock import Mock, patch

from al_results.failure_report import capture_failures, record_failure
from al_results.models import WorkerEvent
from al_results.nonecap.client import Client, ServiceError


class FailureReportTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        env = patch.dict(os.environ, {'LOCALAPPDATA': str(self.root)})
        env.start()
        self.addCleanup(env.stop)
        self.events = []
        self.key = 'nc_live_' + 'x' * 32

    def rows(self):
        files = list(self.root.rglob('failure-*.jsonl'))
        self.assertEqual(len(files), 1)
        raw = files[0].read_text(encoding='utf-8')
        for sensitive in (self.key, 'private-nic', 'private-body', 'private-url'):
            self.assertNotIn(sensitive, raw)
        return [json.loads(line) for line in raw.splitlines()]

    def test_five_workers_keep_the_first_observed_failure_for_each_row(self):
        with capture_failures(self.events.append) as emit, patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect = urllib.error.URLError(socket.gaierror(-1, 'private-body'))
            def worker(n):
                emit(WorkerEvent('current', {'position': 34+n, 'worker': n, 'nic': 'private-nic'}))
                with self.assertRaises(ServiceError):
                    Client(self.key).balance()
                record_failure('billing', 'billing_unconfirmed')
            with ThreadPoolExecutor(max_workers=5) as pool:
                list(pool.map(worker, range(1, 6)))
            self.assertEqual(opener.return_value.open.call_count, 5)
        rows = self.rows()
        self.assertEqual(len(rows), 5)
        self.assertEqual({(r['row'], r['worker']) for r in rows}, {(35+n, n) for n in range(1, 6)})
        self.assertTrue(all(r['outcome']=='dns_error' and r['operation']=='balance check' and r['elapsed_ms']>=0 for r in rows))

    def test_reports_distinguish_http_socket_and_invalid_replies(self):
        with capture_failures(self.events.append) as emit, patch('urllib.request.build_opener') as opener:
            for i, failure in enumerate((TimeoutError(), ssl.SSLError(), ConnectionResetError(),
                    urllib.error.HTTPError('private-url', 503, 'private-body', {}, io.BytesIO(b'private-body')))):
                emit(WorkerEvent('current', {'position':i}))
                opener.return_value.open.side_effect = failure
                with self.assertRaises(ServiceError):
                    Client(self.key).balance()
            opener.return_value.open.side_effect = None
            response = opener.return_value.open.return_value.__enter__.return_value
            response.status = 200
            response.read.return_value = b'<private-body>'
            emit(WorkerEvent('current', {'position':4}))
            with self.assertRaises(ServiceError):
                Client(self.key).balance()
            emit(WorkerEvent('current', {'position':5}))
            record_failure('result wait', 'result_timeout', wait_limit_s=20)
        rows = self.rows()
        self.assertEqual([r['outcome'] for r in rows], ['timeout','tls_error','connection_reset','http_error','invalid_json','result_timeout'])
        self.assertEqual([r.get('http_status') for r in rows], [None,None,None,503,200,None])
        self.assertEqual(rows[-1]['wait_limit_s'], 20)

    def test_clean_run_creates_no_report_and_unwritable_report_preserves_error(self):
        with capture_failures(self.events.append) as emit:
            emit(WorkerEvent('current', {'position':0}))
        self.assertFalse(list(self.root.rglob('*.jsonl')))
        with capture_failures(self.events.append) as emit:
            emit(WorkerEvent('current', {'position':1}))
            with patch.object(Path, 'open', side_effect=PermissionError('private-body')):
                record_failure('unexpected-private-operation', 'private-body')
        self.assertTrue(any('could not be saved' in e.payload.get('text','') for e in self.events))
        record_failure('billing', 'billing_unconfirmed')
        self.assertFalse(list(self.root.rglob('*.jsonl')))

    def test_source_workflow_reports_five_simultaneous_failures_and_keeps_rows_pending(self):
        import pandas as pd
        from PySide6.QtWidgets import QApplication
        from al_results.nonecap.collector import private_core
        from qt_app.backend import Bridge

        app = QApplication.instance() or QApplication([])
        book = self.root / 'fictional.xlsx'
        pd.DataFrame({'NIC': [f'00000000{i:04}' for i in range(100)]}).to_excel(book, index=False)
        bridge = Bridge()
        core = private_core()
        class OfflineSession:
            def __init__(self):
                self.driver = Mock()
                self.driver.execute_script.return_value = {'sitekey': 'offline'}

            def fetch(self, nic, config, stop, skip, ready):
                ready()
                raise AssertionError('Continued after the connection failure')

            def close(self):
                pass

        core.BrowserSession = OfflineSession
        bridge._collector.core_factory = lambda: core
        bridge.filePath = str(book)
        bridge.outputFolder = str(self.root)
        bridge.captchaMode = 'Automatic'
        bridge.apiKey = self.key
        bridge.workerCount = '5'
        barrier = threading.Barrier(5)

        def unavailable(request, timeout):
            self.assertEqual(request.get_method(), 'GET')
            barrier.wait(timeout=5)
            raise urllib.error.URLError(TimeoutError('private-body'))

        try:
            with patch('urllib.request.build_opener') as opener:
                opener.return_value.open.side_effect = unavailable
                bridge.startCollection()
                deadline = time.monotonic() + 15
                while bridge.running and time.monotonic() < deadline:
                    app.processEvents()
                    time.sleep(.005)
                app.processEvents()
                self.assertFalse(bridge.running, bridge.status)
                self.assertEqual(opener.return_value.open.call_count, 5)
            self.assertEqual((bridge.total, bridge.processed, bridge.failed), (100, 0, 0))
            self.assertIn('Failure report:', bridge.logText)
            rows = self.rows()
            self.assertEqual({r['row'] for r in rows}, set(range(1, 6)))
            self.assertEqual({r['worker'] for r in rows}, set(range(1, 6)))
            self.assertTrue(all(r['operation']=='balance check' and r['outcome']=='timeout' for r in rows))
        finally:
            bridge.requestClose()
            bridge.timer.stop()
            bridge.deleteLater()
