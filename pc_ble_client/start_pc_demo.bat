@echo off
REM Start GUI using project .venv (create it automatically if missing)

cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    echo Starting with project venv ...
    ".venv\Scripts\python.exe" run_gui.py %*
    goto end
)

echo No project .venv found. Running setup_venv.bat first ...
call "%~dp0setup_venv.bat"
if errorlevel 1 (
    echo ERROR: setup failed.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: still no .venv after setup.
    pause
    exit /b 1
)

echo Starting with project venv ...
".venv\Scripts\python.exe" run_gui.py %*

:end
if errorlevel 1 pause
