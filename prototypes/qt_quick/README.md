# Qt Quick performance prototype

Standalone PySide6 / Qt Quick version of the existing Obsidian Bento design.
The original app still starts with `py checker.py` from the project root.
Nothing in the working app or its dependency files was changed for this prototype.

## Launch

Double-click `run_prototype.cmd`, or run from the project root:

```powershell
.\prototypes\qt_quick\run_prototype.cmd
```

The isolated `.venv` is already installed on this machine. To recreate it:

```powershell
py -m venv prototypes/qt_quick/.venv
.\prototypes\qt_quick\.venv\Scripts\python.exe -m pip install -r prototypes/qt_quick/requirements.txt
```

## What to try

- Resize, maximize, minimize and restore the window, including during the demo.
- Switch System / Light / Dark themes.
- Search the existing 63-entry catalogue by name, alias (`ICT`) or code (`20`). Selections survive filtering. The list creates delegates as needed rather than creating every checkbox up front.
- Run the synthetic 1,000-student demo, pause/resume, and skip a student.

This is a UI and rendering experiment. The workbook picker only displays a path;
it does not read the file. Field selections, exam year and advanced settings are
visual previews. There is no website access, CAPTCHA, real collection, checkpoint
save or Excel export. The export button explains this in the activity feed.
Themes and selections are held in memory for this session only.

## Comparison on this machine

Measured 2026-11-13, Windows, Python 3.15, Qt/PySide6 6.12.0, Tk 9.0.4,
Legion 24-10 screen at device pixel ratio 1.0. Qt reported **Direct3D11**.

| Operation | Saved CustomTkinter app | Qt Quick prototype |
| --- | ---: | ---: |
| Maximize / restore samples | 366–622 ms | 11–44 ms |
| Resize, median of 12 steps | 419.62 ms | 9.86 ms |
| Subject filtering, median of 11 queries | 106.29 ms | 4.02 ms |

These are single-run local measurements, not portable guarantees. Both harnesses
use the same window operations, resize dimensions and search queries, with settling
time excluded. Tk measures through `app.update()`; Qt waits for `frameSwapped`
(frame queued for presentation, not the end of the Windows animation). Minimize
measures event processing because a minimized window does not present frames.
The two toolkit endpoints differ, so these are practical responsiveness indicators,
not a precise display-latency comparison. The idle CPU fields include the harness's
1 ms polling loop and should not be used as normal idle CPU measurements.
The demo speed says nothing about scraping or workbook performance.

Raw results are in `benchmark-tk.json` and `benchmark-qt.json`. Reproduce sequentially
from the project root (these commands briefly open and manipulate test windows):

```powershell
py prototypes/qt_quick/benchmark_tk.py --report prototypes/qt_quick/benchmark-tk.json
.\prototypes\qt_quick\.venv\Scripts\python.exe prototypes/qt_quick/main.py --benchmark --report prototypes/qt_quick/benchmark-qt.json
```

Model/theme/demo smoke checks:

```powershell
.\prototypes\qt_quick\.venv\Scripts\python.exe prototypes/qt_quick/main.py --smoke-test --report prototypes/qt_quick/smoke-report.json
```

## Baseline preservation

`baseline_snapshot/` contains copies of the 16 existing source/config/catalogue files
at the start of this experiment; `baseline_manifest.json` records their SHA-256
hashes. The Tk benchmark uses that snapshot, with a temporary app-data directory.
No student workbooks are included. The snapshot and prototype `.venv` are ignored
by Git. The prototype reads the original subject catalogue/search module but does
not import the original UI or collector.

If this feels better in manual use, the next step is connecting the existing Python
collection and Excel code through a worker thread and queued Qt signals. Keep the
working app available until the real collection/resume/export workflow is verified.
