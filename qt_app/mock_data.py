"""Offline simulation. This module never constructs a browser or sends requests."""
from pathlib import Path
import tempfile
import time
import os

from openpyxl import Workbook
from al_results.collector import check_controls, SkipCurrentRow, StopRequested
from al_results.excel_io import load_workbook, publish_export
from al_results.models import RowResult, WorkerEvent
from al_results.parsing import parse_results
from al_results.subjects import load_subjects

MARKER = 'FICTIONAL MOCK DATA V1'


def mock_nic(number):
    return f'INVALID-MOCK-{number:06}' if number % 50 == 0 else f'MOCK-{number:06}'


def verify_mock_workbook(book):
    required = {'NIC', 'Mock Row', 'Mock Dataset'}
    if not required.issubset(book.frame.columns):
        raise ValueError('Mock mode accepts only its generated fictional workbook.')
    for number, (_, row) in enumerate(book.frame.iterrows(), 1):
        if row['Mock Dataset'] != MARKER or row['Mock Row'] != number or row['NIC'] != mock_nic(number):
            raise ValueError('The mock workbook was changed. Use a new mock workspace to generate a clean test.')
    return len(book.frame) // 50


def generate_workbook(folder: Path, count=1500) -> Path:
    if not 1 <= count <= 100000:
        raise ValueError('Mock row count must be between 1 and 100,000.')
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'mock-students-{count}.xlsx'
    if path.exists():
        book = load_workbook(path)
        verify_mock_workbook(book)
        if len(book.frame) != count:
            raise ValueError('Existing mock workbook has the wrong row count.')
        return path  # Preserve identical file bytes so checkpoint resume works.
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet('Fictional students')
    sheet.append(['NIC', 'Student', 'Mock Row', 'Mock Dataset'])
    for number in range(1, count + 1):
        sheet.append([mock_nic(number), f'MOCK STUDENT {number:06}', number, MARKER])
    fd, name = tempfile.mkstemp(prefix='.mock-input-', suffix='.xlsx', dir=folder)
    os.close(fd)
    temporary = Path(name)
    try:
        workbook.save(temporary)
        publish_export(temporary, path)
    finally:
        workbook.close()
        temporary.unlink(missing_ok=True)
    return path


def synthetic_card(number, subject_ids):
    subjects = {subject.id: subject for subject in load_subjects()}
    lines = ['Examination', 'MOCK DATA - NOT OFFICIAL RESULTS', 'Year', '2025',
             'Candidate Name', f'MOCK STUDENT {number:06}', 'Index Number', f'MOCK-{number:06}',
             'District Rank', str(number % 200 + 1), 'Island Rank', str(number),
             'Z-Score', f'{(number % 250) / 100:.4f}', 'Subject Stream', 'MOCK STREAM']
    grades = ('A', 'B', 'C', 'S', 'F', 'W', 'AB')
    for index, sid in enumerate(subject_ids):
        if number % 23 == 0 and index == 0:
            continue
        grade = str(number * 7 % 101) if sid == '12' else grades[(number - 1 + index) % len(grades)]
        lines.extend([subjects[sid].name, grade])
    return '\n'.join(lines)


class MockCollector:
    """Same event/store contract as collect; intentional local delays and failures."""
    def __init__(self, delay_scale=1.0):
        if not 0 <= delay_scale <= 100:
            raise ValueError('Mock delay scale must be between 0 and 100.')
        self.delay_scale = delay_scale

    def _wait(self, number, stop, skip):
        seconds = (.035 + number % 5 * .01 + (.35 if number % 31 == 0 else 0)) * self.delay_scale
        deadline = time.monotonic() + seconds
        while True:
            check_controls(stop, skip)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            stop.wait(min(.01, remaining))

    def __call__(self, config, workbook, store, emit, stop_event, skip_event):
        counts = dict(total=len(workbook.frame), processed=0, completed=0, skipped=0, failed=0)
        keys = {'Completed': 'completed', 'Skipped': 'skipped', 'Error': 'failed'}
        terminal = 'finished'; error = ''
        try:
            verify_mock_workbook(workbook)
            for result in store.results():
                counts['processed'] += 1; counts[keys[result.status]] += 1
            emit(WorkerEvent('progress', dict(counts)))
            emit(WorkerEvent('log', {'text': 'MOCK TEST: fictional results only. No browser, website or CAPTCHA.'}))
            for position in store.pending_positions():
                check_controls(stop_event)
                skip_event.clear()
                number = position + 1
                emit(WorkerEvent('current', {'position': position, 'nic': mock_nic(number)}))
                try:
                    self._wait(number, stop_event, skip_event)
                    if number % 50 == 0:
                        result = RowResult(position, 'Skipped', {}, 'Mock invalid input row')
                    elif number % 97 == 0:
                        result = RowResult(position, 'Error', {}, 'Simulated timeout (no request was made)')
                    else:
                        values = parse_results(synthetic_card(number, config.subject_ids), config.subject_ids, config.fields)
                        missing = [sid for sid in config.subject_ids if values[f'subject:{sid}'] is None]
                        note = 'Mock selected subject missing: ' + ', '.join(missing) if missing else ''
                        result = RowResult(position, 'Completed', values, note)
                except SkipCurrentRow:
                    result = RowResult(position, 'Skipped', {}, 'Mock student skipped by user')
                store.save(result)
                counts['processed'] += 1; counts[keys[result.status]] += 1
                emit(WorkerEvent('progress', dict(counts)))
                emit(WorkerEvent('log', {'text': f'Mock row {number}: {result.status}' + (f' — {result.note}' if result.note else '')}))
        except StopRequested:
            terminal = 'stopped'
        except Exception as exc:
            terminal = 'fatal'; error = str(exc)
        finally:
            store.close()
        emit(WorkerEvent(terminal, {**counts, 'error': error}))
