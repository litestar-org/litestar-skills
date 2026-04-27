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


def test_claude_marketplace_does_not_include_codex_policy() -> None:
    """Claude marketplace plugin entries must not include Codex-only policy fields."""
    manifest_path = REPO_ROOT / ".claude-plugin" / "marketplace.json"
    assert manifest_path.exists(), f"{manifest_path} is missing"

    with open(manifest_path, encoding="utf-8") as f:
        data: dict[str, object] = json.load(f)

    plugins = data.get("plugins")
    assert isinstance(plugins, list), "Claude marketplace 'plugins' field must be a list"
    plugins_list = cast("list[object]", plugins)
    for index, entry in enumerate(plugins_list):
        assert isinstance(entry, dict), f"Claude marketplace plugin {index} must be an object"
        assert "policy" not in entry, "Claude marketplace plugin entries reject the 'policy' key"


def test_host_facing_plugin_identity_is_litestar() -> None:
    """Host manifests should expose a clean `litestar` plugin/marketplace identity."""
    claude_marketplace_path = REPO_ROOT / ".claude-plugin" / "marketplace.json"
    claude_plugin_path = REPO_ROOT / ".claude-plugin" / "plugin.json"
    codex_marketplace_path = REPO_ROOT / ".agents" / "plugins" / "marketplace.json"
    codex_plugin_path = REPO_ROOT / ".codex-plugin" / "plugin.json"
    gemini_path = REPO_ROOT / "gemini-extension.json"
    cursor_path = REPO_ROOT / ".cursor-plugin" / "plugin.json"

    claude_marketplace = json.loads(claude_marketplace_path.read_text(encoding="utf-8"))
    claude_plugin = json.loads(claude_plugin_path.read_text(encoding="utf-8"))
    codex_marketplace = json.loads(codex_marketplace_path.read_text(encoding="utf-8"))
    codex_plugin = json.loads(codex_plugin_path.read_text(encoding="utf-8"))
    gemini = json.loads(gemini_path.read_text(encoding="utf-8"))
    cursor = json.loads(cursor_path.read_text(encoding="utf-8"))

    assert claude_marketplace["name"] == "litestar"
    assert claude_marketplace["plugins"][0]["name"] == "litestar"
    assert claude_plugin["name"] == "litestar"
    assert codex_marketplace["name"] == "litestar"
    assert codex_marketplace["plugins"][0]["name"] == "litestar"
    assert codex_marketplace["plugins"][0]["source"]["path"] == "./plugins/litestar"
    assert codex_plugin["name"] == "litestar"
    assert gemini["name"] == "litestar"
    assert cursor["name"] == "litestar"


def test_python_distribution_remains_litestar_skills() -> None:
    """The clean host identity break does not rename the Python package."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '\nname = "litestar-skills"\n' in pyproject


def test_codex_plugin_manifest_agents_is_string() -> None:
    """Codex CLI plugin.json 'agents' field should be a string directory path.

    Codex 0.125+ resolves marketplace `source.path` against the repo root, so
    the canonical plugin manifest lives at `<repo>/.codex-plugin/plugin.json`
    and the package at `<repo>/plugins/litestar/` symlinks back to it.
    """
    manifest_path = REPO_ROOT / ".codex-plugin" / "plugin.json"
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
