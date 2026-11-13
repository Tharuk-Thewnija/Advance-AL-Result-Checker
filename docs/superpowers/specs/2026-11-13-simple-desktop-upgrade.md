# Simple desktop upgrade

Status: workflow and scope approved in conversation on 2026-11-13. Implementation choices below are proposals for plan review.

## Purpose

Make it easier for tuition teachers and institutes to find their students' A/L results. This is an open source, local Windows desktop application. Keep Python, CustomTkinter and Selenium.

## User experience

Choose one Excel file, select subjects and optional output fields, start, complete each CAPTCHA in Chrome, and export results. One file and one active run at a time. No accounts, class management, dashboards, multi-file queues, or central server.

A single window contains file selection, searchable subject checkboxes, optional field checkboxes, exam year, and Start. During collection show current student, completed/total, successes, skips and failures, a bounded activity log, Stop and Skip Current. After collection show the saved file and Open Folder. Timeout is an advanced setting. No separate wizard is necessary.

Support Light, Dark and System appearance; remember appearance and selections. All custom surfaces and text must remain readable in every mode.

## Subjects and output

Provide a maintained catalogue covering current official A/L subjects, with names, codes where available, explicit website aliases, and source/date metadata. Verify the list against official examination material during implementation. Include General English and the Common General Test as applicable result options. Users can search and select multiple subjects; do not infer subject matches through ambiguous substrings.

Optional fields are Candidate Name, School, District, Medium, Index Number, District Rank, Island Rank, Z-Score and Subject Stream. Missing website fields remain blank. Do not invent values. Raw website text is not a default export field.

Keep the existing NIC-based input workflow and first-sheet behavior in this release. Accept .xlsx and .xls with their required readers. Preserve original row order, values and columns, including repeated NICs; each input row remains independently represented. Export selected subject grades, selected optional fields, Scrape Status and Scrape Notes. If generated column names collide with input columns, use a distinct Results-prefixed name and a deterministic numeric suffix if necessary. Never overwrite the input workbook. Preserve values, not workbook styling, formulas or macros; exports are .xlsx.

## Recovery and file management

Persist each processed row locally before reporting it as saved. Use a small SQLite checkpoint under the user's application-data directory; this is an implementation detail, not a job-management interface. Store only input identity, frozen run settings, row progress and selected result values needed for recovery.

When the same unchanged input is selected with the same settings, offer Resume or Start Fresh. Verify input content hash, worksheet and frozen settings before resuming; changed input/settings require a fresh run. Resume pending rows without repeating completed ones. Skipped/error rows remain recorded; users may start fresh to recollect them. Do not introduce retry controls in this version.

Offer an output-folder choice defaulting to the input folder. Use unique timestamped output names. Export through a temporary file in the destination directory and replace only the newly allocated destination. If export is blocked, retain progress and let the user choose another destination. A stopped run can export partial results. Keep checkpoints until successful export; after success remove its checkpoint. No full Excel rewrite per student.

## Collection and performance

Reuse one Chrome instance, retain a worker thread, and send compact UI events. Keep GUI work on its main thread. Cap visible logs at 500 entries. Maintain at most one pending progress snapshot, without dropping completion/error events. Always close Chrome and database connections on stop/failure/exit.

Retain the verified A/L option-value selection and option-loading waits. CAPTCHA stays manual. Do not depend on the temporary result.jsf URL, which returned 404 during investigation. A website/form failure must produce a useful error and preserve saved progress. Cancel/skip checks must also run during form-loading waits.

Benchmark import, checkpoint and export with 1,000 synthetic rows; distinguish those timings from website/CAPTCHA time. There is no promised collection throughput or need to change language without measurements.

## Release

Keep checker.py as the launch command and move responsibilities into focused modules. Provide documented dependencies and tests, synthetic sample data, and a Windows application bundle/installer. Verify on a machine without a separate Python installation. Source, student workbooks, checkpoints and logs must not be bundled together. The maintainer must choose an open source licence before public release; do not silently choose one for them.

## Acceptance

An ICT teacher can select one workbook and ICT only, complete CAPTCHA, stop and resume an interrupted run, and export the original rows with ICT grades and status. Multiple selected subjects and optional fields also work. Existing form-selection regression checks pass. A 1,000-row synthetic run keeps memory/log growth bounded by the input and selected results and does not rewrite the workbook per row. Theme and installation checks pass on Windows.
