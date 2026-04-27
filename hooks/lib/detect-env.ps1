<#
.SYNOPSIS
    Project-aware library detection for litestar-skills (PowerShell parity of detect-env.sh).

.DESCRIPTION
    Emits JSON to stdout:
      { "detected_skills": [...], "context": "<reminder text>", "project_root": "<path>" }

    Honors LITESTAR_SKILLS_HOOK_DISABLE=1 (emits "{}" and exits 0).

    The detection logic itself is delegated to python3 because the bash variant
    already requires python3 — keeping a single canonical detector keeps the
    .sh and .ps1 outputs identical.

.PARAMETER ProjectRoot
    Project directory to inspect. Defaults to current directory.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$ProjectRoot = $PWD.Path
)

$ErrorActionPreference = 'Stop'

if ($env:LITESTAR_SKILLS_HOOK_DISABLE -eq '1') {
    Write-Output '{}'
    exit 0
}

if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) {
    Write-Output '{}'
    exit 0
}

$libDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$skillMap = Join-Path $libDir 'skill-map.json'
$detector = Join-Path $libDir '_detector.py'

# Prefer python3, fall back to python (Windows often only has python.exe).
$python = Get-Command python3 -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command python -ErrorAction SilentlyContinue }

if ($python) {
    & $python.Path $detector $ProjectRoot $skillMap
    exit $LASTEXITCODE
}

# No Python — emit minimal JSON with intro only.
$intro = 'litestar loaded.'
$out = [ordered]@{
    detected_skills = @()
    context         = $intro
    project_root    = $ProjectRoot
}
$out | ConvertTo-Json -Compress -Depth 10
