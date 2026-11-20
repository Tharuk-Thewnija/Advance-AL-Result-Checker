import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QObject, QMetaObject, QCoreApplication, QEvent, QPointF
from PySide6.QtQuick import QQuickItem
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlExpression

from qt_app.storage import configure_storage
from qt_app.main import load_ui
from qt_app.backend import Bridge as PrototypeBridge
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
        self.assertTrue((self.root / 'ALResultsCollectorQt').exists())
        self.assertFalse((self.root / 'ALResultsCollectorNoneCAPPrototype').exists())
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
            self.assertEqual(window.title(),'A/L Results Collector')
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

    def test_solve_timeout_shows_pending_and_paid_resume_warning(self):
        self.bridge._handle(WorkerEvent('stopped', {'reason':'automatic_timeout'}))
        self.assertIn('pending', self.bridge.status)
        self.assertIn('new paid solve', self.bridge.status)
        self.assertFalse(self.bridge._collector.disabled)

    def test_submission_timeout_shows_pending_without_manual_fallback(self):
        self.bridge._handle(WorkerEvent('stopped', {'reason':'submission_timeout'}))
        self.assertIn('pending', self.bridge.status)
        self.assertIn('new paid solve', self.bridge.status)
        self.assertNotIn('manually', self.bridge.status)
        self.assertFalse(self.bridge._collector.disabled)

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

    def test_account_can_collapse_and_limits_help_is_optional(self):
        self.bridge.captchaMode='Automatic'
        engine,window=load_ui(self.bridge)
        try:
            self.app.processEvents()
            details=window.findChild(QObject,'accountDetails')
            self.assertTrue(details.property('visible'))
            toggle=window.findChild(QObject,'accountToggle')
            QMetaObject.invokeMethod(toggle,'clicked'); self.app.processEvents()
            self.assertFalse(details.property('visible'))
            help_text=window.findChild(QObject,'limitsHelp')
            self.assertFalse(help_text.property('visible'))
            QMetaObject.invokeMethod(window.findChild(QObject,'limitsHelpToggle'),'clicked')
            self.app.processEvents(); self.assertTrue(help_text.property('visible'))
            self.assertIn('0 / 3 attempts',self.bridge.usageText)
            for name,tone in [('stopCollection','stop'),('skipCurrent','warning'),('exportResults','success'),('openOutputFolder','info')]:
                self.assertEqual(window.findChild(QObject,name).property('tone'),tone)
        finally:
            window.close(); engine.deleteLater()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_two_workbooks_can_run_without_restarting_and_keep_usage(self):
        import pandas as pd
        from al_results.nonecap.benchmark import SimulatedClient,WIDGET,CARD
        client=SimulatedClient(0)
        self.bridge.client_factory=lambda key:client
        self.bridge.apiKey=KEY; self.bridge.captchaMode='Automatic'
        self.bridge.creditLimit='100'; self.bridge.maxAttempts='10'
        def factory(core,solver,emit,label=''):
            class Session:
                def fetch(self,nic,config,stop,skip,ready): solver.solve(WIDGET,stop,skip); return CARD
                def close(self): pass
            return Session
        self.bridge._collector.session_type=factory
        def pump():
            deadline=time.monotonic()+10
            while self.bridge.running and not self.bridge.needsDecision and time.monotonic()<deadline:
                self.app.processEvents(); time.sleep(.005)
            self.assertTrue(not self.bridge.running or self.bridge.needsDecision)
        first=self.root/'first.xlsx'; second=self.root/'second.xlsx'
        for path,nic in [(first,'200000000001'),(second,'200000000002')]:
            pd.DataFrame({'NIC':[nic]}).to_excel(path,index=False)
        self.bridge.filePath=str(first); self.bridge.startCollection(); pump()
        self.assertEqual(self.bridge.completed,1)
        self.bridge.exportResults(); pump()
        first_export=Path(self.bridge.lastOutput)
        self.assertTrue(first_export.exists())
        self.bridge.filePath=str(second); self.bridge.startCollection(); pump()
        self.assertTrue(self.bridge.decisionMismatch)
        self.bridge.decide('restart'); pump()
        self.assertEqual(self.bridge.completed,1)
        self.assertEqual((self.bridge.budget.attempts,self.bridge.budget.spent),(2,24))
        self.assertEqual(self.bridge.apiKey,KEY)
        self.assertTrue(first_export.exists())
        self.assertEqual(len(list(self.data.glob('archived-*.sqlite3'))),1)

    def test_actions_fit_minimum_window_with_long_status_in_both_themes(self):
        self.bridge.captchaMode='Automatic'; self.bridge.workerCount='5'
        self.bridge._counts.update(total=4,processed=4,completed=4)
        self.bridge._has_results=True
        self.bridge._performance='5 workers · 4 rows · 84.2s · 2.9 rows/min'
        self.bridge._status='Automatic collection paused because a final charge cannot be confirmed. Pending rows are kept. Check NoneCAP history or select Manual; raising limits will not clear this billing pause.'
        engine,window=load_ui(self.bridge)
        try:
            window.resize(1020,750)
            for theme in ('Dark','Light'):
                self.bridge.theme=theme
                for _ in range(10): self.app.processEvents(); time.sleep(.01)
                for name in ('startCollection','stopCollection','skipCurrent','exportResults','openOutputFolder'):
                    button=window.findChild(QQuickItem,name)
                    bottom=button.mapToScene(QPointF(0,button.height())).y()
                    self.assertLessEqual(bottom,window.height()-60,(theme,name,bottom))
                    self.assertGreater(button.width(),70)
        finally:
            window.close(); engine.deleteLater()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_invalid_key_check_is_visible_in_main_status(self):
        self.bridge.apiKey='invalid'
        self.bridge.checkBalance()
        self.assertIn('API key',self.bridge.status)
        self.assertFalse(self.bridge.running)

    def test_key_cleanup_preserves_bound_method_custom_collectors(self):
        class Receiver:
            def run(self,*args): pass
        bridge=PrototypeBridge(collector=Receiver().run)
        try:
            bridge.apiKey=''; bridge.captchaMode='Automatic'; bridge.captchaMode='Manual'
            self.assertTrue(bridge.requestClose())
        finally: bridge.timer.stop()
