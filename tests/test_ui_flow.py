from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import pandas as pd
from al_results.ui import ScraperApp
from tests.test_collector import BrowserStub


class UIFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'class.xlsx'
        pd.DataFrame({'NIC': ['900000000V', '200000000001'], 'Student': ['Example A', 'Example B']}).to_excel(self.path, index=False)
        self.checkpoint = self.root / 'current.sqlite3'
        for name, kwargs in [
            ('al_results.checkpoints.checkpoint_path', {'return_value': self.checkpoint}),
            ('al_results.ui.checkpoint_path', {'return_value': self.checkpoint}),
            ('al_results.settings.preferences_path', {'return_value': self.root / 'preferences.json'}),
            ('al_results.collector.BrowserSession', {'new': BrowserStub}),
            ('al_results.ui.filedialog.askdirectory', {'return_value': str(self.root)}),
            ('al_results.ui.messagebox.showerror', {}),
            ('al_results.ui.messagebox.askyesnocancel', {'return_value': True}),
            ('al_results.ui.messagebox.askyesno', {'return_value': True}),
        ]:
            p = patch(name, **kwargs); p.start(); self.addCleanup(p.stop)
        BrowserStub.calls = []; BrowserStub.failure = None; BrowserStub.closed = False; BrowserStub.stop_after = None
        self.app = ScraperApp(); self.app.withdraw()
        self.addCleanup(self.app.destroy)
        self.app.path_var.set(str(self.path))

    def pump_idle(self):
        deadline = time.monotonic() + 10
        while self.app.busy and time.monotonic() < deadline:
            self.app.update(); time.sleep(0.02)
        self.app.update()
        self.assertFalse(self.app.busy, f'Worker stuck in {self.app.phase}')

    def test_ict_only_export_failure_and_retry(self):
        before = self.path.read_bytes()
        self.app.start_scraping(); self.pump_idle()
        self.assertTrue(self.app.has_results)
        with patch('al_results.ui.export_results', side_effect=PermissionError('Locked output')):
            self.app.start_export(); self.pump_idle()
        self.assertTrue(self.app.has_results)
        self.assertTrue(self.checkpoint.exists())
        self.app.start_export(); self.pump_idle()
        output = pd.read_excel(self.app.last_output)
        self.assertEqual(output['Information & Communication Technology Result'].tolist(), ['A', 'A'])
        self.assertNotIn('District Rank', output.columns)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(self.checkpoint.exists())

    def test_stop_partial_export_then_resume(self):
        BrowserStub.stop_after = 1
        self.app.start_scraping(); self.pump_idle()
        self.assertEqual(len(BrowserStub.calls), 1)
        self.app.start_export(); self.pump_idle()
        self.assertTrue(self.checkpoint.exists())
        result = pd.read_excel(self.app.last_output)
        self.assertEqual(result['Scrape Status'].tolist(), ['Completed', 'Pending'])
        BrowserStub.stop_after = None
        self.app.start_scraping(); self.pump_idle()
        self.assertEqual(len(BrowserStub.calls), 2)
        self.app.start_export(); self.pump_idle()
        self.assertFalse(self.checkpoint.exists())

    def test_themes_and_search_preserve_selection(self):
        for theme in ('Light', 'Dark', 'System'):
            self.app.appearance_var.set(theme)
            self.app.change_appearance(theme)
            self.app.update()
        self.app.search_var.set('Physics'); self.app.update()
        self.assertTrue(self.app.subject_vars['20'].get())
        self.app.clear_subjects()
        self.assertEqual(self.app.selection_label.cget('text'), '0 selected')

    def test_keyboard_checkbox_activation_and_tab_focus(self):
        self.app.deiconify(); self.app.update(); self.app.focus_force(); self.app.update()
        physics = self.app.subject_widgets[0]
        physics.focus_set(); self.app.update()
        target = self.app.focus_get()
        target.event_generate('<KeyPress-space>'); self.app.update()
        self.assertTrue(self.app.subject_vars['01'].get())
        target.event_generate('<Tab>'); self.app.update()
        self.assertEqual(self.app.focus_get(), self.app.subject_widgets[1]._text_label)
        field = next(w for w in self.app.settings_widgets if hasattr(w, 'cget') and
                     isinstance(w, __import__('customtkinter').CTkCheckBox))
        field.focus_set(); self.app.update()
        self.app.focus_get().event_generate('<KeyPress-space>'); self.app.update()
        self.assertTrue(self.app.field_vars['Candidate Name'].get())
        last = self.app.subject_widgets[-1]
        last.focus_set(); self.app.update()
        self.assertGreater(self.app.subject_list._parent_canvas.yview()[0], 0)

    def test_minimum_window_keeps_primary_actions_visible(self):
        self.app.geometry('980x720'); self.app.deiconify(); self.app.update()
        bottom = self.app.winfo_rooty() + self.app.winfo_height()
        for button in (self.app.start_button, self.app.export_button, self.app.open_button):
            self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), bottom)
