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
   **Maximum attempts** to **1**. Start with a copy of a small workbook.
4. Optionally **Check balance**; this reads balance/daily allowance without a
   solve. Entering a key or changing modes makes no API request.
5. Start collection. Automatic mode can spend credits. Complete CAPTCHA manually
   in Chrome on fallback. Stop, resume and export use the existing workflow.

The key is masked and held in memory only. It is not saved to preferences,
checkpoints, logs or command-line arguments. Close the window or use **Clear key**
to remove it from the app. Each launch defaults to Manual with an empty key.
Do not paste a real key into chat, issue reports or screenshots.

## Credit controls

Defaults: **10-credit stop threshold**, **3 automatic attempts**. Counters cover
the entire window, including Stop/Resume, Start fresh, key and mode changes.
Editing limits does not clear counters. Closing resets local counters; these are
not an account-wide budget.

**The credit threshold is soft.** The final charge arrives after a solve finishes;
an in-flight solve can exceed the threshold. Use a dedicated API key with a
provider-side credit cap in the NoneCAP dashboard for stronger control.
The maximum attempt count is a strict local submission limit, including free or
failed attempts. Only one solve runs at a time. There are no automatic paid retries.

Before each solve, the prototype checks limits and balance/daily allowance.
Exhausted limits, rejected tokens, unsupported widgets, service errors or unknown
charges disable automatic mode for this window. The same student is handed to
manual entry without a reload or skip. A manual attempt can still time out normally.

Stop, Skip and closing request cancellation of known pending jobs. HTTP calls
have a five-second timeout, so cancellation may not be immediate. Completion can
race with cancellation and still incur a charge. An unconfirmed charge blocks
further automatic requests for this window. Check the provider dashboard before
restarting after an uncertain request; closing the app does not prove an unknown
server-side job was cancelled. The displayed balance is the last checked balance.

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

Tests use simulated API replies and a local HTML page in real headless Chrome.
They cover credit guards, ambiguous submissions, cancellation races, same-student
manual fallback, masked Qt input, storage isolation, callbacks and Excel export.
No real key or paid solve was used.

```powershell
.venv\Scripts\python.exe -m unittest discover -s experiments/nonecap/tests -v
.venv\Scripts\python.exe -m experiments.nonecap --smoke-test
.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Real authentication, billing and examination-site token acceptance still need
your small live trial. A working extension does not establish API compatibility.
Some sites bind tokens to browser sessions or IPs; this prototype has no proxy
integration. Unsupported/multiple widgets or a changed website may need manual
mode. After automatic submission it waits up to 20 seconds for results, then
allows the normal manual CAPTCHA timeout on the same page. This prototype is not
included in the EXE/installer or release.

Sources: [NoneCAP API reference](https://nonecap.com/api-reference/),
[pricing](https://nonecap.com/pricing/).
