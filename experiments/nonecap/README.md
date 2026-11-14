# Isolated NoneCAP prototype

This experimental source-only launcher is on `codex/nonecap-prototype`. The
released app, launchers, installer and checkpoints are unchanged. It reuses the
existing Excel/Qt backend and loads a private collector module without patching
the production collector's globals.

## Run locally

Double-click `experiments\nonecap\run_prototype.cmd`, or run from the project root:

```powershell
.venv\Scripts\python.exe -m experiments.nonecap
```

It uses the existing environment and requirements; no new dependencies.
The title/footer say **NONECAP PROTOTYPE**. Normal `run.cmd` opens the released app.

1. Select a workbook with a `NIC` column, subjects and extra result fields.
2. Leave **Manual** selected for the existing CAPTCHA workflow with no automatic
   service requests.
3. For a small live trial, choose **Automatic**, paste your key locally, and set
   **Maximum solves** to **1**. Start with a copy of a small workbook.
4. Optionally **Check balance**; this reads balance/daily allowance without a
   solve. Entering a key or changing modes makes no API request.
5. Start collection. Automatic mode can spend credits. Complete CAPTCHA manually
   in Chrome on fallback. Stop, resume and export use the existing workflow.

Automatic mode delivers a token to the page; it does not click or visually tick
the CAPTCHA checkbox. Leave the checkbox untouched while the automatic attempt
runs, and intervene only when prompted for manual entry. The activity feed records
the reported charge, session usage, token callback delivery, submission and result
receipt. If the page already held a CAPTCHA response before token delivery, the
log flags possible overlapping browser verification. A token receipt or charge
alone does not establish that the examination site accepted it.

The key is masked and held in memory only. It is not saved to preferences,
checkpoints, logs or command-line arguments. Close the window or use **Clear key**
to remove it from the app. Each launch defaults to Manual with an empty key.
Do not paste a real key into chat, issue reports or screenshots.

## Credit controls

Choose **1** or **2 concurrent browser workers** in Automatic mode. Each worker
owns one Chrome session and its own solver state. The two browser windows are
labelled Worker 1 and Worker 2. Manual mode continues to use a single browser.
Browser startup is serialized to protect Selenium Manager's shared driver cache;
the actual page work and solving overlap once each session is ready.
Stop & save and closing stop both workers; **Skip worker** applies only to the
selected worker. One coordinator writes all completed results to SQLite, and
export keeps the workbook's original row order.

Defaults: **1 worker**, **10-credit stop threshold**, **3 automatic solves**. Counters cover
the entire window, including Stop/Resume, Start fresh, key and mode changes.
Editing limits does not clear counters. Closing resets local counters; these are
not an account-wide budget.

**The credit threshold is soft.** The final charge arrives after a solve finishes;
all in-flight solves can exceed the threshold. Use a dedicated API key with a
provider-side credit cap in the NoneCAP dashboard for stronger control.
The maximum attempt count is a strict local submission limit, including free or
failed attempts. There is at most one solve per worker in flight, and no automatic
paid retries. Counters and admission checks are shared atomically between workers.
**Maximum solves = 1 allows one API job for the whole window**, not one attempt
per student or per worker, and does not control hCaptcha challenge rounds.

Before each solve, the prototype checks limits and balance/daily allowance.
An exhausted budget blocks Start before opening browsers. If a limit is reached
while collecting, new automatic work pauses and unsaved students remain pending;
already admitted jobs finish and their actual charges are recorded. Raise limits
and resume, or explicitly choose Manual. The prototype no longer starts a manual
timeout just because a session limit was reached.

Rejected tokens, unsupported widgets and service errors still disable automatic
mode for this window and hand the same student to manual entry, without a reload
or skip. The log labels the worker needing attention. A manual attempt can time
out normally. After a failure, another Automatic Start is blocked rather than
silently continuing manually. An unconfirmed charge pauses automatic work.

