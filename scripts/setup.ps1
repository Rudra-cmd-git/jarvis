<#
.SYNOPSIS
    Create the JARVIS virtual environment and install dependencies.
.DESCRIPTION
    The virtual environment is stored outside the project folder (OneDrive-synced
    folders are a poor home for thousands of venv files). Override with JARVIS_VENV.
#>
[CmdletBinding()]
param(
    [switch]$SkipModel,
    [string]$VenvPath
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $VenvPath) {
    $VenvPath = if ($env:JARVIS_VENV) { $env:JARVIS_VENV } else { Join-Path $env:LOCALAPPDATA "JARVIS\venv" }
}

$Python = Join-Path $VenvPath "Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Host "Creating virtual environment at $VenvPath" -ForegroundColor Cyan
    $base = Get-Command python -ErrorAction SilentlyContinue
    if (-not $base) { $base = Get-Command py -ErrorAction SilentlyContinue }
    if (-not $base) {
        throw "Python 3.11+ was not found. Install it from https://www.python.org/downloads/windows/ (tick 'Add python.exe to PATH')."
    }
    & $base.Source -m venv $VenvPath
    if ($LASTEXITCODE -ne 0) { throw "Could not create the virtual environment." }
} else {
    Write-Host "Using existing environment at $VenvPath" -ForegroundColor DarkGray
}

Write-Host "Installing Python dependencies (this can take a few minutes)..." -ForegroundColor Cyan
& $Python -m pip install --upgrade pip --disable-pip-version-check
& $Python -m pip install --disable-pip-version-check -r (Join-Path $ProjectRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

$postInstall = Join-Path $VenvPath "Scripts\pywin32_postinstall.py"
if (Test-Path $postInstall) {
    Write-Host "Configuring pywin32 COM extensions..." -ForegroundColor DarkGray
    & $Python $postInstall -install | Out-Null
}

if (-not $SkipModel) {
    Write-Host "Downloading the offline speech model (about 40 MB, once)..." -ForegroundColor Cyan
    $env:PYTHONPATH = Join-Path $ProjectRoot "src"
    & $Python -c "from jarvis.config import get_paths; from jarvis.voice.models import ensure_model; print(ensure_model(get_paths().models_dir))"
}

Write-Host ""
Write-Host "Setup complete. Start JARVIS with scripts\run_jarvis.ps1" -ForegroundColor Green
Write-Host "Environment: $VenvPath" -ForegroundColor DarkGray