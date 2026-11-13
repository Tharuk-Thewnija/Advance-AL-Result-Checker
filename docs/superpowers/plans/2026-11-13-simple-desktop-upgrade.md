# Simple Desktop Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Deliver a simple, recoverable, installable A/L results collector for one Excel file at a time.

**Architecture:** Retain Python, CustomTkinter and Selenium, with checker.py as a thin entry point. Separate parsing, Excel I/O, checkpoint storage, browser collection and the GUI. Use one worker and one browser; SQLite records progress locally, with Excel written only on export.

**Tech Stack:** Python, CustomTkinter, Selenium, pandas, openpyxl, xlrd, SQLite (standard library), unittest, PyInstaller and Inno Setup.

**Spec:** `docs/superpowers/specs/2026-11-13-simple-desktop-upgrade.md`

## Global Constraints

- One file and one active run at a time.
- Keep the existing NIC-based input workflow and first-sheet behavior in this release.
- Never overwrite the input workbook.
- CAPTCHA stays manual.
- Cap visible logs at 500 entries.
- No accounts, class management, dashboards, multi-file queues, or central server.
- Do not silently choose an open source licence for the maintainer.

## Review Focus

- Numeric, blank and invalid NIC cells must retain their original exported values and get an honest row status (Task 3).
- A changed input with the same filename must not reuse saved results (Task 4).
- Existing user columns named like generated results must survive export (Task 3).
- Browser/network failure or Stop during loading must preserve completed rows and close resources (Task 5).
- A locked export file or unwritable destination must not discard completed results (Tasks 3, 6).

## File boundaries

- `checker.py`: launch and compatibility entry point.
- `al_results/models.py`: frozen RunConfig, InputWorkbook, RowResult and WorkerEvent records.
- `al_results/parsing.py`: text parsing and NIC normalization extracted from checker.py.
- `al_results/subjects.py` and `al_results/data/subjects.json`: sourced catalogue and explicit aliases.
- `al_results/excel_io.py`: first-sheet loading, row validation, safe column allocation and export.
- `al_results/checkpoints.py`: SQLite recovery; no visible history or class model.
- `al_results/collector.py`: browser form, CAPTCHA polling and collection worker.
- `al_results/ui.py` and `al_results/settings.py`: window, bounded messages and persisted preferences.
- `tests/`: unittest tests and synthetic fixtures. Browser tests use local HTML rather than real student data.
- `requirements.txt`, `requirements-dev.txt`, `packaging/checker.spec`, `packaging/installer.iss`, `README.md`: reproducible setup and distribution.

## Task 1: Extract the working core without changing behavior

**Files:** checker.py, al_results/__init__.py, models.py, parsing.py, collector.py, ui.py, tests/test_parsing.py, tests/test_form.py, requirements*.txt.

**Interfaces:** Define frozen `RunConfig(input_path: Path, subject_ids: tuple[str, ...], fields: tuple[str, ...], exam_year: str, captcha_timeout: int, output_dir: Path)`. Define `InputWorkbook(path: Path, content_hash: str, sheet_name: str, frame: pd.DataFrame)`, `RowResult(position: int, status: str, values: dict[str, str | None], note: str)` and `WorkerEvent(kind: str, payload: dict)`. Statuses are Completed, Skipped and Error. Extract current parsing functions and `open_search_form(driver, exam_year)` first; retain compatibility exports until callers migrate.

- [x] Write characterization tests with synthetic result cards: split subject/grade lines, absent ranks, valid/invalid NICs. Assert literal grades and metadata, not generated expectations.
- [x] Restore form regression coverage (previous test_checker.py is absent from the current working tree): original/rescrutiny labels and delayed exam/year loading using local HTML in headless Chrome. Run `py -m unittest discover -s tests -v` and establish the baseline.
- [x] Move functions/classes without changing their behavior; keep `py checker.py` launching the same window. Introduce the new records for later tasks without wiring new features yet. Record tested Python/dependency versions in requirements; verify their Windows compatibility rather than guessing version floors.
- [x] Run the whole suite, `py -m compileall checker.py al_results`, and launch/close the GUI. Ensure importing parsing does not construct a window.
- [x] Review the diff and commit only Task 1 files; do not stage unrelated user files or Legacy/ content.

## Task 2: Multiple subjects and explicit output selection

