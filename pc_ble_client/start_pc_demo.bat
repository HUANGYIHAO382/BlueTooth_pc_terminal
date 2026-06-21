@echo off
cd /d "%~dp0"

set "PY312=B:\python3.12\python.exe"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" run_gui.py
    goto end
)

if exist "%PY312%" (
    echo WARN: no .venv, using B:\python3.12. Run setup_venv.bat first.
    "%PY312%" run_gui.py
    goto end
)

echo ERROR: no .venv and no %PY312%
pause
exit /b 1

:end
if errorlevel 1 pause
