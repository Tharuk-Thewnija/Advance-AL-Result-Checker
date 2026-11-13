# A/L Results Collector

A local Windows desktop tool for tuition teachers and institutes. Upload one class
workbook, choose the subjects and fields you need, complete CAPTCHA in Chrome, and
export a new Excel file. The main interface now uses Python and Qt Quick (PySide6).

## Run

- Installer: `dist/installer/ALResultsCollector-Setup-0.3.0.exe`.
- Portable: extract `dist/ALResultsCollector-0.3.0-portable.zip` and open
  `ALResultsCollector/ALResultsCollector.exe`. Keep `_internal` beside the EXE.
- Source: double-click `run.cmd` after the setup below.

The installer runs for the current Windows user and adds a Start menu shortcut and
uninstaller. Python is bundled. Chrome and an internet connection are needed for
real collection. Selenium Manager obtains a compatible ChromeDriver when needed.
The application does not solve or bypass CAPTCHA.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe checker.py
```

Tested on 64-bit Windows with Python 3.15 and PySide6 Essentials 6.12.0.
The retired Tkinter UI and comparison prototype are recoverable from Git tag
`backup/pre-qt-main-2026-11-13` (commit `136e7ae`). They are not runtime dependencies.

## Collect a class

1. Choose an `.xlsx` or `.xls` workbook. The first worksheet needs exactly one
   `NIC` column. Store NICs as Excel text to preserve leading zeros. Invalid or
   blank NICs are marked skipped; duplicate students remain separate rows.
   **NIC is the only required column.** A one-column sheet is enough. Names, class
   labels and other columns are optional and are retained in the export.
2. Search and select subjects by name, alias or code. ICT is selected initially.
   Optional fields are Candidate Name, Index Number, District Rank, Island Rank,
   Z-Score and Subject Stream. Missing results stay blank with an explanatory note.
3. Set the exam year. Advanced settings provides the CAPTCHA timeout and output
   folder; the default is the input workbook's folder. Light/Dark/System themes
   and selections are remembered locally.
4. Start collection. Complete CAPTCHA and submit in Chrome for each student.
   Stop & save keeps processed rows; Skip current skips the current student.
5. Export to Excel, then Open folder. Each export gets a timestamp and unique suffix.

Import, browser collection and export run on worker threads. Closing during an
operation waits for cleanup; browser startup/navigation can take time to stop.
Changing subjects or input after a run configures the next collection. An export
continues to use the captured workbook/selections for the completed or paused run;
the output folder can be changed before exporting again.

Exports preserve the original first-sheet rows and columns, selected grades and
fields, Scrape Status and Scrape Notes. They are **value-only `.xlsx` files**: other
sheets, formatting, formulas and macros are not preserved. The input is never edited.
Completed means a result card was read; it does not mean the student passed or that
every selected subject was present. Conflicting output column names are made unique.

## Saved progress and the UI migration

Each processed row is committed to SQLite before the counter advances. Restart
with the same unchanged workbook and selections to resume pending rows. Completed,
skipped and error rows are retained. Start fresh archives the previous checkpoint;
it does not delete it. Partial and full exports retain the checkpoint for recovery
and repeat exports. Failed exports can be retried without collecting again.

The Qt app continues using its existing directory:

```text
%LOCALAPPDATA%\ALResultsCollectorQt\ALResultsCollector\
    current.sqlite3
    archived-<timestamp>-<id>.sqlite3
    preferences.json
    collector.lock
```

The retired UI's `%LOCALAPPDATA%\ALResultsCollector\` directory is kept unchanged.
Its checkpoint is not automatically imported or overwritten by the Qt app. Before
retiring the UI, consistent local database backups were saved under
`%LOCALAPPDATA%\ALResultsCollectorBackups\pre-qt-main-<timestamp>\`. Student data is
not in Git. The installer upgrades only installed application files; uninstall
retains all checkpoint/preferences directories and exported workbooks.

One normal collection window is supported. Student NICs are sent only to the
examination website for requested lookups. There is no application server or
analytics upload. Keep workbooks, checkpoints and archives private.

## Offline performance test

From source, double-click `qt_app/run_mock_test.cmd`, or run:

```powershell
.\.venv\Scripts\python.exe checker.py --mock
```

The portable EXE also accepts `--mock`. It loads 1,500 fictional students and runs
without a browser or website requests. The generated identifiers fail real NIC
validation. Try resizing/minimizing, stopping, partial export, resuming and final
export. The default simulation takes roughly two minutes, depending on the machine.

Without manual skips, expect 1,455 completed rows, 30 deliberate skips and 15
simulated timeout errors. 64 completed rows omit the first selected subject with a
note. All 1,500 rows remain in the final export. Errors in this mode are intentional.

Mock inputs, checkpoints, exports and performance reports are separate:
`%LOCALAPPDATA%\ALResultsCollectorQtMock\ALResultsCollector\`.
The footer shows sampled RAM, CPU and the largest UI timer interval. A JSON report
is saved under `reports` on close. Startup/background throttling can increase the
largest interval; it is not GPU frame time. This does not measure live scraping,
Chrome memory, network or CAPTCHA overhead. Use `--mock-rows 5000` for a larger file.

## Development and builds

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q checker.py al_results qt_app
powershell -ExecutionPolicy Bypass -File packaging/build.ps1
```

The build script uses PyInstaller 6.22.3 and an installed Inno Setup compiler. Pass
`-Iscc 'path\to\ISCC.exe'` if needed, or `-SkipInstaller` for the portable bundle.
It bundles QML, the Qt runtime/plugins, subject catalogue, Selenium Manager and
third-party notices. It excludes Tkinter, tests and local student files. See
`packaging/THIRD_PARTY_NOTICES.md` and the installed licence files.

Smoke-check a bundle and write a JSON report:

```powershell
.\dist\ALResultsCollector\ALResultsCollector.exe --smoke-test --report startup-report.json
.\dist\ALResultsCollector\ALResultsCollector.exe --verify-mock --report mock-release-report.json
```

The offline release check uses a fresh workspace next to its report, tests the real
view through stop/export/resume, and verifies exact 1,500-row exports. It sends no
student data. Its shortened delays are not a prediction of live collection speed.
Install and verify on a separate Windows computer without Python before public
release. The binaries are unsigned; this development machine cannot establish
clean-machine compatibility or sign them without a code-signing certificate.

## Subject catalogue and contributing

The catalogue has 63 result options. Version, verification date and official sources
are recorded in `al_results/data/subjects.json`. Future years and website label
changes may require updates. Report unrecognised labels with anonymized examples.

Keep browser/parsing/Excel/checkpoint code under `al_results/`, and Qt UI/controller
code under `qt_app/`. Use synthetic fixtures and run the complete test suite.
Do not commit student workbooks, results or application data. The project is intended
to be open source; the maintainer still needs to choose a source licence before
public release. No project licence has been chosen automatically.
