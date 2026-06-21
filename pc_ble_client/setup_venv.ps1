# Setup .venv for pc_ble_client (PowerShell, ASCII-only)
Set-Location -LiteralPath $PSScriptRoot

$Py312 = "B:\python3.12\python.exe"

if (-not (Test-Path -LiteralPath $Py312)) {
    Write-Error "Python not found: $Py312"
    exit 1
}

Write-Host "Using: $Py312"
Write-Host "Creating .venv ..."
& $Py312 -m venv .venv
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$VenvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $VenvPy -m pip install --upgrade pip
& $VenvPy -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "DONE. Start with: .\start_pc_demo.ps1"
