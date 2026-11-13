"""Bounded worker-to-Tk handoff; progress/current are replaceable snapshots."""
from collections import deque
import threading
from .models import WorkerEvent


class EventBuffer:
    def __init__(self):
        self._lock = threading.Lock()
        self._latest = {}
        self._logs = deque(maxlen=500)
        self._reliable = deque()

    def put(self, event: WorkerEvent) -> None:
        with self._lock:
            if event.kind in ('current', 'progress'):
                self._latest[event.kind] = event
            elif event.kind == 'log':
                self._logs.append(event)
            else:
                self._reliable.append(event)

    def drain(self) -> list[WorkerEvent]:
        with self._lock:
            events = [*self._latest.values(), *self._logs, *self._reliable]
            self._latest.clear(); self._logs.clear(); self._reliable.clear()
            return events
