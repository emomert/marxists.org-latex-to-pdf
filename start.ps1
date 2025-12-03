[CmdletBinding()]
param(
    [switch]$UseGlobalPython,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3

$repoRoot = $PSScriptRoot
Set-Location $repoRoot

function Write-Step($message) {
    Write-Host "==> $message" -ForegroundColor Cyan
}

function Fail($message) {
    Write-Host "ERROR: $message" -ForegroundColor Red
    exit 1
}

Write-Step "Checking Python..."
$pythonCmd = "python"
$python = Get-Command $pythonCmd -ErrorAction SilentlyContinue
if (-not $python) {
    Fail "Python 3.8+ is required. Install Python and ensure 'python' is on PATH."
}

$pyVersion = & $pythonCmd - <<'PY'
import sys
print(".".join(map(str, sys.version_info[:3])))
PY
if (-not $?) {
    Fail "Could not determine Python version."
}

$verParts = $pyVersion.Split(".") | ForEach-Object { [int]$_ }
if ($verParts[0] -lt 3 -or ($verParts[0] -eq 3 -and $verParts[1] -lt 8)) {
    Fail "Python 3.8+ is required (found $pyVersion)."
}

$pythonInVenv = $null
if (-not $UseGlobalPython) {
    $venvPath = Join-Path $repoRoot ".venv"
    $pythonInVenv = Join-Path $venvPath "Scripts\python.exe"

    if (-not (Test-Path $pythonInVenv)) {
        Write-Step "Creating virtual environment in .venv..."
        & $pythonCmd -m venv $venvPath
    }

    $pythonCmd = $pythonInVenv
    Write-Step "Using virtual environment at .venv"
} else {
    Write-Step "Using global Python (no virtualenv)."
}

if (-not $SkipInstall) {
    Write-Step "Upgrading pip and installing requirements..."
    & $pythonCmd -m pip install --upgrade pip
    & $pythonCmd -m pip install -r requirements.txt
} else {
    Write-Step "Skipping dependency installation (per --SkipInstall)."
}

Write-Step "Checking for xelatex..."
$xelatex = Get-Command xelatex -ErrorAction SilentlyContinue
if (-not $xelatex) {
    Fail "xelatex not found. Install MiKTeX or TeX Live and ensure 'xelatex' is on PATH."
}

# Sanity check that xelatex runs
& xelatex --version > $null

Write-Step "Launching app..."
& $pythonCmd run.py @args
