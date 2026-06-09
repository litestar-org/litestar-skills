#!/usr/bin/env pwsh
#Requires -Version 7.0
<#
.SYNOPSIS
    Install litestar-skills for every supported AI agent CLI detected on the system.

.DESCRIPTION
    Native Windows installer mirroring tools/install.sh. Auto-installs for
    Gemini CLI, Codex CLI, and OpenCode (via file copy, not symlink);
    prints instructions for Claude Code, Cursor, and VS Code.

    PowerShell 7+ only. Uses Get-Command for host detection and Copy-Item
    for OpenCode (Windows symlinks require admin or developer-mode, so the
    installer deliberately copies the plugin entrypoint).

    Repo: https://github.com/litestar-org/litestar-skills

.PARAMETER Only
    Install for specific host(s) only. Accepts a comma-separated list or
    repeated usage. Valid values: claude, gemini, codex, opencode, cursor,
    vscode.

.PARAMETER Skip
    Skip the named host(s). Accepts a comma-separated list or repeated
    usage. Same values as -Only.

.PARAMETER DryRun
    Preview actions without executing them.

.PARAMETER Force
    Overwrite existing installs without prompting.

.PARAMETER ClaudeSettings
    Also whitelist the repo in $env:APPDATA\Claude\settings.json under
    extraKnownMarketplaces. Opt-in because it edits a host-owned file.

.PARAMETER AntigravitySymlink
    Create .agent -> .agents symbolic link in $PWD so Google Antigravity
    (singular .agent) discovers skills installed under .agents/skills/.
    Opt-in - community workaround, not a Google-blessed integration.
    Requires Developer Mode or admin rights on Windows for symlink
    creation. Skipped if .agent already exists.

.EXAMPLE
    pwsh -File tools/install.ps1
    Install for every detected host.

.EXAMPLE
    pwsh -File tools/install.ps1 -DryRun
    Preview without changes.

.EXAMPLE
    pwsh -File tools/install.ps1 -Only gemini,codex
    Install only for Gemini CLI and Codex CLI.

.EXAMPLE
    pwsh -File tools/install.ps1 -ClaudeSettings
    Whitelist the marketplace in Claude Code settings and print the
    /plugin install instructions.
#>

[CmdletBinding()]
param(
    [string[]]$Only,
    [string[]]$Skip,
    [switch]$DryRun,
    [switch]$Force,
    [switch]$ClaudeSettings,
    [switch]$AntigravitySymlink
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# =============================================================================
# Constants
# =============================================================================
$script:Version = '0.3.0'
$script:RepoUrl = 'https://github.com/litestar-org/litestar-skills'
$script:RepoSlug = 'litestar-org/litestar-skills'
$script:MarketplaceName = 'litestar'
$script:PluginName = 'litestar'
$script:ScriptDir = Split-Path -Parent $PSCommandPath
$script:RepoRoot = Split-Path -Parent $script:ScriptDir

# Status tracking (mirrors install.sh STATUSES array)
$script:Statuses = [System.Collections.Generic.List[string]]::new()

# =============================================================================
# Logging helpers
# =============================================================================
function Write-Info {
    param([string]$Msg)
    Write-Host "[INFO]  $Msg" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Msg)
    Write-Host "[OK]    $Msg" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Msg)
    Write-Host "[WARN]  $Msg" -ForegroundColor Yellow
}

function Write-Err {
    param([string]$Msg)
    Write-Host "[ERROR] $Msg" -ForegroundColor Red
}

# =============================================================================
# Host detection + filtering
# =============================================================================
function Test-HostInstalled {
    # Wraps Get-Command so every host-detection site shares one policy.
    # Get-Command searches $env:PATH plus PowerShell's alias/function tables;
    # Get-Command with -ErrorAction SilentlyContinue returns $null when
    # missing (instead of throwing), which is what we want for host probes.
    param([string]$Command)
    return [bool](Get-Command $Command -ErrorAction SilentlyContinue)
}

function Get-HostCommandPath {
    # Return the resolved executable path (or $null) for a host CLI.
    # Used by diagnostic output; complements Test-HostInstalled which
    # only returns a boolean.
    param([string]$Command)
    $info = Get-Command $Command -ErrorAction SilentlyContinue
    if ($null -eq $info) { return $null }
    return $info.Source
}

function Test-ShouldInstall {
    param([string]$HostName)
    if ($Only -and $Only.Count -gt 0) {
        return $Only -contains $HostName
    }
    if ($Skip -and $Skip.Count -gt 0 -and ($Skip -contains $HostName)) {
        return $false
    }
    return $true
}

