"""Single-window desktop workflow. All Tk operations stay on the main thread."""
from collections import deque
from datetime import datetime
import os
from pathlib import Path
import textwrap
import threading
from tkinter import filedialog, messagebox
import customtkinter as ctk

from . import __version__
from .checkpoints import CheckpointStore, CheckpointMismatch, checkpoint_path
from .collector import collect
from .events import EventBuffer
from .excel_io import load_workbook, export_results, validate_rows
from .models import RunConfig, WorkerEvent
from .settings import load_preferences, save_preferences, validate_config
from .subjects import FIELDS, load_subjects, search_subjects
from .widgets import (
    KeyboardButton, KeyboardCheckBox, KeyboardOptionMenu,
    ResponsiveScrollableFrame, ResponsiveTextbox,
)

# Obsidian Bento Palette (Light, Dark)
BG = ('#EDF1F7', '#0B0B10')
SHELL = ('#F6F8FC', '#121219')
PANEL = ('#FFFFFF', '#181822')
SURFACE = ('#F0F3F9', '#111118')
INK = ('#111827', '#F3F4F8')
MUTED = ('#5E6B80', '#8B8E9F')
DIM = ('#8D99AD', '#5B5E70')
LINE = ('#DCE3EE', '#262634')
LINE_BRIGHT = ('#C5D0E2', '#343448')

ACCENT = ('#5941D6', '#6147E5')
HOVER = ('#4832BE', '#7259F0')
ACCENT_SOFT = ('#EAE6FD', '#231D42')
ACCENT_INK = ('#4A35B8', '#A799FF')

BTN_SURFACE = ('#E9EEF6', '#1E1E2B')
BTN_HOVER = ('#DCE4F0', '#29293A')

SUCCESS = ('#059669', '#34D399')
SUCCESS_SOFT = ('#ECFDF5', '#132A24')
WARN = ('#D97706', '#FBBF24')
WARN_SOFT = ('#FFFBEB', '#2B2214')
DANGER = ('#DC2626', '#F87171')
DANGER_SOFT = ('#FEF2F2', '#2D171C')


class ActivityLog:
    def __init__(self):
        self.lines = deque(maxlen=500)

    def append(self, text):
        self.lines.append(text)


