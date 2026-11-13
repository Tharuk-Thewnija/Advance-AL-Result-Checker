# A/L Results Collector

A local Windows desktop tool for tuition teachers and institutes. Choose one
student list, select the subjects and fields you need, complete CAPTCHA in Chrome,
and export the results to a new Excel file.

## Run the application

The Windows bundle is `dist/ALResultsCollector/ALResultsCollector.exe`. Keep its
`_internal` folder beside it. If using an installer, run
`dist/installer/ALResultsCollector-Setup-0.2.1.exe`; it installs for the current user
and adds a Start menu shortcut and uninstaller. Customers do not need Python.

Google Chrome and an internet connection are required. Selenium Manager may need
internet access on first use to obtain a compatible ChromeDriver; it caches the
driver for later use. Chrome updates can require another driver download. The
application does not bypass or solve CAPTCHA.

To run from source, use a virtual environment on Windows (tested with Python 3.15):

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe checker.py
```

## Collect results

1. Choose an `.xlsx` or `.xls` workbook. The **first worksheet** must contain a
   column named **NIC** and one row per student. Store NICs as Excel text to retain
   leading zeros. Existing numeric cells are normalized for lookup; exported input
   values are preserved. Invalid or blank NICs are marked skipped.
2. Search by subject name or code and tick one or more subjects. ICT is selected
   initially. Optional fields include name, index number, district/island ranks,
   Z-score and stream. School, district and medium are not offered as output fields.
3. Confirm the exam year. The department's website may offer only its latest year.
4. Choose **Start collection**. For each student, complete CAPTCHA and submit on
   the results website in Chrome. You can skip the current student or stop.
5. Choose **Export results to Excel** and select an output folder. Open the saved
   folder from the application.

Advanced settings contain the output-folder preference and CAPTCHA timeout.
Light, Dark and System appearance modes are available. Appearance, subjects,
fields, year and timeout are remembered locally.

### What is exported

The original first-sheet rows and columns, selected subject grades, selected
optional fields, Scrape Status and Scrape Notes. Other sheets, workbook formatting,
formulas and macros are not preserved; this is a **value-only `.xlsx` export**.
Missing results stay blank; check Scrape Notes. Completed means a result card was
read, not that the student passed or every selected subject was present.

Input files are never overwritten. Output names include a timestamp and unique
suffix. If a generated column name already exists, a distinct Results-prefixed
column is added. Duplicate students remain separate rows, matching the input.

## Stop and resume

Each processed row is committed to a local SQLite checkpoint before the progress
counter advances. After interruption, select the same unchanged workbook with
the same subjects, fields, year and timeout, then choose Resume. Saved completed,
skipped and error rows are retained; only pending rows are collected. Start Fresh
discards those saved results and recollects all rows.

Only one unfinished collection and one application window are supported. Selecting
another workbook or different settings asks before discarding unfinished progress.
Changing an input file prevents accidental reuse of its old results. Exporting
partial results keeps the checkpoint so the rest can still be collected. A final
successful export removes the checkpoint. If export fails, choose another folder
and try again; progress remains saved.

Application data lives under `%LOCALAPPDATA%\ALResultsCollector`. It is separate
from the installation folder and is retained on uninstall. Checkpoints contain
input fingerprints, selections, row status and selected results, not a copy of the
whole input workbook. Student NICs are entered only into the department's results
website for lookups; there is no application server or analytics upload. Student
files and results should not be committed to this repository.

## Subject catalogue

The bundled catalogue has 63 result options: the department's subject-number list,
cross-checked with its 2025 subject-performance tables, plus the Common General Test.
Source URLs, catalogue version and verification date are recorded in
[`al_results/data/subjects.json`](al_results/data/subjects.json).

- [Official subject numbers](https://doenets.lk/documents/news-headlines/Common_Documentor3languages_Subject_List.pdf)
- [2025 performance report, Tables 14–15](https://www.doenets.lk/images/resources/STAT/2025ALPOCFinal%20%20EDIT_1775557559480.pdf)

Future exam years and website label variants may require catalogue updates.
Explicit aliases distinguish Mathematics from Combined Mathematics, English from
General English, and individual history/drama options. Report an unrecognised
label with an anonymized example; do not post student NICs or real results.

## Development and verification

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q checker.py al_results
```

Browser tests require Chrome and use local HTML; no student IDs are sent to the
department. UI tests create temporary synthetic workbooks and briefly construct
Tk windows. Tests cover selected-only export, column collisions, disk/export
failures, stop/resume, 1,000 synthetic rows and bounded UI buffers. The synthetic
collector benchmark excludes real browser, network and CAPTCHA time; it is not
a real-world collection-speed promise.

Run `python examples/create_sample.py` from an empty directory for a sample list.
Its NIC placeholders are intentionally invalid. Replace them before collecting.

## Build on Windows

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm packaging/checker.spec
& 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe' packaging/installer.iss
```

The spec bundles CustomTkinter assets, the subject catalogue, Selenium Manager,
and Excel readers. It excludes local student workbooks and application data.
Inno Setup 6.7.4 was used for the installer recipe. Adapt the compiler path to your
installation. Builds target 64-bit Windows; no administrator privileges are
required by this application's installer.

For a bundle startup check:

```powershell
.\dist\ALResultsCollector\ALResultsCollector.exe --smoke-test --report smoke-report.json
```

Before public release, test installation, collection and uninstall on a clean
Windows machine without Python. This development machine cannot establish that
clean-machine compatibility. Website/form-only verification also does not replace
a real student collection test with the owner completing CAPTCHA.

## Contributing and licence

Keep `checker.py` as the launcher. Parsing, subject data, Excel I/O, recovery,
browser collection and the UI live in focused modules under `al_results/`.
Use synthetic fixtures, run the suite, and describe behavior and validation in
contributions. `Legacy/` is a historical copy and is not the application entry point.

The project is intended to be open source. The maintainer still needs to select
and add a licence before a public release; none has been chosen automatically.
