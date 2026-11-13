"""Value-only Excel import and atomic, non-overwriting exports."""
import hashlib
from io import BytesIO
import os
from pathlib import Path
import tempfile
from datetime import datetime
from uuid import uuid4
import pandas as pd
from openpyxl import Workbook

from .models import InputWorkbook, RunConfig, RowResult
from .parsing import normalize_nic, is_valid_nic
from .subjects import load_subjects


def load_workbook(path: Path) -> InputWorkbook:
    path = Path(path).resolve()
    if path.suffix.lower() not in ('.xlsx', '.xls'):
        raise ValueError('Choose an .xlsx or .xls file.')
    data = path.read_bytes()
    with pd.ExcelFile(BytesIO(data), engine='xlrd' if path.suffix.lower() == '.xls' else 'openpyxl') as book:
        sheet = book.sheet_names[0]
        frame = pd.read_excel(book, sheet_name=sheet, dtype=object, keep_default_na=False)
    if 'NIC' not in frame.columns:
        raise ValueError("The first worksheet must contain a column named 'NIC'.")
    if frame.empty:
        raise ValueError('The first worksheet contains no students.')
    return InputWorkbook(path, hashlib.sha256(data).hexdigest(), sheet, frame)


def validate_rows(workbook: InputWorkbook) -> list[tuple[int, str, str | None]]:
    rows = []
    for position, value in enumerate(workbook.frame['NIC']):
        nic = normalize_nic(value)
        rows.append((position, nic, None if is_valid_nic(nic) else 'Invalid NIC format'))
    return rows


def output_columns(workbook: InputWorkbook, config: RunConfig) -> dict[str, str]:
    subjects = {s.id: s for s in load_subjects()}
    desired = {f'subject:{sid}': f'{subjects[sid].name} Result' for sid in config.subject_ids}
    desired.update({field: field for field in config.fields})
    desired.update({'status': 'Scrape Status', 'note': 'Scrape Notes'})
    used = set(workbook.frame.columns)
    result = {}
    for key, name in desired.items():
        candidate = name if name not in used else 'Results ' + name
        base = candidate
        suffix = 2
        while candidate in used:
            candidate = f'{base} ({suffix})'
            suffix += 1
        used.add(candidate)
        result[key] = candidate
    return result


def publish_export(temporary: Path, destination: Path) -> None:
    if os.name == 'nt':
        # Windows rename is atomic and refuses an existing destination. Unlike
        # hard links, it also works on removable FAT/exFAT output drives.
        os.rename(temporary, destination)
    else:
        os.link(temporary, destination)


def export_results(workbook: InputWorkbook, config: RunConfig, results: list[RowResult]) -> Path:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    columns = output_columns(workbook, config)
    by_position = {result.position: result for result in results}
    # Streaming workbook avoids building another full DataFrame for export.
    excel = Workbook(write_only=True)
    sheet = excel.create_sheet('Results')
    from openpyxl.cell import WriteOnlyCell

    def append(values):
        cells = []
        for value in values:
            cell = WriteOnlyCell(sheet, value=None if pd.isna(value) else value)
            if isinstance(value, str):
                cell.data_type = 's'  # Preserve literal strings, including those starting '='.
            cells.append(cell)
        sheet.append(cells)

    append([*workbook.frame.columns, *columns.values()])
    for position, values in enumerate(workbook.frame.itertuples(index=False, name=None)):
        result = by_position.get(position)
        extras = dict(result.values) if result else {}
        extras['status'] = result.status if result else 'Pending'
        extras['note'] = result.note if result else ''
        append([*values, *(extras.get(key) for key in columns)])
    fd, temporary = tempfile.mkstemp(prefix='.al-export-', suffix='.xlsx', dir=config.output_dir)
    os.close(fd)
    temporary = Path(temporary)
    destination = config.output_dir / f'results_{datetime.now():%Y%m%d_%H%M%S}_{uuid4().hex[:8]}.xlsx'
    try:
        excel.save(temporary)
        publish_export(temporary, destination)
        return destination
    finally:
        excel.close()
        temporary.unlink(missing_ok=True)
