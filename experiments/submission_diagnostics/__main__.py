"""Separate diagnostic UI; starts in Manual and never starts a job automatically."""
import argparse
import json
from datetime import datetime
import os
from pathlib import Path
import sys
import time
from uuid import uuid4


def configure_storage():
    base = Path(os.environ.get('LOCALAPPDATA') or Path.home()/'.local'/'share')
    root = base/'ALResultsCollectorSubmissionDiagnostics'
    os.environ['LOCALAPPDATA'] = str(root)
    return root/'ALResultsCollector'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true', help='Run local Chrome failure/delay scenarios with fake tokens; no paid requests')
    parser.add_argument('--smoke-test', action='store_true', help='Render diagnostic UI and close without website/API calls')
    parser.add_argument('--network-only', action='store_true', help='Key-free connectivity check; no solves or student lookups')
    args = parser.parse_args()
    if sum((args.offline,args.smoke_test,args.network_only))>1:
        parser.error('Choose one mode')
    if args.network_only:
        from .connectivity import main as connectivity
        return connectivity()
    if args.offline:
        import unittest
        from . import test_scenarios
        from . import test_transport
        suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(module) for module in (test_scenarios,test_transport))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1

    from PySide6.QtCore import QCoreApplication, QEvent, QTimer, Qt
    from PySide6.QtWidgets import QApplication
    from al_results.instance import InstanceLock
    from qt_app.backend import Bridge
    from qt_app.main import load_ui
    from .collector import DiagnosticCollector, Recorder
    from .transport import DiagnosticClient

    data = configure_storage()
    report = data/'reports'/f'submission-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:6]}.jsonl'
    app = QApplication(sys.argv[:1])
    app.setApplicationName('ALResultsCollectorSubmissionDiagnostics')
    import hashlib
    from al_results import collector as core_source
    from al_results.nonecap import collector as auto_source
    from . import transport
    manifest = {'diagnostic_version':2,'request_timeout_seconds':5,
                'source_sha256':{name:hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
                                 for name,module in (('collector',core_source),('automatic_collector',auto_source),('diagnostic_transport',transport))}}
    report.parent.mkdir(parents=True,exist_ok=True)
    report.with_suffix('.manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    with InstanceLock():
        recorder = Recorder(report)
        collector = DiagnosticCollector(lambda update: bridge.creditUpdate.emit(update), recorder)
        bridge = Bridge(collector=collector,client_factory=lambda key:DiagnosticClient(key,recorder))
        bridge._status = 'SUBMISSION DIAGNOSTICS — separate saved progress. Start a small test explicitly.'
        bridge.log('DIAGNOSTICS: observes submitted results for up to 60s; records the original 20s cutoff. No automatic paid retries.')
        bridge.log('DIAGNOSTICS v2: API request stage, HTTP status, timeout/DNS/TLS/JSON failures and source fingerprints are recorded without keys or response bodies.')
        bridge.log(f'Diagnostic report (created when collection starts): {report}')
        bridge.outputFolder = str(data/'exports')
        engine, window = load_ui(bridge)
        window.setTitle('A/L Results Collector — Submission diagnostics v2')
        try:
            if args.smoke_test:
                window.frameSwapped.connect(window.close, Qt.ConnectionType.SingleShotConnection)
                QTimer.singleShot(15000, lambda: app.exit(1))
            return app.exec()
        finally:
            bridge.requestClose()
            while bridge.running:
                app.processEvents(); time.sleep(.01)
            bridge.apiKey = ''
            collector.solver = None
            bridge.timer.stop()
            engine.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == '__main__':
    sys.exit(main())
