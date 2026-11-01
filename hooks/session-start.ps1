# Litestar SessionStart context hook — Native PowerShell 5.1+ / 7+.
# Supports: --harness <agy|claude|cursor|opencode|json> --project <dir>

$ErrorActionPreference = "Stop"

if ($env:LITESTAR_SKILLS_HOOK_DISABLE -eq "1" -or $env:LITESTAR_SKILLS_HOOK_DISABLE -eq "true") {
    Write-Output "{}"
    exit 0
}

$Harness = "claude"
$ProjectDir = ""

for ($i = 0; $i -lt $args.Count; $i++) {
    switch ($args[$i]) {
        "--harness" {
            if ($i + 1 -lt $args.Count) { $Harness = $args[$i + 1]; $i++ }
        }
        "--project" {
            if ($i + 1 -lt $args.Count) { $ProjectDir = $args[$i + 1]; $i++ }
        }
    }
}

if ($Harness -eq "claude" -and $env:CURSOR_VERSION) {
    Write-Output "{}"
    exit 0
}

if (-not $ProjectDir -and [Console]::IsInputRedirected) {
    try {
        $StdinText = [Console]::In.ReadToEnd()
        if ($StdinText) {
            $Payload = $StdinText | ConvertFrom-Json -ErrorAction SilentlyContinue
            if ($Payload.workspacePaths -and $Payload.workspacePaths.Count -gt 0) {
                $ProjectDir = $Payload.workspacePaths[0]
            } elseif ($Payload.cwd) {
                $ProjectDir = $Payload.cwd
            } elseif ($Payload.workspace_roots -and $Payload.workspace_roots.Count -gt 0) {
                $ProjectDir = $Payload.workspace_roots[0]
            }
        }
    } catch {
        # Ignore malformed stdin
    }
}

if (-not $ProjectDir) {
    if ($env:CLAUDE_PROJECT_DIR) {
        $ProjectDir = $env:CLAUDE_PROJECT_DIR
    } elseif ($env:CURSOR_PROJECT_DIR) {
        $ProjectDir = $env:CURSOR_PROJECT_DIR
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
    if ($Content -match '(?i)litestar[-_]mcp' -and $OwnPackage -ne 'litestar-mcp') { Add-Skill 'litestar-mcp' }
    if ($Content -match '(?i)litestar[-_]email' -and $OwnPackage -ne 'litestar-email') { Add-Skill 'litestar-email' }
    if ($Content -match '(?i)google[-_]adk|google[-_]genai') { Add-Skill 'litestar-ai' }
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
    $SkillSummary = "Available Litestar skills: litestar, sqlspec, advanced-alchemy, msgspec, litestar-granian, litestar-saq, litestar-queues, litestar-security, litestar-autowire, litestar-vite, litestar-htmx, litestar-mcp, litestar-email, litestar-ai, litestar-testing, pytest-databases, polyfactory, litestar-docs, litestar-build, litestar-deployment, litestar-styleguide."
}

$Context = @"
<EXTREMELY_IMPORTANT>
Litestar Framework Ecosystem Active (v0.10.0)
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
        $Out = @{ additional_context = $Context }
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
        $Out = @{
            hookSpecificOutput = @{
                hookEventName = "SessionStart"
                additionalContext = $Context
            }
            systemMessage = $Context
        }
        $Out | ConvertTo-Json -Compress -Depth 5
    }
}
