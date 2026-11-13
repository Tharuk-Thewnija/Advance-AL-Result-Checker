import json
from pathlib import Path
import tempfile
import time
import unittest
from PySide6.QtWidgets import QApplication
from qt_app.backend import Bridge
from qt_app.metrics import SessionMetrics


class MetricsTests(unittest.TestCase):
    def test_session_records_memory_ui_ticks_and_json_report(self):
        app = QApplication.instance() or QApplication([])
        bridge = Bridge(mock=True)
        metrics = SessionMetrics(bridge)
        try:
            end = time.monotonic() + .12
            while time.monotonic() < end:
                app.processEvents(); time.sleep(.002)
            report = metrics.snapshot()
            self.assertGreater(report['ui_heartbeat_ticks'], 0)
            self.assertGreater(report['max_ui_gap_ms'], 0)
            self.assertIn('idle', report['max_ui_gap_by_phase_ms'])
            self.assertGreater(report['peak_rss_mib'], 0)
            self.assertGreaterEqual(report['peak_rss_mib'], report['current_rss_mib'])
            with tempfile.TemporaryDirectory() as folder:
                path = metrics.save_report(Path(folder))
                saved = json.loads(path.read_text())
                self.assertEqual(saved['mode'], 'offline_mock')
                self.assertEqual(saved['counts']['processed'], 0)
            self.assertIn('RAM', bridge.diagnostics)
        finally:
            metrics.stop(); bridge.timer.stop(); bridge.deleteLater()