Stop, Skip and closing request cancellation of known pending jobs. HTTP calls
have a five-second timeout, so cancellation may not be immediate. Completion can
race with cancellation and still incur a charge. An unconfirmed charge blocks
further automatic requests for this window. Check the provider dashboard before
restarting after an uncertain request; closing the app does not prove an unknown
server-side job was cancelled. The displayed balance is the last checked balance.

If a terminal job's final charge is absent or invalid, the app reads the same job
once more. This is a receipt lookup, not a paid solve retry. A valid refreshed
receipt allows the existing token to continue. If its charge remains unclear,
the app pauses with a **billing-unconfirmed** warning and leaves the student
pending. Other already admitted jobs can finish. A billing pause is separate from
an exhausted session limit; increasing local limits does not clear it. The log
reports the terminal status when available, without exposing tokens or API keys.

## Isolation and data

The launcher changes `LOCALAPPDATA` inside its own process only. Preferences,
checkpoint and instance lock are under:

```text
%LOCALAPPDATA%\ALResultsCollectorNoneCAPPrototype\ALResultsCollector
```

This is separate from the released app's `ALResultsCollectorQt` directory. Both
apps can run together; use separate export folders for comparisons.
No workbook contents, student names, NICs or cookies are sent to NoneCAP. The key
travels only in the HTTPS Authorization header. The body contains the fixed public
form URL, sitekey, optional challenge `rqdata` and browser user-agent. Tokens and
response keys are used only in the browser, excluded from logs/checkpoints.
Redirects are refused and provider errors are replaced with fixed messages.

## Verification and limits

For a live comparison, use the same small copied workbook for separate one- and
two-worker runs. For two students, choose **2 workers**, **maximum solves 2** and
a deliberate credit threshold (24 matched the observed two 12-credit solves, but
is not a guaranteed price or spending ceiling). Select Start fresh when comparing
already completed rows; saved prototype progress is archived. Raising limits does
not erase usage from earlier runs in the same window. Do not run comparisons in
two prototype windows simultaneously; the instance lock protects saved progress.
The activity feed and CAPTCHA card report wall time and newly saved rows/minute.

NoneCAP documents five concurrent API jobs on its free trial, shared per account
across all keys. This prototype deliberately exposes one or two workers for the
first comparison. Provider capacity does not establish the examination site's
throughput or acceptance limits.

Tests use simulated API replies and a local HTML page in real headless Chrome.
They cover credit guards, ambiguous submissions, cancellation races, same-student
manual fallback, masked Qt input, storage isolation, callbacks and Excel export.
No real key or paid solve was used.

```powershell
.venv\Scripts\python.exe -m unittest discover -s experiments/nonecap/tests -v
.venv\Scripts\python.exe -m experiments.nonecap --smoke-test
.venv\Scripts\python.exe -m experiments.nonecap --compare-workers
.venv\Scripts\python.exe -m unittest discover -s tests -q
```

The offline comparison runs the real collector/checkpoint paths on 12 fictional
rows, replacing browsers/API calls with a 0.25-second simulated solve. It checks
identical saved results and reports peak parallel solves, elapsed time, rows/min
and relative speedup. JSON is saved in the prototype data folder's `reports`
directory, or at `--report <path>`. It spends no credits. Its speedup demonstrates
scheduling overlap only; it does not predict live NoneCAP or Doenets throughput.

Real authentication, billing and examination-site token acceptance still need
your small live trial. A working extension does not establish API compatibility.
Some sites bind tokens to browser sessions or IPs; this prototype has no proxy
integration. Unsupported/multiple widgets or a changed website may need manual
mode. After automatic submission it waits up to 20 seconds for results, then
allows the normal manual CAPTCHA timeout on the same page. This prototype is not
included in the EXE/installer or release.

Sources: [NoneCAP API reference](https://nonecap.com/api-reference/),
[pricing](https://nonecap.com/pricing/).
