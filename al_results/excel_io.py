"""Value-only Excel import and atomic, non-overwriting exports."""
import hashlib
from io import BytesIO
import os
from pathlib import Path
import tempfile
from datetime import datetime
from uuid import uuid4
import pandas as pd
from openpyxl import Workbook, load_workbook as read_xlsx

from .models import InputWorkbook, RunConfig, RowResult
from .parsing import normalize_nic, is_valid_nic
from .subjects import load_subjects


def _used_rows(source):
    """Keep internal gaps, without materializing trailing formatting-only rows."""
    rows = []
    for position, row in enumerate(source):
        width = len(row)
        while width and row[width - 1] in (None, ''):
            width -= 1
        if width:
            rows.extend([()] * (position - len(rows)))
            rows.append(tuple(row[:width]))
    return rows


def load_workbook(path: Path) -> InputWorkbook:
    path = Path(path).resolve()
    if path.suffix.lower() not in ('.xlsx', '.xls'):
        raise ValueError('Choose an .xlsx or .xls file.')
    data = path.read_bytes()
    if path.suffix.lower() == '.xlsx':
        book = read_xlsx(BytesIO(data), read_only=True, data_only=True, keep_links=False)
        try:
            worksheet = book.worksheets[0]
            sheet = worksheet.title
            # Read the actual row widths. The declared range can include a
            # single formatted cell thousands of rows beyond the data.
            worksheet.reset_dimensions()
            rows = _used_rows(worksheet.iter_rows(values_only=True))
        finally:
            book.close()
    else:
        import xlrd
        book = xlrd.open_workbook(file_contents=data, on_demand=True)
        try:
            worksheet = book.sheet_by_index(0)
            sheet = worksheet.name

            def value(cell):
                if cell.ctype == xlrd.XL_CELL_DATE:
                    return xlrd.xldate_as_datetime(cell.value, book.datemode)
                if cell.ctype == xlrd.XL_CELL_ERROR:
                    return xlrd.error_text_from_code[cell.value]
                if cell.ctype == xlrd.XL_CELL_BOOLEAN:
                    return bool(cell.value)
                return cell.value

            rows = _used_rows(tuple(value(cell) for cell in worksheet.row(i)) for i in range(worksheet.nrows))
        finally:
            book.release_resources()
    # Native readers retain Excel errors and duplicate/blank header labels.
    # Ignore trailing rows/columns containing only formatting, not values.
    if not rows:
        raise ValueError('The first worksheet contains no students.')
    width = max(map(len, rows))
    headers = rows[0] + (None,) * (width - len(rows[0]))
    if headers.count('NIC') != 1:
        raise ValueError("The first worksheet must contain exactly one column named 'NIC'.")
    data_rows = (row + (None,) * (width - len(row)) for row in rows[1:])
    frame = pd.DataFrame(data_rows, columns=pd.Index(headers, dtype=object), dtype=object)
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
