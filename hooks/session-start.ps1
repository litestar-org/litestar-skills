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
if (Test-Path -LiteralPath $PyprojectPath) {
    $Content = Get-Content -LiteralPath $PyprojectPath -Raw -ErrorAction SilentlyContinue
    if ($Content -match '(?ms)^\[project\].*?^\s*name\s*=\s*"([^"]+)"') {
        $OwnPackage = $Matches[1].ToLowerInvariant().Replace("_", "-")
    }
    if ($Content -match '(?i)litestar' -and $OwnPackage -ne 'litestar') { Add-Skill 'litestar' }
    if ($Content -match '(?i)advanced[-_]alchemy' -and $OwnPackage -ne 'advanced-alchemy') { Add-Skill 'advanced-alchemy' }
    if ($Content -match '(?i)sqlspec' -and $OwnPackage -ne 'sqlspec') { Add-Skill 'sqlspec' }
    if ($Content -match '(?i)msgspec' -and $OwnPackage -ne 'msgspec') { Add-Skill 'msgspec' }
    if ($Content -match '(?i)litestar[-_]granian|granian' -and $OwnPackage -ne 'litestar-granian') { Add-Skill 'litestar-granian' }
    if ($Content -match '(?i)litestar[-_]saq' -and $OwnPackage -ne 'litestar-saq') { Add-Skill 'litestar-saq' }
    if ($Content -match '(?i)litestar[-_]queues' -and $OwnPackage -ne 'litestar-queues') { Add-Skill 'litestar-queues' }
    if ($Content -match '(?i)litestar[-_]security' -and $OwnPackage -ne 'litestar-security') { Add-Skill 'litestar-security' }
    if ($Content -match '(?i)litestar[-_]autowire' -and $OwnPackage -ne 'litestar-autowire') { Add-Skill 'litestar-autowire' }
    if ($Content -match '(?i)litestar[-_]vite' -and $OwnPackage -ne 'litestar-vite') { Add-Skill 'litestar-vite' }
    if ($Content -match '(?i)litestar[-_]htmx' -and $OwnPackage -ne 'litestar-htmx') { Add-Skill 'litestar-htmx' }
    if ($Content -match '(?i)litestar[-_]mcp|google[-_]adk|google[-_]genai' -and $OwnPackage -ne 'litestar-mcp') { Add-Skill 'litestar-mcp' }
    if ($Content -match '(?i)litestar[-_]email' -and $OwnPackage -ne 'litestar-email') { Add-Skill 'litestar-email' }
    if ($Content -match '(?i)pytest') { Add-Skill 'litestar-testing' }
    if ($Content -match '(?i)pytest[-_]databases' -and $OwnPackage -ne 'pytest-databases') { Add-Skill 'pytest-databases' }
    if ($Content -match '(?i)polyfactory' -and $OwnPackage -ne 'polyfactory') { Add-Skill 'polyfactory' }
    if ($Content -match '(?i)zensical|mkdocstrings|shibuya|litestar[-_]sphinx[-_]theme') { Add-Skill 'litestar-docs' }
}

if ((Test-Path -LiteralPath (Join-Path $ProjectDir "zensical.toml")) -or (Test-Path -LiteralPath (Join-Path $ProjectDir "docs/conf.py"))) {
    Add-Skill 'litestar-docs'
}
if ((Test-Path -LiteralPath (Join-Path $ProjectDir "vite.config.ts")) -and $OwnPackage -ne 'litestar-vite') {
    Add-Skill 'litestar-vite'
}
if (Test-Path -LiteralPath (Join-Path $ProjectDir "Dockerfile")) {
    Add-Skill 'litestar-deployment'
}

if ($DetectedSkills.Count -gt 0) {
    $SkillSummary = "Detected Litestar stack skills for this workspace: $($DetectedSkills -join ' ')."
} else {
    $SkillSummary = "Available Litestar skills: litestar, sqlspec, advanced-alchemy, msgspec, litestar-granian, litestar-saq, litestar-queues, litestar-security, litestar-autowire, litestar-vite, litestar-htmx, litestar-mcp, litestar-email, litestar-testing, pytest-databases, polyfactory, litestar-docs, litestar-build, litestar-deployment, litestar-styleguide."
}

$Context = @"
<EXTREMELY_IMPORTANT>
Litestar Framework Ecosystem Active
$SkillSummary
- Activate the matching Litestar skill before writing, refactoring, or reviewing Litestar application or library code.
- Match the project's existing stack (SQLSpec vs Advanced Alchemy, Provide vs Dishka, msgspec vs Pydantic, Zensical vs Sphinx).
- Keep all route handlers, guards, dependencies, and I/O async; enforce PEP 604 unions (T | None).
</EXTREMELY_IMPORTANT>
"@ -replace "`r`n", "`n"

switch ($Harness) {
    "agy" {
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
            systemMessage = $Context
            hookSpecificOutput = [ordered]@{
                hookEventName = "SessionStart"
                additionalContext = $Context
            }
        }
        $Out | ConvertTo-Json -Compress -Depth 5
    }
}
