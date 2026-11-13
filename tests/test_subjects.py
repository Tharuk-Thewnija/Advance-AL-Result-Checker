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

    def test_blank_metadata_does_not_consume_next_label(self):
        text = 'District Rank\n\nIsland Rank\n12\nZ-Score\n\nSubject Stream\nSCIENCE'
        self.assertEqual(parse_results(text, (), ('District Rank', 'Island Rank', 'Z-Score', 'Subject Stream')),
                         {'District Rank': None, 'Island Rank': '12', 'Z-Score': None, 'Subject Stream': 'SCIENCE'})
        self.assertEqual(parse_results('Nameplate: VALUE\nIndex Number\n1000001', (), ('Candidate Name', 'Index Number')),
                         {'Candidate Name': None, 'Index Number': '1000001'})

    def test_search_by_name_and_official_code(self):
        self.assertEqual([s.id for s in search_subjects('01')], ['01'])
        self.assertEqual([s.id for s in search_subjects('1')], ['01'])
        self.assertEqual([s.id for s in search_subjects('25a')], ['25A'])
        self.assertEqual([s.id for s in search_subjects('  information communication  ')], ['20'])

    def test_grouped_grades_ignore_metadata_matching_subject_names(self):
        text = 'Medium\nEnglish\nSubject Stream\nEngineering Technology\nPhysics\nChemistry\nGeneral English\nA\nB\nC'
        self.assertEqual(parse_results(text, ('01', '02', '13', '65', '73'), ()),
                         {'subject:01': 'A', 'subject:02': 'B', 'subject:13': 'C', 'subject:65': None, 'subject:73': None})

    def test_incomplete_group_does_not_assign_first_grade_to_last_subject(self):
        self.assertEqual(parse_results('Physics\nChemistry\nA', ('01', '02'), ()),
                         {'subject:01': None, 'subject:02': None})

    def test_catalogue_and_search(self):
        subjects = load_subjects()
        self.assertEqual(len({s.id for s in subjects}), len(subjects))
        self.assertEqual(search_subjects('ICT')[0].id, '20')
        self.assertEqual(search_subjects('20')[0].name, 'Information & Communication Technology')
        self.assertIn('12', {s.id for s in subjects})
        self.assertIn('13', {s.id for s in subjects})
        self.assertIn('88', {s.id for s in subjects})  # 2025 official statistics
        self.assertEqual(search_subjects('unlisted subject'), ())
