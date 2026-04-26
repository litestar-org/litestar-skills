"""Tests for host-specific plugin.json manifest schemas."""

import json
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_claude_plugin_manifest_agents_is_list() -> None:
    """Claude Code plugin.json 'agents' field MUST be a list of strings or a glob."""
    manifest_path = REPO_ROOT / ".claude-plugin" / "plugin.json"
    assert manifest_path.exists(), f"{manifest_path} is missing"

    with open(manifest_path, encoding="utf-8") as f:
        data: dict[str, object] = json.load(f)

    agents: object = data.get("agents")
    assert isinstance(agents, list), (
        f"Claude Code manifest 'agents' field must be a list of strings, got {type(agents).__name__!r} ({agents!r})"
    )
    # Use cast to satisfy pyright
    agents_list = cast("list[object]", agents)
    assert len(agents_list) > 0, "Claude Code manifest 'agents' list is empty"
    for entry in agents_list:
        msg = f"Claude Code manifest 'agents' entry must be a string, got {type(entry).__name__!r}"
        assert isinstance(entry, str), msg
        assert entry.endswith(".md"), f"Claude Code manifest 'agents' entry {entry!r} must be a .md file"


def test_codex_plugin_manifest_agents_is_string() -> None:
    """Codex CLI plugin.json 'agents' field should be a string directory path.

    Codex 0.125+ requires the plugin manifest under
    `.agents/plugins/plugins/<name>/.codex-plugin/plugin.json` so the
    marketplace `source.path` can be a non-empty subdirectory.
    """
    manifest_path = REPO_ROOT / ".agents" / "plugins" / "plugins" / "litestar-skills" / ".codex-plugin" / "plugin.json"
    assert manifest_path.exists(), f"{manifest_path} is missing"

    with open(manifest_path, encoding="utf-8") as f:
        data: dict[str, object] = json.load(f)

    agents: object = data.get("agents")
    assert isinstance(agents, str), f"Codex manifest 'agents' field must be a string, got {type(agents).__name__!r}"
    assert agents.endswith("/"), "Codex manifest directory paths should end with a slash"


def test_cursor_plugin_manifest_skills_is_string() -> None:
    """Cursor plugin.json 'skills' field should be a string directory path."""
    manifest_path = REPO_ROOT / ".cursor-plugin" / "plugin.json"
    if not manifest_path.exists():
        return

    with open(manifest_path, encoding="utf-8") as f:
        data: dict[str, object] = json.load(f)

    skills: object = data.get("skills")
    assert isinstance(skills, str), f"Cursor manifest 'skills' field must be a string, got {type(skills).__name__!r}"
