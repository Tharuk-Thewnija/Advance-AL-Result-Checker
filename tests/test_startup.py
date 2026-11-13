import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class StartupTests(unittest.TestCase):
    def test_smoke_startup_exits_without_destroying_titlebar_initialization(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'report.json'
            env = dict(os.environ, LOCALAPPDATA=directory)
            script = '''
import time
import customtkinter as ctk
from al_results.ui import launch
original = ctk.CTk._windows_set_titlebar_color
def slow_titlebar(self, mode):
    time.sleep(1.3)
    return original(self, mode)
ctk.CTk._windows_set_titlebar_color = slow_titlebar
launch()
'''
            result = subprocess.run(
                [sys.executable, '-c', script, '--smoke-test', '--report', str(report)],
                cwd=Path(__file__).resolve().parents[1], env=env,
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('application has been destroyed', result.stderr)
            self.assertEqual(json.loads(report.read_text())['gui'], 'opened')
