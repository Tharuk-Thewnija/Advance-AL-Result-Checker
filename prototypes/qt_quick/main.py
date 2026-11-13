"""Standalone Qt Quick spike. The working Tk application is not imported."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QCoreApplication, QEvent, QUrl, qVersion
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication
from backend import Bridge


def create_app():
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName('ALResultsQtPrototype')
    QQuickStyle.setStyle('Basic')
    bridge = Bridge()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty('bridge', bridge)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / 'qml' / 'Main.qml')))
    if not engine.rootObjects():
        raise RuntimeError('Qt Quick prototype did not load; see QML errors above.')
    window = engine.rootObjects()[0]
    return app, bridge, engine, window


def cleanup(app, bridge, engine, window):
    bridge.timer.stop()
    window.close()
    engine.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--smoke-test', action='store_true')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--benchmark', action='store_true')
    args = parser.parse_args()
    started = time.perf_counter()
    app, bridge, engine, window = create_app()
    try:
        if args.smoke_test or args.benchmark:
            from verification import exercise
            result = exercise(app, bridge, window, started, benchmark=args.benchmark)
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
            print(json.dumps(result, indent=2))
            return 0
        return app.exec()
    finally:
        cleanup(app, bridge, engine, window)


if __name__ == '__main__':
    raise SystemExit(main())
