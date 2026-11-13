# Desktop upgrade verification — 2026-11-13

Implementation is on `feature/simple-desktop-upgrade`, based on `8b9048d`.
Version: **0.2.0**. This is a local release candidate, not a published release.

## Delivered

- One-file, NIC-based Excel workflow with 63 sourced subject options and optional output fields.
- Single-window interface, searchable checkboxes, keyboard activation and visible focus, Light/Dark/System themes, persisted selections.
- One browser/worker, bounded progress/log buffers, Stop/Skip, per-row SQLite checkpoints and resume.
- Selected-only value exports that preserve source rows, duplicate/blank headers and error values without overwriting input files.
- Unique output files, column-collision handling, partial export and retry after export failure.
- Windows bundle and per-user installer with Start menu shortcut and uninstall support.
- Setup, usage, recovery, contributor and build instructions in README; safe sample generator.

## Evidence

- `py -m unittest discover -s tests -v`: **40 tests passed**, 40.731 seconds in the final run.
- `py -m compileall -q checker.py al_results`: passed.
- `git diff --check`: no whitespace errors.
- Local-HTML Chrome tests: old/new examination labels, delayed dropdown data and cancellation during loading.
- Live form-only check: A/L After Rescrutiny, year 2025 and NIC search selected successfully. No student identifier was entered and no CAPTCHA was solved.
- GUI integration: ICT-only collection/export, stop/partial export/resume, failed export then retry, preferences/themes, Tab/Space navigation and visible actions at 980×720.
- A separate process committed a row and exited without cleanup; reopening retained the result and pending positions.
- 1,000-row synthetic collection: all rows reopened successfully, event backlog at most 503, no automatic Excel export. Final run: 8.80 seconds with tracemalloc, 0.39 MiB peak traced collector allocations. This excludes total process RAM, Chrome, network and human CAPTCHA time.
- Earlier standalone 1,000-row import/export measurement: 0.043 / 0.107 seconds. This preceded the final native-reader fidelity fix, so it is only a development reference, not a final performance guarantee.
- PyInstaller 6.22.3 and Inno Setup 6.7.4 builds succeeded on Windows/Python 3.15.
- Final bundled startup with Python removed from PATH: exit 0; report confirmed version 0.2.0, 63 subjects, frozen executable and opened GUI.
- Final installer install, installed-app startup and uninstall in a temporary development-machine directory: all exit 0.
- Bundled Selenium Manager `--version`: 0.4.52.

Installer: `dist/installer/ALResultsCollector-Setup-0.2.0.exe`

SHA-256: `BAEDA7038973FFDF81A54371BEAC025DC8FA0538B9C50DB4E4BAF2BB03D7E9DA`

## Independent review and fix pass

One read-only reviewer examined the full branch and ran the then-current 33-test suite. No Critical or Minor findings were reported. Three Important findings were reproduced with failing tests, corrected, and verified with the final green suite:

1. Blank optional values consumed following field labels. Field boundaries now prevent fabricated rank/Z-score values and prefix-label matches.
2. pandas import normalized Excel error cells and duplicate/blank headers. Native openpyxl/xlrd readers now retain original values and headers. Duplicate NIC headers are rejected as ambiguous.
3. CustomTkinter checkboxes lacked keyboard activation. Focusable controls now support Tab/Space/Return, show focus, and scroll focused selections into view.

During the fix pass, two more failing fixtures exposed grouped-grade ambiguity. Metadata such as Medium=English no longer participates as a subject, and incomplete grade groups no longer assign the first grade to the last subject. There was no second reviewer dispatch; the fixes were verified by regression tests and the full suite.

## Execution decisions and tradeoffs, in order

1. Use a feature branch in the existing folder because execution was requested in this session. `main` remains available; this working folder displays the feature changes.
2. Keep one current checkpoint and ask before discarding a different unfinished run. This prevents silent replacement, at the cost of a prompt when changing unfinished work.
3. Retry stale dropdown elements during waits. This tolerates website redraws, at the cost of waiting up to the existing timeout when the form is unavailable.
4. Retain checkpoints after partial export until pending rows are collected. This preserves resume, at the cost of keeping local checkpoint data longer.
5. Add a per-user single-instance lock. This protects the checkpoint, at the cost of refusing a second application window.
6. Publish exports with atomic Windows rename. This supports FAT/exFAT output drives without overwriting existing files; Windows remains the supported distribution target.
7. Leave clean-machine validation as a release check because a clean Windows machine/VM was unavailable. Compatibility beyond this development environment remains unestablished.
8. Leave a genuine student CAPTCHA/results run to owner validation. Development sent no student identifiers; unobserved real result-card variants may still require fixtures.
9. Keep the approved value-only export scope. Styling, formulas, macros and additional sheets are not cloned; the original workbook remains intact.

No minor findings were deferred.

## Before public release

- The maintainer must select an open source licence; no licence was chosen automatically.
- Test the final installer and collection workflow on a clean Windows machine without Python.
- Test genuine result collection with the owner completing CAPTCHA and verify the selected grades against the website.
- The generated installer is unsigned. No package has been uploaded, pushed or published by this implementation session.
