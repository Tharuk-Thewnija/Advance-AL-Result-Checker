"""Qt entry point with process-local storage isolation and safe worker shutdown."""
import argparse
import json
from pathlib import Path
import sys
import time

from PySide6.QtCore import QCoreApplication, QEvent, QTimer, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from al_results import __version__
from al_results.instance import InstanceLock
from .backend import Bridge
from .storage import configure_storage


def load_ui(bridge):
    QCoreApplication.setApplicationVersion(__version__)
    QApplication.instance().setWindowIcon(QIcon(str(Path(__file__).resolve().parents[1] / 'packaging' / 'app.ico')))
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
    parser.add_argument('--report', type=Path, help='Write startup or offline verification JSON')
    parser.add_argument('--verify-mock', action='store_true', help='Run a 1,500-row offline release check in a fresh report workspace')
    parser.add_argument('--verify-browser', action='store_true', help='Test real Chrome with a local page; no examination-site lookup')
    parser.add_argument('--mock', action='store_true', help='Offline 1,500-student test; no website requests')
    parser.add_argument('--mock-rows', type=int, default=1500, help='Number of fictional rows (1–100000)')
    parser.add_argument('--compare-workers',action='store_true',help='Offline comparison of 1–5 workers; no paid solves')
    parser.add_argument('--verify-nonecap',action='store_true',help='Verify automatic collection with local Chrome pages and simulated API replies')
    args = parser.parse_args()
    if args.compare_workers or args.verify_nonecap:
        if args.compare_workers and args.verify_nonecap or args.mock or args.smoke_test or args.verify_mock or args.verify_browser or args.mock_rows!=1500:
            parser.error('Choose one diagnostic mode at a time.')
        if args.verify_nonecap:
            if args.report is None: parser.error('--verify-nonecap requires --report')
            from al_results.nonecap.verification import run
            return run(args.report)
        from datetime import datetime
        from al_results.nonecap.benchmark import run
        run(args.report or configure_storage(mock=True)/'reports'/f'worker-comparison-{datetime.now():%Y%m%d-%H%M%S}.json')
        return 0
    if args.verify_browser:
        if args.report is None:
            parser.error('--verify-browser requires --report')
        from .browser_check import run
        return run(args.report)
    if args.verify_mock:
        if args.report is None:
            parser.error('--verify-mock requires --report')
        from uuid import uuid4
        from .mock_benchmark import run
        args.report.parent.mkdir(parents=True, exist_ok=True)
        generated = run(args.report.parent / f'mock-verification-{uuid4().hex[:8]}')
        args.report.write_text(generated.read_text(encoding='utf-8'), encoding='utf-8')
        return 0
    if args.report and not args.smoke_test:
        parser.error('--report requires --smoke-test, --verify-mock or --verify-browser')
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
                    frames = []
                    window.frameSwapped.connect(lambda: frames.append(True))
                    def report():
                        if not frames:
                            return
                        smoke_timer.stop()
                        result = dict(toolkit='QtQuick', version=__version__,
                                      graphics_api=window.rendererInterface().graphicsApi().name,
                                      subjects=bridge.source.rowCount(), loaded=True,
                                      data_directory=str(data_dir), mock=args.mock)
                        result.update(captcha_mode=bridge.captchaMode,max_workers=len(bridge.workerOptions),
                                      automatic_controls=not bridge.mockMode)
                        try:
                            if args.report:
                                args.report.parent.mkdir(parents=True, exist_ok=True)
                                args.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
                        except OSError as exc:
                            if sys.stderr is not None:
                                print(f'Could not write startup report: {exc}', file=sys.stderr)
                            app.exit(1)
                            return
                        if sys.stdout is not None:
                            print(json.dumps(result))
                        window.close()
                    smoke_timer = QTimer(bridge)
                    smoke_timer.setInterval(50); smoke_timer.timeout.connect(report); smoke_timer.start()
                    QTimer.singleShot(15000, lambda: app.exit(1) if smoke_timer.isActive() else None)
                return app.exec()
            finally:
                # Also protect against an external quit while a task is alive.
                bridge.requestClose()
                while bridge.running:
                    app.processEvents(); time.sleep(.01)
                bridge.apiKey = ''
                if metrics:
                    metrics.stop()
                    try:
                        report_path = metrics.save_report(data_dir / 'reports')
                        if sys.stdout is not None:
                            print(f'Mock performance report: {report_path}')
                    except OSError as exc:
                        if sys.stderr is not None:
                            print(f'Could not save mock performance report: {exc}', file=sys.stderr)
                bridge.timer.stop()
                engine.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    except (RuntimeError, OSError, ValueError) as exc:
        if args.smoke_test:
            if args.report:
                try:
                    args.report.parent.mkdir(parents=True, exist_ok=True)
                    args.report.write_text(json.dumps(dict(loaded=False, error=str(exc)), indent=2) + '\n', encoding='utf-8')
                except OSError:
                    pass
            if sys.stderr is not None:
                print(f'Could not open application: {exc}', file=sys.stderr)
            return 1
        QMessageBox.critical(None, 'Cannot open A/L Results Collector', str(exc))
        return 1
