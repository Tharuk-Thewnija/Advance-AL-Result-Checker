# Qt collection integration

User requested connecting the existing scraper and Excel handling to the approved
Qt Quick design while preserving the working app until real testing is complete.
They previously requested direct execution in this session; routine implementation
choices are delegated.

Use a separate `checker_qt.py` launcher and `qt_app/` package. Preserve both the
CustomTkinter app and the rendering-only prototype byte for byte. Reuse shared
collector, parsing, workbook and checkpoint code without modifying it. The Qt
process gets a separate LOCALAPPDATA namespace, including checkpoint, preferences
and instance lock. Changing this environment variable affects only this process.

Approaches: reuse the backend through worker threads (chosen: smallest change,
existing tested logic); rewrite the collector (adds unnecessary regression risk);
run the entire original GUI as a subprocess (does not integrate the new UI).

Run workbook import, checkpoint preparation, collection and Excel export on QThread
tasks. The GUI drains bounded worker progress/log messages on a timer. Terminal
handling occurs after the thread exits. Never close the window while a task owns
the browser or checkpoint. Stop requests cooperative cancellation, then waits for
cleanup without blocking the UI. Close during import/export waits for that task.

Keep subject/field/year/timeout/output settings bound to the new UI. Freeze them
during any operation. Prompt to resume, archive-and-restart, or cancel when saved
progress is present or mismatched. Archive old Qt checkpoints instead of deleting
them. Keep checkpoints after export for recovery and repeat exports. The existing
app's files, student workbook and checkpoint must remain untouched.

Test real workbook -> collector -> SQLite -> export behavior with only the browser
boundary replaced by synthetic results. Cover partial resume, failed exports,
mismatch cancellation, validation, large files and safe shutdown. Inspect the Qt
screen. Live CAPTCHA and actual student results require the user's manual test;
do not look up student IDs during automated verification.
