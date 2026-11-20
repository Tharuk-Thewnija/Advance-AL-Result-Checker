"""One resumable run, saved transactionally in per-user application data."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import sqlite3

from .models import InputWorkbook, RunConfig, RowResult
from .subjects import catalogue_metadata


def app_data_dir() -> Path:
    root = os.environ.get('LOCALAPPDATA')
    return (Path(root) if root else Path.home() / '.local' / 'share') / 'ALResultsCollector'


def checkpoint_path() -> Path:
    return app_data_dir() / 'current.sqlite3'


class CheckpointMismatch(ValueError):
    pass


def identity(workbook: InputWorkbook, config: RunConfig) -> dict:
    # The export folder may be changed without recollecting results.
    return dict(schema=1, content_hash=workbook.content_hash, sheet=workbook.sheet_name,
                row_count=len(workbook.frame), subjects=list(config.subject_ids),
                fields=list(config.fields), year=config.exam_year, timeout=config.captcha_timeout,
                catalogue=catalogue_metadata()['version'])


class CheckpointStore:
    def __init__(self, path: Path, connection: sqlite3.Connection, metadata: dict):
        self.path = path
        self.connection = connection
        self.metadata = metadata
        self.closed = False

    @classmethod
    def open_for_export(cls, workbook: InputWorkbook, config: RunConfig) -> 'CheckpointStore':
        path = checkpoint_path()
        try:
            connection = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
        except sqlite3.OperationalError as exc:
            raise OSError('Cannot open the saved checkpoint for export. Restore it or check file access.') from exc
        try:
            row = connection.execute('SELECT value FROM metadata WHERE id=1').fetchone()
            metadata = json.loads(row[0]) if row else None
            if metadata != identity(workbook, config):
                raise CheckpointMismatch('The saved checkpoint does not match this collection.')
            return cls(path, connection, metadata)
        except Exception:
            connection.close()
            raise

    @classmethod
    def open(cls, workbook: InputWorkbook, config: RunConfig) -> 'CheckpointStore':
        path = checkpoint_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        try:
            connection.execute('PRAGMA synchronous=FULL')
            with connection:
                connection.execute('CREATE TABLE IF NOT EXISTS metadata (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)')
                connection.execute('CREATE TABLE IF NOT EXISTS results (position INTEGER PRIMARY KEY, status TEXT NOT NULL, value TEXT NOT NULL, note TEXT NOT NULL)')
                row = connection.execute('SELECT value FROM metadata WHERE id=1').fetchone()
                metadata = identity(workbook, config)
                if row:
                    if json.loads(row[0]) != metadata:
                        raise CheckpointMismatch('Saved progress belongs to a different workbook or different selections.')
                else:
                    connection.execute('INSERT INTO metadata VALUES (1, ?)', (json.dumps(metadata, sort_keys=True),))
            return cls(path, connection, metadata)
        except Exception:
            connection.close()
            raise

    def matches(self, workbook: InputWorkbook, config: RunConfig) -> bool:
        return self.metadata == identity(workbook, config)

    def save(self, result: RowResult) -> None:
        if not 0 <= result.position < self.metadata['row_count']:
            raise ValueError('Result position is outside the input workbook')
        if result.status not in ('Completed', 'Skipped', 'Error'):
            raise ValueError('Invalid result status')
        encoded = json.dumps(result.values, ensure_ascii=False)
        with self.connection:
            self.connection.execute('INSERT OR REPLACE INTO results VALUES (?, ?, ?, ?)',
                                    (result.position, result.status, encoded, result.note))

    def results(self) -> list[RowResult]:
        return [RowResult(position, status, json.loads(values), note) for position, status, values, note
                in self.connection.execute('SELECT position, status, value, note FROM results ORDER BY position')]

    def pending_positions(self) -> list[int]:
        saved = {row[0] for row in self.connection.execute('SELECT position FROM results')}
        return [i for i in range(self.metadata['row_count']) if i not in saved]

    def close(self) -> None:
        if not self.closed:
            self.connection.close()
            self.closed = True

    def discard(self) -> None:
        self.close()
        self.path.unlink(missing_ok=True)
