# Build Windows portable (green) package with PyInstaller.
# IMPORTANT: keep this file ASCII-only (PowerShell encoding on Chinese Windows).
#
# Output:
#   dist\PCBleGateway\          runnable folder
#   dist\PCBleGateway-vX.Y.Z-win64.zip
#
# Usage:
#   .\build_exe.ps1              full rebuild
#   .\build_exe.ps1 -SkipBuild   only copy defaults + zip (reuse existing dist)

param(
    [switch]$SkipBuild
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$VenvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPy)) {
    Write-Error "Missing .venv. Run .\setup_venv.ps1 first."
    exit 1
}

# Read version from gateway_config.py (GATEWAY_VERSION = "x.y.z")
$verLine = Select-String -Path (Join-Path $PSScriptRoot "gateway_config.py") -Pattern 'GATEWAY_VERSION\s*=\s*"([^"]+)"'
$Version = if ($verLine) { $verLine.Matches[0].Groups[1].Value } else { "0.0.0" }
Write-Host "Version: $Version"
Write-Host "Python : $VenvPy"

$DistApp = Join-Path $PSScriptRoot "dist\PCBleGateway"
$ExePath = Join-Path $DistApp "PCBleGateway.exe"

if (-not $SkipBuild) {
    Write-Host "Installing PyInstaller ..."
    & $VenvPy -m pip install -U "pyinstaller>=6.0"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    if (Test-Path -LiteralPath $DistApp) {
        Remove-Item -LiteralPath $DistApp -Recurse -Force
    }

    Write-Host "Running PyInstaller (this may take several minutes) ..."
    & $VenvPy -m PyInstaller --noconfirm --clean (Join-Path $PSScriptRoot "pc_ble_gateway.spec")
    if ($LASTEXITCODE -ne 0) {
        Write-Error "PyInstaller failed"
        exit $LASTEXITCODE
    }
}
else {
    Write-Host "SkipBuild: reuse existing dist folder."
}

if (-not (Test-Path -LiteralPath $ExePath)) {
    Write-Error "PCBleGateway.exe not found: $ExePath"
    exit 1
}

# Copy clean defaults next to exe (ASCII filenames only)
$Defaults = Join-Path $PSScriptRoot "release_defaults"
Copy-Item -LiteralPath (Join-Path $Defaults "gateway.json") -Destination (Join-Path $DistApp "gateway.json") -Force
Copy-Item -LiteralPath (Join-Path $Defaults "devices.json") -Destination (Join-Path $DistApp "devices.json") -Force
Copy-Item -LiteralPath (Join-Path $Defaults "README.txt") -Destination (Join-Path $DistApp "README.txt") -Force

# Zip for GitHub Releases
$ZipName = "PCBleGateway-v$Version-win64.zip"
$ZipPath = Join-Path $PSScriptRoot "dist\$ZipName"
if (Test-Path -LiteralPath $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}
Write-Host "Creating zip: $ZipPath"
Compress-Archive -Path $DistApp -DestinationPath $ZipPath -Force

Write-Host ""
Write-Host "DONE."
Write-Host "  Folder : $DistApp"
Write-Host "  Zip    : $ZipPath"
Write-Host "Test: double-click dist\PCBleGateway\PCBleGateway.exe"
Write-Host "Then upload the zip to GitHub Releases."
