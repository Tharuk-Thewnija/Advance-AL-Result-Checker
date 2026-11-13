"""Real Excel/SQLite/collector integration; only the network browser is substituted."""
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import pandas as pd
from PySide6.QtWidgets import QApplication
from al_results.collector import StopRequested, SkipCurrentRow
from tests.test_parsing import CARD
from qt_app.backend import Bridge
from qt_app.storage import qt_data_root, configure_storage
from al_results.models import WorkerEvent
from selenium.common.exceptions import InvalidSessionIdException


class Browser:
    stop_after = None
    calls = []
    wait_for_stop = False
    wait_for_skip = False

    def fetch(self, nic, config, stop, skip, captcha_ready):
        type(self).calls.append(nic)
        captcha_ready()
        if self.wait_for_skip and len(self.calls) == 1:
            while not skip.wait(.01):
                if stop.is_set():
                    raise StopRequested()
            skip.clear()
            raise SkipCurrentRow('Skipped from Qt')
        if self.wait_for_stop:
            while not stop.wait(.01):
                pass
            raise StopRequested()
        if self.stop_after and len(self.calls) >= self.stop_after:
            stop.set()
        return CARD

    def close(self):
        pass


class WorkflowTests(unittest.TestCase):
    def test_browser_closed_message_is_actionable_and_saved_results_can_resume(self):
        Browser.stop_after = 1
        self.start()
        Browser.stop_after = None
        self.start()
        with patch.object(Browser, 'fetch', side_effect=InvalidSessionIdException('session deleted', stacktrace=['Native stack detail'])):
            self.bridge.decide('resume'); self.pump()
        self.assertIn('Chrome was closed', self.bridge.status)
        self.assertNotIn('Native stack detail', self.bridge.logText)
        self.assertEqual(self.bridge.processed, 1)
        self.assertTrue(self.bridge.canExport)
        self.start(); self.bridge.decide('resume'); self.pump()
        self.assertEqual(self.bridge.completed, 2)

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = patch.dict(os.environ, {'LOCALAPPDATA': str(self.root / 'data')})
        env.start(); self.addCleanup(env.stop)
        browser = patch('al_results.collector.BrowserSession', Browser)
        browser.start(); self.addCleanup(browser.stop)
        Browser.calls = []; Browser.stop_after = None; Browser.wait_for_stop = False; Browser.wait_for_skip = False
        self.path = self.root / 'students.xlsx'
        pd.DataFrame({'NIC': ['900000000V', '200000000001'],
                      'Student': ['Example A', 'Example B']}).to_excel(self.path, index=False)
        self.bridge = Bridge()
        self.bridge.filePath = str(self.path)
        self.bridge.outputFolder = str(self.root / 'out')
        self.addCleanup(self.cleanup_bridge)

    def cleanup_bridge(self):
        self.bridge.requestClose()
        self.pump(lambda: not self.bridge.running)
        self.bridge.timer.stop()
        self.bridge.deleteLater()
        self.app.processEvents()

    def pump(self, condition=None):
        condition = condition or (lambda: not self.bridge.running or self.bridge.needsDecision)
        deadline = time.monotonic() + 15
        while not condition() and time.monotonic() < deadline:
            self.app.processEvents(); time.sleep(.005)
        self.app.processEvents()
        self.assertTrue(condition(), self.bridge.status)

    def start(self):
        self.bridge.startCollection(); self.pump()

    def test_selected_fields_export_and_input_is_unchanged(self):
        before = self.path.read_bytes()
        self.bridge.selectField('Candidate Name', True)
        self.start()
        self.assertEqual(self.bridge.completed, 2)
        # Editing the next run must not change the captured run being exported.
        self.bridge.clearSubjects(); self.bridge.selectSubject('01', True)
        self.bridge.filePath = str(self.root / 'another.xlsx')
        self.bridge.exportResults(); self.pump()
        output = pd.read_excel(self.bridge.lastOutput)
        self.assertEqual(output['Information & Communication Technology Result'].tolist(), ['A', 'A'])
        self.assertEqual(output['Candidate Name'].tolist(), ['SAMPLE STUDENT'] * 2)
        self.assertNotIn('District Rank', output.columns)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertTrue(self.bridge.canExport)  # Export again without recollecting.

    def test_partial_export_resume_only_pending_rows(self):
        Browser.stop_after = 1
        self.start()
        self.assertEqual(self.bridge.processed, 1)
        self.bridge.exportResults(); self.pump()
        self.assertEqual(pd.read_excel(self.bridge.lastOutput)['Scrape Status'].tolist(), ['Completed', 'Pending'])
        Browser.stop_after = None
        self.start(); self.assertTrue(self.bridge.needsDecision)
        self.bridge.decide('resume'); self.pump()
        self.assertEqual(self.bridge.completed, 2)
        self.assertEqual(len(Browser.calls), 2)

    def test_mismatch_cancel_preserves_saved_rows_and_restart_archives(self):
        self.start()
        self.bridge.examYear = '2024'
        self.start(); self.assertTrue(self.bridge.decisionMismatch)
        self.bridge.decide('cancel'); self.assertFalse(self.bridge.running)
        self.bridge.examYear = '2025'
        self.start(); self.assertFalse(self.bridge.decisionMismatch)
        self.bridge.decide('resume'); self.pump()
        self.assertEqual(len(Browser.calls), 2)
        self.bridge.examYear = '2024'
        self.start(); self.bridge.decide('restart'); self.pump()
        self.assertEqual(len(Browser.calls), 4)
        self.assertEqual(len(list((self.root / 'data' / 'ALResultsCollector').glob('archived-*.sqlite3'))), 1)

    def test_export_failure_keeps_recoverable_results(self):
        self.start()
        with patch('qt_app.backend.export_results', side_effect=PermissionError('Locked output')):
            self.bridge.exportResults(); self.pump()
        self.assertIn('Locked output', self.bridge.status)
        self.assertTrue(self.bridge.canExport)
        self.bridge.exportResults(); self.pump()
        self.assertTrue(Path(self.bridge.lastOutput).is_file())

    def test_invalid_configuration_and_bad_workbook_do_not_start_browser(self):
        self.bridge.captchaTimeout = 'bad'
        self.start(); self.assertIn('timeout', self.bridge.status.lower())
        self.bridge.captchaTimeout = '180'
        pd.DataFrame({'wrong': ['bad']}).to_excel(self.path, index=False)
        self.start(); self.assertIn('NIC', self.bridge.status)
        self.assertEqual(Browser.calls, [])

    def test_close_waits_for_worker_and_keeps_ui_event_loop_alive(self):
        Browser.wait_for_stop = True
        self.bridge.startCollection()
        self.pump(lambda: bool(Browser.calls))
        self.assertFalse(self.bridge.requestClose())
        self.assertTrue(self.bridge.running)
        self.pump(lambda: not self.bridge.running)
        self.assertTrue(self.bridge.requestClose())

    def test_skip_is_forwarded_and_settings_are_frozen_while_collecting(self):
        Browser.wait_for_skip = True
        self.bridge.startCollection()
        self.pump(lambda: bool(Browser.calls))
        self.bridge.examYear = '2024'
        self.assertEqual(self.bridge.examYear, '2025')
        self.bridge.skipCurrent(); self.pump()
        self.assertEqual((self.bridge.completed, self.bridge.skipped), (1, 1))
        self.bridge.exportResults(); self.pump()
        self.assertEqual(pd.read_excel(self.bridge.lastOutput)['Scrape Status'].tolist(), ['Skipped', 'Completed'])

    def test_close_during_loading_never_starts_collection(self):
        from al_results.excel_io import load_workbook
        entered = threading.Event(); release = threading.Event()
        def delayed(path):
            entered.set(); release.wait(5)
            return load_workbook(path)
        with patch('qt_app.backend.load_workbook', side_effect=delayed):
            self.bridge.startCollection(); self.pump(entered.is_set)
            self.assertFalse(self.bridge.requestClose())
            release.set(); self.pump(lambda: not self.bridge.running)
        self.assertEqual(Browser.calls, [])

    def test_close_during_export_waits_for_atomic_file_write(self):
        from al_results.excel_io import export_results
        self.start()
        entered = threading.Event(); release = threading.Event()
        def delayed(*args):
            entered.set(); release.wait(5)
            return export_results(*args)
        with patch('qt_app.backend.export_results', side_effect=delayed):
            self.bridge.exportResults(); self.pump(entered.is_set)
            self.assertFalse(self.bridge.requestClose())
            release.set(); self.pump(lambda: not self.bridge.running)
        self.assertTrue(Path(self.bridge.lastOutput).is_file())

    def test_1001_rows_real_import_checkpoint_export(self):
        pd.DataFrame({'NIC': ['900000000V'] * 1001}).to_excel(self.path, index=False)
        self.start(); self.assertEqual(self.bridge.completed, 1001)
        self.bridge.exportResults(); self.pump()
        self.assertEqual(len(pd.read_excel(self.bridge.lastOutput)), 1001)
        self.assertLessEqual(len(self.bridge.logText.splitlines()), 200)

    def test_log_burst_refreshes_the_view_once(self):
        notifications = []
        self.bridge.logChanged.connect(lambda: notifications.append(True))
        for i in range(1000):
            self.bridge.events.put(WorkerEvent('log', {'text': f'message {i}'}))
        self.pump(lambda: 'message 999' in self.bridge.logText)
        self.assertEqual(len(notifications), 1)
        self.assertEqual(len(self.bridge.logText.splitlines()), 200)

    def test_qt_storage_namespace_is_separate(self):
        self.assertEqual(qt_data_root(Path('base')), Path('base') / 'ALResultsCollectorQt')
        legacy = self.root / 'data' / 'ALResultsCollector'
        legacy.mkdir(parents=True)
        (legacy / 'current.sqlite3').write_bytes(b'Existing app checkpoint must stay untouched')
        (legacy / 'preferences.json').write_text('{"year":"2020"}')
        isolated = configure_storage()
        self.start()
        self.assertTrue((isolated / 'current.sqlite3').is_file())
        self.assertEqual((legacy / 'current.sqlite3').read_bytes(), b'Existing app checkpoint must stay untouched')
        self.assertEqual((legacy / 'preferences.json').read_text(), '{"year":"2020"}')


if __name__ == '__main__':
    unittest.main()
