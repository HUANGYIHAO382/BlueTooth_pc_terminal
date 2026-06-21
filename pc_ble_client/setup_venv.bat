@echo off
cd /d "%~dp0"

set "PY312=B:\python3.12\python.exe"

if not exist "%PY312%" (
    echo ERROR: Python not found at %PY312%
    pause
    exit /b 1
)

echo Using: %PY312%
echo Creating .venv ...
"%PY312%" -m venv .venv
if errorlevel 1 (
    echo ERROR: failed to create .venv
    pause
    exit /b 1
)

echo Installing requirements.txt ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed
    pause
    exit /b 1
)

echo.
echo DONE. Run start_pc_demo.bat or start_pc_demo.ps1
pause