function Invoke-Step {
    param(
        [string]$Description,
        [scriptblock]$Action
    )
    Write-Info $Description
    if ($DryRun) {
        $preview = $Action.ToString().Trim() -replace '\s+', ' '
        if ($preview.Length -gt 120) { $preview = $preview.Substring(0, 117) + '...' }
        Write-Host "  [DRY-RUN] $preview" -ForegroundColor DarkGray
        return
    }
    & $Action
}

# =============================================================================
# Per-host install functions
# =============================================================================

# ------ Claude Code (instructions + optional settings edit) ------------------
function Install-ClaudeCode {
    if (-not (Test-ShouldInstall 'claude')) { return }
    Write-Info 'Claude Code setup'

    if ($ClaudeSettings) {
        $settingsPath = Join-Path $env:APPDATA 'Claude\settings.json'
        Invoke-Step "Updating Claude Code settings whitelist: $settingsPath" {
            $settingsDir = Split-Path $settingsPath
            if (-not (Test-Path $settingsDir)) {
                New-Item -ItemType Directory -Path $settingsDir -Force | Out-Null
            }
            $config = @{}
            if (Test-Path $settingsPath) {
                try {
                    $raw = Get-Content $settingsPath -Raw
                    if ($raw.Trim()) {
                        $config = $raw | ConvertFrom-Json -AsHashtable
                    }
                } catch {
                    Write-Warn "Could not parse existing settings.json; starting fresh"
                    $config = @{}
                }
            }
            if (-not $config.ContainsKey('extraKnownMarketplaces')) {
                $config['extraKnownMarketplaces'] = @()
            }
            $existing = [System.Collections.Generic.List[string]]::new()
            foreach ($item in $config['extraKnownMarketplaces']) { $existing.Add($item) }
            if (-not $existing.Contains($script:RepoSlug)) {
                $existing.Add($script:RepoSlug)
                $config['extraKnownMarketplaces'] = ($existing | Sort-Object -Unique)
                $config | ConvertTo-Json -Depth 10 | Set-Content $settingsPath -Encoding UTF8
                Write-Success "Added $script:RepoSlug to extraKnownMarketplaces"
            } else {
                Write-Info "$script:RepoSlug already whitelisted"
            }
        }
    }

    Write-Host @"

Next steps (inside Claude Code):

  /plugin marketplace add $script:RepoSlug
  /plugin install $script:PluginName@$script:MarketplaceName

Re-run this installer with -ClaudeSettings to whitelist the marketplace
ahead of time and skip the first command.

"@
    $script:Statuses.Add('claude:instructions-printed')
}

# ------ Gemini CLI -----------------------------------------------------------
function Install-GeminiCli {
    if (-not (Test-ShouldInstall 'gemini')) { return }
    if (-not (Test-HostInstalled 'gemini')) {
        Write-Info 'Gemini CLI not found on PATH - skipping'
        $script:Statuses.Add('gemini:not-installed')
        return
    }
    Write-Info 'Installing for Gemini CLI'

    $already = $false
    try {
        $existing = & gemini extensions list 2>$null
        if ($LASTEXITCODE -eq 0 -and $existing -match [regex]::Escape($script:PluginName)) {
            $already = $true
        }
    } catch {
        # list command may error if nothing is installed; treat as "not already installed"
        $already = $false
    }

    if ($already) {
        Invoke-Step "gemini extensions update $script:PluginName" {
            & gemini extensions update $script:PluginName
            if ($LASTEXITCODE -ne 0) {
                Write-Warn 'Gemini update failed; try uninstall + reinstall'
                $script:Statuses.Add('gemini:update-failed')
                return
            }
        }
    } else {
        Invoke-Step "gemini extensions install $script:RepoUrl --auto-update" {
            & gemini extensions install $script:RepoUrl --auto-update
            if ($LASTEXITCODE -ne 0) {
                Write-Err 'Gemini install failed'
                $script:Statuses.Add('gemini:failed')
                return
            }
        }
    }
    Write-Success 'Gemini CLI: installed'
    $script:Statuses.Add('gemini:installed')
}