**Files:** subjects.py, data/subjects.json, parsing.py, tests/test_subjects.py, tests/test_parsing.py.

**Interfaces:** `Subject(id: str, name: str, code: str | None, aliases: tuple[str, ...])`; `load_subjects() -> tuple[Subject, ...]`; `search_subjects(query: str) -> tuple[Subject, ...]`; `parse_results(text: str, subject_ids: tuple[str, ...], fields: tuple[str, ...]) -> dict[str, str | None]`. Subject result keys are `subject:<id>`; field keys use the spec's display labels. Exclude unselected values from the returned map.

- [x] Write failing tests: selecting ICT returns ICT's grade and no Mathematics result; selecting both returns both; selecting only District Rank excludes Name; absent ICT yields None; similar subject names do not cross-match. Search matches subject name/code without changing selections.
- [x] Run the tests and confirm failures reflect the missing multiple-selection behavior.
- [x] Verify current official subject coverage from primary Department of Examinations documents. Record exact source URLs, exam year and verification date in the catalogue; include General English and Common General Test. If official completeness cannot be established, explicitly flag that gap instead of claiming all subjects.
- [x] Implement the catalogue and alias-based matching using existing normalization. Remove substring matching from the new path. Keep extraction of all available subject grades internal, but return only requested values.
- [x] Run all tests and commit the reviewed Task 2 changes.

## Task 3: Safe Excel input and export

**Files:** excel_io.py, tests/test_excel_io.py, tests/fixtures/ (synthetic only).

**Interfaces:** `load_workbook(path: Path) -> InputWorkbook`; `validate_rows(workbook: InputWorkbook) -> list[tuple[int, str, str | None]]` returns original position, normalized NIC and validation error; `export_results(workbook: InputWorkbook, config: RunConfig, results: list[RowResult]) -> Path`. Preserve the original frame separately from normalized IDs. Resolve output labels from the selected subject catalogue.

- [x] Write failing tests for .xlsx/.xls first sheets, missing NIC column, blank/numeric/legacy NIC cells, repeated NICs, original row order, no source overwrite, and selected-only output columns. Assert input values remain unchanged after export.
- [x] Add collision tests: an existing `ICT Result` column survives, generated grades use `Results ICT Result`, and a second collision receives a deterministic numeric suffix. Add an export failure test that leaves the source and saved results intact.
- [x] Run the tests to confirm the new behavior is missing.
- [x] Implement first-sheet reading with required engines, SHA-256 input identity, position-based result merging and export to a unique filename. Write a temporary .xlsx in the output directory, then publish it without overwriting an existing file; clean up only the temporary file owned by this export on failure.
- [x] Run all tests, verify synthetic exports by reopening them, and commit Task 3.

## Task 4: Per-student recovery without a job-management UI

**Files:** checkpoints.py, tests/test_checkpoints.py.

**Interfaces:** `CheckpointStore.open(workbook: InputWorkbook, config: RunConfig) -> CheckpointStore`; `store.matches(workbook, config) -> bool`; `store.save(result: RowResult) -> None`; `store.results() -> list[RowResult]`; `store.pending_positions() -> list[int]`; `store.close() -> None`; `store.discard() -> None`. Use a per-user application-data path and one current checkpoint. Persist source identity and frozen settings, including catalogue version, before collection.

- [x] Write failing tests: save/reopen retains a completed row; pending positions exclude all persisted terminal rows; interruption after a committed row loses no committed result; same filename with changed content/settings/sheet refuses resume; Start Fresh replaces only this app's checkpoint.
- [x] Run the failing tests.
- [x] Implement SQLite transactions per row, unique row positions, deterministic configuration serialization and explicit close/discard. Store selected values and necessary status only. Surface disk-write failures before reporting row completion.
- [x] Run all tests and commit Task 4.

## Task 5: Integrate the recoverable collection worker

**Files:** collector.py, models.py, tests/test_collector.py, tests/test_form.py.

**Interfaces:** `collect(config: RunConfig, workbook: InputWorkbook, store: CheckpointStore, emit: Callable[[WorkerEvent], None], stop_event: threading.Event, skip_event: threading.Event) -> None`. The worker owns its SQLite connection and browser. Event kinds: current, progress, log, stopped, finished, fatal. Progress payload includes total, processed, completed, skipped, failed; stopped/finished occur after cleanup and carry saved-row counts. Excel export remains separate, using stored RowResults.

