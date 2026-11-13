"""Single-window desktop workflow. All Tk operations stay on the main thread."""
from collections import deque
from datetime import datetime
import os
from pathlib import Path
import threading
from tkinter import filedialog, messagebox
import customtkinter as ctk

from . import __version__
from .checkpoints import CheckpointStore, CheckpointMismatch, checkpoint_path, app_data_dir
from .collector import collect
from .events import EventBuffer
from .excel_io import load_workbook, export_results, validate_rows
from .models import RunConfig, WorkerEvent
from .settings import load_preferences, save_preferences, validate_config
from .subjects import FIELDS, load_subjects, search_subjects
from .widgets import KeyboardButton, KeyboardCheckBox, KeyboardOptionMenu

BG = ('#F2F5FA', '#131B29')
PANEL = ('#FFFFFF', '#1C2739')
INK = ('#172B49', '#E7EEF8')
MUTED = ('#52657D', '#A9B8CD')
LINE = ('#D9E2EF', '#35445D')
ACCENT = ('#2456C6', '#739EFF')
BUTTON = ('#2456C6', '#3564CD')
HOVER = ('#1946A9', '#4778E6')


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
        self.geometry('1120x850')
        self.minsize(980, 720)
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
        self.subject_vars = {s.id: ctk.BooleanVar(value=s.id in self.preferences['subjects']) for s in load_subjects()}
        self.field_vars = {f: ctk.BooleanVar(value=f in self.preferences['fields']) for f in FIELDS}
        self.settings_widgets = []
        self.subject_widgets = []
        self._build_layout()
        self.search_var.trace_add('write', lambda *_: self._render_subjects())
        self._render_subjects()
        self.protocol('WM_DELETE_WINDOW', self.on_close)
        self.after(100, self.process_events)

    def label(self, parent, text, size=14, bold=False, muted=False, **kwargs):
        return ctk.CTkLabel(parent, text=text, text_color=MUTED if muted else INK,
                            font=ctk.CTkFont(family='Segoe UI', size=size, weight='bold' if bold else 'normal'), **kwargs)

    def button(self, parent, text, command, primary=False, **kwargs):
        return KeyboardButton(parent, text=text, command=command, height=36,
                            fg_color=BUTTON if primary else ('#E5ECF7', '#2A3A54'),
                            hover_color=HOVER if primary else ('#D6E1F2', '#3A4C69'),
                            text_color='white' if primary else INK, corner_radius=7, **kwargs)

    def _build_layout(self):
        header = ctk.CTkFrame(self, fg_color='transparent')
        header.grid(row=0, column=0, sticky='ew', padx=26, pady=(22, 16))
        header.grid_columnconfigure(0, weight=1)
        self.label(header, 'A/L Results Collector', 27, True).grid(row=0, column=0, sticky='w')
        self.label(header, 'Your class list. Only the results you need.', muted=True).grid(row=1, column=0, sticky='w', pady=(4, 0))
        self.theme_menu = KeyboardOptionMenu(header, values=['System', 'Light', 'Dark'], variable=self.appearance_var,
                                           command=self.change_appearance, width=112, fg_color=BUTTON, button_color=BUTTON)
        self.theme_menu.grid(row=0, column=1, rowspan=2, sticky='e')
        body = ctk.CTkFrame(self, fg_color='transparent')
        body.grid(row=1, column=0, sticky='nsew', padx=26, pady=(0, 14))
        body.grid_columnconfigure(0, weight=3, minsize=460)
        body.grid_columnconfigure(1, weight=2, minsize=350)
        body.grid_rowconfigure(0, weight=1)
        setup = ctk.CTkScrollableFrame(body, fg_color=PANEL, corner_radius=10, border_width=1, border_color=LINE)
        setup.grid(row=0, column=0, sticky='nsew', padx=(0, 16))
        setup.grid_columnconfigure(0, weight=1)
        self.label(setup, 'Collect results', 19, True).grid(row=0, column=0, sticky='w', padx=14, pady=(14, 14))
        self.label(setup, 'Student list', bold=True).grid(row=1, column=0, sticky='w', padx=14)
        file_row = ctk.CTkFrame(setup, fg_color='transparent')
        file_row.grid(row=2, column=0, sticky='ew', padx=14, pady=(6, 4)); file_row.grid_columnconfigure(0, weight=1)
        entry = ctk.CTkEntry(file_row, textvariable=self.path_var, placeholder_text='Choose an Excel file', height=36)
        entry.grid(row=0, column=0, sticky='ew', padx=(0, 8))
        browse = self.button(file_row, 'Browse', self.browse_file, width=84)
        browse.grid(row=0, column=1)
        self.settings_widgets.extend([entry, browse])
        self.label(setup, "Use the first sheet, with a column named NIC.", 12, muted=True).grid(row=3, column=0, sticky='w', padx=14)
        subject_header = ctk.CTkFrame(setup, fg_color='transparent')
        subject_header.grid(row=4, column=0, sticky='ew', padx=14, pady=(18, 7)); subject_header.grid_columnconfigure(0, weight=1)
        self.label(subject_header, 'Subjects', bold=True).grid(row=0, column=0, sticky='w')
        self.selection_label = self.label(subject_header, '', 12, muted=True)
        self.selection_label.grid(row=0, column=1)
        clear = self.button(subject_header, 'Clear', self.clear_subjects, width=54)
        clear.grid(row=0, column=2, padx=(10, 0)); self.settings_widgets.append(clear)
        search_row = ctk.CTkFrame(setup, fg_color='transparent')
        search_row.grid(row=5, column=0, sticky='ew', padx=14, pady=(0, 8))
        search_row.grid_columnconfigure(0, weight=1)
        self.label(search_row, 'Search by subject name or code', 12, muted=True).grid(row=0, column=0, sticky='w', pady=(0, 4))
        self.search_entry = ctk.CTkEntry(search_row, textvariable=self.search_var, height=34)
        self.search_entry.grid(row=1, column=0, sticky='ew')
        self.settings_widgets.append(self.search_entry)
        self.subject_list = ctk.CTkScrollableFrame(setup, height=210, fg_color=BG, corner_radius=7)
        self.subject_list.grid(row=6, column=0, sticky='ew', padx=14)
        self.subject_list.grid_columnconfigure(0, weight=1)
        self.label(setup, 'Include extra fields', bold=True).grid(row=7, column=0, sticky='w', padx=14, pady=(18, 8))
        fields = ctk.CTkFrame(setup, fg_color='transparent')
        fields.grid(row=8, column=0, sticky='ew', padx=14)
        fields.grid_columnconfigure((0, 1), weight=1)
        for i, (name, variable) in enumerate(self.field_vars.items()):
            widget = KeyboardCheckBox(fields, text=name, variable=variable, text_color=INK, font=('Segoe UI', 12),
                                     checkbox_width=19, checkbox_height=19, fg_color=BUTTON, hover_color=HOVER)
            widget.grid(row=i // 2, column=i % 2, sticky='w', pady=5, padx=(0, 8))
            self.settings_widgets.append(widget)
        options = ctk.CTkFrame(setup, fg_color='transparent')
        options.grid(row=9, column=0, sticky='ew', padx=14, pady=(18, 0)); options.grid_columnconfigure(1, weight=1)
        self.label(options, 'Exam year').grid(row=0, column=0, sticky='w', padx=(0, 14))
        year = ctk.CTkEntry(options, textvariable=self.year_var, width=100)
        year.grid(row=0, column=1, sticky='w'); self.settings_widgets.append(year)
        self.advanced_button = self.button(setup, 'Advanced settings', self.toggle_advanced, width=150)
        self.advanced_button.grid(row=10, column=0, sticky='w', padx=14, pady=14)
        self.advanced = ctk.CTkFrame(setup, fg_color='transparent')
        self.advanced.grid_columnconfigure(0, weight=1)
        self.label(self.advanced, 'Output folder (defaults to the input folder)', 12).grid(row=0, column=0, sticky='w')
        folder_entry = ctk.CTkEntry(self.advanced, textvariable=self.folder_var, placeholder_text='Same folder as the student list')
        folder_entry.grid(row=1, column=0, sticky='ew', pady=6, padx=(0, 8))
        folder_button = self.button(self.advanced, 'Choose', self.browse_folder, width=80)
        folder_button.grid(row=1, column=1)
        self.label(self.advanced, 'CAPTCHA timeout in seconds', 12).grid(row=2, column=0, sticky='w', pady=(7, 3))
        timeout = ctk.CTkEntry(self.advanced, textvariable=self.timeout_var, width=100)
        timeout.grid(row=3, column=0, sticky='w', pady=(0, 14))
        self.settings_widgets.extend([folder_entry, folder_button, timeout])
        right = ctk.CTkFrame(body, fg_color='transparent')
        right.grid(row=0, column=1, sticky='nsew'); right.grid_columnconfigure(0, weight=1); right.grid_rowconfigure(4, weight=1)
        self.label(right, 'Collection progress', 19, True).grid(row=0, column=0, sticky='w', pady=(14, 10))
        self.status_label = self.label(right, 'Ready when you are.', 16, True, anchor='w', justify='left', wraplength=340)
        self.status_label.grid(row=1, column=0, sticky='ew', pady=(0, 10))
        info = ctk.CTkFrame(right, fg_color=PANEL, corner_radius=9, border_width=1, border_color=LINE)
        info.grid(row=2, column=0, sticky='ew'); info.grid_columnconfigure(0, weight=1)
        self.count_label = self.label(info, '0 / 0 students', 22, True)
        self.count_label.grid(row=0, column=0, sticky='w', padx=18, pady=(18, 12))
        self.progress = ctk.CTkProgressBar(info, progress_color=BUTTON, height=9)
        self.progress.set(0); self.progress.grid(row=1, column=0, sticky='ew', padx=18)
        self.summary_label = self.label(info, 'Completed 0   Skipped 0   Errors 0', 12, muted=True)
        self.summary_label.grid(row=2, column=0, sticky='w', padx=18, pady=(10, 8))
        self.current_label = self.label(info, 'No student in progress', 12, muted=True, anchor='w')
        self.current_label.grid(row=3, column=0, sticky='ew', padx=18, pady=(0, 18))
        self.label(right, 'Chrome will open for CAPTCHA. Complete it and\nsubmit on the results website for each student.', 13,
                   muted=True, justify='left', anchor='w').grid(row=3, column=0, sticky='ew', pady=14)
        self.log_box = ctk.CTkTextbox(right, fg_color=PANEL, text_color=INK, font=('Segoe UI', 12), corner_radius=9, wrap='word', state='disabled')
        self.log_box.grid(row=4, column=0, sticky='nsew')
        action_row = ctk.CTkFrame(right, fg_color='transparent')
        action_row.grid(row=5, column=0, sticky='ew', pady=(14, 8)); action_row.grid_columnconfigure((0, 1), weight=1)
        self.stop_button = self.button(action_row, 'Stop & save progress', self.stop_scraping, state='disabled')
        self.stop_button.grid(row=0, column=0, sticky='ew', padx=(0, 5))
        self.skip_button = self.button(action_row, 'Skip current', self.skip_current, state='disabled')
        self.skip_button.grid(row=0, column=1, sticky='ew', padx=(5, 0))
        self.start_button = self.button(right, 'Start collection', self.start_scraping, primary=True)
        self.start_button.grid(row=6, column=0, sticky='ew', pady=(0, 8))
        self.export_button = self.button(right, 'Export results to Excel', self.start_export, state='disabled')
        self.export_button.grid(row=7, column=0, sticky='ew', pady=(0, 8))
        self.open_button = self.button(right, 'Open output folder', self.open_output, state='disabled')
        self.open_button.grid(row=8, column=0, sticky='ew')
        self.label(self, f'v{__version__}  |  Student data stays on this computer, apart from lookups on doenets.lk.', 11,
                   muted=True).grid(row=2, column=0, sticky='w', padx=26, pady=(0, 12))

    def _render_subjects(self):
        import textwrap
        for widget in self.subject_list.winfo_children():
            widget.destroy()
        self.subject_widgets.clear()
        for row, subject in enumerate(search_subjects(self.search_var.get())):
            widget = KeyboardCheckBox(self.subject_list, text=f'{subject.code}  ' + textwrap.fill(subject.name, width=43),
                                     variable=self.subject_vars[subject.id], command=self.update_selection_count,
                                     text_color=INK, fg_color=BUTTON, hover_color=HOVER,
                                     font=('Segoe UI', 13), checkbox_width=20, checkbox_height=20,
                                     state='disabled' if self.busy else 'normal')
            widget.grid(row=row, column=0, sticky='w', padx=8, pady=7)
            self.subject_widgets.append(widget)
        if not self.subject_widgets:
            self.label(self.subject_list, 'No matching subjects.', muted=True).grid(row=0, column=0, pady=14)
        self.subject_list._parent_canvas.yview_moveto(0)
        self.update_selection_count()

    def update_selection_count(self):
        self.selection_label.configure(text=f'{sum(v.get() for v in self.subject_vars.values())} selected')

    def clear_subjects(self):
        for variable in self.subject_vars.values(): variable.set(False)
        self.update_selection_count()

    def toggle_advanced(self):
        if self.advanced.winfo_manager(): self.advanced.grid_remove()
        else: self.advanced.grid(row=11, column=0, sticky='ew', padx=14)

    def browse_file(self):
        path = filedialog.askopenfilename(title='Choose a student list', filetypes=[('Excel workbooks', '*.xlsx *.xls')])
        if path: self.path_var.set(path)

    def browse_folder(self):
        path = filedialog.askdirectory(title='Choose output folder')
        if path: self.folder_var.set(path)

    def change_appearance(self, value):
        ctk.set_appearance_mode(value)
        self.persist_preferences()

    def persist_preferences(self):
        try:
            timeout = int(self.timeout_var.get())
        except ValueError:
            timeout = 180
        try:
            save_preferences({'appearance': self.appearance_var.get(),
                              'subjects': [sid for sid, v in self.subject_vars.items() if v.get()],
                              'fields': [name for name, v in self.field_vars.items() if v.get()],
                              'year': self.year_var.get().strip(), 'timeout': timeout})
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
        self.busy = busy; self.phase = phase
        for widget in [*self.settings_widgets, *self.subject_widgets]:
            widget.configure(state='disabled' if busy else 'normal')
        self.start_button.configure(state='disabled' if busy else 'normal')
        self.export_button.configure(state='normal' if self.has_results and not busy else 'disabled')
        self.stop_button.configure(state='normal' if busy and phase == 'collecting' else 'disabled')
        self.skip_button.configure(state='normal' if busy and phase == 'collecting' else 'disabled')

    def _spawn(self, target):
        self.worker_thread = threading.Thread(target=target, daemon=False)
        self.worker_thread.start()

    def start_scraping(self):
        if self.busy: return
        try:
            path = Path(self.path_var.get().strip()).resolve()
            config = RunConfig(path, tuple(sid for sid, v in self.subject_vars.items() if v.get()),
                               tuple(name for name, v in self.field_vars.items() if v.get()),
                               self.year_var.get().strip(), int(self.timeout_var.get()),
                               Path(self.folder_var.get().strip()).resolve() if self.folder_var.get().strip() else path.parent)
            validate_config(config)
        except ValueError as exc:
            messagebox.showerror('Check your selections', str(exc), parent=self); return
        self.persist_preferences()
        self.set_busy(True, 'loading'); self.status_label.configure(text='Checking your student list…')
        def prepare():
            try:
                book = load_workbook(config.input_path)
                try:
                    store = CheckpointStore.open(book, config)
                    saved = len(store.results()); store.close(); mismatch = False
                except CheckpointMismatch:
                    saved = 0; mismatch = True
                invalid = sum(error is not None for _, _, error in validate_rows(book))
                self.events.put(WorkerEvent('prepared', {'book': book, 'config': config, 'saved': saved,
                                                        'mismatch': mismatch, 'invalid': invalid}))
            except Exception as exc:
                self.events.put(WorkerEvent('preparation_failed', {'error': str(exc)}))
        self._spawn(prepare)

    def _prepared(self, payload):
        if self.closing:
            self.set_busy(False); self.destroy(); return
        fresh = False
        if payload['mismatch']:
            fresh = messagebox.askyesno('Unfinished collection',
                'Saved progress belongs to another workbook or different selections.\n\nDiscard that progress and start this collection?', parent=self)
            if not fresh:
                self.set_busy(False); self.status_label.configure(text='Saved progress kept.'); return
        elif payload['saved']:
            answer = messagebox.askyesnocancel('Resume collection',
                f"{payload['saved']} rows are already saved.\n\nYes: resume pending students.\nNo: discard these results and start fresh.\nCancel: keep progress without starting.", parent=self)
            if answer is None:
                self.set_busy(False); self.status_label.configure(text='Saved progress kept.'); return
            fresh = not answer
        self.workbook = payload['book']; self.config = payload['config']
        self.has_results = bool(payload['saved'] and not fresh)
        self.stop_event.clear(); self.skip_event.clear()
        self.progress.set(0)
        self.count_label.configure(text=f"{0 if fresh else payload['saved']} / {len(self.workbook.frame)} students")
        self.append_log(f"Loaded {len(self.workbook.frame)} rows. {payload['invalid']} invalid NICs will be marked skipped.")
        self.set_busy(True, 'collecting'); self.status_label.configure(text='Opening the results website…')
        def run():
            try:
                if fresh: checkpoint_path().unlink(missing_ok=True)
                store = CheckpointStore.open(self.workbook, self.config)
                collect(self.config, self.workbook, store, self.events.put, self.stop_event, self.skip_event)
            except Exception as exc:
                self.events.put(WorkerEvent('fatal', {'error': str(exc), 'processed': 0}))
        self._spawn(run)

    def stop_scraping(self):
        self.stop_event.set(); self.status_label.configure(text='Stopping and keeping saved progress…')
        self.stop_button.configure(state='disabled'); self.skip_button.configure(state='disabled')

    def skip_current(self):
        self.skip_event.set()

    def start_export(self):
        if self.busy or not self.has_results: return
        folder = filedialog.askdirectory(title='Export results to this folder', initialdir=str(self.config.output_dir))
        if not folder: return
        from dataclasses import replace
        config = replace(self.config, output_dir=Path(folder))
        self.set_busy(True, 'exporting'); self.status_label.configure(text='Writing your Excel file…')
        def run():
            store = None
            try:
                store = CheckpointStore.open(self.workbook, self.config)
                results = store.results()
                pending = bool(store.pending_positions())
                output = export_results(self.workbook, config, results)
                if not pending: store.discard()
                self.events.put(WorkerEvent('exported', {'path': output, 'pending': pending}))
            except Exception as exc:
                self.events.put(WorkerEvent('export_failed', {'error': str(exc)}))
            finally:
                if store: store.close()
        self._spawn(run)

    def process_events(self):
        for event in self.events.drain():
            p = event.payload
            if event.kind == 'log': self.append_log(p['text'])
            elif event.kind == 'prepared': self._prepared(p)
            elif event.kind == 'current':
                self.current_label.configure(text=f"Row {p['position'] + 1}  ·  NIC {p['nic'] or '(blank)'}")
                self.status_label.configure(text='Complete CAPTCHA in Chrome.')
            elif event.kind == 'progress': self._show_progress(p)
            elif event.kind in ('finished', 'stopped', 'fatal'):
                self.has_results = p.get('processed', 0) > 0
                if 'total' in p: self._show_progress(p)
                self.set_busy(False)
                self.current_label.configure(text='No student in progress')
                text = {'finished': 'Collection finished. Export your results.', 'stopped': 'Stopped. Resume or export partial results.',
                        'fatal': 'Collection interrupted. Saved progress is kept.'}[event.kind]
                self.status_label.configure(text=text); self.append_log(text)
                if event.kind == 'fatal':
                    self.append_log(p['error'])
                    if not self.closing: messagebox.showerror('Collection interrupted', p['error'], parent=self)
                if self.closing: self.persist_preferences(); self.destroy(); return
            elif event.kind == 'preparation_failed':
                self.set_busy(False); self.status_label.configure(text='Check the student list and try again.')
                if not self.closing: messagebox.showerror('Cannot read student list', p['error'], parent=self)
                else: self.destroy(); return
            elif event.kind == 'exported':
                self.last_output = p['path']; self.has_results = p['pending']; self.set_busy(False)
                self.status_label.configure(text='Excel file saved.' if not p['pending'] else 'Partial results saved. You can resume collection.')
                self.append_log(f"Saved to {p['path']}")
                self.open_button.configure(state='normal')
                if self.closing: self.destroy(); return
            elif event.kind == 'export_failed':
                self.set_busy(False); self.status_label.configure(text='Export failed. Progress is still saved.')
                self.append_log(p['error'])
                if not self.closing:
                    messagebox.showerror('Cannot save Excel file', 'Close any locked workbook or choose another output folder, then export again.\n\n' + p['error'], parent=self)
                else: self.destroy(); return
        if self.winfo_exists():
            self._render_log()
            self.after(150, self.process_events)

    def _show_progress(self, p):
        self.progress.set(p['processed'] / p['total'] if p['total'] else 0)
        self.count_label.configure(text=f"{p['processed']} / {p['total']} students")
        self.summary_label.configure(text=f"Completed {p['completed']}   Skipped {p['skipped']}   Errors {p['failed']}")

    def open_output(self):
        if self.last_output: os.startfile(str(self.last_output.parent))

    def on_close(self):
        if self.busy:
            if not messagebox.askyesno('Close collector', 'Stop collection and close after saving progress?\nAny export already running will finish first.', parent=self): return
            self.closing = True
            self.stop_scraping()
        else:
            self.persist_preferences(); self.destroy()

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
    parser.add_argument('--smoke-test', action='store_true', help='Open and close the window for distribution verification')
    parser.add_argument('--report', type=Path, help='Write smoke-test diagnostics to this file')
    args = parser.parse_args()
    try:
        with InstanceLock():
            app = ScraperApp()
            if args.smoke_test:
                def finish():
                    if args.report:
                        args.report.write_text(json.dumps({'version': __version__, 'subjects': len(load_subjects()),
                                                         'frozen': bool(getattr(sys, 'frozen', False)), 'gui': 'opened'}, indent=2), encoding='utf-8')
                    app.destroy()
                app.after(1200, finish)
            app.mainloop()
    except RuntimeError as exc:
        root = ctk.CTk(); root.withdraw()
        messagebox.showerror('Cannot open collector', str(exc), parent=root)
        root.destroy()
