import unittest

from al_results.parsing import normalize_nic, is_valid_nic, parse_results


CARD = '''Examination
G.C.E.(A/L) EXAMINATION-(After Rescrutiny)
Year
2025
Name
SAMPLE STUDENT
Index Number
1000001
Subject Stream
COMMERCE
INFORMATION & COMMUNICATION TECHNOLOGY
A
BUSINESS STUDIES
C
'''


class ParsingTests(unittest.TestCase):
    def test_signed_inline_score(self):
        for label in ('Z-Score: -0.4512', 'Z Score -0.4512', 'Z-Score - -0.4512', 'Z-Score\n-0.4512'):
            with self.subTest(label=label):
                self.assertEqual(parse_results(label, (), ('Z-Score',))['Z-Score'], '-0.4512')

    def test_blank_field_before_subject(self):
        for field in ('Z-Score', 'Candidate Name'):
            for body in ('Physics\nA', '01 Physics A', 'Physics\nChemistry\nA\nB'):
                with self.subTest(field=field, body=body):
                    values = parse_results(field + '\n\n' + body, ('01',), (field,))
                    self.assertEqual(values, {'subject:01': 'A', field: None})
        legacy = parse_results('Z-Score\n\nPhysics\nA', 'Physics')
        self.assertIsNone(legacy['Z-Score'])
        self.assertEqual(legacy['Selected Subject Result'], 'A')

    def test_subject_named_stream_value_with_spacing(self):
        values = parse_results('Subject Stream\n\nEngineering Technology\nPhysics\nA',
                               ('01',), ('Subject Stream',))
        self.assertEqual(values, {'subject:01': 'A', 'Subject Stream': 'Engineering Technology'})

    def test_split_subject_grade_and_absent_ranks(self):
        result = parse_results(CARD, 'Information & Communication Technology')
        self.assertEqual(result['Selected Subject Result'], 'A')
        self.assertEqual(result['Candidate Name'], 'SAMPLE STUDENT')
        self.assertIsNone(result['District Rank'])

    def test_nic_normalization(self):
        self.assertEqual(normalize_nic(200000000001.0), '200000000001')
        self.assertEqual(normalize_nic(' 900000000v '), '900000000V')
        self.assertEqual(normalize_nic(None), '')
        self.assertTrue(is_valid_nic('900000000V'))
        self.assertFalse(is_valid_nic('123'))

