# Start pc_ble_client GUI (PowerShell, ASCII-only)
# Prefer project .venv; if missing, print how to create it.

Set-Location -LiteralPath $PSScriptRoot

$VenvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (Test-Path -LiteralPath $VenvPy) {
    Write-Host "Starting with project venv: $VenvPy"
    & $VenvPy run_gui.py @args
    exit $LASTEXITCODE
}

Write-Host "No project .venv found."
Write-Host "Creating it now (one-time setup) ..."
& (Join-Path $PSScriptRoot "setup_venv.ps1")
if ($LASTEXITCODE -ne 0) {
    Write-Error "setup_venv.ps1 failed. Fix Python install, then retry."
    exit $LASTEXITCODE
}

if (-not (Test-Path -LiteralPath $VenvPy)) {
    Write-Error "Still no .venv after setup. Abort."
    exit 1
}

Write-Host "Starting with project venv: $VenvPy"
& $VenvPy run_gui.py @args
exit $LASTEXITCODE
