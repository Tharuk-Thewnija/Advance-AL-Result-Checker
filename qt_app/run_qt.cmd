@echo off
setlocal
set "QT_PYTHON=%~dp0..\.venv\Scripts\python.exe"
if not exist "%QT_PYTHON%" (
    echo Follow qt_app\README.md to create the isolated Qt environment.
    pause
    exit /b 1
)
"%QT_PYTHON%" "%~dp0..\checker.py" %*
if errorlevel 1 pause
