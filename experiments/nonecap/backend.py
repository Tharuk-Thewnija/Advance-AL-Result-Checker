"""Session-only NoneCAP settings around the unchanged production Qt bridge."""
from PySide6.QtCore import Property, Signal, Slot, Qt

from al_results.models import WorkerEvent
from qt_app.backend import Bridge
from .budget import Budget, LimitReached, ChargeUnconfirmed
from .client import Client, ServiceError
from .collector import PrototypeCollector, MAX_WORKERS
from .solver import Solver


class PrototypeBridge(Bridge):
    captchaChanged = Signal()
    creditUpdate = Signal(dict)

    def __init__(self, *, client_factory=Client):
        self._mode, self._api_key = 'Manual', ''
        self._credit_limit, self._max_attempts = '10', '3'
        self._worker_count, self._skip_worker = '1', '1'
        self._performance = 'Choose 1–5 workers to compare batch throughput.'
        self._balance = 'Balance not checked'
        self._auto_status = 'Manual mode: solve CAPTCHA in Chrome. No automatic requests.'
        self.budget = Budget()
        self.client_factory = client_factory
        super().__init__()
        self._collector = PrototypeCollector(self.creditUpdate.emit)
        self.creditUpdate.connect(self._credit_update, Qt.ConnectionType.QueuedConnection)
        self._logs.clear()
        self.log('NONECAP PROTOTYPE — separate saved progress. API key is kept only in this window.')

    def _session_setting(name, notify):
        def get(self): return getattr(self, name)
        def set(self, value):
            if not self.running:
                if name == '_mode' and value not in ('Manual', 'Automatic'): return
                if name == '_worker_count' and value not in self.workerOptions: return
                setattr(self, name, value)
                if name == '_worker_count' and int(self._skip_worker)>int(value): self._skip_worker='1'
                if name == '_api_key':
                    # Drop the old client's reference too when clearing/changing a key.
                    self._collector.solver = None
                    self._balance = 'Balance not checked'
                if name == '_mode':
                    if value == 'Manual': self._collector.solver = None
                    self._auto_status = ('Manual mode: solve CAPTCHA in Chrome. No automatic requests.' if value == 'Manual' else
                        'Automatic mode is disabled for this window; collection will continue manually.' if self._collector.disabled else
                        'Automatic mode selected. Start may spend NoneCAP credits.')
                self.captchaChanged.emit()
        return Property(str, get, set, notify=notify)

    captchaMode = _session_setting('_mode', captchaChanged)
    apiKey = _session_setting('_api_key', captchaChanged)
    creditLimit = _session_setting('_credit_limit', captchaChanged)
    maxAttempts = _session_setting('_max_attempts', captchaChanged)
    workerCount = _session_setting('_worker_count', captchaChanged)
    workerOptions = Property('QVariantList',lambda self:[str(n) for n in range(1,MAX_WORKERS+1)],constant=True)
    skipOptions = Property('QVariantList',lambda self:[str(n) for n in range(1,int(self._worker_count)+1)],notify=captchaChanged)
    performanceText = Property(str,lambda self:self._performance,notify=captchaChanged)

    @Property(str,notify=captchaChanged)
    def skipWorker(self): return self._skip_worker

    @skipWorker.setter
    def skipWorker(self,value):
        if value in self.skipOptions:
            self._skip_worker=value; self.captchaChanged.emit()

    @Slot()
    def skipCurrent(self):
        if self.collecting and self._mode=='Automatic' and int(self._worker_count)>1:
            self._collector.worker_skips[int(self._skip_worker)-1].set()
        else:
            super().skipCurrent()
    balanceText = Property(str, lambda self: self._balance, notify=captchaChanged)
    autoStatus = Property(str, lambda self: self._auto_status, notify=captchaChanged)
    usageText = Property(str, lambda self: (
        f"This window: {self.budget.snapshot()['attempts']} / {self._max_attempts or '—'} attempts · "
        f"{self.budget.snapshot()['spent']} / {self._credit_limit or '—'} credits" +
        (' · charge unconfirmed' if self.budget.snapshot()['blocked'] else '')), notify=captchaChanged)

    @Slot(dict)
    def _credit_update(self, data):
        if data.get('performance'): self._performance=data['performance']
        if 'balance' in data:
            self._balance = f"Last checked: {data['balance']} credits · daily allowance left: {data['plan_remaining']}"
        if data.get('status'):
            self._auto_status = data['status']
            if self.collecting:
                self._status = self._auto_status
                self.stateChanged.emit()
        self.captchaChanged.emit()

    @Slot()
    def checkBalance(self):
        if self.running or self._closing: return
        try:
            client = self.client_factory(self._api_key)
        except ServiceError as exc:
            self._auto_status = str(exc); self._status=self._auto_status
            self.captchaChanged.emit(); self.stateChanged.emit(); return

        def check():
            try:
                return WorkerEvent('nonecap_balance', client.balance())
            except ServiceError as exc:
                return WorkerEvent('nonecap_error', {'message': str(exc)})
        self._launch('checking', 'Checking NoneCAP balance (no solve)…', check)

    def _handle(self, event):
        if event.kind == 'nonecap_balance':
            self._credit_update(event.payload)
            self._status = 'Balance checked. No solve was requested.'
        elif event.kind == 'nonecap_error':
            self._auto_status = event.payload['message']
            self._status = self._auto_status
            self.captchaChanged.emit()
        else:
            super()._handle(event)
            if event.kind=='stopped' and event.payload.get('reason')=='automatic_limit':
                self._status='Automatic collection paused at the session limit. Pending rows are kept. Adjust limits or select Manual before starting again.'
                self.log(self._status)
            elif event.kind=='stopped' and event.payload.get('reason')=='billing_unconfirmed':
                self._status='Automatic collection paused because a final charge cannot be confirmed. Pending rows are kept. Check NoneCAP history or select Manual; raising limits will not clear this billing pause.'
                self._auto_status=self._status
                self.captchaChanged.emit(); self.log(self._status)

    @Slot()
    def startCollection(self):
        if self.running or self._closing: return
        try:
            if self._mode == 'Automatic':
                try:
                    self.budget.configure(int(self._credit_limit), int(self._max_attempts))
                except ValueError:
                    raise ValueError('Enter whole numbers: credit threshold 1–100,000 and attempts 1–1,000.') from None
                client = self.client_factory(self._api_key)
                self.budget.check()
                if self._collector.disabled:
                    raise LimitReached('Automatic mode was disabled after an earlier failure in this window.')
                self._collector.solver = Solver(client, self.budget, self.creditUpdate.emit)
                self._collector.workers = int(self._worker_count)
                self._auto_status = f'Automatic mode selected: {self._worker_count} worker(s), with shared session limits. Start may spend NoneCAP credits.'
            else:
                self._collector.solver = None
                self._auto_status = 'Manual mode: solve CAPTCHA in Chrome. No automatic requests.'
        except ChargeUnconfirmed as exc:
            self._status=str(exc)+' No automatic request was made. Check NoneCAP history or select Manual; increasing limits will not clear this pause.'
            self._auto_status=self._status; self.log(self._status)
            self.stateChanged.emit(); self.captchaChanged.emit(); return
        except LimitReached as exc:
            self._status=str(exc)+' No automatic request was made. Session counters are retained; adjust limits or select Manual.'
            self._auto_status=self._status; self.log(self._status)
            self.stateChanged.emit(); self.captchaChanged.emit(); return
        except (ServiceError, ValueError) as exc:
            self._status = str(exc); self.stateChanged.emit(); return
        self.captchaChanged.emit()
        super().startCollection()
