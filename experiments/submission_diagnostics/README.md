# Submission diagnostic experiment

Source-only investigation of the failure seen during the 99-row real collection.
The released app, existing checkpoints, preferences and installer are unchanged.

## API network diagnostics (v2)

For the simultaneous five-worker failure logged at 23:57:26, first run
`run_nonecap_network_diagnostics.cmd` from the project folder. This makes three
unauthenticated GET requests to the fixed NoneCAP account endpoint. **No API key,
student lookup or solve is sent.** HTTP 401 is expected and means the API answered;
it cannot explain an earlier outage or verify an authenticated solve.

To capture a failure during actual collection, run `run_submission_diagnostics.cmd`
and confirm **DIAGNOSTICS v2** appears in its activity log. Enter the key locally
and explicitly start Automatic only when ready to use credits. No solve or POST is
retried automatically. This diagnostic launcher pauses on service errors instead
of starting a manual timeout cascade. Production's other service-error behavior
is not changed by this diagnostic script.

Each `api_request` record identifies `account`, `create`, `poll`, or `cancel`,
row/worker, elapsed time, HTTP status, response byte count and a fixed outcome:
`timeout`, `dns_error`, `tls_error`, `connection_reset`, `connection_refused`,
`network_error`, `invalid_json`, `invalid_shape`, `response_too_large`, `http_error`,
or `ok`. Known provider error codes are allowlisted; unknown strings are discarded.
No headers, URLs, job IDs, exception messages or response bodies are written.
The five-second request timeout matches production; it is not a total DNS-to-body
deadline. No paid request is made by the key-free connectivity script.

Share the generated `.jsonl` and its companion `.manifest.json`. The manifest
records diagnostic version, request timeout and source SHA-256 fingerprints, so
we can verify which source files were in use. Reports are under the separate
diagnostic data folder below; their paths appear in the console/activity log.

These records distinguish where a failure occurred, but a timeout alone cannot
prove whether the cause was the provider, local connection, ISP or firewall.

## Offline checks (no credits)

From the project folder run:

```cmd
run_submission_diagnostics.cmd --offline
```

Uses local HTML in real headless Chrome and fictional students/fake API replies.
Checks that an unknown submission outcome no longer causes a manual-timeout
cascade, checks a delayed result, and verifies that collection pauses with rows pending.
Does not contact NoneCAP or the examination website. Chrome/Selenium Manager may
need its usual driver download if Chrome's matching driver is not cached.

## Live investigation (uses credits only when you start Automatic)

1. Run `run_submission_diagnostics.cmd`. Starts in Manual mode.
2. Choose a small workbook with a **NIC** column heading (for example 10 students).
3. Select the examination year/subjects, Automatic, your API key and 1 worker.
4. Set the attempts/credit limits deliberately. At roughly 12 credits per solve,
   10 attempts could cost roughly 120 credits. These are soft session limits,
   not a provider-side hard spending cap. Active solves can exceed a credit limit.
5. Press Start. Avoid interacting with the CAPTCHA during the automatic run.
6. Export completed results. If needed, compare with 5 workers using a separate
   workbook/checkpoint; do not restart a fresh paid run just to obtain a log.

The key remains in memory. No paid retries or extra submissions are introduced.
This experiment observes submitted results for **60 seconds**, records the
production **20-second cutoff**, and pauses on failure. Already-started
workers may finish; unfinished rows stay pending. Resuming a failed row requests
a new token and can cost credits: review its report first.

Data is separate, under:
`%LOCALAPPDATA%\ALResultsCollectorSubmissionDiagnostics\ALResultsCollector`.
Checkpoints/Excel exports contain student data, just like the main app. **Only the
`reports\submission-*.jsonl` diagnostic file is intended for sharing.** Its path is
shown in the activity log. Do not share the database, workbook or full page.

Reports contain row numbers, elapsed timings, token-application booleans,
visible-result state, fixed message classifications and aggregate HTTP status
counts for page fetch/XHR calls. No NICs, names, grades, API keys, tokens, URLs,
screenshots, HTML, raw messages, headers or response bodies are recorded.

`late_result` means the result arrived after the old cutoff without a resubmit.
`captcha_message` indicates visible message text matched a verification keyword;
it does not prove token rejection. HTTP counts cover page fetch/XHR, not CAPTCHA
iframe traffic or top-level navigations, and HTTP 200 does not prove acceptance.
If no visible error or HTTP failure appears, the cause remains unconfirmed.

Diagnostic update after the 20-student test: new reports include a fixed pause
reason code and separate aborted requests, request timeouts, opaque responses and
unknown statuses from actual network errors. The original probe counted every
status-zero completion as a network error, including on successful rows; those
old counters cannot establish a transport failure. Worker labels at the start of
each row are also captured after the worker session is assigned.

This is temporary diagnostic code, not a release or a confirmed site-side fix.
