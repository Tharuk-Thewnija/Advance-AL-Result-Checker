import time
import unittest
from unittest.mock import patch
import customtkinter as ctk
from al_results.widgets import ResponsiveScrollbar, ResponsiveScrollableFrame


class RenderingTests(unittest.TestCase):
    def setUp(self):
        self.root = ctk.CTk(); self.root.withdraw()
        self.addCleanup(self.close_root)

    def close_root(self):
        for job in self.root.tk.call('after', 'info'):
            self.root.tk.call('after', 'cancel', job)
        self.root.destroy()

    def pump(self, seconds=0.05):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.root.update(); time.sleep(0.002)

    def test_scrollbar_coalesces_burst_updates_and_keeps_latest_position(self):
        scrollbar = ResponsiveScrollbar(self.root)
        scrollbar.pack()
        self.pump()
        draw = scrollbar._draw_engine.draw_rounded_scrollbar
        with patch.object(scrollbar._draw_engine, 'draw_rounded_scrollbar', wraps=draw) as rendering:
            for i in range(100):
                scrollbar.set(i / 200, (i + 50) / 200)
            self.assertEqual(rendering.call_count, 0)
            self.pump()
            self.assertEqual(rendering.call_count, 1)
            self.assertEqual(scrollbar.get(), (0.495, 0.745))
            scrollbar.set(0.495, 0.745); self.pump()
            self.assertEqual(rendering.call_count, 1)

    def test_redrawing_does_not_force_a_nested_idle_flush(self):
        scrollbar = ResponsiveScrollbar(self.root)
        scrollbar.pack(); self.pump()
        errors = []
        self.root.report_callback_exception = lambda *error: errors.append(error)
        with patch.object(scrollbar._canvas, 'update_idletasks', side_effect=AssertionError('Nested idle flush')):
            scrollbar.set(0.2, 0.8); self.pump()
        self.assertEqual(errors, [])

    def test_destroy_ignores_late_scroll_notifications(self):
        scrollbar = ResponsiveScrollbar(self.root)
        scrollbar.pack(); self.pump()
        scrollbar.set(0.1, 0.4)
        scrollbar.destroy()
        scrollbar.set(0.2, 0.6)
        self.assertIsNone(scrollbar._draw_job)
        self.pump()

    def test_scroll_frame_installs_local_scrollbar_and_cancels_pending_draw(self):
        frame = ResponsiveScrollableFrame(self.root, height=100)
        frame.pack()
        self.assertIsInstance(frame._scrollbar, ResponsiveScrollbar)
        frame._scrollbar.set(0.1, 0.5)
        frame.destroy()
        self.pump()

    def test_log_textbox_uses_coalesced_scrollbars_and_retains_text(self):
        from al_results.widgets import ResponsiveTextbox
        textbox = ResponsiveTextbox(self.root, width=200, height=100)
        textbox.pack()
        textbox.insert('end', '\n'.join(str(i) for i in range(100)))
        self.pump()
        self.assertIsInstance(textbox._x_scrollbar, ResponsiveScrollbar)
        self.assertIsInstance(textbox._y_scrollbar, ResponsiveScrollbar)
        textbox.see('end'); self.pump()
        self.assertIn('99', textbox.get('1.0', 'end'))
        self.assertGreater(textbox.yview()[0], 0)

    def test_scrollbar_preserves_theme_and_hover_colours(self):
        scrollbar = ResponsiveScrollbar(
            self.root, fg_color='transparent', bg_color=('#112233', '#223344'),
            button_color=('#345678', '#456789'), button_hover_color=('#567890', '#678901'),
        )
        scrollbar.pack()
        for mode, track, thumb, hover in (
            ('Light', '#112233', '#345678', '#567890'),
            ('Dark', '#223344', '#456789', '#678901'),
        ):
            ctk.set_appearance_mode(mode); scrollbar._on_leave(); self.pump()
            self.assertEqual(scrollbar._canvas.cget('bg'), track)
            items = scrollbar._canvas.find_withtag('scrollbar_parts')
            self.assertTrue(items)
            self.assertEqual({scrollbar._canvas.itemcget(item, 'fill') for item in items}, {thumb})
            scrollbar._on_enter(); self.pump()
            self.assertEqual({scrollbar._canvas.itemcget(item, 'fill') for item in items}, {hover})
