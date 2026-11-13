"""One finite backend operation per thread; never touch QML from this thread."""
from PySide6.QtCore import QThread
from al_results.models import WorkerEvent


class Task(QThread):
    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self.operation = operation
        self.result = None

    def run(self):
        try:
            self.result = self.operation()
        except Exception as exc:
            self.result = WorkerEvent('operation_failed', {'error': str(exc)})
