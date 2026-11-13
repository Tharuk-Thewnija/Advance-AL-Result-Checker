"""Scope the Qt process to its own preferences, checkpoint and instance lock."""
import os
from pathlib import Path


def qt_data_root(base: Path) -> Path:
    return base / 'ALResultsCollectorQt'


def configure_storage(*, mock=False) -> Path:
    base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local' / 'share')
    root = base / 'ALResultsCollectorQtMock' if mock else qt_data_root(base)
    os.environ['LOCALAPPDATA'] = str(root)
    return root / 'ALResultsCollector'
