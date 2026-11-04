"""Validate manifests, hooks, subagents, skills, links, and repository layout."""

from __future__ import annotations

import json
import os
import re
import sys
import tomllib as _tomllib
from pathlib import Path
from typing import Any, TypeGuard

__all__ = [
    "ALLOWED_ANTIGRAVITY_PLUGIN_KEYS",
    "BUMPVERSION_EXPECTED_FILES",
    "FENCED_BLOCK_RE",
    "FORBIDDEN_DESCRIPTION_TERMS",
    "FRONTMATTER_RE",
    "INLINE_CODE_RE",
    "MAX_DESCRIPTION_CHARS",
    "MAX_SKILL_BYTES",
    "MD_LINK_RE",
    "PLUGIN_ID",
    "REPO_NAME",
    "REPO_ROOT",
    "REQUIRED_SKILL_XML_TAGS",
    "RETIRED_SPRAWL_PATHS",
    "main",
    "parse_simple_frontmatter",
    "validate_anti_sprawl",
    "validate_hooks",
    "validate_manifests",
    "validate_markdown_links",
    "validate_repository",
    "validate_skills",
    "validate_subagents",
]

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ID = "litestar"
REPO_NAME = "litestar-skills"
MAX_SKILL_BYTES = 24_000
MAX_DESCRIPTION_CHARS = 500
ALLOWED_ANTIGRAVITY_PLUGIN_KEYS: frozenset[str] = frozenset(
    {
        "$schema",
        "name",
        "displayName",
        "version",
        "description",
        "contextFileName",
        "excludeTools",
        "skills",
        "agents",
        "rules",
        "mcpServers",
        "apps",
    }
)
FORBIDDEN_DESCRIPTION_TERMS = (
    "Auto-activate",
    "Produces",
    "Expert knowledge",
    "Comprehensive",
)
REQUIRED_SKILL_XML_TAGS = (
    "<workflow>",
    "</workflow>",
    "<guardrails>",
    "</guardrails>",
    "<validation>",
    "</validation>",
    "<example>",
    "</example>",
)
RETIRED_SPRAWL_PATHS = (
    "CLAUDE.md",
    "GEMINI.md",
    ".github/agents",
    "plugins",
    "commands",
    "agents/claude",
    ".opencode/agents",
    ".opencode/INSTALL.md",
    ".codex/INSTALL.md",
    ".codex/hooks.json",
    ".codex/config.toml",
    "hooks/lib",
    "hooks/hooks.json",
    "hooks/hooks-agy.json",
    "hooks/hooks-codex.json",
    "hooks/run-hook.cmd",
    "hooks/session-start.js",
    "tools/agent-sources",
    "tools/generate-agents.py",
    "tools/sync-codex-package.py",
    "tools/sync-codex-package.sh",
    "tools/sync-manifests.py",
    "tools/validate-codex-manifest.py",
    "tools/validate-skills.py",
    "tools/install.sh",
    "tools/install.ps1",
    "tools/uninstall.sh",
)
BUMPVERSION_EXPECTED_FILES = {
    "package.json",
    "plugin.json",
    ".claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
    ".codex-plugin/plugin.json",
    ".cursor-plugin/plugin.json",
    ".agents/plugins/marketplace.json",
}
FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n?(.*)$", re.DOTALL)
FENCED_BLOCK_RE = re.compile(r"^(`{3,})[^\n]*\n.*?\n\1[ \t]*$", re.MULTILINE | re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
MD_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def parse_simple_frontmatter(raw: str) -> tuple[dict[str, str | list[str]], str] | None:
    """Parse YAML frontmatter supporting scalar values and simple string lists.

    Args:
        raw: Full Markdown file content.

    Returns:
        A tuple of ``(frontmatter_dict, body)`` or ``None`` when frontmatter is invalid.
    """
    match = FRONTMATTER_RE.match(raw)
    if not match:
        return None
    fm_block, body = match.group(1), match.group(2)
    result: dict[str, str | list[str]] = {}
    current_list_key: str | None = None
    for line in fm_block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            if current_list_key is None:
                return None
            item = stripped[2:].strip().strip('"').strip("'")
            existing = result.get(current_list_key)
            if isinstance(existing, list):
                existing.append(item)
            continue
        if ":" not in line:
            return None
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if not val:
            result[key] = []
            current_list_key = key
        else:
            current_list_key = None
            result[key] = val.strip('"').strip("'")
    return result, body


def validate_manifests(repo_root: Path, errors: list[str]) -> None:
    """Validate version synchronization and single-root paths across all 8 manifests."""
    pyproject_path = repo_root / "pyproject.toml"
    if not pyproject_path.is_file():
        errors.append(f"Missing required manifest: {pyproject_path}")
        return
    try:
        pyproject_data: dict[str, Any] = _tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except (_tomllib.TOMLDecodeError, OSError) as exc:
        errors.append(f"Invalid TOML in {pyproject_path}: {exc}")
        return

    project_raw = pyproject_data.get("project")
    project_table = project_raw if _is_str_dict(project_raw) else {}
    expected_version = project_table.get("version")
    if not isinstance(expected_version, str) or not expected_version:
        errors.append("pyproject.toml missing project.version")
        return
    if project_table.get("name") != REPO_NAME:
        errors.append(f"pyproject.toml project.name must be {REPO_NAME!r}")

    tool_raw = pyproject_data.get("tool")
    tool_table = tool_raw if _is_str_dict(tool_raw) else {}
    bump_raw = tool_table.get("bumpversion")
    bump_table = bump_raw if _is_str_dict(bump_raw) else {}
    files_raw = bump_table.get("files")
    files_list = files_raw if _is_any_list(files_raw) else []
    bumpversion_files: set[str] = set()
    for item in files_list:
        if _is_str_dict(item):
            filename = item.get("filename")
            if isinstance(filename, str):
                bumpversion_files.add(filename)

    missing_bump_files = BUMPVERSION_EXPECTED_FILES - bumpversion_files
    if missing_bump_files:
        errors.append(f"pyproject.toml [[tool.bumpversion.files]] missing manifests: {sorted(missing_bump_files)}")

    pkg_data = _load_json(repo_root / "package.json", errors)
    if pkg_data is not None:
        if pkg_data.get("name") != REPO_NAME:
            errors.append(f"package.json name must be {REPO_NAME!r}")
        if pkg_data.get("version") != expected_version:
            errors.append(f"package.json version {pkg_data.get('version')!r} != {expected_version!r}")
        if pkg_data.get("main") != f".opencode/plugins/{PLUGIN_ID}.js":
            errors.append(f"package.json main must be '.opencode/plugins/{PLUGIN_ID}.js'")

    agy_plugin = _load_json(repo_root / "plugin.json", errors)
    if agy_plugin is not None:
        if agy_plugin.get("name") != PLUGIN_ID:
            errors.append(f"plugin.json name must be {PLUGIN_ID!r}")
        if agy_plugin.get("version") != expected_version:
            errors.append(f"plugin.json version {agy_plugin.get('version')!r} != {expected_version!r}")
        for required_key in ("$schema", "displayName", "description"):
            if not agy_plugin.get(required_key):
                errors.append(f"plugin.json missing required field {required_key!r}")
        disallowed_keys = sorted(set(agy_plugin.keys()) - ALLOWED_ANTIGRAVITY_PLUGIN_KEYS)
        if disallowed_keys:
            errors.append(f"plugin.json disallowed Antigravity manifest keys: {disallowed_keys}")

    claude_plugin = _load_json(repo_root / ".claude-plugin" / "plugin.json", errors)
    if claude_plugin is not None:
        if claude_plugin.get("name") != PLUGIN_ID:
            errors.append(f".claude-plugin/plugin.json name must be {PLUGIN_ID!r}")
        if claude_plugin.get("version") != expected_version:
            errors.append(
                f".claude-plugin/plugin.json version {claude_plugin.get('version')!r} != {expected_version!r}"
            )
        if claude_plugin.get("hooks") != "./hooks/hooks-claude.json":
            errors.append(".claude-plugin/plugin.json hooks must be './hooks/hooks-claude.json'")
        for forbidden_key in ("skills", "commands"):
            if forbidden_key in claude_plugin:
                errors.append(f".claude-plugin/plugin.json must not declare {forbidden_key!r}")

    claude_mp = _load_json(repo_root / ".claude-plugin" / "marketplace.json", errors)
    if claude_mp is not None:
        plugins = claude_mp.get("plugins")
        if not _is_any_list(plugins) or len(plugins) != 1 or not _is_str_dict(plugins[0]):
            errors.append(".claude-plugin/marketplace.json must contain a single plugin entry")
        else:
            entry = plugins[0]
            if entry.get("name") != PLUGIN_ID:
                errors.append(f".claude-plugin/marketplace.json plugin name must be {PLUGIN_ID!r}")
            if entry.get("version") != expected_version:
                errors.append(
                    f".claude-plugin/marketplace.json version {entry.get('version')!r} != {expected_version!r}"
                )
            if entry.get("source") != "./":
                errors.append(".claude-plugin/marketplace.json source must be './'")
            if "commands" in entry:
                errors.append(".claude-plugin/marketplace.json must not declare 'commands'")

    codex_plugin = _load_json(repo_root / ".codex-plugin" / "plugin.json", errors)
    if codex_plugin is not None:
        if codex_plugin.get("name") != PLUGIN_ID:
            errors.append(f".codex-plugin/plugin.json name must be {PLUGIN_ID!r}")
        if codex_plugin.get("version") != expected_version:
            errors.append(f".codex-plugin/plugin.json version {codex_plugin.get('version')!r} != {expected_version!r}")
        if codex_plugin.get("skills") not in ("./skills", "./skills/"):
            errors.append(".codex-plugin/plugin.json skills must be './skills/'")
        if codex_plugin.get("hooks") != "./hooks/hooks-claude.json":
            errors.append(".codex-plugin/plugin.json hooks must be './hooks/hooks-claude.json'")

    cursor_plugin = _load_json(repo_root / ".cursor-plugin" / "plugin.json", errors)
    if cursor_plugin is not None:
        if cursor_plugin.get("name") != PLUGIN_ID:
            errors.append(f".cursor-plugin/plugin.json name must be {PLUGIN_ID!r}")
        if cursor_plugin.get("version") != expected_version:
            errors.append(
                f".cursor-plugin/plugin.json version {cursor_plugin.get('version')!r} != {expected_version!r}"
            )
        if cursor_plugin.get("hooks") not in ("./hooks/hooks-cursor.json", "hooks/hooks-cursor.json"):
            errors.append(".cursor-plugin/plugin.json hooks must be './hooks/hooks-cursor.json'")
        for forbidden_key in ("skills", "commands"):
            if forbidden_key in cursor_plugin:
                errors.append(f".cursor-plugin/plugin.json must not declare {forbidden_key!r}")

    agents_mp = _load_json(repo_root / ".agents" / "plugins" / "marketplace.json", errors)
    if agents_mp is not None:
        plugins = agents_mp.get("plugins")
        if not _is_any_list(plugins) or len(plugins) != 1 or not _is_str_dict(plugins[0]):
            errors.append(".agents/plugins/marketplace.json must contain a single plugin entry")
        else:
            entry = plugins[0]
            if entry.get("name") != PLUGIN_ID:
                errors.append(f".agents/plugins/marketplace.json plugin name must be {PLUGIN_ID!r}")
            if entry.get("version") != expected_version:
                errors.append(
                    f".agents/plugins/marketplace.json version {entry.get('version')!r} != {expected_version!r}"
                )
            source = entry.get("source")
            if not _is_str_dict(source) or source.get("path") != "./":
                errors.append(".agents/plugins/marketplace.json source.path must be './'")


def validate_hooks(repo_root: Path, errors: list[str]) -> None:
    """Validate SessionStart hook manifests, scripts, OpenCode plugin, and Antigravity rules."""
    agy_hooks = _load_json(repo_root / "hooks.json", errors)
    if agy_hooks is not None:
        if "hooks" in agy_hooks:
            errors.append("hooks.json must not wrap hooks under a top-level 'hooks' key")
        priming = agy_hooks.get(f"{PLUGIN_ID}-priming")
        session_start = priming.get("SessionStart") if _is_str_dict(priming) else None
        if not _is_any_list(session_start) or not session_start or not _is_str_dict(session_start[0]):
            errors.append(f"hooks.json missing '{PLUGIN_ID}-priming.SessionStart' list")
        else:
            cmd = session_start[0].get("command", "")
            if cmd != "sh ./hooks/session-start.sh --harness agy":
                errors.append(f"hooks.json unexpected command {cmd!r}")

    claude_hooks = _load_json(repo_root / "hooks" / "hooks-claude.json", errors)
    if claude_hooks is not None:
        hooks_table = claude_hooks.get("hooks")
        nested = hooks_table.get("SessionStart") if _is_str_dict(hooks_table) else None
        if not _is_any_list(nested) or not nested or not _is_str_dict(nested[0]):
            errors.append("hooks/hooks-claude.json missing 'hooks.SessionStart'")
        else:
            inner = nested[0].get("hooks")
            if not _is_any_list(inner) or not inner or not _is_str_dict(inner[0]):
                errors.append("hooks/hooks-claude.json missing inner hook definition")
            else:
                hook_def = inner[0]
                cmd_posix = hook_def.get("command")
                cmd_win = hook_def.get("commandWindows")
                if not isinstance(cmd_posix, str) or "session-start.sh" not in cmd_posix:
                    errors.append("hooks/hooks-claude.json missing POSIX session-start.sh command")
                if not isinstance(cmd_win, str) or "session-start.ps1" not in cmd_win:
                    errors.append("hooks/hooks-claude.json missing commandWindows PowerShell entry")

    cursor_hooks = _load_json(repo_root / "hooks" / "hooks-cursor.json", errors)
    if cursor_hooks is not None:
        cursor_table = cursor_hooks.get("hooks")
        nested_cursor = cursor_table.get("sessionStart") if _is_str_dict(cursor_table) else None
        if not _is_any_list(nested_cursor) or not nested_cursor or not _is_str_dict(nested_cursor[0]):
            errors.append("hooks/hooks-cursor.json missing 'hooks.sessionStart'")
        elif nested_cursor[0].get("command") != "sh ./hooks/session-start.sh --harness cursor":
            errors.append("hooks/hooks-cursor.json must invoke 'sh ./hooks/session-start.sh --harness cursor'")

    sh_script = repo_root / "hooks" / "session-start.sh"
    if not sh_script.is_file():
        errors.append("Missing hooks/session-start.sh")
    else:
        content = sh_script.read_text(encoding="utf-8")
        if not content.startswith("#!/bin/sh"):
            errors.append("hooks/session-start.sh must start with '#!/bin/sh'")
        if os.name != "nt" and not os.access(sh_script, os.X_OK):
            errors.append("hooks/session-start.sh must be executable (chmod +x)")

    ps1_script = repo_root / "hooks" / "session-start.ps1"
    if not ps1_script.is_file():
        errors.append("Missing hooks/session-start.ps1")

    opencode_plugin = repo_root / ".opencode" / "plugins" / f"{PLUGIN_ID}.js"
    if not opencode_plugin.is_file():
        errors.append(f"Missing .opencode/plugins/{PLUGIN_ID}.js")
    else:
        js_text = opencode_plugin.read_text(encoding="utf-8")
        if "node:fs" not in js_text or "node:path" not in js_text:
            errors.append(f".opencode/plugins/{PLUGIN_ID}.js must use in-process node:fs and node:path")
        if f'id: "{PLUGIN_ID}"' not in js_text or "async setup(ctx)" not in js_text:
            errors.append(
                f".opencode/plugins/{PLUGIN_ID}.js must export OpenCode V2 {{ id: '{PLUGIN_ID}', async setup(ctx) }}"
            )

    agy_rule = repo_root / "rules" / f"{PLUGIN_ID}-antigravity.md"
    if not agy_rule.is_file():
        errors.append(f"Missing rules/{PLUGIN_ID}-antigravity.md")


def validate_subagents(repo_root: Path, errors: list[str]) -> None:
    """Validate Markdown subagents in agents/ and matching Codex TOML agents."""
    agents_dir = repo_root / "agents"
    codex_agents_dir = repo_root / ".codex" / "agents"
    if not agents_dir.is_dir():
        errors.append("Missing agents/ directory")
        return

    md_agents = sorted(agents_dir.glob("*.md"))
    if not md_agents:
        errors.append("No subagent .md files found in agents/")
        return

    for md_path in md_agents:
        raw = md_path.read_text(encoding="utf-8")
        parsed = parse_simple_frontmatter(raw)
        if parsed is None:
            errors.append(f"{md_path}: invalid or missing YAML frontmatter")
            continue
        fm, body = parsed
        stem = md_path.stem
        if fm.get("name") != stem:
            errors.append(f"{md_path}: frontmatter name {fm.get('name')!r} != {stem!r}")
        if not isinstance(fm.get("description"), str) or not fm.get("description"):
            errors.append(f"{md_path}: missing non-empty description")
        if fm.get("model") != "inherit":
            errors.append(f"{md_path}: model must be 'inherit'")
        if fm.get("mainAgent") != "false":
            errors.append(f"{md_path}: mainAgent must be false")
        if fm.get("subagent") != "true":
            errors.append(f"{md_path}: subagent must be true")
        if fm.get("readonly") != "true":
            errors.append(f"{md_path}: readonly must be true")
        if fm.get("commandExecutionPolicy") != "off":
            errors.append(f"{md_path}: commandExecutionPolicy must be 'off'")

        for list_key in ("disallowedTools", "skills"):
            val = fm.get(list_key)
            if not isinstance(val, list) or not val:
                errors.append(f"{md_path}: {list_key!r} must be a non-empty YAML list")

        skills_list = fm.get("skills")
        if isinstance(skills_list, list):
            for skill_name in skills_list:
                if not (repo_root / "skills" / skill_name / "SKILL.md").is_file():
                    errors.append(f"{md_path}: references unknown skill {skill_name!r}")

        stripped_code = FENCED_BLOCK_RE.sub("", body)
        h1_matches = re.findall(r"^# .+$", stripped_code, flags=re.MULTILINE)
        h2_plus_matches = re.findall(r"^#{2,} .+$", stripped_code, flags=re.MULTILINE)
        if not h1_matches:
            errors.append(f"{md_path}: subagent body must contain '# ' H1 sections")
        if h2_plus_matches:
            errors.append(f"{md_path}: subagent body must use only '# ' H1 headings, found H2+")

        toml_path = codex_agents_dir / f"{stem}.toml"
        if not toml_path.is_file():
            errors.append(f"Missing matching Codex subagent: {toml_path}")
            continue
        try:
            toml_data: dict[str, Any] = _tomllib.loads(toml_path.read_text(encoding="utf-8"))
        except (_tomllib.TOMLDecodeError, OSError) as exc:
            errors.append(f"Invalid TOML in {toml_path}: {exc}")
            continue
        if toml_data.get("name") != stem:
            errors.append(f"{toml_path}: name must be {stem!r}")
        if not isinstance(toml_data.get("description"), str) or not toml_data.get("description"):
            errors.append(f"{toml_path}: missing description")
        if not isinstance(toml_data.get("developer_instructions"), str) or not toml_data.get("developer_instructions"):
            errors.append(f"{toml_path}: missing developer_instructions")
        if "tools" in toml_data:
            errors.append(f"{toml_path}: must not declare top-level 'tools'")
        if toml_data.get("sandbox_mode") != "read-only":
            errors.append(f"{toml_path}: read-only subagent must set sandbox_mode = 'read-only'")


def validate_skills(repo_root: Path, errors: list[str]) -> None:
    """Validate skill byte budgets, frontmatter rules, and required XML tags."""
    skills_dir = repo_root / "skills"
    if not skills_dir.is_dir():
        errors.append("Missing skills/ directory")
        return

    skill_dirs = sorted(p for p in skills_dir.iterdir() if p.is_dir())
    if not skill_dirs:
        errors.append("No skill directories found in skills/")
        return

    for skill_dir in skill_dirs:
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            errors.append(f"Missing SKILL.md in {skill_dir}")
            continue
        raw_bytes = skill_md.read_bytes()
        if len(raw_bytes) >= MAX_SKILL_BYTES:
            errors.append(f"{skill_md}: size {len(raw_bytes)} bytes exceeds {MAX_SKILL_BYTES} byte limit")
        raw_text = raw_bytes.decode("utf-8")
        parsed = parse_simple_frontmatter(raw_text)
        if parsed is None:
            errors.append(f"{skill_md}: invalid or missing YAML frontmatter")
            continue
        fm, body = parsed
        if fm.get("name") != skill_dir.name:
            errors.append(f"{skill_md}: frontmatter name {fm.get('name')!r} != directory {skill_dir.name!r}")
        desc = fm.get("description")
        if not isinstance(desc, str) or not desc:
            errors.append(f"{skill_md}: missing description")
        else:
            if not desc.startswith("Use when"):
                errors.append(f"{skill_md}: description must start with 'Use when'")
            if len(desc) > MAX_DESCRIPTION_CHARS:
                errors.append(f"{skill_md}: description length {len(desc)} > {MAX_DESCRIPTION_CHARS}")
            for forbidden in FORBIDDEN_DESCRIPTION_TERMS:
                if forbidden.lower() in desc.lower():
                    errors.append(f"{skill_md}: description contains forbidden phrase {forbidden!r}")

        for tag in REQUIRED_SKILL_XML_TAGS:
            if tag not in body:
                errors.append(f"{skill_md}: missing required XML tag {tag}")


def validate_markdown_links(repo_root: Path, errors: list[str]) -> None:
    """Validate that relative Markdown links resolve to existing files inside repo_root."""
    md_files: list[Path] = []
    for top_doc in ("README.md", "AGENTS.md", "CONTRIBUTING.md"):
        candidate = repo_root / top_doc
        if candidate.is_file():
            md_files.append(candidate)
    for folder in ("skills", "agents", "rules"):
        base = repo_root / folder
        if base.is_dir():
            md_files.extend(sorted(base.rglob("*.md")))

    resolved_root = repo_root.resolve()
    for md_file in md_files:
        text = md_file.read_text(encoding="utf-8")
        scrubbed = INLINE_CODE_RE.sub("", FENCED_BLOCK_RE.sub("", text))
        for match in MD_LINK_RE.finditer(scrubbed):
            raw_target = match.group(1).strip()
            if not raw_target or raw_target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            target_path_str = raw_target.split("#", 1)[0].split("?", 1)[0].strip()
            if not target_path_str:
                continue
            resolved_target = (md_file.parent / target_path_str).resolve()
            try:
                resolved_target.relative_to(resolved_root)
            except ValueError:
                errors.append(f"{md_file}: link {raw_target!r} escapes repository root")
                continue
            if not resolved_target.exists():
                errors.append(f"{md_file}: broken relative link {raw_target!r}")


def validate_anti_sprawl(repo_root: Path, errors: list[str]) -> None:
    """Validate absence of retired multi-harness sprawl paths and private lockfile URLs."""
    for rel_path in RETIRED_SPRAWL_PATHS:
        candidate = repo_root / rel_path
        if candidate.exists():
            errors.append(f"Retired sprawl path must not exist: {rel_path}")

    skills_dir = repo_root / "skills"
    if skills_dir.is_dir():
        for legacy_openai in sorted(skills_dir.glob("*/agents/openai.yaml")):
            errors.append(f"Retired sprawl path must not exist: {legacy_openai.relative_to(repo_root)}")

    uv_lock = repo_root / "uv.lock"
    if uv_lock.is_file():
        lock_text = uv_lock.read_text(encoding="utf-8")
        for url in re.findall(r'https?://[^\s"\']+', lock_text):
            if not (url.startswith("https://pypi.org/") or url.startswith("https://files.pythonhosted.org/")):
                errors.append(f"uv.lock contains non-PyPI URL: {url}")


def validate_repository(repo_root: Path = REPO_ROOT) -> list[str]:
    """Run all repository validation checks and return collected error messages."""
    errors: list[str] = []
    validate_manifests(repo_root, errors)
    validate_hooks(repo_root, errors)
    validate_subagents(repo_root, errors)
    validate_skills(repo_root, errors)
    validate_markdown_links(repo_root, errors)
    validate_anti_sprawl(repo_root, errors)
    return errors


def main() -> int:
    """CLI entry point for repository validation."""
    errors = validate_repository(REPO_ROOT)
    if errors:
        for err in errors:
            sys.stderr.write(f"ERROR: {err}\n")
        sys.stderr.write(f"\nValidation failed with {len(errors)} error(s).\n")
        return 1
    sys.stdout.write("All manifests, hooks, subagents, skills, and links validated.\n")
    return 0


def _is_str_dict(val: object) -> TypeGuard[dict[str, Any]]:
    """Return True when val is a dictionary with string keys."""
    return isinstance(val, dict)


def _is_any_list(val: object) -> TypeGuard[list[Any]]:
    """Return True when val is a list."""
    return isinstance(val, list)


def _load_json(path: Path, errors: list[str]) -> dict[str, Any] | None:
    """Load a JSON object from disk and append an error on failure."""
    if not path.is_file():
        errors.append(f"Missing required JSON file: {path}")
        return None
    try:
        data: object = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        errors.append(f"Invalid JSON in {path}: {exc}")
        return None
    if not _is_str_dict(data):
        errors.append(f"Expected JSON object in {path}")
        return None
    return data


if __name__ == "__main__":
    raise SystemExit(main())
