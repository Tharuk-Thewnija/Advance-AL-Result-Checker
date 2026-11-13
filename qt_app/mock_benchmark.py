"""Visible, offline 1,500-row stop/export/resume test. Run with python -m qt_app.mock_benchmark."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import time
from uuid import uuid4

import pandas as pd
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication, QEvent
from al_results.instance import InstanceLock
from .backend import Bridge
from .main import load_ui
from .metrics import SessionMetrics
from .mock_data import generate_workbook, MockCollector


def run(workspace):
    workspace = Path(workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=False)
    # Every benchmark gets fresh app-data, never the interactive mock checkpoint.
    os.environ['LOCALAPPDATA'] = str(workspace / 'appdata')
    source = generate_workbook(workspace / 'inputs', 1500)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    app = QApplication.instance() or QApplication([])
    with InstanceLock():
        bridge = Bridge(mock=True, collector=MockCollector(delay_scale=.05))
        bridge.filePath = str(source); bridge.outputFolder = str(workspace / 'exports')
        bridge.selectField('Candidate Name', True); bridge.selectField('Index Number', True)
        engine, window = load_ui(bridge)
        metrics = SessionMetrics(bridge)
        frames = []
        window.frameSwapped.connect(lambda: frames.append(time.perf_counter()))

        def wait_for(condition, timeout=90):
            deadline = time.monotonic() + timeout
            while not condition() and time.monotonic() < deadline:
                app.processEvents(); time.sleep(.002)
            app.processEvents()
            if not condition():
                raise AssertionError(f'Test timed out: {bridge.status}')

        def change_window(label, action):
            previous = len(frames); started = time.perf_counter()
            action(); window.requestUpdate()
            wait_for(lambda: len(frames) > previous, timeout=5)
            return {'operation': label, 'next_frame_ms': round((time.perf_counter() - started)*1000, 2)}

        try:
            wait_for(lambda: bool(frames), timeout=10)
            bridge.startCollection()
            wait_for(lambda: bridge.processed >= 100)
            transitions = [change_window('maximize', window.showMaximized),
                           change_window('restore', window.showNormal)]
            for width in (1100, 1150, 1200):
                transitions.append(change_window(f'resize-{width}', lambda width=width: window.resize(width, 820)))
            bridge.stopCollection(); wait_for(lambda: not bridge.running)
            partial_count = bridge.processed
            assert 0 < partial_count < 1500
            bridge.exportResults(); wait_for(lambda: not bridge.running)
            partial_export = bridge.lastOutput
            bridge.startCollection(); wait_for(lambda: bridge.needsDecision)
            assert not bridge.decisionMismatch
            bridge.decide('resume'); wait_for(lambda: not bridge.running)
            assert bridge.processed == 1500, bridge.status
            bridge.exportResults(); wait_for(lambda: not bridge.running)
            metrics.stop()
            report = metrics.snapshot()
            report.update(graphics_api=window.rendererInterface().graphicsApi().name,
                          first_frame_after_monitor_start_ms=round((frames[0] - metrics.started) * 1000, 2),
                          window_changes=transitions, partial_rows_before_resume=partial_count,
                          delay_scale=.05, frames_queued=len(frames))
            # Validate exports after stopping the monitor, so the harness's own
            # synchronous readback does not count as a UI stall in the application.
            partial = pd.read_excel(partial_export)
            final = pd.read_excel(bridge.lastOutput)
            assert (partial['Scrape Status'] == 'Pending').sum() == 1500 - partial_count
            assert len(final) == 1500
            assert final['Scrape Status'].value_counts().to_dict() == {'Completed': 1455, 'Skipped': 30, 'Error': 15}
            assert final['Information & Communication Technology Result'].notna().sum() == 1391
            assert final['NIC'].tolist() == pd.read_excel(source)['NIC'].tolist()
            assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
            assert len(bridge.logText.splitlines()) <= 200
            report['checks'] = 'passed: stop, partial export, resume, final export, exact row/outcome/grade counts, unchanged source'
            path = workspace / 'benchmark-report.json'
            path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
            print(json.dumps({'report': str(path), **report}, indent=2))
            return path
        finally:
            metrics.stop(); bridge.requestClose()
            wait_for(lambda: not bridge.running)
            bridge.timer.stop(); window.close(); engine.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=Path('.superpowers') / f'mock-benchmark-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:6]}')
    run(parser.parse_args().workspace)
