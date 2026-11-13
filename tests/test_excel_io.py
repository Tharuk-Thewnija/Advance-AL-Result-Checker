from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd
import xlwt
from al_results.excel_io import load_workbook, validate_rows, export_results
from al_results.models import RunConfig, RowResult


class ExcelTests(unittest.TestCase):
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
        with patch('al_results.excel_io.os.link', side_effect=PermissionError('Locked destination')):
            with self.assertRaises(PermissionError):
                export_results(book, self.config, [])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.root.glob('.al-export-*')), [])

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
