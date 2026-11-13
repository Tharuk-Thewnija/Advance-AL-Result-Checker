"""Virtualized subject list; filtering does not change the source selections."""
from PySide6.QtCore import QAbstractListModel, QModelIndex, QSortFilterProxyModel, Qt, Signal
from al_results.subjects import load_subjects, search_subjects


class Subjects(QAbstractListModel):
    selectionChanged = Signal()
    ID, CODE, NAME, SELECTED = range(257, 261)

    def __init__(self, selected, parent=None):
        super().__init__(parent)
        self.items = load_subjects()
        self.selected = set(selected)

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
        self.dataChanged.emit(self.index(0), self.index(len(self.items) - 1), [self.SELECTED])
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
