@echo off
REM 备用启动：与 start_pc_demo.bat 相同策略，固定 B:\python3.12
cd /d "%~dp0"

set "PY312=B:\python3.12\python.exe"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" run_gui.py
    goto end
)

if exist "%PY312%" (
    "%PY312%" run_gui.py
    goto end
)

echo [错误] 未找到 .venv 或 %PY312%
pause
exit /b 1

:end
if errorlevel 1 pause
