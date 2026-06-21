# Start pc_ble_client GUI (PowerShell, ASCII-only)
Set-Location -LiteralPath $PSScriptRoot

$VenvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$Py312 = "B:\python3.12\python.exe"

if (Test-Path -LiteralPath $VenvPy) {
    & $VenvPy run_gui.py
    exit $LASTEXITCODE
}

if (Test-Path -LiteralPath $Py312) {
    Write-Host "WARN: no .venv, using B:\python3.12. Run .\setup_venv.ps1 first."
    & $Py312 run_gui.py
    exit $LASTEXITCODE
}

Write-Error "No .venv and no B:\python3.12\python.exe. Run .\setup_venv.ps1 first."
exit 1