class ScraperApp(ctk.CTk):
    def __init__(self):
        self.preferences = load_preferences()
        ctk.set_appearance_mode(self.preferences['appearance'])
        ctk.set_default_color_theme('blue')
        super().__init__()
        self.title('A/L Results Collector')
        self.geometry('1180x880')
        self.minsize(1020, 750)
        self.configure(fg_color=BG)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.events = EventBuffer()
        self.stop_event = threading.Event()
        self.skip_event = threading.Event()
        self.worker_thread = None
        self.busy = False
        self.phase = 'idle'
        self.closing = False
        self.workbook = None
        self.config = None
        self.has_results = False
        self.last_output = None
        self.log = ActivityLog()
        self.log_dirty = False
        self._destroyed = False

        self.path_var = ctk.StringVar()
        self.folder_var = ctk.StringVar()
        self.year_var = ctk.StringVar(value=self.preferences['year'])
        self.timeout_var = ctk.StringVar(value=str(self.preferences['timeout']))
        self.search_var = ctk.StringVar()
        self.appearance_var = ctk.StringVar(value=self.preferences['appearance'])
        self.subject_vars = {
            s.id: ctk.BooleanVar(value=s.id in self.preferences['subjects'])
            for s in load_subjects()
        }
        self.field_vars = {
            f: ctk.BooleanVar(value=f in self.preferences['fields'])
            for f in FIELDS
        }
        self.settings_widgets = []
        self.subject_widgets = []
        self._subject_cache = {}
        self._subject_filter_ids = ()
        self._subject_empty_label = None
        self.stage_pills = {}

        self._build_layout()
        self._set_stage('configure')
        self.search_var.trace_add('write', lambda *_: self._render_subjects())
        self._render_subjects()
        self.protocol('WM_DELETE_WINDOW', self.on_close)
        self.after(100, self.process_events)

    def label(self, parent, text, size=13, bold=False, muted=False, color=None, **kwargs):
        text_color = color if color is not None else (MUTED if muted else INK)
        return ctk.CTkLabel(
            parent,
            text=text,
            text_color=text_color,
            font=ctk.CTkFont(family='Segoe UI', size=size, weight='bold' if bold else 'normal'),
            **kwargs,
        )

    def button(self, parent, text, command, primary=False, pill=True, height=38, **kwargs):
        radius = height // 2 if pill else 10
        defaults = dict(
            height=height,
            corner_radius=radius,
            fg_color=ACCENT if primary else BTN_SURFACE,
            hover_color=HOVER if primary else BTN_HOVER,
            text_color='#FFFFFF' if primary else INK,
            border_width=0 if primary else 1,
            border_color=ACCENT if primary else LINE_BRIGHT,
            font=ctk.CTkFont(family='Segoe UI', size=13, weight='bold' if primary else 'normal'),
        )
        defaults.update(kwargs)
        return KeyboardButton(parent, text=text, command=command, **defaults)

    def card(self, parent, radius=16, fg=PANEL):
        return ctk.CTkFrame(
            parent,
            fg_color=fg,
            corner_radius=radius,
            border_width=1,
            border_color=LINE,
        )

    def entry(self, parent, height=38, **kwargs):
        defaults = dict(
            height=height,
            corner_radius=height // 2,
            fg_color=SURFACE,
            border_width=1,
            border_color=LINE_BRIGHT,
            text_color=INK,
            placeholder_text_color=DIM,
            font=ctk.CTkFont(family='Segoe UI', size=13),
        )
        defaults.update(kwargs)
        return ctk.CTkEntry(parent, **defaults)

    def _set_stage(self, active):
        for key, (frame, lbl) in self.stage_pills.items():
            if key == active:
                frame.configure(fg_color=ACCENT_SOFT, border_width=1, border_color=ACCENT)
                lbl.configure(text_color=ACCENT_INK)
            else:
                frame.configure(fg_color='transparent', border_width=0, border_color=LINE)
                lbl.configure(text_color=MUTED)

    def _set_status_pill(self, text, state='idle'):
        styles = {
            'idle': (BTN_SURFACE, MUTED),
            'running': (ACCENT_SOFT, ACCENT_INK),
            'success': (SUCCESS_SOFT, SUCCESS),
            'warn': (WARN_SOFT, WARN),
            'error': (DANGER_SOFT, DANGER),
        }
        bg, fg = styles.get(state, styles['idle'])
        self.status_pill_frame.configure(fg_color=bg, border_color=LINE)
        self.status_pill.configure(text=f'●  {text}', text_color=fg)

    def _build_layout(self):
        # ── Top Navigation Bar ────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color='transparent', corner_radius=0)
        header.grid(row=0, column=0, sticky='ew', padx=28, pady=(20, 14))
        header.grid_columnconfigure(1, weight=1)

        brand_icon = ctk.CTkFrame(
            header, width=40, height=40, corner_radius=12,
            fg_color=ACCENT_SOFT, border_width=1, border_color=ACCENT,
        )
        brand_icon.grid(row=0, column=0, rowspan=2, sticky='w', padx=(0, 14))
        brand_icon.grid_propagate(False)
        brand_icon.grid_columnconfigure(0, weight=1)
        brand_icon.grid_rowconfigure(0, weight=1)
        self.label(brand_icon, '✦', size=18, bold=True, color=ACCENT_INK).grid(row=0, column=0)

        self.label(header, 'A/L Results Collector', size=21, bold=True).grid(row=0, column=1, sticky='w')
        self.label(header, 'Class lookup  ·  doenets.lk', size=12, muted=True).grid(
            row=1, column=1, sticky='w', pady=(1, 0)
        )

        # Workflow pill bar (inspired by top segmented pill nav)
        stage_bar = ctk.CTkFrame(
            header, fg_color=PANEL, corner_radius=20, border_width=1, border_color=LINE
        )
        stage_bar.grid(row=0, column=2, rowspan=2, padx=(0, 14))
        for col, (key, title) in enumerate([
            ('configure', '01  Configure'),
            ('collect', '02  Collect'),
            ('export', '03  Export'),
        ]):
            pill = ctk.CTkFrame(
                stage_bar, fg_color='transparent', corner_radius=15, border_width=0, border_color=LINE
            )
            pill.grid(row=0, column=col, padx=4, pady=4)
            lbl = self.label(pill, title, size=12, bold=True, muted=True)
            lbl.grid(row=0, column=0, padx=12, pady=4)
            self.stage_pills[key] = (pill, lbl)

        # Theme capsule
        nav_right = ctk.CTkFrame(
            header, fg_color=PANEL, corner_radius=20, border_width=1, border_color=LINE
        )
        nav_right.grid(row=0, column=3, rowspan=2, sticky='e')
        self.label(nav_right, 'Theme', size=12, muted=True).grid(row=0, column=0, padx=(14, 8), pady=6)
        self.theme_menu = KeyboardOptionMenu(
            nav_right,
            values=['System', 'Light', 'Dark'],
            variable=self.appearance_var,
            command=self.change_appearance,
            width=98,
            height=30,
            corner_radius=15,
            fg_color=SURFACE,
            button_color=BTN_SURFACE,
            button_hover_color=BTN_HOVER,
            text_color=INK,
            dropdown_fg_color=PANEL,
            dropdown_hover_color=BTN_HOVER,
            dropdown_text_color=INK,
            font=ctk.CTkFont(family='Segoe UI', size=12),
        )
        self.theme_menu.grid(row=0, column=1, padx=(0, 6), pady=5)

        # ── Main Elevated Bento Shell ─────────────────────────────────────────
        shell = ctk.CTkFrame(
            self,
            fg_color=SHELL,
            corner_radius=22,
            border_width=1,
            border_color=LINE,
        )
        shell.grid(row=1, column=0, sticky='nsew', padx=28, pady=(0, 12))
        shell.grid_columnconfigure(0, weight=13, minsize=500)
        shell.grid_columnconfigure(1, weight=10, minsize=380)
        shell.grid_rowconfigure(0, weight=1)

        # ── Left Column: Configuration Bento Cards ────────────────────────────
        setup = ResponsiveScrollableFrame(
            shell,
            fg_color='transparent',
            scrollbar_button_color=LINE_BRIGHT,
            scrollbar_button_hover_color=MUTED,
        )
        setup.grid(row=0, column=0, sticky='nsew', padx=(14, 8), pady=14)
        setup.grid_columnconfigure(0, weight=1)

        # Card 1: Student List
        source_card = self.card(setup)
        source_card.grid(row=0, column=0, sticky='ew', pady=(0, 12))
        source_card.grid_columnconfigure(0, weight=1)

        self.label(source_card, '01  ·  STUDENT LIST', size=11, bold=True, color=ACCENT_INK).grid(
            row=0, column=0, sticky='w', padx=18, pady=(16, 2)
        )
        self.label(source_card, 'Source workbook', size=16, bold=True).grid(
            row=1, column=0, sticky='w', padx=18, pady=(0, 10)
        )

        file_row = ctk.CTkFrame(source_card, fg_color='transparent', corner_radius=0)
        file_row.grid(row=2, column=0, sticky='ew', padx=18)
        file_row.grid_columnconfigure(0, weight=1)

        path_entry = self.entry(
            file_row, textvariable=self.path_var, placeholder_text='Choose an Excel file (.xlsx / .xls)'
        )
        path_entry.grid(row=0, column=0, sticky='ew', padx=(0, 8))
        browse = self.button(file_row, 'Browse', self.browse_file, width=88, height=38)
        browse.grid(row=0, column=1)
        self.settings_widgets.extend([path_entry, browse])

        self.label(
            source_card, 'Uses the first worksheet with a column named NIC.', size=12, muted=True
        ).grid(row=3, column=0, sticky='w', padx=18, pady=(8, 16))

        # Card 2: Subjects
        subjects_card = self.card(setup)
        subjects_card.grid(row=1, column=0, sticky='ew', pady=(0, 12))
        subjects_card.grid_columnconfigure(0, weight=1)

        subj_top = ctk.CTkFrame(subjects_card, fg_color='transparent', corner_radius=0)
        subj_top.grid(row=0, column=0, sticky='ew', padx=18, pady=(16, 10))
        subj_top.grid_columnconfigure(0, weight=1)

        subj_title_wrap = ctk.CTkFrame(subj_top, fg_color='transparent', corner_radius=0)
        subj_title_wrap.grid(row=0, column=0, sticky='w')
        self.label(subj_title_wrap, '02  ·  SUBJECTS', size=11, bold=True, color=ACCENT_INK).grid(
            row=0, column=0, sticky='w'
        )
        self.label(subj_title_wrap, 'Filter target subjects', size=16, bold=True).grid(
            row=1, column=0, sticky='w'
        )

        pill_wrap = ctk.CTkFrame(
            subj_top, fg_color=ACCENT_SOFT, corner_radius=12, border_width=1, border_color=LINE
        )
        pill_wrap.grid(row=0, column=1, padx=(0, 8))
        self.selection_label = self.label(pill_wrap, '0 selected', size=11, bold=True, color=ACCENT_INK)
        self.selection_label.grid(row=0, column=0, padx=10, pady=4)

        clear = self.button(subj_top, 'Clear', self.clear_subjects, width=64, height=30)
        clear.grid(row=0, column=2)
        self.settings_widgets.append(clear)

        search_row = ctk.CTkFrame(subjects_card, fg_color='transparent', corner_radius=0)
        search_row.grid(row=1, column=0, sticky='ew', padx=18, pady=(0, 10))
        search_row.grid_columnconfigure(0, weight=1)
        self.label(search_row, 'Search by subject name or code', size=12, muted=True).grid(
            row=0, column=0, sticky='w', pady=(0, 4)
        )
        self.search_entry = self.entry(search_row, height=36, textvariable=self.search_var)
        self.search_entry.grid(row=1, column=0, sticky='ew')
        self.settings_widgets.append(self.search_entry)

        self.subject_list = ResponsiveScrollableFrame(
            subjects_card,
            height=210,
            fg_color=SURFACE,
            corner_radius=14,
            border_width=1,
            border_color=LINE,
            scrollbar_button_color=LINE_BRIGHT,
            scrollbar_button_hover_color=MUTED,
        )
        self.subject_list.grid(row=2, column=0, sticky='ew', padx=18, pady=(0, 16))
        self.subject_list.grid_columnconfigure(0, weight=1)

        # Card 3: Fields & Exam Options
        options_card = self.card(setup)
        options_card.grid(row=2, column=0, sticky='ew', pady=(0, 4))
        options_card.grid_columnconfigure(0, weight=1)

        self.label(options_card, '03  ·  OPTIONS', size=11, bold=True, color=ACCENT_INK).grid(
            row=0, column=0, sticky='w', padx=18, pady=(16, 2)
        )
        self.label(options_card, 'Extra fields & exam settings', size=16, bold=True).grid(
            row=1, column=0, sticky='w', padx=18, pady=(0, 10)
        )

        fields = ctk.CTkFrame(
            options_card, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=LINE
        )
        fields.grid(row=2, column=0, sticky='ew', padx=18, pady=(0, 14))
        fields.grid_columnconfigure((0, 1), weight=1)

        for i, (name, variable) in enumerate(self.field_vars.items()):
            widget = KeyboardCheckBox(
                fields,
                text=name,
                variable=variable,
                text_color=INK,
                font=('Segoe UI', 12),
                checkbox_width=18,
                checkbox_height=18,
                corner_radius=6,
                border_width=2,
                border_color=LINE_BRIGHT,
                checkmark_color='#FFFFFF',
                fg_color=ACCENT,
                hover_color=HOVER,
            )
            widget.grid(row=i // 2, column=i % 2, sticky='w', padx=14, pady=8)
            self.settings_widgets.append(widget)

        year_row = ctk.CTkFrame(options_card, fg_color='transparent', corner_radius=0)
        year_row.grid(row=3, column=0, sticky='ew', padx=18, pady=(0, 12))
        year_row.grid_columnconfigure(1, weight=1)

        self.label(year_row, 'Exam year', size=13, bold=True).grid(row=0, column=0, sticky='w', padx=(0, 14))
        year_entry = self.entry(year_row, textvariable=self.year_var, width=110, height=34)
        year_entry.grid(row=0, column=1, sticky='w')
        self.settings_widgets.append(year_entry)

        self.advanced_button = self.button(
            year_row, 'Advanced settings ▾', self.toggle_advanced, width=154, height=32
        )
        self.advanced_button.grid(row=0, column=2, sticky='e')

        self.advanced = ctk.CTkFrame(
            options_card, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=LINE
        )
        self.advanced.grid_columnconfigure(0, weight=1)

        self.label(self.advanced, 'Output folder (defaults to input folder)', size=12, muted=True).grid(
            row=0, column=0, columnspan=2, sticky='w', padx=14, pady=(12, 4)
        )
        folder_entry = self.entry(
            self.advanced, textvariable=self.folder_var, placeholder_text='Same folder as the student list', height=34
        )
        folder_entry.grid(row=1, column=0, sticky='ew', padx=(14, 8), pady=(0, 10))
        folder_button = self.button(self.advanced, 'Choose', self.browse_folder, width=82, height=34)
        folder_button.grid(row=1, column=1, padx=(0, 14), pady=(0, 10))

        self.label(self.advanced, 'CAPTCHA timeout (seconds)', size=12, muted=True).grid(
            row=2, column=0, sticky='w', padx=14, pady=(0, 4)
        )
        timeout = self.entry(self.advanced, textvariable=self.timeout_var, width=110, height=34)
        timeout.grid(row=3, column=0, sticky='w', padx=14, pady=(0, 14))
        self.settings_widgets.extend([folder_entry, folder_button, timeout])

        ctk.CTkFrame(options_card, fg_color='transparent', corner_radius=0, height=8).grid(row=5, column=0)

        # ── Right Column: Telemetry, Activity & Actions ───────────────────────
        right = ctk.CTkFrame(shell, fg_color='transparent', corner_radius=0)
        right.grid(row=0, column=1, sticky='nsew', padx=(8, 16), pady=14)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)

        # Card 4: Hero Telemetry Card
        progress_card = self.card(right)
        progress_card.grid(row=0, column=0, sticky='ew', pady=(0, 12))
        progress_card.grid_columnconfigure(0, weight=1)

        p_head = ctk.CTkFrame(progress_card, fg_color='transparent', corner_radius=0)
        p_head.grid(row=0, column=0, sticky='ew', padx=18, pady=(16, 4))
        p_head.grid_columnconfigure(0, weight=1)

        self.label(p_head, 'LIVE TELEMETRY', size=11, bold=True, color=ACCENT_INK).grid(row=0, column=0, sticky='w')

        self.status_pill_frame = ctk.CTkFrame(
            p_head, fg_color=BTN_SURFACE, corner_radius=12, border_width=1, border_color=LINE
        )
        self.status_pill_frame.grid(row=0, column=1, sticky='e')
        self.status_pill = self.label(self.status_pill_frame, '●  Ready', size=11, bold=True, muted=True)
        self.status_pill.grid(row=0, column=0, padx=10, pady=3)

        self.count_label = self.label(progress_card, '0 / 0 students', size=28, bold=True)
        self.count_label.grid(row=1, column=0, sticky='w', padx=18, pady=(2, 2))

        self.status_label = self.label(
            progress_card, 'Ready when you are.', size=13, muted=True, anchor='w', justify='left', wraplength=350
        )
        self.status_label.grid(row=2, column=0, sticky='ew', padx=18, pady=(0, 12))

        bar_row = ctk.CTkFrame(progress_card, fg_color='transparent', corner_radius=0)
        bar_row.grid(row=3, column=0, sticky='ew', padx=18, pady=(0, 14))
        bar_row.grid_columnconfigure(0, weight=1)

        self.progress = ctk.CTkProgressBar(
            bar_row, fg_color=SURFACE, progress_color=ACCENT, height=8, corner_radius=4
        )
        self.progress.set(0)
        self.progress.grid(row=0, column=0, sticky='ew', padx=(0, 10))
        self.percent_label = self.label(bar_row, '0%', size=12, bold=True, color=ACCENT_INK)
        self.percent_label.grid(row=0, column=1, sticky='e')

        # 3 Mini Bento Stat Tiles
        stats_row = ctk.CTkFrame(progress_card, fg_color='transparent', corner_radius=0)
        stats_row.grid(row=4, column=0, sticky='ew', padx=18, pady=(0, 12))
        stats_row.grid_columnconfigure((0, 1, 2), weight=1)

        self.completed_val = self._make_stat_tile(stats_row, 0, 'Completed', SUCCESS, (0, 6))
        self.skipped_val = self._make_stat_tile(stats_row, 1, 'Skipped', WARN, (3, 3))
        self.failed_val = self._make_stat_tile(stats_row, 2, 'Errors', DANGER, (6, 0))

        # Current student capsule
        current_pill = ctk.CTkFrame(
            progress_card, fg_color=SURFACE, corner_radius=12, border_width=1, border_color=LINE
        )
        current_pill.grid(row=5, column=0, sticky='ew', padx=18, pady=(0, 10))
        current_pill.grid_columnconfigure(0, weight=1)
        self.current_label = self.label(
            current_pill, 'No student in progress', size=12, muted=True, anchor='w'
        )
        self.current_label.grid(row=0, column=0, sticky='ew', padx=12, pady=8)

        self.label(
            progress_card,
            'Chrome opens per run—solve CAPTCHA & submit for each student.',
            size=11,
            color=DIM,
            anchor='w',
        ).grid(row=6, column=0, sticky='ew', padx=18, pady=(0, 16))

        # Card 5: Activity Log
        log_card = self.card(right)
        log_card.grid(row=1, column=0, sticky='nsew', pady=(0, 12))
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(1, weight=1)

        log_head = ctk.CTkFrame(log_card, fg_color='transparent', corner_radius=0)
        log_head.grid(row=0, column=0, sticky='ew', padx=18, pady=(14, 8))
        log_head.grid_columnconfigure(0, weight=1)
        self.label(log_head, 'Activity feed', size=14, bold=True).grid(row=0, column=0, sticky='w')
        self.label(log_head, 'SESSION LOG', size=10, bold=True, color=DIM).grid(row=0, column=1, sticky='e')

        self.log_box = ResponsiveTextbox(
            log_card,
            fg_color=SURFACE,
            text_color=INK,
            border_width=1,
            border_color=LINE,
            font=('Segoe UI', 12),
            corner_radius=12,
            wrap='word',
            state='disabled',
        )
        self.log_box.grid(row=1, column=0, sticky='nsew', padx=16, pady=(0, 16))

        # Card 6: Action Controls
        controls = self.card(right)
        controls.grid(row=2, column=0, sticky='ew')
        controls.grid_columnconfigure(0, weight=1)

        self.start_button = self.button(
            controls, 'Start collection', self.start_scraping, primary=True, height=42
        )
        self.start_button.grid(row=0, column=0, sticky='ew', padx=16, pady=(16, 8))

        mid_actions = ctk.CTkFrame(controls, fg_color='transparent', corner_radius=0)
        mid_actions.grid(row=1, column=0, sticky='ew', padx=16, pady=(0, 8))
        mid_actions.grid_columnconfigure((0, 1), weight=1)

        self.stop_button = self.button(
            mid_actions, 'Stop & save', self.stop_scraping, state='disabled', height=36
        )
        self.stop_button.grid(row=0, column=0, sticky='ew', padx=(0, 4))
        self.skip_button = self.button(
            mid_actions, 'Skip current', self.skip_current, state='disabled', height=36
        )
        self.skip_button.grid(row=0, column=1, sticky='ew', padx=(4, 0))

        exp_actions = ctk.CTkFrame(controls, fg_color='transparent', corner_radius=0)
        exp_actions.grid(row=2, column=0, sticky='ew', padx=16, pady=(0, 16))
        exp_actions.grid_columnconfigure((0, 1), weight=1)

        self.export_button = self.button(
            exp_actions, 'Export to Excel', self.start_export, state='disabled', height=36
        )
        self.export_button.grid(row=0, column=0, sticky='ew', padx=(0, 4))
        self.open_button = self.button(
            exp_actions, 'Open folder', self.open_output, state='disabled', height=36
        )
        self.open_button.grid(row=0, column=1, sticky='ew', padx=(4, 0))

        # ── Footer Trust Strip ────────────────────────────────────────────────
        footer = ctk.CTkFrame(self, fg_color='transparent', corner_radius=0)
        footer.grid(row=2, column=0, sticky='ew', padx=28, pady=(0, 14))
        footer.grid_columnconfigure(1, weight=1)

        trust_pill = ctk.CTkFrame(
            footer, fg_color=PANEL, corner_radius=14, border_width=1, border_color=LINE
        )
        trust_pill.grid(row=0, column=0, sticky='w')
        self.label(
            trust_pill, '●  Local-first · Data stays on this computer', size=11, muted=True
        ).grid(row=0, column=0, padx=12, pady=4)

        self.label(
            footer, f'v{__version__}  ·  Results fetched directly from doenets.lk', size=11, color=DIM
        ).grid(row=0, column=1, sticky='e')

    def _make_stat_tile(self, parent, col, title, dot_color, padx):
        tile = ctk.CTkFrame(
            parent, fg_color=SURFACE, corner_radius=12, border_width=1, border_color=LINE
        )
        tile.grid(row=0, column=col, sticky='ew', padx=padx)
        tile.grid_columnconfigure(0, weight=1)
        self.label(tile, f'● {title}', size=11, color=dot_color).grid(
            row=0, column=0, sticky='w', padx=10, pady=(8, 0)
        )
        val = self.label(tile, '0', size=18, bold=True)
        val.grid(row=1, column=0, sticky='w', padx=10, pady=(0, 8))
        return val

    def _render_subjects(self):
        matches = search_subjects(self.search_var.get())
        visible_ids = tuple(subject.id for subject in matches)
        if self._subject_cache and visible_ids == self._subject_filter_ids:
            self.update_selection_count()
            return
        self._subject_filter_ids = visible_ids
        for widget in self.subject_widgets:
            widget.grid_remove()
        self.subject_widgets.clear()
        if self._subject_empty_label is not None:
            self._subject_empty_label.grid_remove()
        for row, subject in enumerate(matches):
            widget = self._subject_cache.get(subject.id)
            if widget is None:
                widget = self._create_subject_checkbox(subject)
                self._subject_cache[subject.id] = widget
            state = 'disabled' if self.busy else 'normal'
            if widget.cget('state') != state:
                widget.configure(state=state)
            widget.grid(row=row, column=0, sticky='w', padx=10, pady=5)
            self.subject_widgets.append(widget)
        if not self.subject_widgets:
            if self._subject_empty_label is None:
                self._subject_empty_label = self.label(self.subject_list, 'No matching subjects.', muted=True)
            self._subject_empty_label.grid(row=0, column=0, pady=16)
        self.subject_list._parent_canvas.yview_moveto(0)
        self.update_selection_count()

    def _create_subject_checkbox(self, subject):
        return KeyboardCheckBox(
            self.subject_list,
            text=f'{subject.code}  ' + textwrap.fill(subject.name, width=42),
            variable=self.subject_vars[subject.id],
            command=self.update_selection_count,
            text_color=INK,
            fg_color=ACCENT,
            hover_color=HOVER,
            border_width=2,
            border_color=LINE_BRIGHT,
            checkmark_color='#FFFFFF',
            corner_radius=6,
            font=('Segoe UI', 12),
            checkbox_width=18,
            checkbox_height=18,
            state='disabled' if self.busy else 'normal',
        )

    def update_selection_count(self):
        self.selection_label.configure(
            text=f'{sum(v.get() for v in self.subject_vars.values())} selected'
        )

    def clear_subjects(self):
        for variable in self.subject_vars.values():
            variable.set(False)
        self.update_selection_count()

    def toggle_advanced(self):
        if self.advanced.winfo_manager():
            self.advanced.grid_remove()
            self.advanced_button.configure(text='Advanced settings ▾')
        else:
            self.advanced.grid(row=4, column=0, sticky='ew', padx=18, pady=(0, 8))
            self.advanced_button.configure(text='Advanced settings ▴')

    def browse_file(self):
        path = filedialog.askopenfilename(
            title='Choose a student list', filetypes=[('Excel workbooks', '*.xlsx *.xls')]
        )
        if path:
            self.path_var.set(path)

    def browse_folder(self):
        path = filedialog.askdirectory(title='Choose output folder')
        if path:
            self.folder_var.set(path)

    def change_appearance(self, value):
        ctk.set_appearance_mode(value)
        self.persist_preferences()

    def persist_preferences(self):
        try:
            timeout = int(self.timeout_var.get())
        except ValueError:
            timeout = 180
        try:
            save_preferences({
                'appearance': self.appearance_var.get(),
                'subjects': [sid for sid, v in self.subject_vars.items() if v.get()],
                'fields': [name for name, v in self.field_vars.items() if v.get()],
                'year': self.year_var.get().strip(),
                'timeout': timeout,
            })
        except OSError:
            self.append_log('Preferences could not be saved. Collection progress is stored separately.')

    def append_log(self, text):
        self.log.append(f'{datetime.now():%H:%M:%S}  {text}')
        self.log_dirty = True

    def _render_log(self):
        if not self.log_dirty:
            return
        self.log_box.configure(state='normal')
        self.log_box.delete('1.0', 'end')
        self.log_box.insert('end', '\n'.join(self.log.lines))
        self.log_box.see('end')
        self.log_box.configure(state='disabled')
        self.log_dirty = False

    def set_busy(self, busy, phase='idle'):
        self.busy = busy
        self.phase = phase
        for widget in [*self.settings_widgets, *self.subject_widgets]:
            widget.configure(state='disabled' if busy else 'normal')
        self.start_button.configure(state='disabled' if busy else 'normal')
        self.export_button.configure(state='normal' if self.has_results and not busy else 'disabled')
        self.stop_button.configure(state='normal' if busy and phase == 'collecting' else 'disabled')
        self.skip_button.configure(state='normal' if busy and phase == 'collecting' else 'disabled')
        if busy:
            self._set_status_pill(phase.capitalize(), 'running')
            if phase in ('loading', 'collecting'):
                self._set_stage('collect')
            elif phase == 'exporting':
                self._set_stage('export')

    def _spawn(self, target):
        self.worker_thread = threading.Thread(target=target, daemon=False)
        self.worker_thread.start()

    def start_scraping(self):
        if self.busy:
            return
        try:
            path = Path(self.path_var.get().strip()).resolve()
            config = RunConfig(
                path,
                tuple(sid for sid, v in self.subject_vars.items() if v.get()),
                tuple(name for name, v in self.field_vars.items() if v.get()),
                self.year_var.get().strip(),
                int(self.timeout_var.get()),
                Path(self.folder_var.get().strip()).resolve()
                if self.folder_var.get().strip()
                else path.parent,
            )
            validate_config(config)
        except ValueError as exc:
            messagebox.showerror('Check your selections', str(exc), parent=self)
            return
        self.persist_preferences()
        self.set_busy(True, 'loading')
        self.status_label.configure(text='Checking your student list…')

        def prepare():
            try:
                book = load_workbook(config.input_path)
                try:
                    store = CheckpointStore.open(book, config)
                    saved = len(store.results())
                    store.close()
                    mismatch = False
                except CheckpointMismatch:
                    saved = 0
                    mismatch = True
                invalid = sum(error is not None for _, _, error in validate_rows(book))
                self.events.put(
                    WorkerEvent('prepared', {
                        'book': book,
                        'config': config,
                        'saved': saved,
                        'mismatch': mismatch,
                        'invalid': invalid,
                    })
                )
            except Exception as exc:
                self.events.put(WorkerEvent('preparation_failed', {'error': str(exc)}))

        self._spawn(prepare)

    def _prepared(self, payload):
        if self.closing:
            self.set_busy(False)
            self.destroy()
            return
        fresh = False
        if payload['mismatch']:
            fresh = messagebox.askyesno(
                'Unfinished collection',
                'Saved progress belongs to another workbook or different selections.\n\n'
                'Discard that progress and start this collection?',
                parent=self,
            )
            if not fresh:
                self.set_busy(False)
                self._set_stage('configure')
                self._set_status_pill('Paused', 'warn')
                self.status_label.configure(text='Saved progress kept.')
                return
        elif payload['saved']:
            answer = messagebox.askyesnocancel(
                'Resume collection',
                f"{payload['saved']} rows are already saved.\n\n"
                'Yes: resume pending students.\n'
                'No: discard these results and start fresh.\n'
                'Cancel: keep progress without starting.',
                parent=self,
            )
            if answer is None:
                self.set_busy(False)
                self._set_stage('configure')
                self._set_status_pill('Paused', 'warn')
                self.status_label.configure(text='Saved progress kept.')
                return
            fresh = not answer

        self.workbook = payload['book']
        self.config = payload['config']
        self.has_results = bool(payload['saved'] and not fresh)
        self.stop_event.clear()
        self.skip_event.clear()

        total = len(self.workbook.frame)
        done = 0 if fresh else payload['saved']
        ratio = (done / total) if total else 0
        self.progress.set(ratio)
        self.percent_label.configure(text=f'{round(ratio * 100)}%')
        self.count_label.configure(text=f'{done} / {total} students')
        if fresh or not done:
            self.completed_val.configure(text='0')
            self.skipped_val.configure(text='0')
            self.failed_val.configure(text='0')

        self.append_log(
            f"Loaded {total} rows. {payload['invalid']} invalid NICs will be marked skipped."
        )
        self.set_busy(True, 'collecting')
        self.status_label.configure(text='Opening the results website…')

        def run():
            try:
                if fresh:
                    checkpoint_path().unlink(missing_ok=True)
                store = CheckpointStore.open(self.workbook, self.config)
                collect(
                    self.config,
                    self.workbook,
                    store,
                    self.events.put,
                    self.stop_event,
                    self.skip_event,
                )
            except Exception as exc:
                self.events.put(WorkerEvent('fatal', {'error': str(exc), 'processed': 0}))

        self._spawn(run)

    def stop_scraping(self):
        self.stop_event.set()
        self._set_status_pill('Stopping', 'warn')
        self.status_label.configure(text='Stopping and keeping saved progress…')
        self.stop_button.configure(state='disabled')
        self.skip_button.configure(state='disabled')

    def skip_current(self):
        self.skip_event.set()

    def start_export(self):
        if self.busy or not self.has_results:
            return
        folder = filedialog.askdirectory(
            title='Export results to this folder', initialdir=str(self.config.output_dir)
        )
        if not folder:
            return
        from dataclasses import replace

        config = replace(self.config, output_dir=Path(folder))
        self.set_busy(True, 'exporting')
        self.status_label.configure(text='Writing your Excel file…')

        def run():
            store = None
            try:
                store = CheckpointStore.open(self.workbook, self.config)
                results = store.results()
                pending = bool(store.pending_positions())
                output = export_results(self.workbook, config, results)
                if not pending:
                    store.discard()
                self.events.put(WorkerEvent('exported', {'path': output, 'pending': pending}))
            except Exception as exc:
                self.events.put(WorkerEvent('export_failed', {'error': str(exc)}))
            finally:
                if store:
                    store.close()

        self._spawn(run)

    def process_events(self):
        for event in self.events.drain():
            p = event.payload
            if event.kind == 'log':
                self.append_log(p['text'])
            elif event.kind == 'prepared':
                self._prepared(p)
            elif event.kind == 'current':
                self.current_label.configure(
                    text=f"Row {p['position'] + 1}  ·  NIC {p['nic'] or '(blank)'}"
                )
                self.status_label.configure(text='Complete CAPTCHA in Chrome.')
            elif event.kind == 'progress':
                self._show_progress(p)
            elif event.kind in ('finished', 'stopped', 'fatal'):
                self.has_results = p.get('processed', 0) > 0
                if 'total' in p:
                    self._show_progress(p)
                self.set_busy(False)
                self._set_stage('export' if self.has_results else 'configure')
                self.current_label.configure(text='No student in progress')
                text = {
                    'finished': 'Collection finished. Export your results.',
                    'stopped': 'Stopped. Resume or export partial results.',
                    'fatal': 'Collection interrupted. Saved progress is kept.',
                }[event.kind]
                pill_map = {
                    'finished': ('Complete', 'success'),
                    'stopped': ('Paused', 'warn'),
                    'fatal': ('Error', 'error'),
                }
                self._set_status_pill(*pill_map[event.kind])
                self.status_label.configure(text=text)
                self.append_log(text)
                if event.kind == 'fatal':
                    self.append_log(p['error'])
                    if not self.closing:
                        messagebox.showerror('Collection interrupted', p['error'], parent=self)
                if self.closing:
                    self.persist_preferences()
                    self.destroy()
                    return
            elif event.kind == 'preparation_failed':
                self.set_busy(False)
                self._set_stage('configure')
                self._set_status_pill('Error', 'error')
                self.status_label.configure(text='Check the student list and try again.')
                if not self.closing:
                    messagebox.showerror('Cannot read student list', p['error'], parent=self)
                else:
                    self.destroy()
                    return
            elif event.kind == 'exported':
                self.last_output = p['path']
                self.has_results = p['pending']
                self.set_busy(False)
                self._set_stage('export' if not p['pending'] else 'configure')
                self._set_status_pill('Exported', 'success')
                self.status_label.configure(
                    text='Excel file saved.'
                    if not p['pending']
                    else 'Partial results saved. You can resume collection.'
                )
                self.append_log(f"Saved to {p['path']}")
                self.open_button.configure(state='normal')
                if self.closing:
                    self.destroy()
                    return
            elif event.kind == 'export_failed':
                self.set_busy(False)
                self._set_stage('export' if self.has_results else 'configure')
                self._set_status_pill('Error', 'error')
                self.status_label.configure(text='Export failed. Progress is still saved.')
                self.append_log(p['error'])
                if not self.closing:
                    messagebox.showerror(
                        'Cannot save Excel file',
                        'Close any locked workbook or choose another output folder, then export again.\n\n'
                        + p['error'],
                        parent=self,
                    )
                else:
                    self.destroy()
                    return
        if self.winfo_exists():
            self._render_log()
            self.after(150, self.process_events)

    def _show_progress(self, p):
        ratio = p['processed'] / p['total'] if p['total'] else 0
        self.progress.set(ratio)
        self.percent_label.configure(text=f'{round(ratio * 100)}%')
        self.count_label.configure(text=f"{p['processed']} / {p['total']} students")
        self.completed_val.configure(text=str(p['completed']))
        self.skipped_val.configure(text=str(p['skipped']))
        self.failed_val.configure(text=str(p['failed']))

    def open_output(self):
        if self.last_output:
            os.startfile(str(self.last_output.parent))

    def on_close(self):
        if self.busy:
            if not messagebox.askyesno(
                'Close collector',
                'Stop collection and close after saving progress?\n'
                'Any export already running will finish first.',
                parent=self,
            ):
                return
            self.closing = True
            self.stop_scraping()
        else:
            self.persist_preferences()
            self.destroy()

    def destroy(self):
        if self._destroyed:
            return
        self._destroyed = True
        # Cancel callbacks before Tcl removes their Python command registrations.
        for callback in self.tk.call('after', 'info'):
            try:
                self.tk.call('after', 'cancel', callback)
            except Exception:
                pass
        super().destroy()


