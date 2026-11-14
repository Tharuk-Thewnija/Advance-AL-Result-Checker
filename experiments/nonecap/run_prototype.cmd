@echo off
setlocal
cd /d "%~dp0\..\.."
if not exist ".venv\Scripts\python.exe" (
    echo The project Python environment was not found. Install the project requirements first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m experiments.nonecap %*
if errorlevel 1 pause
endlocal
