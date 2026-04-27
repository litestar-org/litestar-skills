<#
.SYNOPSIS
    SessionStart hook for litestar-skills (PowerShell parity of session-start.sh).

.DESCRIPTION
    Detects the host via env vars and emits the host-correct JSON shape with
    project-aware skill reminders. Detection logic is delegated to detect-env.ps1
    (which in turn delegates to python3 / hooks/lib/_detector.py).
#>

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$detectEnv = Join-Path $scriptDir 'lib/detect-env.ps1'

if (-not (Test-Path -LiteralPath $detectEnv)) {
    Write-Output '{}'
    return
}

$detectorOutput = & $detectEnv $PWD.Path
if (-not $detectorOutput -or $detectorOutput.Trim() -eq '{}') {
    Write-Output '{}'
    return
}

$detector = $detectorOutput | ConvertFrom-Json
$context = if ($detector.context) { $detector.context } else { '' }

$host_ = 'unknown'
if ($env:CLAUDE_PLUGIN_ROOT)   { $host_ = 'claude'  }
elseif ($env:CODEX_PLUGIN_ROOT) { $host_ = 'codex'   }
elseif ($env:CURSOR_PLUGIN_ROOT){ $host_ = 'cursor'  }
elseif ($env:GEMINI_CLI -or $env:GEMINI_EXTENSION_NAME) { $host_ = 'gemini' }

switch ($host_) {
    { $_ -in 'claude','codex' } {
        $out = [ordered]@{
            hookSpecificOutput = [ordered]@{
                hookEventName     = 'SessionStart'
                additionalContext = $context
            }
        }
    }
    'gemini' {
        $out = [ordered]@{
            hookSpecificOutput = [ordered]@{
                hookEventName     = 'SessionStart'
                additionalContext = $context
            }
            systemMessage = $context
        }
    }
    default {
        $out = [ordered]@{ additional_context = $context }
    }
}

$out | ConvertTo-Json -Compress -Depth 20
