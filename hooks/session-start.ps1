#!/usr/bin/env pwsh
# Litestar SessionStart context hook — Native PowerShell 5.1+ / 7+.
# Supports: --harness <agy|claude|cursor|opencode|json> --project <dir>

$ErrorActionPreference = "Stop"

if ($env:LITESTAR_SKILLS_HOOK_DISABLE -eq "1" -or $env:LITESTAR_SKILLS_HOOK_DISABLE -eq "true") {
    [Console]::Out.WriteLine("{}")
    exit 0
}

$Harness = "claude"
$ProjectDir = ""

for ($i = 0; $i -lt $args.Count; $i++) {
    $arg = [string]$args[$i]
    if ($arg -eq "--harness" -or $arg -eq "-Harness") {
        if ($i + 1 -lt $args.Count) {
            $Harness = [string]$args[$i + 1]
            $i++
        }
    } elseif ($arg -like "--harness=*") {
        $Harness = $arg.Substring(10)
    } elseif ($arg -like "-Harness=*") {
        $Harness = $arg.Substring(9)
    } elseif ($arg -eq "--project" -or $arg -eq "-Project") {
        if ($i + 1 -lt $args.Count) {
            $ProjectDir = [string]$args[$i + 1]
            $i++
        }
    } elseif ($arg -like "--project=*") {
        $ProjectDir = $arg.Substring(10)
    } elseif ($arg -like "-Project=*") {
        $ProjectDir = $arg.Substring(9)
    }
}

if ($Harness -eq "claude" -and -not [string]::IsNullOrEmpty($env:CURSOR_VERSION)) {
    [Console]::Out.WriteLine('{"continue":true}')
    exit 0
}

if (-not $ProjectDir -and [Console]::IsInputRedirected) {
    try {
        $StdinText = [Console]::In.ReadToEnd()
        if ($StdinText) {
            foreach ($pattern in @(
                '"workspacePaths"\s*:\s*\[\s*"([^"]+)"',
                '"workspace_roots"\s*:\s*\[\s*"([^"]+)"',
                '"cwd"\s*:\s*"([^"]+)"',
                '"workspaceRoot"\s*:\s*"([^"]+)"'
            )) {
                $m = [regex]::Match($StdinText, $pattern)
                if ($m.Success) {
                    $ProjectDir = $m.Groups[1].Value -replace '\\\\', '/'
                    break
                }
            }
        }
    } catch {
        # Ignore malformed stdin
    }
}

if (-not $ProjectDir) {
    if ($env:CURSOR_PROJECT_DIR) {
        $ProjectDir = $env:CURSOR_PROJECT_DIR
    } elseif ($env:CLAUDE_PROJECT_DIR) {
        $ProjectDir = $env:CLAUDE_PROJECT_DIR
    } else {
        $ProjectDir = (Get-Location).Path
    }
}

$DetectedSkills = New-Object System.Collections.Generic.List[string]
function Add-Skill([string]$Name) {
    if (-not $DetectedSkills.Contains($Name)) {
        $DetectedSkills.Add($Name)
    }
}

$PyprojectPath = Join-Path $ProjectDir "pyproject.toml"
$OwnPackage = ""
$IsPluginRepo = $false
$IsUpstream = $false
$HasCore = $false
$UpstreamPackages = @(
    "litestar",
    "advanced-alchemy",
    "sqlspec",
    "msgspec",
    "litestar-granian",
    "litestar-saq",
    "litestar-queues",
    "litestar-security",
    "litestar-autowire",
    "litestar-vite",
    "litestar-htmx",
    "litestar-mcp",
    "litestar-email",
    "pytest-databases",
    "polyfactory"
)