- [x] Write failing integration tests for pending-only collection, row commit preceding progress, invalid rows, manual-CAPTCHA timeout, skip/stop during form/result waits, navigation failure and database failure. Inject a small browser boundary for external operations; retain real parser/storage and use real local HTML for selector tests.
- [x] Verify tests fail for the missing worker behavior.
- [x] Implement the worker using Tasks 2–4; retain `al` selection and loaded-option waits. Poll cancellation during form loading. Preserve errors/skips with notes, never mark missing subjects as fabricated grades, close browser/storage in finally blocks. Do not automatically submit or solve CAPTCHA.
- [x] Add a 1,000-row synthetic run with a fake external-browser boundary, real parsing and SQLite: assert every row survives reopen, event backlog is bounded at the UI handoff, and Excel export happens only on request. Record memory and I/O timings; do not set a website-throughput target.
- [x] Run all tests, run a live form-only smoke test without student identifiers or CAPTCHA interaction, and commit Task 5.

## Task 6: Simple UI, preferences and Windows release

**Files:** ui.py, settings.py, tests/test_settings.py, tests/test_ui_events.py, packaging/checker.spec, packaging/installer.iss, README.md, .gitignore.

**Interfaces:** `load_preferences() -> dict`; `save_preferences(preferences: dict) -> None`; `launch() -> None`. The UI uses the frozen RunConfig, Task 3 import/export and Task 5 worker; worker events never mutate Tk widgets directly. Keep source workbook and checkpoint identity stable while running.

- [x] Write failing tests for persisted appearance/selections, corrupted-preference fallback, at least one selected subject validation, log truncation at 500 entries, coalesced progress with reliable terminal events, and export failure retaining results for another destination.
- [x] Run tests and confirm the new behavior is absent.
- [x] Build the single-window layout from the spec: file/output folder, searchable subject checkboxes, optional fields, year, appearance, Start, progress, Stop, Skip Current, Export and Open Folder. Keep timeout under Advanced. Display a clear manual CAPTCHA instruction. Use light/dark colour pairs and System appearance.
- [x] Wire Resume/Start Fresh for matching checkpoints, mismatch explanations, partial export after stop, and retrying export to a new location. Discard checkpoints only after successful export. Disable conflicting actions during collection/export; export on a worker to keep the GUI responsive.
- [x] Run all tests and manually verify all themes, small-window scrolling, keyboard access, empty selection, stopping, recovery after force-close, and locked-output behavior. Check with 1,000 synthetic rows. Document actual results and unresolved issues.
- [x] Package a one-folder Windows bundle and Inno Setup installer; document Chrome/driver requirements and separate application data. Development-machine install/start/uninstall checks passed. Clean Windows validation remains an unchecked release gate below.
- [x] Update README with setup, usage, value-only Excel export limitations, recovery behavior, tests/build commands and synthetic examples. Ignore student workbooks, checkpoints, logs and build outputs without deleting existing user files. Ask the maintainer to choose the licence before public release; packaging work can proceed meanwhile.
- [x] Commit reviewed release files. Report installer validation honestly; if no clean Windows environment is available, mark that check outstanding rather than claiming release readiness.

## Final verification and handoff

- [x] Run `py -m unittest discover -s tests -v` and compilation checks after all changes.
- [x] Repeat the ICT-only acceptance flow with a synthetic workbook and local browser fixture, including interruption/resume and partial/final export.
- [x] Review the complete diff against the spec and report remaining external dependencies: official catalogue verification, chosen licence and clean Windows installer verification.

Plan self-review: all approved features have owning tasks; no implementation has begun. Proposed recovery/file-column behavior is documented for review, rather than assumed approved.

## Execution result (2026-11-13)

Six implementation tasks completed directly in this session. One independent final review identified three Important findings; regression fixes and additional grouped-grade checks passed the final 40-test suite. See `docs/superpowers/verification/2026-11-13-desktop-upgrade.md` for evidence, decisions and tradeoffs. No publication or push was performed.

Remaining external release gates:

- [ ] Maintainer selects an open source licence.
- [ ] Validate final installer on a clean Windows machine without Python.
- [ ] Owner validates a real student lookup with manual CAPTCHA and confirms exported grades.
