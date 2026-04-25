"""Generate per-host agent dialects from canonical YAML sources.

Reads ``tools/agent-sources/*.yaml`` and writes the four host dialects:

* ``agents/<name>.md``                    — Gemini CLI: YAML-list ``tools``
* ``.claude-plugin/agents/<name>.md``     — Claude Code: comma-string ``tools``
* ``.opencode/agents/<name>.md``          — OpenCode: dict ``tools`` + ``mode: subagent``
* ``.codex/agents/<name>.toml``           — Codex CLI: pure TOML, no ``tools``

CI gate: regenerate, ``git diff --exit-code`` fails if any hand edits drifted.

Usage:
    python3 tools/generate-agents.py            # regenerate all
    python3 tools/generate-agents.py --check    # exit 1 if regenerated output != on-disk
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, cast

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCES_DIR = REPO_ROOT / "tools" / "agent-sources"
GEMINI_DIR = REPO_ROOT / "agents"
CLAUDE_DIR = REPO_ROOT / ".claude-plugin" / "agents"
OPENCODE_DIR = REPO_ROOT / ".opencode" / "agents"
CODEX_DIR = REPO_ROOT / ".codex" / "agents"

# Canonical-tool -> per-host name. Each canonical tool MUST have an entry here;
# missing entries fail the generator.
TOOL_MAP: dict[str, dict[str, str]] = {
    "read": {"gemini": "read_file", "claude": "Read", "opencode": "read"},
    "grep": {"gemini": "grep_search", "claude": "Grep", "opencode": "grep"},
    "glob": {"gemini": "glob", "claude": "Glob", "opencode": "glob"},
    "bash": {"gemini": "run_shell_command", "claude": "Bash", "opencode": "bash"},
}


def _yaml_load(path: Path) -> dict[str, Any]:
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        msg = f"{path}: top-level must be a mapping"
        raise SystemExit(msg)
    return cast("dict[str, Any]", raw)


def _quote_yaml_description(description: str) -> str:
    """Render a description string as YAML, preserving the existing single-quoted shape.

    The on-disk frontmatter uses double-quoted strings; we mirror that for the
    Gemini/Claude/OpenCode markdown variants. The description itself contains
    apostrophes ("project's"), so we double-quote and escape any embedded ``"``.
    """
    escaped = description.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _map_tool(canonical: str, host: str) -> str:
    if canonical not in TOOL_MAP:
        msg = f"unknown canonical tool {canonical!r} (add to TOOL_MAP)"
        raise SystemExit(msg)
    if host not in TOOL_MAP[canonical]:
        msg = f"no {host} mapping for canonical tool {canonical!r}"
        raise SystemExit(msg)
    return TOOL_MAP[canonical][host]


def _render_gemini(name: str, description: str, tools: list[str], body: str) -> str:
    """Gemini CLI: YAML list of tool names (read_file / grep_search / glob / run_shell_command)."""
    tools_yaml = "\n".join(f"  - {_map_tool(t, 'gemini')}" for t in tools)
    return (
        f"---\nname: {name}\ndescription: {_quote_yaml_description(description)}\ntools:\n{tools_yaml}\n---\n\n{body}\n"
    )


def _render_claude(name: str, description: str, tools: list[str], body: str) -> str:
    """Claude Code: comma-separated string of PascalCase tool names."""
    tools_str = ", ".join(_map_tool(t, "claude") for t in tools)
    return (
        f"---\nname: {name}\ndescription: {_quote_yaml_description(description)}\ntools: {tools_str}\n---\n\n{body}\n"
    )


def _render_opencode(name: str, description: str, tools: list[str], body: str) -> str:
    """OpenCode: dict mapping with bool values + mode: subagent."""
    tools_dict = "\n".join(f"  {_map_tool(t, 'opencode')}: true" for t in tools)
    return (
        f"---\n"
        f"name: {name}\n"
        f"description: {_quote_yaml_description(description)}\n"
        f"mode: subagent\n"
        f"tools:\n{tools_dict}\n"
        f"---\n\n"
        f"{body}\n"
    )


def _render_codex(name: str, description: str, body: str) -> str:
    """Codex CLI: pure TOML; tools omitted (inherited from session config.toml)."""
    body_escaped = body.replace("\\", "\\\\")
    description_escaped = description.replace("\\", "\\\\").replace('"', '\\"')
    return (
        f'name = "{name}"\ndescription = "{description_escaped}"\n\ndeveloper_instructions = """\n{body_escaped}\n"""\n'
    )


def _write_if_changed(path: Path, content: str, *, check_only: bool) -> bool:
    """Return True if path's content matches `content`; False if it would change."""
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    if existing == content:
        return True
    if check_only:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def _generate(source_path: Path, *, check_only: bool) -> bool:
    data = _yaml_load(source_path)
    name = str(data["name"])
    description = str(data["description"]).strip()
    tools_raw: Any = data.get("tools") or []
    if not isinstance(tools_raw, list):
        msg = f"{source_path}: 'tools' must be a list"
        raise SystemExit(msg)
    tools: list[str] = [str(t) for t in tools_raw]  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
    body = str(data["body"]).rstrip("\n")

    targets = {
        GEMINI_DIR / f"{name}.md": _render_gemini(name, description, tools, body),
        CLAUDE_DIR / f"{name}.md": _render_claude(name, description, tools, body),
        OPENCODE_DIR / f"{name}.md": _render_opencode(name, description, tools, body),
        CODEX_DIR / f"{name}.toml": _render_codex(name, description, body),
    }
    all_match = True
    for target_path, target_content in targets.items():
        ok = _write_if_changed(target_path, target_content, check_only=check_only)
        if not ok:
            all_match = False
            sys.stderr.write(f"DRIFT: {target_path.relative_to(REPO_ROOT)}\n")
    return all_match


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if regenerated output differs from on-disk (CI drift gate)",
    )
    args = parser.parse_args(argv[1:])

    sources = sorted(SOURCES_DIR.glob("*.yaml"))
    if not sources:
        sys.stderr.write(f"no agent sources found in {SOURCES_DIR.relative_to(REPO_ROOT)}\n")
        return 1

    all_ok = True
    for source in sources:
        if not _generate(source, check_only=args.check):
            all_ok = False

    if args.check:
        if all_ok:
            sys.stdout.write(f"[ OK ] {len(sources)} agent source(s) — no drift\n")
            return 0
        sys.stderr.write("DRIFT detected — run `make agents` to regenerate\n")
        return 1

    sys.stdout.write(f"[ OK ] regenerated {len(sources)} agent(s)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
