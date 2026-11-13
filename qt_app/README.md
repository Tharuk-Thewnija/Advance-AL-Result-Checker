# Qt interface

Qt Quick is now the main application. See [the project guide](../README.md) for
setup, collection, saved progress, tests and Windows builds.

- `run_qt.cmd` starts `checker.py` using the root `.venv`.
- `run_mock_test.cmd` starts the independent offline 1,500-student mock mode.
- The Qt tests now live under `tests/test_qt_*.py` and run with the full suite.

Normal Qt and mock saved-progress paths are unchanged by the promotion to the main
UI. The retired UI and prototype source are backed up at Git tag
`backup/pre-qt-main-2026-11-13`.
