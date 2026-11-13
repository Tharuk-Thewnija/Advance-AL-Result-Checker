# Qt collection integration implementation plan

> Execute directly in this session using executing-plans and test-driven-development.

Goal: use the existing scraper and Excel handling from the approved Qt interface.
Architecture: separate Qt launcher/package, existing backend, QThread tasks with
bounded events, separate process-local app-data namespace.
Tech stack: Python, PySide6/Qt Quick, Selenium, pandas, openpyxl, SQLite.
Spec: ../specs/2026-11-13-qt-integration-design.md

## Constraints and review focus

Preserve existing app and prototype sources. Keep student data local. Do not run
live student lookups in verification. Test cancel/mismatch, stop/close during work,
export errors/retry, input edits after a run and 1,000+ rows.

## Task 1: worker and Qt controller

- [x] Add failing integration tests in qt_app/tests/test_workflow.py for selected-only
      exports, partial resume, mismatch cancellation, validation, safe closing and
      export retry. Use temporary workbook/storage and replace only BrowserSession.
- [x] Add qt_app/backend.py, workers.py, storage.py and isolated launcher. Keep
      workbook/config owned by each run; allow one worker at a time. QThread returns
      prepared/exported events; collector feeds bounded EventBuffer.
- [x] Run the workflow tests and verify independent app-data paths.

## Task 2: connected QML and launch

- [x] Copy prototype QML into qt_app/qml, preserving originals. Bind real field/year/
      timeout/folder settings, progress/errors, Start/Stop/Skip/Export/Open Folder.
- [x] Add resume/archive/cancel dialog and safe window-closing handling.
- [x] Load QML, test bindings and inspect the running screen.

## Task 3: verification and handoff

- [x] Run original unittest suite and Qt workflow suite, compile new sources.
- [x] Verify original and prototype hashes unchanged. Document independent launch,
      checkpoints and remaining manual CAPTCHA/real collection test.
- [x] Leave changes uncommitted for comparison/review with user's existing changes.


## Verification record

- Original application: all 52 unittest tests passed; 16 source/config/catalogue
  files and 16 baseline copies match the saved SHA-256 manifest.
- Qt integration: all 13 tests passed, including real QML bindings/scrolling,
  1,001 rows, partial resume, failed export retry, isolation and safe shutdown.
- Launcher smoke check: Direct3D11, 63 subjects, successful exit with no QML warnings.
- Manual UI: used three invalid synthetic NIC placeholders in isolated test app-data;
  all skipped without a browser, Excel export verified, resume dialog inspected and
  cancelled, then window closed normally. No live student lookups performed.
- Independent review: no Critical/Important findings; setup guide added to resolve
  the one Minor finding. Final batching/scrolling changes reviewed without findings.
- Ruling: keep changes uncommitted and use this checkout — existing user changes
  and comparison prototype must remain available in place.
- Ruling: keep checkpoints after export, archive on explicit Start fresh — preserves
  re-export/recovery and makes restart reversible. Documented in the Qt guide.
- Remaining acceptance: user completes a small real collection with CAPTCHA,
  verifies grades and export, and exercises stop/resume before replacing the old UI.
