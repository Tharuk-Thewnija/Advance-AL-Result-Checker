from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd
import xlwt
from al_results.excel_io import load_workbook, validate_rows, export_results, publish_export
from al_results.models import RunConfig, RowResult


class ExcelTests(unittest.TestCase):
    def test_ragged_streaming_sheet_preserves_all_columns_and_rows(self):
        from openpyxl import Workbook
        workbook = Workbook(write_only=True)
        sheet = workbook.create_sheet()
        sheet.append(['NIC'])
        sheet.append(['900000000V', 'extra'])
        sheet.append([])
        sheet.append(['900000001V'])
        workbook.save(self.path)
        workbook.close()
        frame = load_workbook(self.path).frame
        self.assertEqual(list(frame.columns), ['NIC', None])
        self.assertEqual(frame.values.tolist(), [['900000000V', 'extra'], [None, None], ['900000001V', None]])

    def test_formatting_does_not_expand_the_input_rectangle(self):
        from openpyxl import Workbook
        from openpyxl.worksheet._read_only import ReadOnlyWorksheet
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(['NIC', 'Unused'])
        sheet.append(['900000000V'])
        sheet.cell(10000, 256).number_format = '0.00'
        workbook.save(self.path)
        workbook.close()
        emitted_cells = 0
        original = ReadOnlyWorksheet.iter_rows
        def observed(*args, **kwargs):
            nonlocal emitted_cells
            for row in original(*args, **kwargs):
                emitted_cells += len(row)
                yield row
        with patch.object(ReadOnlyWorksheet, 'iter_rows', observed):
            frame = load_workbook(self.path).frame
        self.assertEqual(frame.shape, (1, 2))
        self.assertLess(emitted_cells, 1000)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'students.xlsx'
        pd.DataFrame({'NIC': ['900000000V', 200000000001, '', 'bad', '900000000V'],
                      'Name': ['a', 'b', 'c', 'd', 'e'],
                      'Information & Communication Technology Result': ['keep'] * 5,
                      'Results Information & Communication Technology Result': ['also keep'] * 5}).to_excel(self.path, index=False)
        self.config = RunConfig(self.path, ('20',), (), '2025', 180, self.root)

    def test_validation_preserves_values_and_order(self):
        book = load_workbook(self.path)
        rows = validate_rows(book)
        self.assertEqual([r[0] for r in rows], list(range(5)))
        self.assertEqual(rows[1][1], '200000000001')
        self.assertIsNotNone(rows[2][2])
        self.assertIsNotNone(rows[3][2])
        self.assertIsNone(rows[4][2])
        self.assertEqual(book.frame.iloc[1]['NIC'], 200000000001)

    def test_safe_selected_export_and_collision(self):
        book = load_workbook(self.path)
        before = self.path.read_bytes()
        output = export_results(book, self.config, [RowResult(0, 'Completed', {'subject:20': 'A'})])
        self.assertNotEqual(output, self.path)
        self.assertEqual(self.path.read_bytes(), before)
        result = pd.read_excel(output, keep_default_na=False)
        self.assertEqual(result.iloc[0]['Information & Communication Technology Result'], 'keep')
        self.assertEqual(result.iloc[0]['Results Information & Communication Technology Result'], 'also keep')
        self.assertEqual(result.iloc[0]['Results Information & Communication Technology Result (2)'], 'A')
        self.assertEqual(result.iloc[1]['Scrape Status'], 'Pending')
        self.assertNotIn('District Rank', result.columns)
        self.assertEqual(result['Name'].tolist(), ['a', 'b', 'c', 'd', 'e'])
        self.assertNotEqual(export_results(book, self.config, []), output)

    def test_failed_export_keeps_input_and_cleans_temp(self):
        book = load_workbook(self.path)
        before = self.path.read_bytes()
        with patch('al_results.excel_io.publish_export', side_effect=PermissionError('Locked destination')):
            with self.assertRaises(PermissionError):
                export_results(book, self.config, [])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.root.glob('.al-export-*')), [])

    def test_publishing_never_overwrites_existing_file(self):
        temporary = self.root / 'ready.xlsx'
        target = self.root / 'existing.xlsx'
        temporary.write_bytes(b'new'); target.write_bytes(b'original')
        with self.assertRaises(FileExistsError):
            publish_export(temporary, target)
        self.assertEqual(target.read_bytes(), b'original')

    def test_literal_formula_strings_are_not_executed(self):
        book = load_workbook(self.path)
        book.frame.at[0, 'Name'] = '=1+1'
        path = export_results(book, self.config, [])
        from openpyxl import load_workbook as open_excel
        with_book = open_excel(path)
        self.assertEqual(with_book.active['B2'].data_type, 's')
        with_book.close()

    def test_error_values_duplicate_and_blank_headers_roundtrip(self):
        from openpyxl import Workbook, load_workbook as read_excel
        excel = Workbook(); sheet = excel.active
        sheet.append(['NIC', 'Name', 'Name', None])
        sheet.append(['#N/A', 'first', 'second', 'unnamed value'])
        excel.save(self.path); excel.close()
        book = load_workbook(self.path)
        self.assertEqual(list(book.frame.columns), ['NIC', 'Name', 'Name', None])
        self.assertEqual(book.frame.iloc[0, 0], '#N/A')
        self.assertIsNotNone(validate_rows(book)[0][2])
        output = export_results(book, self.config, [])
        excel = read_excel(output)
        self.assertEqual([c.value for c in excel.active[1]][:4], ['NIC', 'Name', 'Name', None])
        self.assertEqual([c.value for c in excel.active[2]][:4], ['#N/A', 'first', 'second', 'unnamed value'])
        excel.close()

    def test_duplicate_nic_headers_are_rejected(self):
        from openpyxl import Workbook
        excel = Workbook(); excel.active.append(['NIC', 'NIC'])
        excel.active.append(['900000000V', '200000000001']); excel.save(self.path); excel.close()
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            load_workbook(self.path)

    def test_missing_nic_and_first_sheet(self):
        with pd.ExcelWriter(self.path) as writer:
            pd.DataFrame({'Wrong': [1]}).to_excel(writer, sheet_name='First', index=False)
            pd.DataFrame({'NIC': ['900000000V']}).to_excel(writer, sheet_name='Second', index=False)
        with self.assertRaisesRegex(ValueError, 'NIC'):
            load_workbook(self.path)

    def test_xls_input(self):
        path = self.root / 'legacy.xls'
        book = xlwt.Workbook()
        sheet = book.add_sheet('First')
        sheet.write(0, 0, 'NIC'); sheet.write(1, 0, '900000000V')
        book.save(str(path))
        result = load_workbook(path)
        self.assertEqual(result.sheet_name, 'First')
        self.assertEqual(result.frame.iloc[0]['NIC'], '900000000V')
