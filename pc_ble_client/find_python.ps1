# Find a Python 3.10+ interpreter for this project (ASCII-only).
# Used by: setup_venv.ps1 / start_pc_demo.ps1
#
# Priority (初心者向け说明见函数上方英文，中文见 README):
#   1) Env var PC_BLE_PYTHON  -> full path to python.exe (manual override)
#   2) Windows "py" launcher  -> try 3.12, 3.11, 3.10, then 3
#   3) "python" / "python3" on PATH (only if version >= 3.10)
#   4) Legacy optional path   -> B:\python3.12\python.exe (old machine only)

function Test-Python310Plus {
    # Return $true if $ExePath runs Python 3.10 or newer.
    param(
        [Parameter(Mandatory = $true)]
        [string]$ExePath
    )
    if (-not (Test-Path -LiteralPath $ExePath)) {
        return $false
    }
    # Tiny Python snippet: exit 0 only when major.minor >= 3.10
    & $ExePath -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
    return ($LASTEXITCODE -eq 0)
}

function Resolve-PyLauncherExe {
    # Ask the Windows py launcher for the real python.exe path of a given version tag.
    param(
        [Parameter(Mandatory = $true)]
        [string]$VersionTag
    )
    try {
        $out = & py -$VersionTag -c "import sys; assert sys.version_info >= (3, 10); print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) {
            $path = ($out | Select-Object -Last 1).ToString().Trim()
            if ($path -and (Test-Path -LiteralPath $path)) {
                return $path
            }
        }
    }
    catch {
        # py not installed or this version missing — ignore and try next
    }
    return $null
}

function Find-ProjectPython {
    # Main entry: return absolute path to a usable python.exe, or $null.
    # --- 1) Manual override (推荐：换机器时也可设这个环境变量) ---
    if ($env:PC_BLE_PYTHON) {
        $override = $env:PC_BLE_PYTHON.Trim().Trim('"')
        if (Test-Python310Plus -ExePath $override) {
            return $override
        }
        Write-Warning "PC_BLE_PYTHON is set but invalid or < 3.10: $override"
    }

    # --- 2) Windows Python Launcher (py -3.12 / py -3.11 / ...) ---
    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        foreach ($tag in @("3.12", "3.11", "3.10", "3")) {
            $found = Resolve-PyLauncherExe -VersionTag $tag
            if ($found) {
                return $found
            }
        }
    }

    # --- 3) python / python3 on PATH ---
    foreach ($name in @("python", "python3")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source) {
            if (Test-Python310Plus -ExePath $cmd.Source) {
                return $cmd.Source
            }
        }
    }

    # --- 4) Legacy hard-coded path (only if that machine still has it) ---
    $legacy = "B:\python3.12\python.exe"
    if (Test-Python310Plus -ExePath $legacy) {
        return $legacy
    }

    return $null
}
