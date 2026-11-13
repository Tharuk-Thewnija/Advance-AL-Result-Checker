"""Exercise Chrome startup through the public release-check entry point."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class BrowserReleaseCheckTests(unittest.TestCase):
    def test_real_browser_local_result_and_closed_session(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'browser.json'
            result = subprocess.run([sys.executable, 'checker.py', '--verify-browser', '--report', str(report)],
                                    cwd=Path(__file__).resolve().parents[1],
                                    env=dict(os.environ, LOCALAPPDATA=directory),
                                    capture_output=True, text=True, timeout=90)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = json.loads(report.read_text())
            self.assertEqual(data['local_result'], {'subject:20': 'A', 'Candidate Name': 'LOCAL TEST STUDENT'})
            self.assertTrue(data['closed_session_detected'])
            self.assertTrue(data['browser_version'])