# ------ Codex CLI ------------------------------------------------------------
function Install-CodexCli {
    if (-not (Test-ShouldInstall 'codex')) { return }
    Write-Info 'Installing for Codex CLI'

    # git is a hard dependency for clone-based install; probe explicitly.
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Warn 'git not found on PATH - install Git for Windows from https://git-scm.com/download/win'
        $script:Statuses.Add('codex:failed')
        return
    }

    $target = Join-Path $env:USERPROFILE '.codex\plugins\litestar'
    $parentDir = Split-Path $target

    if ((Test-Path (Join-Path $target '.git')) -and (-not $Force)) {
        Invoke-Step "Pulling latest in $target" {
            & git -C $target fetch --quiet
            & git -C $target reset --hard origin/HEAD --quiet
        }
    } else {
        if (Test-Path $target) {
            if ($Force) {
                Invoke-Step "Removing existing $target" {
                    Remove-Item $target -Recurse -Force
                }
            } else {
                Write-Warn "$target exists but is not a git repo. Use -Force to overwrite."
                $script:Statuses.Add('codex:path-conflict')
                return
            }
        }
        Invoke-Step "Creating $parentDir" {
            New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
        }
        Invoke-Step "git clone --depth 1 $script:RepoUrl $target" {
            & git clone --quiet --depth 1 $script:RepoUrl $target
            if ($LASTEXITCODE -ne 0) {
                Write-Err "git clone failed"
                $script:Statuses.Add('codex:failed')
                return
            }
        }
    }
    Write-Success "Codex CLI: installed at $target (includes .codex/agents/litestar-reviewer.toml)"
    $script:Statuses.Add('codex:installed')
}

# ------ OpenCode -------------------------------------------------------------
function Install-OpenCode {
    if (-not (Test-ShouldInstall 'opencode')) { return }
    Write-Info 'Installing for OpenCode'

    $target = Join-Path $env:APPDATA 'opencode\plugins\litestar.js'
    $source = Join-Path $script:RepoRoot '.opencode\plugins\litestar.js'
    $targetDir = Split-Path $target

    if (-not (Test-Path $source)) {
        Write-Warn "OpenCode plugin source not found at $source - are you running from a repo clone?"
        $script:Statuses.Add('opencode:source-missing')
        return
    }
    if ((Test-Path $target) -and (-not $Force)) {
        Write-Info "OpenCode plugin already at $target (use -Force to overwrite)"
        $script:Statuses.Add('opencode:already-installed')
        return
    }

    Invoke-Step "Creating $targetDir" {
        New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
    }
    Invoke-Step "Copy-Item $source -> $target" {
        Copy-Item $source $target -Force
    }
    Write-Success "OpenCode: installed at $target (file copy; re-run -Force after repo updates)"
    $script:Statuses.Add('opencode:installed')
}

# ------ Cursor (instructions) ------------------------------------------------
function Install-Cursor {
    if (-not (Test-ShouldInstall 'cursor')) { return }
    Write-Info 'Cursor setup'
    Write-Host @"

Cursor reads SKILL.md from any path added as a Remote Rule:

  Cursor -> Settings -> Rules -> Add Remote Rule -> $script:RepoUrl

Cursor also reads .agents/skills/ and .cursor/skills/ natively in projects --
drop the skills/ tree from this repo into either path for local install.

"@
    $script:Statuses.Add('cursor:instructions-printed')
}

# ------ Google Antigravity (opt-in workspace symlink) -----------------------
function Install-AntigravitySymlink {
    # Opt-in workaround: Antigravity reads `.agent\skills\` (singular) while
    # this repo + Claude/OpenCode/VS Code all use `.agents\skills\` (plural).
    # Windows symlinks require Developer Mode or admin rights; Copy-Item is
    # offered as a fallback when New-Item -ItemType SymbolicLink fails.
    if (-not $AntigravitySymlink) { return }

    Write-Info 'Antigravity workspace symlink'
    $skillsDir = Join-Path $PWD '.agents\skills'
    $target = Join-Path $PWD '.agent'

    if (-not (Test-Path $skillsDir)) {
        Write-Warn "No .agents\skills\ in $PWD - install skills there first, then re-run with -AntigravitySymlink"
        $script:Statuses.Add('antigravity:no-skills-dir')
        return
    }
    if (Test-Path $target) {
        Write-Warn ".agent already exists in $PWD - refusing to overwrite (remove it manually if intentional)"
        $script:Statuses.Add('antigravity:path-conflict')
        return
    }

    Invoke-Step "New-Item -ItemType SymbolicLink -Path $target -Target .agents" {
        try {
            New-Item -ItemType SymbolicLink -Path $target -Target '.agents' | Out-Null
        } catch {
            Write-Warn "Symlink failed: $($_.Exception.Message). Enable Developer Mode or run as admin, or copy .agents to .agent manually."
            $script:Statuses.Add('antigravity:symlink-failed')
            return
        }
    }
    if (Test-Path $target) {
        Write-Warn 'Created .agent -> .agents symlink (community workaround; not a Google-blessed integration)'
        $script:Statuses.Add('antigravity:symlinked')
    }
}

