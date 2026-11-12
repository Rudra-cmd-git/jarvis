<#
.SYNOPSIS
    Launch J.A.R.V.I.S.
.DESCRIPTION
    Creates the environment on first run, then starts the desktop application.
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

$env:PYTHONPATH = Join-Path $ProjectRoot "src"
& $Python -m jarvis
exit $LASTEXITCODE