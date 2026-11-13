"""Test the public launcher, not an internal UI entry point."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class StartupTests(unittest.TestCase):
    def test_report_write_failure_exits_instead_of_leaving_window_open(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, 'checker.py', '--smoke-test', '--report', directory],
                                    cwd=Path(__file__).resolve().parents[1],
                                    env=dict(os.environ, LOCALAPPDATA=directory),
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 1)
            self.assertIn('report', result.stderr.lower())

    def test_missing_qml_is_reported_without_a_modal_dialog_in_smoke_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'failure.json'
            script = '''
from unittest.mock import patch
from qt_app.main import launch
with patch('qt_app.main.load_ui', side_effect=RuntimeError('Missing QML plugin')), patch('qt_app.main.QMessageBox.critical', side_effect=AssertionError('Diagnostic mode must not open a modal dialog')):
    raise SystemExit(launch())
'''
            result = subprocess.run([sys.executable, '-c', script, '--smoke-test', '--report', str(report)],
                                    cwd=Path(__file__).resolve().parents[1],
                                    env=dict(os.environ, LOCALAPPDATA=directory),
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 1)
            data = json.loads(report.read_text())
            self.assertFalse(data['loaded'])
            self.assertIn('Missing QML plugin', data['error'])

    def test_default_launcher_opens_qt_and_preserves_both_checkpoint_folders(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            preserved = []
            for relative in ('ALResultsCollector', 'ALResultsCollectorQt/ALResultsCollector'):
                folder = root / relative; folder.mkdir(parents=True)
                path = folder / 'current.sqlite3'
                path.write_bytes(b'Existing saved progress must stay unchanged')
                preserved.append(path)
            report = root / 'startup-report.json'
            result = subprocess.run([sys.executable, 'checker.py', '--smoke-test', '--report', str(report)],
                                    cwd=Path(__file__).resolve().parents[1],
                                    env=dict(os.environ, LOCALAPPDATA=directory),
                                    capture_output=True, text=True, timeout=45)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = json.loads(report.read_text())
            self.assertEqual(data['toolkit'], 'QtQuick')
            self.assertTrue(data['loaded'])
            self.assertEqual(data['subjects'], 63)
            self.assertEqual(Path(data['data_directory']), root / 'ALResultsCollectorQt' / 'ALResultsCollector')
            for path in preserved:
                self.assertEqual(path.read_bytes(), b'Existing saved progress must stay unchanged')