if (Test-Path -LiteralPath $PyprojectPath) {
    $Content = Get-Content -LiteralPath $PyprojectPath -Raw -ErrorAction SilentlyContinue
    if ($Content -match '(?ms)^\[project\].*?^\s*name\s*=\s*"([^"]+)"') {
        $OwnPackage = $Matches[1].ToLowerInvariant().Replace("_", "-")
    }
    if ($OwnPackage -eq "litestar-skills") {
        $IsPluginRepo = $true
        Add-Skill 'litestar-styleguide'
    } else {
        if ($UpstreamPackages -contains $OwnPackage) {
            $IsUpstream = $true
            $HasCore = $true
        }
        if ($Content -match '(?i)litestar') {
            $HasCore = $true
            if ($OwnPackage -ne 'litestar') { Add-Skill 'litestar' }
        }
        if ($Content -match '(?i)advanced[-_]alchemy') {
            $HasCore = $true
            if ($OwnPackage -ne 'advanced-alchemy') { Add-Skill 'advanced-alchemy' }
        }
        if ($Content -match '(?i)sqlspec') {
            $HasCore = $true
            if ($OwnPackage -ne 'sqlspec') { Add-Skill 'sqlspec' }
        }
        if ($Content -match '(?i)msgspec') {
            $HasCore = $true
            if ($OwnPackage -ne 'msgspec') { Add-Skill 'msgspec' }
        }
        if ($Content -match '(?i)litestar[-_]granian') {
            $HasCore = $true
            if ($OwnPackage -ne 'litestar-granian') { Add-Skill 'litestar-granian' }
        }
        if ($Content -match '(?i)litestar[-_]saq') {
            $HasCore = $true
            if ($OwnPackage -ne 'litestar-saq') { Add-Skill 'litestar-saq' }
        }
        if ($Content -match '(?i)litestar[-_]queues') {
            $HasCore = $true
            if ($OwnPackage -ne 'litestar-queues') { Add-Skill 'litestar-queues' }
        }
        if ($Content -match '(?i)litestar[-_]security') {
            $HasCore = $true
            if ($OwnPackage -ne 'litestar-security') { Add-Skill 'litestar-security' }
        }
        if ($Content -match '(?i)litestar[-_]autowire') {
            $HasCore = $true
            if ($OwnPackage -ne 'litestar-autowire') { Add-Skill 'litestar-autowire' }
        }
        if ($Content -match '(?i)litestar[-_]vite') {
            $HasCore = $true
            if ($OwnPackage -ne 'litestar-vite') { Add-Skill 'litestar-vite' }
        }
        if ($Content -match '(?i)litestar[-_]htmx') {
            $HasCore = $true
            if ($OwnPackage -ne 'litestar-htmx') { Add-Skill 'litestar-htmx' }
        }
        if ($Content -match '(?i)litestar[-_]mcp') {
            $HasCore = $true
            if ($OwnPackage -ne 'litestar-mcp') { Add-Skill 'litestar-mcp' }
        }
        if ($Content -match '(?i)litestar[-_]email') {
            $HasCore = $true
            if ($OwnPackage -ne 'litestar-email') { Add-Skill 'litestar-email' }
        }
        if ($Content -match '(?i)pytest[-_]databases') {
            $HasCore = $true
            if ($OwnPackage -ne 'pytest-databases') { Add-Skill 'pytest-databases' }
        }
        if ($Content -match '(?i)polyfactory') {
            $HasCore = $true
            if ($OwnPackage -ne 'polyfactory') { Add-Skill 'polyfactory' }
        }
        if ($Content -match '(?i)litestar[-_]sphinx[-_]theme') {
            $HasCore = $true
            Add-Skill 'litestar-docs'
        }
        if ($HasCore) {
            if ($Content -match '(?i)granian' -and $OwnPackage -ne 'litestar-granian') { Add-Skill 'litestar-granian' }
            if ($Content -match '(?i)google[-_]adk|google[-_]genai' -and $OwnPackage -ne 'litestar-mcp') { Add-Skill 'litestar-mcp' }
            if ($Content -match '(?i)pytest') { Add-Skill 'litestar-testing' }
            if ($Content -match '(?i)zensical|mkdocstrings|shibuya') { Add-Skill 'litestar-docs' }
        }
    }
}

