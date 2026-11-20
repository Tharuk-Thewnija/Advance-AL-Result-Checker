@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo The project Python environment was not found.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m experiments.submission_diagnostics --network-only
pause
endlocal
