"""UI-only demo state. No scraper, checkpoints, workbook reads or preferences."""
from PySide6.QtCore import QObject, Property, Signal, Slot, QAbstractListModel, QModelIndex, Qt, QSortFilterProxyModel, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFileDialog
from al_results.subjects import FIELDS, load_subjects, search_subjects


class Subjects(QAbstractListModel):
    selectionChanged = Signal()
    ID, CODE, NAME, SELECTED = range(257, 261)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = load_subjects()
        self.selected = {'20'}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.items)

    def roleNames(self):
        return {self.ID: b'subjectId', self.CODE: b'subjectCode',
                self.NAME: b'displayName', self.SELECTED: b'subjectSelected'}

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.items):
            return None
        subject = self.items[index.row()]
        return {self.ID: subject.id, self.CODE: subject.code, self.NAME: subject.name,
                self.SELECTED: subject.id in self.selected}.get(role)

    def select(self, subject_id, checked):
        for row, subject in enumerate(self.items):
            if subject.id == subject_id:
                if checked:
                    self.selected.add(subject_id)
                else:
                    self.selected.discard(subject_id)
                index = self.index(row, 0)
                self.dataChanged.emit(index, index, [self.SELECTED])
                self.selectionChanged.emit()
                return

    def clear(self):
        self.selected.clear()
        self.dataChanged.emit(self.index(0, 0), self.index(len(self.items) - 1, 0), [self.SELECTED])
        self.selectionChanged.emit()


class SubjectFilter(QSortFilterProxyModel):
    def __init__(self, source, parent=None):
        super().__init__(parent)
        self.allowed = {subject.id for subject in source.items}
        self.setSourceModel(source)

    def filterAcceptsRow(self, row, parent):
        return self.sourceModel().items[row].id in self.allowed

    def search(self, query):
        self.beginFilterChange()
        self.allowed = {subject.id for subject in search_subjects(query)}
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)


class Bridge(QObject):
    stateChanged = Signal()
    selectionChanged = Signal()
    logChanged = Signal()
    pathChanged = Signal()
    themeChanged = Signal()

    def __init__(self):
        super().__init__()
        self.source = Subjects(self)
        self.filtered = SubjectFilter(self.source, self)
        self.source.selectionChanged.connect(self.selectionChanged)
        self._path = ''
        self._theme = 'System'
        self._running = False
        self._done = self._completed = self._skipped = 0
        self._stage = 'configure'
        self._status = 'UI prototype — ready for a simulated collection.'
        self._logs = ['Qt Quick prototype. No student lookups or result files are written.']
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self.advance)
        QGuiApplication.styleHints().colorSchemeChanged.connect(lambda _: self.themeChanged.emit())

    subjects = Property(QObject, lambda self: self.filtered, constant=True)
    fields = Property('QVariantList', lambda self: list(FIELDS), constant=True)
    selectedCount = Property(int, lambda self: len(self.source.selected), notify=selectionChanged)
    total = Property(int, lambda self: 1000, constant=True)
    processed = Property(int, lambda self: self._done, notify=stateChanged)
    completed = Property(int, lambda self: self._completed, notify=stateChanged)
    skipped = Property(int, lambda self: self._skipped, notify=stateChanged)
    running = Property(bool, lambda self: self._running, notify=stateChanged)
    stage = Property(str, lambda self: self._stage, notify=stateChanged)
    status = Property(str, lambda self: self._status, notify=stateChanged)
    logText = Property(str, lambda self: '\n'.join(self._logs), notify=logChanged)
    systemDark = Property(bool, lambda self: QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark, notify=themeChanged)

    @Property(str, notify=themeChanged)
    def theme(self):
        return self._theme

    @theme.setter
    def theme(self, value):
        if value in ('System', 'Light', 'Dark'):
            self._theme = value
            self.themeChanged.emit()

    @Property(str, notify=pathChanged)
    def filePath(self):
        return self._path

    @filePath.setter
    def filePath(self, value):
        self._path = value
        self.pathChanged.emit()

    @Slot(str)
    def search(self, query):
        self.filtered.search(query)

    @Slot(str, bool)
    def selectSubject(self, subject_id, checked):
        if not self._running:
            self.source.select(subject_id, checked)

    @Slot()
    def clearSubjects(self):
        if not self._running:
            self.source.clear()

    @Slot()
    def browse(self):
        path, _ = QFileDialog.getOpenFileName(None, 'Choose a workbook (preview only)', '', 'Excel workbooks (*.xlsx *.xls)')
        if path:
            self.filePath = path  # Path display only; the workbook is not opened.

    def log(self, message):
        self._logs.append(message)
        self._logs = self._logs[-200:]
        self.logChanged.emit()

    @Slot()
    def startDemo(self):
        if not self.source.selected:
            self._status = 'Select at least one subject to run the demo.'
            self.stateChanged.emit()
            return
        if self._done >= self.total:
            self._done = self._completed = self._skipped = 0
        self._running = True
        self._stage = 'collect'
        self._status = 'Simulated collection — no website requests or CAPTCHA.'
        self.log('Started synthetic 1,000-student animation. This is not scraping throughput.')
        self.stateChanged.emit()
        self.timer.start()

    @Slot()
    def advance(self):
        amount = min(25, self.total - self._done)
        self._done += amount
        self._completed += amount
        if self._done == self.total:
            self.timer.stop()
            self._running = False
            self._stage = 'export'
            self._status = 'Demo finished. Real collection/export remain in the original app.'
            self.log('Demo complete. No student results were fetched or saved.')
        self.stateChanged.emit()

    @Slot()
    def stopDemo(self):
        self.timer.stop()
        self._running = False
        self._status = 'Demo paused. Start again to continue the animation.'
        self.log('Paused the synthetic demo; no checkpoint was created.')
        self.stateChanged.emit()

    @Slot()
    def skipDemo(self):
        if self._running and self._done < self.total:
            self._done += 1
            self._skipped += 1
            self.stateChanged.emit()

    @Slot()
    def exportDemo(self):
        self.log('Export is intentionally not connected in this UI/performance prototype.')
