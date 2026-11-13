"""Offline scale-test contract: real parsing/storage/export, zero live lookups."""
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from al_results.checkpoints import CheckpointStore
from al_results.excel_io import load_workbook, export_results
from al_results.models import RunConfig
from al_results.parsing import is_valid_nic, parse_results
from qt_app.mock_data import generate_workbook, MockCollector, synthetic_card
from qt_app.storage import configure_storage


class MockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = patch.dict(os.environ, {'LOCALAPPDATA': str(self.root / 'data')})
        env.start(); self.addCleanup(env.stop)
        no_browser = patch('al_results.collector.BrowserSession', side_effect=AssertionError('Unexpected live browser'))
        no_browser.start(); self.addCleanup(no_browser.stop)
        no_network = patch('socket.create_connection', side_effect=AssertionError('Unexpected network'))
        no_network.start(); self.addCleanup(no_network.stop)
        self.stop = threading.Event(); self.skip = threading.Event(); self.events = []

    def prepare(self, count=1500):
        self.path = generate_workbook(self.root / 'mock', count)
        self.book = load_workbook(self.path)
        self.config = RunConfig(self.path, ('20',), ('Candidate Name',), '2025', 180, self.root / 'exports')

    def collect(self, emit=None, delay_scale=0):
        store = CheckpointStore.open(self.book, self.config)
        MockCollector(delay_scale=delay_scale)(self.config, self.book, store,
                                              emit or self.events.append, self.stop, self.skip)
        self.assertTrue(store.closed)

    def test_generated_input_is_fictional_and_stable_for_resume(self):
        self.prepare()
        self.assertEqual(len(self.book.frame), 1500)
        self.assertTrue(all(not is_valid_nic(str(nic)) for nic in self.book.frame['NIC']))
        original = self.path.read_bytes()
        self.assertEqual(generate_workbook(self.root / 'mock', 1500).read_bytes(), original)

    def test_1500_rows_export_has_exact_outcomes_and_missing_subjects(self):
        self.prepare(); self.collect()
        reader = CheckpointStore.open(self.book, self.config)
        try:
            results = reader.results()
            self.assertEqual(len(results), 1500)
            self.assertEqual(sum(r.status == 'Completed' for r in results), 1455)
            self.assertEqual(sum(r.status == 'Skipped' for r in results), 30)
            self.assertEqual(sum(r.status == 'Error' for r in results), 15)
            self.assertEqual(sum(r.status == 'Completed' and r.values['subject:20'] is None for r in results), 64)
            self.assertEqual(results[0].values['subject:20'], 'A')
            self.assertEqual(results[0].values['Candidate Name'], 'MOCK STUDENT 000001')
            output = export_results(self.book, self.config, results)
        finally:
            reader.close()
        import pandas as pd
        frame = pd.read_excel(output)
        self.assertEqual(len(frame), 1500)
        self.assertEqual(frame['Scrape Status'].value_counts().to_dict(), {'Completed': 1455, 'Skipped': 30, 'Error': 15})
        self.assertEqual(frame['Information & Communication Technology Result'].notna().sum(), 1391)
        self.assertEqual(self.events[-1].kind, 'finished')

    def test_stop_partial_export_and_resume_leave_saved_rows_intact(self):
        self.prepare(100)
        def emit(event):
            self.events.append(event)
            if event.kind == 'progress' and event.payload['processed'] == 10:
                self.stop.set()
        self.collect(emit)
        self.assertEqual(self.events[-1].kind, 'stopped')
        reader = CheckpointStore.open(self.book, self.config)
        saved = reader.results(); self.assertEqual(len(saved), 10)
        partial = export_results(self.book, self.config, saved); reader.close()
        import pandas as pd
        self.assertEqual((pd.read_excel(partial)['Scrape Status'] == 'Pending').sum(), 90)
        self.stop.clear(); self.collect()
        reader = CheckpointStore.open(self.book, self.config)
        try:
            self.assertEqual(reader.results()[:10], saved)
            self.assertEqual(len(reader.results()), 100)
        finally:
            reader.close()

    def test_skip_control_and_slow_rows_are_interruptible(self):
        self.prepare(2)
        def emit(event):
            self.events.append(event)
            if event.kind == 'current' and event.payload['position'] == 0:
                self.skip.set()
        self.collect(emit, delay_scale=.01)
        reader = CheckpointStore.open(self.book, self.config)
        try:
            self.assertEqual([r.status for r in reader.results()], ['Skipped', 'Completed'])
        finally:
            reader.close()

    def test_cards_support_selected_subjects_and_general_test_marks(self):
        values = parse_results(synthetic_card(1, ('20', '12')), ('20', '12'), ('Index Number',))
        self.assertEqual(values, {'subject:20': 'A', 'subject:12': '7', 'Index Number': 'MOCK-000001'})

    def test_mock_namespace_cannot_replace_normal_saved_progress(self):
        normal = self.root / 'data' / 'ALResultsCollectorQt' / 'ALResultsCollector'
        normal.mkdir(parents=True)
        (normal / 'current.sqlite3').write_bytes(b'Normal Qt saved progress')
        mock = configure_storage(mock=True)
        self.assertEqual(mock, self.root / 'data' / 'ALResultsCollectorQtMock' / 'ALResultsCollector')
        self.prepare(2); self.collect()
        self.assertTrue((mock / 'current.sqlite3').exists())
        self.assertEqual((normal / 'current.sqlite3').read_bytes(), b'Normal Qt saved progress')

    def test_mock_ui_reports_only_intentional_invalid_rows(self):
        from PySide6.QtWidgets import QApplication
        from qt_app.backend import Bridge
        app = QApplication.instance() or QApplication([])
        self.prepare(100)
        bridge = Bridge(mock=True, collector=MockCollector(delay_scale=0))
        bridge.filePath = str(self.path)
        try:
            bridge.startCollection()
            deadline = time.monotonic() + 10
            while bridge.running and time.monotonic() < deadline:
                app.processEvents(); time.sleep(.002)
            self.assertFalse(bridge.running, bridge.status)
            self.assertEqual((bridge.completed, bridge.skipped, bridge.failed), (97, 2, 1))
            self.assertIn('2 intentionally invalid mock rows', bridge.logText)
        finally:
            bridge.requestClose(); bridge.timer.stop(); bridge.deleteLater()


if __name__ == '__main__':
    unittest.main()
