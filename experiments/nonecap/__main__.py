"""Run with python -m experiments.nonecap (never stores the API key)."""
import argparse
import os
from pathlib import Path
import sys
import time

from PySide6.QtCore import QCoreApplication, QEvent, QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from al_results.instance import InstanceLock
from al_results import __version__
from .backend import PrototypeBridge


def configure_storage():
    base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local' / 'share')
    root = base / 'ALResultsCollectorNoneCAPPrototype'
    os.environ['LOCALAPPDATA'] = str(root)
    return root / 'ALResultsCollector'


from qt_app.main import load_ui

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--smoke-test', action='store_true', help='Open and render, then exit; no website/API requests')
    parser.add_argument('--compare-workers',action='store_true',help='Compare 1–5 workers offline with simulated API latency')
    parser.add_argument('--report',type=Path,help='JSON report path for --compare-workers')
    args = parser.parse_args()
    if args.smoke_test and args.compare_workers: parser.error('Choose either --smoke-test or --compare-workers.')
    if args.report and not args.compare_workers: parser.error('--report requires --compare-workers.')
    data_dir = configure_storage()
    if args.compare_workers:
        from datetime import datetime
        from .benchmark import run
        run(args.report or data_dir/'reports'/f'worker-comparison-{datetime.now():%Y%m%d-%H%M%S}.json')
        return 0
    app = QApplication(sys.argv[:1])
    app.setApplicationName('ALResultsCollectorNoneCAPPrototype')
    app.setApplicationVersion(__version__)
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parents[2] / 'packaging' / 'app.ico')))
    try:
        with InstanceLock():
            bridge = PrototypeBridge()
            engine, window = load_ui(bridge)
            try:
                if args.smoke_test:
                    def rendered():
                        print(f'NoneCAP prototype rendered. Mode={bridge.captchaMode}; subjects={bridge.source.rowCount()}; storage={data_dir}')
                        window.close()
                    window.frameSwapped.connect(rendered, Qt.ConnectionType.SingleShotConnection)
                    QTimer.singleShot(15000, lambda: app.exit(1))
                return app.exec()
            finally:
                bridge.requestClose()
                while bridge.running:
                    app.processEvents(); time.sleep(.01)
                bridge.apiKey = ''
                bridge._collector.solver = None
                bridge.timer.stop()
                engine.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    except (RuntimeError, OSError) as exc:
        if args.smoke_test:
            print(str(exc), file=sys.stderr)
        else:
            QMessageBox.critical(None, 'Cannot open NoneCAP prototype', str(exc))
        return 1


if __name__ == '__main__':
    sys.exit(main())
