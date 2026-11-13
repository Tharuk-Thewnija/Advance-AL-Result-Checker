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

