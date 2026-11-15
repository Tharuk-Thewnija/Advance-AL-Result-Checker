# A/L Results Collector

A local Windows desktop tool for tuition teachers and institutes. Upload one class
workbook, choose the subjects and fields you need, verify CAPTCHA manually or with
optional NoneCAP automation, and
export a new Excel file. The main interface now uses Python and Qt Quick (PySide6).

## Run

- Installer: `dist/installer/ALResultsCollector-Setup-0.4.0.exe`.
- Portable: extract `dist/ALResultsCollector-0.4.0-portable.zip` and open
  `ALResultsCollector/ALResultsCollector.exe`. Keep `_internal` beside the EXE.
- Source: double-click `run.cmd` after the setup below.

The installer defaults to `C:\Program Files\ALResultsCollector` and asks for
administrator approval during installation. The destination page lets you choose
another location. The application itself runs normally without administrator
rights. Checkpoints/preferences remain per-user in AppData; exports go to the
chosen output folder. A Start menu shortcut and uninstaller are included.
Python is bundled. Chrome and an internet connection are needed for
real collection. Selenium Manager obtains a compatible ChromeDriver when needed.
Manual verification is the default and needs no NoneCAP account. Automatic mode
uses your own NoneCAP API key and can spend provider credits.

**Upgrading from an older AppData installation:** export any results you need,
close the app and uninstall the older per-user installation first, then install
this build. Uninstall preserves saved progress, preferences and exported files.
Double-click setup normally and approve its Windows prompt; the app does not need
to be configured to always run as administrator.

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
4. Choose Manual or Automatic verification. In Manual mode, complete CAPTCHA and
   submit in Chrome. In Automatic mode, enter your NoneCAP API key, choose 1–5
   parallel browsers and set the session limits. Leave CAPTCHA untouched unless
   prompted for manual help. Stop & save keeps processed rows; Skip targets the
   current student or selected worker.
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

## NoneCAP automation and credit costs

**Observed cost: one NIC lookup / one complete CAPTCHA solve used 12 NoneCAP
credits in the maintainer's November 2026 live tests.** For planning, 5 NICs at
that observed rate would use about 60 credits. This is a test observation, not a
fixed price or guarantee. It is not 12 credits per image or per challenge round:
one solve can contain multiple rounds, and provider charges can vary. Check your
dashboard and [NoneCAP's pricing](https://nonecap.com/pricing/) before large runs.

- **Parallel browsers (1–5):** each worker owns its Chrome session. The free API
  trial currently allows five jobs in flight per account, shared across keys and
  other clients. More workers improve batch throughput only when the provider and
  examination site can serve them. Browser startup is serialized to protect the
  driver cache; solving then overlaps.
- **Solve attempts:** the maximum number of automatic solve requests across the
  entire app window. Free and failed attempts count too. This does not set the
  number of hCaptcha image rounds or retries per student. No paid solve is silently
  retried.
- **Pause at (credits):** new solves pause once confirmed session spending reaches
  this amount. **It is a soft threshold: all already active solves can finish above
  it.** A dedicated provider-side key cap offers stronger spending control.
- **This window:** used/allowed counters carry over across workers, Stop/Resume
  and additional workbooks. Changing the worker count does not raise the limits.
  Closing resets the app's local counters, not the provider's balance or charges.

Unknown billing pauses automatic work and keeps the student pending. The app
rechecks the same job once if its final charge is missing; this is a read-only
receipt lookup, not a new paid solve. Raising the spending limit does not clear
an unconfirmed charge. Check the provider history before restarting after an
uncertain request. Stop/Skip/closing request cancellation of pending jobs, but a
solve can finish before cancellation and still incur a charge.

The masked key stays in memory and is not saved by the app or put in logs,
checkpoints, command-line arguments or exports. The app sends NoneCAP the public
form URL, widget sitekey, optional challenge data and user-agent; it does not send
student NICs, names or workbook contents. Tokens are delivered to the examination
page and are not stored. Account and billing details: [NoneCAP API reference](https://nonecap.com/api-reference/).

To run another class without restarting, export the current results, choose the
next workbook, press Start and choose **Start fresh** if prompted. The previous
checkpoint is archived. The key and session usage remain in the current window;
automatic mode still needs enough allowance. **Stop & save** keeps progress in
the app; **Export to Excel** creates the spreadsheet file.

The isolated comparison launcher remains available under `experiments/nonecap/`.
Its app data stays in `ALResultsCollectorNoneCAPPrototype`; it is not imported into
or overwritten by the normal app. Previous source checkpoints remain in Git tags
`backup/pre-nonecap-main-2026-11-15` and `backup/nonecap-prototype-2026-11-15`.

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
.\dist\ALResultsCollector\ALResultsCollector.exe --verify-browser --report browser-release-report.json
.\dist\ALResultsCollector\ALResultsCollector.exe --verify-nonecap --report nonecap-local-report.json
.\dist\ALResultsCollector\ALResultsCollector.exe --compare-workers --report worker-comparison.json
```

The offline release check uses a fresh workspace next to its report, tests the real
view through stop/export/resume, and verifies exact 1,500-row exports. It sends no
student data. Its shortened delays are not a prediction of live collection speed.
The NoneCAP diagnostic uses two real headless Chrome sessions with local HTML,
simulated service replies, receipt reconciliation and real Excel export. It makes
no paid API calls or examination lookups. The worker comparison uses synthetic
records and simulated latency for all five worker counts.
Install and verify on a separate Windows computer without Python before public
release. The binaries are unsigned; this development machine cannot establish
clean-machine compatibility or sign them without a code-signing certificate.

## Subject catalogue and contributing

The catalogue has 63 result options. Version, verification date and official sources
are recorded in `al_results/data/subjects.json`. Future years and website label
changes may require updates. Report unrecognised labels with anonymized examples.

Keep browser/parsing/Excel/checkpoint code under `al_results/`, and Qt UI/controller
code under `qt_app/`. Use synthetic fixtures and run the complete test suite.
Do not commit student workbooks, results or application data.

## License

This project's original source code is licensed under the [MIT License](LICENSE).
You may use, modify and redistribute it, including commercially, provided you
retain the copyright and licence notice. See the licence for the complete terms
and warranty disclaimer.

Third-party components retain their own licences. In particular, MIT does not
replace Qt/PySide6's licensing requirements. See
[third-party notices](packaging/THIRD_PARTY_NOTICES.md) and the licence files
included with the application.
