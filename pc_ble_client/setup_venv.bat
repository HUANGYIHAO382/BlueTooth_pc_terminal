@echo off
REM Create project-local .venv and install requirements.txt
REM Auto-detects Python 3.10+ (no hard-coded machine path required)

cd /d "%~dp0"

call "%~dp0find_python.bat"
if not defined PYEXE (
    echo ERROR: Python 3.10+ not found.
    echo.
    echo Install Python 3.12 from https://www.python.org/downloads/
    echo   - Enable: Add python.exe to PATH
    echo   - Enable: Install py launcher
    echo.
    echo Or set a full path then re-run:
    echo   set PC_BLE_PYTHON=C:\Path\To\python.exe
    echo   setup_venv.bat
    pause
    exit /b 1
)

echo Using Python: %PYEXE%
"%PYEXE%" -c "import sys; print('Version:', sys.version.split()[0])"

echo Creating .venv ...
"%PYEXE%" -m venv .venv
if errorlevel 1 (
    echo ERROR: failed to create .venv
    pause
    exit /b 1
)

echo Upgrading pip ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
echo Installing requirements.txt ...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed
    pause
    exit /b 1
)

echo.
echo DONE. Project venv is ready: .venv\
echo Start GUI with: start_pc_demo.bat
pause