# ------ VS Code / Copilot (instructions) -------------------------------------
function Install-VsCode {
    if (-not (Test-ShouldInstall 'vscode')) { return }
    Write-Info 'VS Code / Copilot setup'
    $target = Join-Path $env:USERPROFILE '.copilot\litestar'
    Write-Host @"

Clone the repo and point chat.skillsLocations at it:

  git clone $script:RepoUrl $target

Then in VS Code settings.json:

  "chat.skillsLocations": {
    "$target\\skills": true
  }

VS Code reads .github/skills/, .claude/skills/, and .agents/skills/ in any
open project natively if you prefer per-project install.

"@
    $script:Statuses.Add('vscode:instructions-printed')
}

# =============================================================================
# Host registry (mirrors install.sh host list)
# =============================================================================
$script:HostRegistry = [ordered]@{
    'claude'   = @{ Command = 'claude';   Install = { Install-ClaudeCode } }
    'gemini'   = @{ Command = 'gemini';   Install = { Install-GeminiCli } }
    'codex'    = @{ Command = 'codex';    Install = { Install-CodexCli } }
    'opencode' = @{ Command = 'opencode'; Install = { Install-OpenCode } }
    'cursor'   = @{ Command = 'cursor';   Install = { Install-Cursor } }
    'vscode'   = @{ Command = 'code';     Install = { Install-VsCode } }
}

function Invoke-HostProbe {
    Write-Info 'Detecting installed CLIs...'
    $detected = [System.Collections.Generic.List[string]]::new()
    foreach ($name in $script:HostRegistry.Keys) {
        $cmd = $script:HostRegistry[$name].Command
        # Explicit Get-Command call per host so trace logs show what was probed.
        $resolved = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($null -ne $resolved) {
            $detected.Add($name)
            Write-Verbose "Found $name at $($resolved.Source)"
        }
    }
    if ($detected.Count -eq 0) {
        Write-Warn 'No supported CLIs detected. Instructions will still be printed.'
    } else {
        Write-Success "Detected: $($detected -join ', ')"
    }
}

function Write-Summary {
    Write-Host ''
    Write-Host '=== Install Summary ===' -ForegroundColor White
    foreach ($entry in $script:Statuses) {
        $parts = $entry -split ':', 2
        $hostName = $parts[0]
        $status = $parts[1]
        switch -Wildcard ($status) {
            'installed'              { Write-Success ("{0,-12} {1}" -f $hostName, $status) }
            'symlinked'              { Write-Success ("{0,-12} {1}" -f $hostName, $status) }
            'instructions-printed'   { Write-Success ("{0,-12} {1}" -f $hostName, $status) }
            'already-installed'      { Write-Info    ("{0,-12} {1}" -f $hostName, $status) }
            'not-installed'          { Write-Info    ("{0,-12} CLI not present; skipped" -f $hostName) }
            'no-skills-dir'          { Write-Info    ("{0,-12} no .agents/skills/ in PWD; skipped" -f $hostName) }
            'source-missing'         { Write-Warn    ("{0,-12} {1}" -f $hostName, $status) }
            '*-failed'               { Write-Err     ("{0,-12} {1}" -f $hostName, $status) }
            '*-conflict'             { Write-Err     ("{0,-12} {1}" -f $hostName, $status) }
            default                  { Write-Info    ("{0,-12} {1}" -f $hostName, $status) }
        }
    }
    Write-Host ''
    if ($DryRun) {
        Write-Info 'Dry-run complete. Re-run without -DryRun to execute.'
    } else {
        Write-Success 'Installation complete.'
    }
}

# =============================================================================
# Main
# =============================================================================
function Invoke-Main {
    Write-Host "litestar-skills installer v$script:Version (Windows / PowerShell 7+)" -ForegroundColor White
    Write-Host ''
    if ($DryRun) { Write-Warn 'Dry-run mode: no changes will be applied' }

    Invoke-HostProbe
    Write-Host ''

    # Validate -Only / -Skip host names up front
    $validHosts = @($script:HostRegistry.Keys)
    foreach ($name in (@($Only) + @($Skip))) {
        if ($name -and -not ($validHosts -contains $name)) {
            Write-Warn "Unknown host '$name' - valid values: $($validHosts -join ', ')"
        }
    }

    foreach ($hostName in $script:HostRegistry.Keys) {
        $spec = $script:HostRegistry[$hostName]
        & $spec.Install
    }

    Install-AntigravitySymlink

    Write-Summary

    # Exit non-zero if any failure / conflict was recorded
    foreach ($entry in $script:Statuses) {
        if ($entry -match ':(failed|path-conflict|update-failed|symlink-failed)$') {
            exit 1
        }
    }
    exit 0
}

Invoke-Main