if ($HasCore -and -not $IsPluginRepo) {
    if ((Test-Path -LiteralPath (Join-Path $ProjectDir "zensical.toml")) -or (Test-Path -LiteralPath (Join-Path $ProjectDir "docs/conf.py"))) {
        Add-Skill 'litestar-docs'
    }
    if (((Test-Path -LiteralPath (Join-Path $ProjectDir "vite.config.ts")) -or (Test-Path -LiteralPath (Join-Path $ProjectDir "vite.config.js")) -or (Test-Path -LiteralPath (Join-Path $ProjectDir "vite.config.mjs"))) -and $OwnPackage -ne 'litestar-vite') {
        Add-Skill 'litestar-vite'
    }
    if ((Test-Path -LiteralPath (Join-Path $ProjectDir "alembic.ini")) -and $OwnPackage -ne 'advanced-alchemy' -and $OwnPackage -ne 'sqlspec') {
        Add-Skill 'advanced-alchemy'
    }
    if ((Test-Path -LiteralPath (Join-Path $ProjectDir "Dockerfile")) -or (Test-Path -LiteralPath (Join-Path $ProjectDir "Containerfile"))) {
        Add-Skill 'litestar-deployment'
    }
    Add-Skill 'litestar-styleguide'
}

if ($DetectedSkills.Count -eq 0 -and -not $IsUpstream -and -not $IsPluginRepo) {
    switch ($Harness) {
        "agy" {
            [Console]::Out.WriteLine("{}")
        }
        "antigravity" {
            [Console]::Out.WriteLine("{}")
        }
        "cursor" {
            [Console]::Out.WriteLine('{"continue":true}')
        }
        "opencode" {
        }
        "json" {
            [Console]::Out.WriteLine('{"detected_skills":[],"context":""}')
        }
        default {
            [Console]::Out.WriteLine('{"continue":true}')
        }
    }
    exit 0
}

$SkillList = $DetectedSkills -join ' '
if ($IsPluginRepo) {
    $Context = "Litestar skills plugin workspace (skills: $SkillList). Follow skills/litestar-styleguide and validate all changes with make check."
} elseif ($IsUpstream) {
    $Context = "Litestar upstream package workspace ('$OwnPackage'; companion skills: $SkillList). Treat this repository's own source code and tests as the authority over its consumer skill; keep async I/O and PEP 604 unions (T | None)."
} else {
    $Context = "Litestar ecosystem detected in workspace (skills: $SkillList). Load the matching skill before writing, refactoring, or reviewing code; match the project's existing stack (SQLSpec vs Advanced Alchemy, Provide vs Dishka, msgspec vs Pydantic, Zensical vs Sphinx); keep handlers, guards, dependencies, and I/O async with PEP 604 unions (T | None)."
}

switch ($Harness) {
    "agy" {
        $Out = @{ injectSteps = @(@{ systemMessage = @{ systemMessage = $Context } }) }
        $Out | ConvertTo-Json -Compress -Depth 5
    }
    "antigravity" {
        $Out = @{ injectSteps = @(@{ systemMessage = @{ systemMessage = $Context } }) }
        $Out | ConvertTo-Json -Compress -Depth 5
    }
    "cursor" {
        $Out = [ordered]@{
            continue = $true
            additional_context = $Context
        }
        $Out | ConvertTo-Json -Compress -Depth 5
    }
    "opencode" {
        Write-Output $Context
    }
    "json" {
        $Out = @{ detected_skills = $DetectedSkills; context = $Context }
        $Out | ConvertTo-Json -Compress -Depth 5
    }
    default {
        $Out = [ordered]@{
            continue = $true
            hookSpecificOutput = [ordered]@{
                hookEventName = "SessionStart"
                additionalContext = $Context
            }
        }
        $Out | ConvertTo-Json -Compress -Depth 5
    }
}
