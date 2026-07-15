@echo off
REM Build green Windows package (calls build_exe.ps1)
cd /d "%~dp0"

where powershell >nul 2>&1
if errorlevel 1 (
    echo ERROR: PowerShell not found.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_exe.ps1"
if errorlevel 1 (
    echo ERROR: build failed.
    pause
    exit /b 1
)

echo.
pause
