# Connected Qt Quick preview

The Qt interface now uses the existing Excel import, Selenium collector, parsing,
SQLite checkpoints and atomic Excel exporter. The original `checker.py` app and
the rendering-only `prototypes/qt_quick/` version remain unchanged.

## Start

Double-click `qt_app/run_qt.cmd`, or run from the project root:

```powershell
.\qt_app\run_qt.cmd
```

The launcher uses the already installed, isolated prototype environment. On another
checkout, create it and install the connected preview dependencies:

```powershell
py -m venv prototypes/qt_quick/.venv
.\prototypes\qt_quick\.venv\Scripts\python.exe -m pip install -r qt_app/requirements.txt
.\prototypes\qt_quick\.venv\Scripts\python.exe checker_qt.py
```

Chrome must be installed. Selenium Manager handles its driver as in the current app.
To compare interfaces, continue launching the current app with `py checker.py`.
The existing packaging/installer still builds the current app, not this preview.

## Offline 1,500-student test

Double-click **`run_mock_test.cmd`** in this folder. It opens the same interface
with a generated fictional workbook already selected. Click **Start mock collection**.
No browser is opened, no website requests are made, and no CAPTCHA is needed.
The MOCK TEST window title, badge and footer stay visible throughout the session.
The generated identifiers cannot pass the real collector's NIC validation.

Try resizing, maximizing and minimizing while it runs. Then try Stop & save,
Export to Excel, Start mock collection → Resume, and a final export. The normal
simulation intentionally takes roughly two minutes, depending on the machine and
disk. It includes varied delays and occasional slower students. Your existing real
workbooks, preferences and checkpoints are separate from the mock workspace.

Without manually skipping rows, the default dataset produces:

| Outcome | Rows |
| --- | ---: |
| Completed | 1,455 |
| Intentionally invalid/skipped | 30 |
| Simulated timeout errors | 15 |
| Total | 1,500 |

64 completed rows omit the first selected subject's result, with an explanatory
note. Other rows contain varied grades, including absent grades; the Common General
Test uses numeric marks. Missing results stay blank in Excel. Manual skips change
these expected totals. All rows remain in the export in their original order.

Inputs, saved progress, exports and performance reports are under:

```text
%LOCALAPPDATA%\ALResultsCollectorQtMock\ALResultsCollector\
    inputs\mock-students-1500.xlsx
    current.sqlite3
    exports\
    reports\mock-performance-<timestamp>-<id>.json
```

The same generated input is reused byte-for-byte so resume survives closing and
reopening. Start fresh archives the mock checkpoint. Do not edit the generated
workbook while testing. Other dataset sizes can be generated with:

```powershell
.\qt_app\run_mock_test.cmd --mock-rows 5000
```

The footer shows process RAM, CPU and the largest UI event-loop timer interval.
A JSON report is saved when the window closes. RAM peak is sampled every 500 ms;
CPU includes all threads of this process and is normalized across logical CPUs.
The 20 ms heartbeat measures timer delivery, not GPU frame presentation. First-frame
startup and Windows throttling of minimized/background windows can increase its
largest gap. Phase labels are approximate at transitions. Monitoring starts after
QML load; it excludes Python imports and initial mock-file generation.

For a repeatable, accelerated test of the real QML view, stop/resume and exact export
contents, run from the project root:

```powershell
.\prototypes\qt_quick\.venv\Scripts\python.exe -m qt_app.mock_benchmark
```

This creates a fresh workspace under `.superpowers/`, with its own checkpoint,
partial and final exports, and `benchmark-report.json`. It changes window sizes
while collecting and verifies exact outcomes, missing grades, row order and the
unchanged input. Its delays are accelerated to 5% of the manual simulation; elapsed
time is not a prediction of real scraping speed. The mock collector uses real
parsing, SQLite and Excel code, while replacing website interaction entirely.

## Use

1. Choose an `.xlsx` or `.xls` student file. Its first worksheet needs exactly one
   `NIC` header. The source workbook is never edited.
2. Select subjects (search by name, alias or code), optional extra fields, and exam
   year. Advanced settings offers an output folder and CAPTCHA timeout. The default
   output folder is the input workbook's folder.
3. Start collection. Complete CAPTCHA and submit in the Chrome window for each
   valid student. Invalid NICs are marked skipped. This version uses the same
   results website and CAPTCHA flow as the existing collector.
4. Stop & save keeps completed rows. Skip current skips the current student. Starting
   again checks saved progress and offers Resume, Start fresh, or Cancel. Start
   fresh archives the previous Qt checkpoint instead of deleting it.
5. Export to Excel writes a new timestamped file. Partial exports include Pending
   rows. Open folder opens the most recent export's directory. Export failures keep
   progress available for retry. Exports retain the checkpoint for repeat exports
   and recovery; a later different class prompts you to archive that checkpoint.

Workbook import, browser collection and export run on worker threads. The UI freezes
run settings during operations and drains bounded progress/log messages. Closing
during collection requests a stop and waits for browser/checkpoint cleanup. Closing
during import/export waits for that operation; keep the window open until it closes
itself. Browser startup/navigation can take time to respond to stop.

Changing subjects or workbook after a run configures the next collection; exporting
still uses the captured workbook and selections from the completed/paused run.
The output folder may be changed before another export.

## Independent saved data

The launcher scopes LOCALAPPDATA **within the Qt process only**, resulting in:

```text
%LOCALAPPDATA%\ALResultsCollectorQt\ALResultsCollector\
    current.sqlite3
    archived-<timestamp>-<id>.sqlite3
    preferences.json
    collector.lock
```

The current app continues using `%LOCALAPPDATA%\ALResultsCollector\`. Qt cannot
resume its checkpoint or replace its preferences. Separate instance locks allow
both interfaces to be open for comparison. Keep actual collection in one interface
at a time to avoid duplicate lookups. Checkpoints/archives contain student results;
keep these files private. There is no application server or analytics upload.

## Verification

From the project root:

```powershell
.\prototypes\qt_quick\.venv\Scripts\python.exe -m unittest discover -s qt_app/tests -v
py -m unittest discover -s tests -v
.\prototypes\qt_quick\.venv\Scripts\python.exe checker_qt.py --smoke-test
```

Qt tests use real workbook/SQLite/export code and replace only the external browser
with synthetic result cards. They cover selected-field export, unchanged input,
partial resume, mismatch cancellation, archive/restart, export retry, skip, frozen
settings, close during loading/collection/export, separate storage and 1,001 rows.
QML tests load the actual view and exercise settings/search/checkbox bindings.

Before replacing the current app, manually test a small real student list with your
own CAPTCHA input, confirm grades/fields against the website, stop/resume and export.
Live student lookups are not part of automated verification. The Qt preview has not
yet been packaged or tested on a clean Windows installation.
