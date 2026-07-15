# Setup project-local .venv for pc_ble_client (PowerShell, ASCII-only)
# This script does NOT hard-code a machine-specific Python path.
# It auto-detects Python 3.10+ and creates .venv next to this script.

Set-Location -LiteralPath $PSScriptRoot

# Load shared finder (defines Find-ProjectPython)
. (Join-Path $PSScriptRoot "find_python.ps1")

$Py = Find-ProjectPython
if (-not $Py) {
    Write-Error @"
Python 3.10+ not found.

Install Python 3.12 from https://www.python.org/downloads/
  - Check: "Add python.exe to PATH"
  - Check: "Install py launcher"

Or set a full path, then re-run this script:
  `$env:PC_BLE_PYTHON = "C:\Path\To\python.exe"
  .\setup_venv.ps1
"@
    exit 1
}

Write-Host "Using Python: $Py"
& $Py -c "import sys; print('Version:', sys.version.split()[0])"

Write-Host "Creating .venv in: $PSScriptRoot"
& $Py -m venv .venv
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to create .venv"
    exit $LASTEXITCODE
}

# Always use the venv interpreter after creation
$VenvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPy)) {
    Write-Error "venv created but python.exe missing: $VenvPy"
    exit 1
}

Write-Host "Upgrading pip ..."
& $VenvPy -m pip install --upgrade pip
Write-Host "Installing requirements.txt ..."
& $VenvPy -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Error "pip install failed"
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "DONE. Project venv is ready: .venv\"
Write-Host "Start GUI with: .\start_pc_demo.ps1"
