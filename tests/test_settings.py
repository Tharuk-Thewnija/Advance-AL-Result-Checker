from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from al_results.settings import load_preferences, save_preferences, validate_config
from al_results.models import RunConfig


class SettingsTests(unittest.TestCase):
    def test_removed_fields_do_not_discard_supported_saved_selections(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'preferences.json'
            path.write_text('{"fields": ["School", "District", "Medium", "District Rank", "Z-Score"]}')
            with patch('al_results.settings.preferences_path', return_value=path):
                self.assertEqual(load_preferences()['fields'], ['District Rank', 'Z-Score'])

    def test_preferences_roundtrip_and_corrupt_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings.json'
            with patch('al_results.settings.preferences_path', return_value=path):
                save_preferences({'appearance': 'Dark', 'subjects': ['20'], 'fields': ['District Rank']})
                self.assertEqual(load_preferences()['appearance'], 'Dark')
                self.assertEqual(load_preferences()['subjects'], ['20'])
                path.write_text('bad json')
                self.assertEqual(load_preferences()['appearance'], 'System')
                path.write_text('{"appearance": "unrecognised", "subjects": ["999"], "fields": "wrong"}')
                self.assertEqual(load_preferences()['subjects'], ['20'])
                self.assertEqual(load_preferences()['fields'], [])

    def test_reject_empty_selection(self):
        config = RunConfig(Path('a.xlsx'), (), (), '2025', 180, Path('.'))
        with self.assertRaisesRegex(ValueError, 'subject'):
            validate_config(config)
