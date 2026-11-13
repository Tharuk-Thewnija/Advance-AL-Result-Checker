"""Prevent two application windows from replacing the same saved progress."""
import os
from pathlib import Path
from .checkpoints import app_data_dir


class InstanceLock:
    def __init__(self, path: Path | None = None):
        self.path = path or app_data_dir() / 'collector.lock'
        self.stream = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open('a+b')
        self.stream.seek(0, os.SEEK_END)
        if self.stream.tell() == 0:
            self.stream.write(b'0'); self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.stream.close(); self.stream = None
            raise RuntimeError('A/L Results Collector is already open. Use the existing window.') from exc
        return self

    def __exit__(self, *_):
        if self.stream:
            self.stream.close()  # OS releases the lock, including after a crash.
            self.stream = None
