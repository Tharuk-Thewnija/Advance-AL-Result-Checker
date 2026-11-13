"""Qt entry point with process-local storage isolation and safe worker shutdown."""
import argparse
import json
from pathlib import Path
import sys
import time

from PySide6.QtCore import QCoreApplication, QEvent, QTimer, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication, QMessageBox

from al_results.instance import InstanceLock
from .backend import Bridge
from .storage import configure_storage


def load_ui(bridge):
    QQuickStyle.setStyle('Basic')
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty('bridge', bridge)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / 'qml' / 'Main.qml')))
    if not engine.rootObjects():
        raise RuntimeError('The Qt interface could not load. See the QML error above.')
    return engine, engine.rootObjects()[0]


def launch():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--smoke-test', action='store_true')
    parser.add_argument('--mock', action='store_true', help='Offline 1,500-student test; no website requests')
    parser.add_argument('--mock-rows', type=int, default=1500, help='Number of fictional rows (1–100000)')
    args = parser.parse_args()
    if not 1 <= args.mock_rows <= 100000:
        parser.error('--mock-rows must be between 1 and 100000')
    if args.mock_rows != 1500 and not args.mock:
        parser.error('--mock-rows requires --mock')
    data_dir = configure_storage(mock=args.mock)
    app = QApplication(sys.argv[:1])
    app.setApplicationName('ALResultsCollectorQt')
    try:
        with InstanceLock():
            bridge = Bridge(mock=args.mock)
            metrics = None
            if args.mock:
                from .mock_data import generate_workbook
                from .metrics import SessionMetrics
                bridge.filePath = str(generate_workbook(data_dir / 'inputs', args.mock_rows))
                bridge.outputFolder = str(data_dir / 'exports')
                bridge._status = f'MOCK TEST: {args.mock_rows:,} fictional students. Click Start mock collection.'
                bridge.log('Offline test: resize the window, try Stop & save, resume, and export. A performance report is saved on close.')
            engine, window = load_ui(bridge)
            if args.mock:
                metrics = SessionMetrics(bridge)
            try:
                if args.smoke_test:
                    def report():
                        print(json.dumps({'graphics_api': window.rendererInterface().graphicsApi().name,
                                          'subjects': bridge.source.rowCount(), 'loaded': True}))
                        window.close()
                    QTimer.singleShot(500, report)
                return app.exec()
            finally:
                # Also protect against an external quit while a task is alive.
                bridge.requestClose()
                while bridge.running:
                    app.processEvents(); time.sleep(.01)
                if metrics:
                    metrics.stop()
                    try:
                        print(f'Mock performance report: {metrics.save_report(data_dir / "reports")}')
                    except OSError as exc:
                        print(f'Could not save mock performance report: {exc}', file=sys.stderr)
                bridge.timer.stop()
                engine.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    except RuntimeError as exc:
        QMessageBox.critical(None, 'Cannot open Qt preview', str(exc))
        return 1
