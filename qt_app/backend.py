"""GUI-thread controller. All workbook, browser and SQLite work runs in Tasks."""
from collections import deque
from dataclasses import replace
from datetime import datetime
from pathlib import Path
import threading
from uuid import uuid4

from PySide6.QtCore import QObject, Property, QTimer, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QFileDialog

from al_results.checkpoints import CheckpointMismatch, CheckpointStore, checkpoint_path
from al_results.collector import collect
from al_results.events import EventBuffer
from al_results.excel_io import load_workbook, validate_rows, export_results
from al_results.models import RunConfig, WorkerEvent
from al_results.settings import load_preferences, save_preferences, validate_config
from al_results.subjects import FIELDS
from .subjects import Subjects, SubjectFilter
from .workers import Task
from al_results.nonecap.client import Client, ServiceError
from al_results.nonecap.budget import Budget, LimitReached, ChargeUnconfirmed
from al_results.nonecap.collector import AutomaticCollector, MAX_WORKERS
from al_results.nonecap.solver import Solver


class Bridge(QObject):
    stateChanged = Signal()
    selectionChanged = Signal()
    settingsChanged = Signal()
    themeChanged = Signal()
    logChanged = Signal()
    readyToClose = Signal()
    diagnosticsChanged = Signal()
    captchaChanged = Signal()
    creditUpdate = Signal(dict)
    prototypeMode = Property(bool, lambda self: self._prototype, constant=True)

    def __init__(self, *, mock=False, collector=None, prototype=False, client_factory=Client):
        super().__init__()
        self._prototype = prototype
        self._mode, self._api_key = 'Manual', ''
        self._credit_limit, self._max_attempts = '10', '3'
        self._worker_count, self._skip_worker = '1', '1'
        self._performance = 'Choose 1–5 workers to compare batch throughput.'
        self._balance = 'Balance not checked'
        self._auto_status = 'Manual mode: solve CAPTCHA in Chrome. No automatic requests.'
        self.budget = Budget()
        self.client_factory = client_factory
        self._mock = mock
        if collector is None and mock:
            from .mock_data import MockCollector
            collector = MockCollector()
        self._collector = collector or (collect if mock else AutomaticCollector(self.creditUpdate.emit))
        self._diagnostics = ''
        prefs = load_preferences()
        self.source = Subjects(prefs['subjects'], self)
        self.filtered = SubjectFilter(self.source, self)
        self.source.selectionChanged.connect(self.selectionChanged)
        self._fields = set(prefs['fields'])
        self._theme = prefs['appearance']
        self._path = self._folder = ''
        self._year = prefs['year']; self._timeout = str(prefs['timeout'])
        self._phase = 'idle'; self._stage = 'configure'
        self._status = 'Choose a student workbook and your subjects.'
        self._current = 'No student in progress'
        self._counts = dict(total=0, processed=0, completed=0, skipped=0, failed=0)
        self._logs = deque(['Ready. Progress is saved locally; any NoneCAP key stays in memory only.'], maxlen=200)
        self._task = None; self._prepared = None
        self._book = self._config = None
        self._has_results = False; self._last_output = ''
        self._closing = False
        self.stop_event = threading.Event(); self.skip_event = threading.Event()
        self.events = EventBuffer()
        self.timer = QTimer(self)
        self.timer.setInterval(40); self.timer.timeout.connect(self._drain)
        self.timer.start()
        self.creditUpdate.connect(self._credit_update, Qt.ConnectionType.QueuedConnection)
        QGuiApplication.styleHints().colorSchemeChanged.connect(lambda _: self.themeChanged.emit())

    mockMode = Property(bool, lambda self: self._mock, constant=True)
    diagnostics = Property(str, lambda self: self._diagnostics, notify=diagnosticsChanged)
    subjects = Property(QObject, lambda self: self.filtered, constant=True)
    fields = Property('QVariantList', lambda self: list(FIELDS), constant=True)
    selectedFields = Property('QVariantList', lambda self: sorted(self._fields), notify=selectionChanged)
    selectedCount = Property(int, lambda self: len(self.source.selected), notify=selectionChanged)
    total = Property(int, lambda self: self._counts['total'], notify=stateChanged)
    processed = Property(int, lambda self: self._counts['processed'], notify=stateChanged)
    completed = Property(int, lambda self: self._counts['completed'], notify=stateChanged)
    skipped = Property(int, lambda self: self._counts['skipped'], notify=stateChanged)
    failed = Property(int, lambda self: self._counts['failed'], notify=stateChanged)
    running = Property(bool, lambda self: self._phase != 'idle', notify=stateChanged)
    collecting = Property(bool, lambda self: self._phase == 'collecting' and not self.stop_event.is_set(), notify=stateChanged)
    phase = Property(str, lambda self: self._phase, notify=stateChanged)
    stage = Property(str, lambda self: self._stage, notify=stateChanged)
    status = Property(str, lambda self: self._status, notify=stateChanged)
    currentStudent = Property(str, lambda self: self._current, notify=stateChanged)
    canExport = Property(bool, lambda self: self._has_results and not self.running, notify=stateChanged)
    lastOutput = Property(str, lambda self: self._last_output, notify=stateChanged)
    needsDecision = Property(bool, lambda self: self._prepared is not None, notify=stateChanged)
    decisionMismatch = Property(bool, lambda self: bool(self._prepared and self._prepared['mismatch']), notify=stateChanged)
    decisionText = Property(str, lambda self: (
        'Saved Qt progress belongs to another workbook or different selections. Start fresh to archive it, or cancel to keep it.'
        if self.decisionMismatch else
        f"{self._prepared['saved'] if self._prepared else 0} rows are already saved. Resume pending students, start fresh (archives saved progress), or cancel."), notify=stateChanged)
    logText = Property(str, lambda self: '\n'.join(self._logs), notify=logChanged)
    systemDark = Property(bool, lambda self: QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark, notify=themeChanged)

    @Property(str, notify=themeChanged)
    def theme(self):
        return self._theme

    @theme.setter
    def theme(self, value):
        if value in ('System', 'Light', 'Dark'):
            self._theme = value; self.themeChanged.emit()

    def _setting(name, notify):
        def get(self):
            return getattr(self, name)
        def set(self, value):
            if not self.running:
                setattr(self, name, value); self.settingsChanged.emit()
        return Property(str, get, set, notify=notify)

    filePath = _setting('_path', settingsChanged)
    outputFolder = _setting('_folder', settingsChanged)
    examYear = _setting('_year', settingsChanged)
    captchaTimeout = _setting('_timeout', settingsChanged)

    @Slot(str)
    def search(self, query):
        self.filtered.search(query)

    @Slot(str, bool)
    def selectSubject(self, subject_id, checked):
        if not self.running:
            self.source.select(subject_id, checked)

    @Slot()
    def clearSubjects(self):
        if not self.running:
            self.source.clear()

    @Slot(str, bool)
    def selectField(self, name, checked):
        if not self.running and name in FIELDS:
            if checked:
                self._fields.add(name)
            else:
                self._fields.discard(name)
            self.selectionChanged.emit()

    @Slot()
    def browse(self):
        if self.running or self._mock:
            return
        path, _ = QFileDialog.getOpenFileName(None, 'Choose a student workbook', '', 'Excel workbooks (*.xlsx *.xls)')
        if path:
            self.filePath = path

    @Slot()
    def browseFolder(self):
        if not self.running:
            folder = QFileDialog.getExistingDirectory(None, 'Choose an output folder', self._folder)
            if folder:
                self.outputFolder = folder

    @Slot()
    def openFolder(self):
        if self._last_output:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self._last_output).parent)))

    def log(self, text):
        self._logs.append(f'{datetime.now():%H:%M:%S}  {text}')
        self.logChanged.emit()

    def update_diagnostics(self, text):
        self._diagnostics = text
        self.diagnosticsChanged.emit()

    def _persist(self):
        try:
            save_preferences(dict(appearance=self.theme, subjects=[s.id for s in self.source.items if s.id in self.source.selected],
                                  fields=[f for f in FIELDS if f in self._fields], year=self._year,
                                  timeout=int(self._timeout)))
        except (OSError, ValueError):
            self.log('Preferences could not be saved. Collection progress is stored separately.')

    def _launch(self, phase, status, operation):
        self._phase = phase; self._status = status
        task = Task(operation, self)
        self._task = task
        task.finished.connect(self._task_finished)
        self.stateChanged.emit()
        task.start()

    def _drain(self):
        # Only progress/current/log are drained during work. Terminal events must
        # wait for thread completion before controls or the window are released.
        log_dirty = False
        state_dirty = False
        for event in self.events.drain():
            if event.kind in ('finished', 'stopped', 'fatal'):
                self._terminal = event
            elif event.kind == 'log':
                self._logs.append(f"{datetime.now():%H:%M:%S}  {event.payload['text']}")
                log_dirty = True
            elif event.kind == 'progress':
                self._counts.update(event.payload); state_dirty = True
            elif event.kind == 'current':
                self._current = f"Row {event.payload['position'] + 1} · NIC {event.payload['nic'] or '(blank)'}"
                if not self.stop_event.is_set():
                    self._status = ('Simulating fictional results — no website requests.' if self._mock else
                                    'Opening the form; complete CAPTCHA in Chrome when prompted.')
                state_dirty = True
        if log_dirty:
            self.logChanged.emit()
        if state_dirty:
            self.stateChanged.emit()

    @Slot()
    def _task_finished(self):
        task = self._task
        self._drain()
        event = task.result or getattr(self, '_terminal', None)
        self._terminal = None
        self._task = None
        task.deleteLater()
        self._phase = 'idle'
        if event:
            self._handle(event)
        if self._closing:
            self._prepared = None; self._phase = 'idle'
            self._persist(); self.readyToClose.emit()
        self.stateChanged.emit()

    @Slot()
    def startCollection(self):
        if self.running or self._closing:
            return
        if not self._prepare_nonecap():
            return
        try:
            if not self._path.strip():
                raise ValueError('Choose an existing Excel file.')
            path = Path(self._path.strip()).resolve()
            try:
                timeout = int(self._timeout)
            except ValueError:
                raise ValueError('Enter a positive integer CAPTCHA timeout.')
            config = RunConfig(path, tuple(s.id for s in self.source.items if s.id in self.source.selected),
                               tuple(f for f in FIELDS if f in self._fields), self._year.strip(), timeout,
                               Path(self._folder.strip()).resolve() if self._folder.strip() else path.parent)
            validate_config(config)
        except (ValueError, OSError) as exc:
            self._status = str(exc); self.stateChanged.emit(); return
        self._persist()

        def prepare():
            book = load_workbook(config.input_path)
            if self._mock:
                from .mock_data import verify_mock_workbook
                invalid = verify_mock_workbook(book)
            else:
                invalid = sum(bool(e) for _, _, e in validate_rows(book))
            try:
                store = CheckpointStore.open(book, config)
                try:
                    results = store.results()
                finally:
                    store.close()
                mismatch = False
            except CheckpointMismatch:
                results = []; mismatch = True
            return WorkerEvent('prepared', dict(book=book, config=config, saved=len(results), results=results,
                                               mismatch=mismatch, invalid=invalid))
        self._launch('loading', 'Checking your student workbook…', prepare)

    def _handle(self, event):
        p = event.payload
        if event.kind == 'nonecap_balance':
            self._credit_update(p); self._status = 'Balance checked. No solve was requested.'
            return
        if event.kind == 'nonecap_error':
            self._auto_status = p['message']; self._status = self._auto_status
            self.captchaChanged.emit()
            return
        if event.kind == 'prepared':
            if self._closing:
                return
            self._prepared = p
            if p['saved'] or p['mismatch']:
                self._phase = 'decision'; self._status = 'Choose how to handle saved progress.'
            else:
                self.decide('resume')
        elif event.kind in ('finished', 'stopped', 'fatal'):
            self._counts.update({k: v for k, v in p.items() if k in self._counts})
            self._has_results = self.processed > 0
            self._current = 'No student in progress'
            self._stage = 'export' if self._has_results else 'configure'
            self._status = {'finished': 'Collection finished. Export your results.',
                            'stopped': 'Stopped. Resume or export partial results.',
                            'fatal': 'Collection interrupted. Saved progress is kept.'}[event.kind]
            if p.get('reason') == 'browser_closed':
                self._status = 'Chrome was closed. Saved progress is kept. Start collection to reopen Chrome and resume.'
            if p.get('error'):
                self._status += ' ' + p['error']
            if p.get('reason') == 'automatic_limit':
                self._status = 'Automatic collection paused at the session limit. Pending rows are kept. Adjust limits or select Manual before starting again.'
            elif p.get('reason') == 'billing_unconfirmed':
                self._status = 'Automatic collection paused because a final charge cannot be confirmed. Pending rows are kept. Check NoneCAP history or select Manual; raising limits will not clear this billing pause.'
                self._auto_status = self._status; self.captchaChanged.emit()
            self.log(self._status)
        elif event.kind == 'exported':
            self._last_output = str(p['path']); self._stage = 'export'
            self._status = 'Partial Excel results saved. Pending students can be resumed.' if p['pending'] else 'Excel results saved.'
            self.log(f"Saved to {p['path']}")
        elif event.kind == 'operation_failed':
            self._status = p['error']; self.log(self._status)

    @Slot(str)
    def decide(self, choice):
        if self._prepared is None or choice not in ('resume', 'restart', 'cancel'):
            return
        p = self._prepared
        if choice == 'resume' and p['mismatch']:
            return
        self._prepared = None
        if choice == 'cancel':
            self._phase = 'idle'; self._status = 'Saved progress kept.'; self.stateChanged.emit(); return
        self._book = p['book']; self._config = p['config']
        counts = dict(total=len(self._book.frame), processed=0, completed=0, skipped=0, failed=0)
        if choice != 'restart':
            keys = {'Completed': 'completed', 'Skipped': 'skipped', 'Error': 'failed'}
            for result in p['results']:
                counts['processed'] += 1; counts[keys[result.status]] += 1
        self._counts = counts; self._has_results = self.processed > 0
        self.stop_event.clear(); self.skip_event.clear()
        self._stage = 'collect'
        invalid_label = 'intentionally invalid mock rows' if self._mock else 'invalid NICs'
        self.log(f"Loaded {self.total} rows. {p['invalid']} {invalid_label} will be marked skipped.")
        book, config = self._book, self._config

        def run():
            if choice == 'restart' and checkpoint_path().exists():
                path = checkpoint_path()
                path.rename(path.with_name(f'archived-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}.sqlite3'))
            store = CheckpointStore.open(book, config)
            self._collector(config, book, store, self.events.put, self.stop_event, self.skip_event)
        self._launch('collecting', 'Running the offline mock test…' if self._mock else 'Opening the results website…', run)

    @Slot()
    def stopCollection(self):
        if self._phase == 'collecting':
            self.stop_event.set()
            self._status = 'Stopping and keeping saved progress…'
            self.stateChanged.emit()

    @Slot()
    def skipCurrent(self):
        if self.collecting:
            if isinstance(self._collector, AutomaticCollector) and self._mode == 'Automatic' and int(self._worker_count) > 1:
                self._collector.worker_skips[int(self._skip_worker)-1].set()
            else:
                self.skip_event.set()

    @Slot()
    def exportResults(self):
        if not self.canExport or self._closing:
            return
        book, original = self._book, self._config
        config = replace(original, output_dir=Path(self._folder.strip()).resolve()) if self._folder.strip() else original

        def export():
            store = CheckpointStore.open(book, original)
            try:
                results = store.results(); pending = bool(store.pending_positions())
                output = export_results(book, config, results)
                return WorkerEvent('exported', dict(path=output, pending=pending))
            finally:
                store.close()
        self._launch('exporting', 'Writing your Excel results…', export)

    @Slot(result=bool)
    def requestClose(self):
        self._closing = True
        if self._task is not None:
            self.stop_event.set()
            self._status = 'Closing safely after the current operation finishes…'
            self.stateChanged.emit()
            return False
        self._prepared = None; self._phase = 'idle'
        self._persist()
        return True


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
                    if isinstance(self._collector,AutomaticCollector): self._collector.solver = None
                    self._balance = 'Balance not checked'
                if name == '_mode':
                    if value == 'Manual' and isinstance(self._collector,AutomaticCollector): self._collector.solver = None
                    self._auto_status = ('Manual mode: solve CAPTCHA in Chrome. No automatic requests.' if value == 'Manual' else
                        'Automatic mode is disabled for this window; collection will continue manually.' if getattr(self._collector, 'disabled', False) else
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

    def _prepare_nonecap(self):
        if self._mock or not isinstance(self._collector, AutomaticCollector): return True
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
            self.stateChanged.emit(); self.captchaChanged.emit(); return False
        except LimitReached as exc:
            self._status=str(exc)+' No automatic request was made. Session counters are retained; adjust limits or select Manual.'
            self._auto_status=self._status; self.log(self._status)
            self.stateChanged.emit(); self.captchaChanged.emit(); return False
        except (ServiceError, ValueError) as exc:
            self._status = str(exc); self.stateChanged.emit(); return False
        self.captchaChanged.emit()
        return True
