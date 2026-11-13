import unittest
from al_results.subjects import load_subjects, search_subjects
from al_results.parsing import parse_results
from tests.test_parsing import CARD


class SubjectTests(unittest.TestCase):
    def test_selection_and_exact_matching(self):
        self.assertEqual(parse_results(CARD, ('20',), ()), {'subject:20': 'A'})
        result = parse_results(CARD, ('20', '32'), ())
        self.assertEqual(result, {'subject:20': 'A', 'subject:32': 'C'})
        self.assertEqual(parse_results(CARD, ('07',), ()), {'subject:07': None})
        self.assertEqual(parse_results('Subject Stream\nSCIENCE\nCOMBINED MATHEMATICS\nB', ('07', '10'), ()),
                         {'subject:07': None, 'subject:10': 'B'})

    def test_optional_fields(self):
        self.assertEqual(parse_results(CARD, (), ('District Rank',)), {'District Rank': None})

    def test_catalogue_and_search(self):
        subjects = load_subjects()
        self.assertEqual(len({s.id for s in subjects}), len(subjects))
        self.assertEqual(search_subjects('ICT')[0].id, '20')
        self.assertEqual(search_subjects('20')[0].name, 'Information & Communication Technology')
        self.assertIn('12', {s.id for s in subjects})
        self.assertIn('13', {s.id for s in subjects})
        self.assertIn('88', {s.id for s in subjects})  # 2025 official statistics
        self.assertEqual(search_subjects('unlisted subject'), ())
