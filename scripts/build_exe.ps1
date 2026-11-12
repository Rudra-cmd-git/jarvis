<#
.SYNOPSIS
    Build a standalone Windows executable with PyInstaller.
.NOTES
    Output: dist\JARVIS\JARVIS.exe
    PyInstaller must support the Python version used for the venv. If your Python
    is newer than PyInstaller supports, create the venv with Python 3.12 or 3.13.
#>
[CmdletBinding()]
param(
    [switch]$SkipSetup,
    [string]$VenvPath
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $VenvPath) {
    $VenvPath = if ($env:JARVIS_VENV) { $env:JARVIS_VENV } else { Join-Path $env:LOCALAPPDATA "JARVIS\venv" }
}
$Python = Join-Path $VenvPath "Scripts\python.exe"

if (-not (Test-Path $Python)) {
    if ($SkipSetup) { throw "Environment missing at $VenvPath. Run scripts\setup.ps1 first." }
    & (Join-Path $PSScriptRoot "setup.ps1") -VenvPath $VenvPath
}

Write-Host "Installing PyInstaller..." -ForegroundColor Cyan
& $Python -m pip install --disable-pip-version-check "pyinstaller>=6.0"

Push-Location $ProjectRoot
try {
    & $Python -m PyInstaller --noconfirm --clean (Join-Path $ProjectRoot "jarvis.spec")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }
}
finally {
    Pop-Location
}

$exe = Join-Path $ProjectRoot "dist\JARVIS\JARVIS.exe"
if (Test-Path $exe) {
    Write-Host ""
    Write-Host "Build complete: $exe" -ForegroundColor Green
} else {
    throw "Build finished but the executable was not found."
}