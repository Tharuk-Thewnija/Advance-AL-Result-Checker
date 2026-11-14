import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QObject, QMetaObject, QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlExpression

from experiments.nonecap.__main__ import configure_storage, load_ui
from experiments.nonecap.backend import PrototypeBridge
from al_results.models import WorkerEvent

KEY = 'nc_live_' + 'x' * 32


class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = patch.dict(os.environ, {'LOCALAPPDATA': str(self.root)})
        env.start(); self.addCleanup(env.stop)
        self.data = configure_storage()
        self.bridge = PrototypeBridge()
        self.addCleanup(self.close)

    def close(self):
        self.bridge.requestClose()
        deadline = time.monotonic() + 5
        while self.bridge.running and time.monotonic() < deadline:
            self.app.processEvents(); time.sleep(.01)
        self.assertFalse(self.bridge.running)
        self.bridge.timer.stop()

    def test_manual_mode_never_constructs_a_client_and_key_is_not_saved(self):
        with patch.object(self.bridge, 'client_factory') as client:
            self.bridge.apiKey = KEY
            self.bridge.startCollection()  # No workbook; no network should be considered.
            client.assert_not_called()
        self.bridge._persist()
        contents = ''.join(p.read_text() for p in self.data.glob('*.json'))
        self.assertNotIn(KEY, contents)
        self.assertNotIn('apiKey', contents)
        self.assertEqual(self.bridge.captchaMode, 'Manual')
        self.assertFalse((self.root / 'ALResultsCollectorQt').exists())
        self.assertFalse((self.root / 'ALResultsCollector').exists())

    def test_automatic_mode_requires_key_before_launch_and_counters_survive_restart(self):
        self.bridge.captchaMode = 'Automatic'
        with patch.object(self.bridge, '_launch') as launch:
            self.bridge.startCollection()
            launch.assert_not_called()
            self.assertIn('API key', self.bridge.status)
        self.bridge.budget.reserve(); self.bridge.budget.settle('solve_test', 2)
        self.bridge.apiKey = KEY
        self.bridge.startCollection()  # Does not reset session counters.
        self.assertEqual(self.bridge.budget.snapshot()['spent'], 2)
        self.assertEqual(self.bridge.budget.snapshot()['attempts'], 1)

    def test_view_has_masked_key_and_mode_binding_without_qml_warnings(self):
        engine, window = load_ui(self.bridge)
        warnings = []
        engine.warnings.connect(lambda errors: warnings.extend(str(e) for e in errors))
        try:
            self.app.processEvents()
            self.assertIn('NONECAP PROTOTYPE', window.title())
            key = window.findChild(QObject, 'apiKeyInput')
            self.assertIsNotNone(key)
            self.assertTrue(QQmlExpression(engine.rootContext(), key, 'echoMode === 2').evaluate()[0])
            self.bridge.captchaMode = 'Automatic'; self.app.processEvents()
            self.bridge.workerCount='5'; self.app.processEvents()
            workers=window.findChild(QObject,'workerCount')
            self.assertEqual(workers.property('count'),5)
            self.assertEqual(workers.property('currentText'),'5')
            self.assertEqual(window.findChild(QObject,'skipWorker').property('count'),5)
            key.setProperty('text', KEY)
            QMetaObject.invokeMethod(key, 'textEdited')
            self.assertEqual(self.bridge.apiKey, KEY)
            self.bridge.apiKey = ''; self.app.processEvents()
            self.assertEqual(key.property('text'), '')
            self.assertIsNone(self.bridge._collector.solver)
            self.assertFalse(warnings, warnings)
        finally:
            window.close(); engine.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_exhausted_credit_budget_prevents_launch_instead_of_manual_timeout(self):
        self.bridge.apiKey=KEY; self.bridge.captchaMode='Automatic'
        self.bridge.budget.reserve(); self.bridge.budget.settle('solve_previous',12)
        with patch.object(self.bridge,'_launch') as launch:
            self.bridge.startCollection()
            launch.assert_not_called()
        self.assertIn('credit threshold',self.bridge.status)
        self.assertIn('No automatic request',self.bridge.status)

    def test_two_worker_skip_routes_to_selected_browser(self):
        self.bridge.captchaMode='Automatic'; self.bridge.workerCount='2'
        self.bridge._phase='collecting'; self.bridge.skipWorker='2'
        self.bridge.skipCurrent()
        self.assertFalse(self.bridge._collector.worker_skips[0].is_set())
        self.assertTrue(self.bridge._collector.worker_skips[1].is_set())
        self.bridge._phase='idle'

    def test_unknown_billing_is_not_labelled_as_a_spending_limit(self):
        self.bridge._handle(WorkerEvent('stopped',{'reason':'billing_unconfirmed','error':'Final charge missing.'}))
        self.assertIn('charge cannot be confirmed',self.bridge.status)
        self.assertNotIn('session limit',self.bridge.status)
        self.assertNotIn('Adjust limits',self.bridge.status)

    def test_raising_limits_does_not_clear_unknown_billing(self):
        self.bridge.apiKey=KEY; self.bridge.captchaMode='Automatic'
        self.bridge.budget.uncertain(); self.bridge.creditLimit='1000'
        with patch.object(self.bridge,'_launch') as launch:
            self.bridge.startCollection()
            launch.assert_not_called()
        self.assertIn('increasing limits will not clear',self.bridge.status)

    def test_worker_range_and_skip_target_follow_selected_count(self):
        self.assertEqual(self.bridge.workerOptions,['1','2','3','4','5'])
        self.bridge.workerCount='5'
        self.assertEqual(self.bridge.skipOptions,['1','2','3','4','5'])
        self.bridge.skipWorker='5'
        self.bridge.captchaMode='Automatic'; self.bridge._phase='collecting'
        self.bridge.skipCurrent()
        self.assertEqual([event.is_set() for event in self.bridge._collector.worker_skips],
                         [False,False,False,False,True])
        self.bridge._phase='idle'; self.bridge.workerCount='2'
        self.assertEqual(self.bridge.skipWorker,'1')
        self.bridge.skipWorker='5'
        self.assertEqual(self.bridge.skipWorker,'1')
        for invalid in ('0','6','abc'):
            self.bridge.workerCount=invalid
            self.assertEqual(self.bridge.workerCount,'2')
