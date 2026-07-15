@echo off
REM Find Python 3.10+ and set PYEXE for the caller.
REM Usage: call "%~dp0find_python.bat"
REM After call, check: if not defined PYEXE ( error )
REM
REM Priority:
REM   1) PC_BLE_PYTHON env var (full path to python.exe)
REM   2) Windows py launcher: 3.12 / 3.11 / 3.10 / 3
REM   3) python on PATH (version checked)
REM   4) Legacy B:\python3.12\python.exe

set "PYEXE="

REM --- 1) Manual override ---
if defined PC_BLE_PYTHON (
    if exist "%PC_BLE_PYTHON%" (
        "%PC_BLE_PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
        if not errorlevel 1 (
            set "PYEXE=%PC_BLE_PYTHON%"
            goto :eof
        )
    )
)

REM --- 2) py launcher ---
where py >nul 2>&1
if not errorlevel 1 (
    for %%V in (3.12 3.11 3.10 3) do (
        if not defined PYEXE (
            for /f "delims=" %%i in ('py -%%V -c "import sys; assert sys.version_info >= (3, 10); print(sys.executable)" 2^>nul') do (
                if exist "%%i" set "PYEXE=%%i"
            )
        )
    )
    if defined PYEXE goto :eof
)

REM --- 3) python on PATH ---
where python >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%i in ('where python') do (
        if not defined PYEXE (
            "%%i" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
            if not errorlevel 1 set "PYEXE=%%i"
        )
    )
    if defined PYEXE goto :eof
)

REM --- 4) Legacy path from older machines ---
if exist "B:\python3.12\python.exe" (
    "B:\python3.12\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if not errorlevel 1 set "PYEXE=B:\python3.12\python.exe"
)

goto :eof