def launch():
    import argparse
    import json
    import sys
    from .instance import InstanceLock

    parser = argparse.ArgumentParser(description='A/L Results Collector')
    parser.add_argument(
        '--smoke-test', action='store_true', help='Open and close the window for distribution verification'
    )
    parser.add_argument('--report', type=Path, help='Write smoke-test diagnostics to this file')
    args = parser.parse_args()
    try:
        with InstanceLock():
            app = ScraperApp()
            if args.smoke_test:
                def finish():
                    if args.report:
                        args.report.write_text(
                            json.dumps(
                                {
                                    'version': __version__,
                                    'subjects': len(load_subjects()),
                                    'frozen': bool(getattr(sys, 'frozen', False)),
                                    'gui': 'opened',
                                },
                                indent=2,
                            ),
                            encoding='utf-8',
                        )
                    app.destroy()

                def finish_after_startup():
                    # CTk.mainloop initializes the Windows titlebar with a nested
                    # event loop. Do not destroy the window from inside that loop.
                    if app._window_exists:
                        app.after(1200, finish)
                    else:
                        app.after(50, finish_after_startup)

                app.after(0, finish_after_startup)
            app.mainloop()
    except RuntimeError as exc:
        root = ctk.CTk()
        root.withdraw()
        messagebox.showerror('Cannot open collector', str(exc), parent=root)
        root.destroy()
