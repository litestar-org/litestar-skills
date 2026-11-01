"""Tests for the unified repository validator and SessionStart hook envelopes."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tools.validate import (
    MAX_SKILL_BYTES,
    PLUGIN_ID,
    REPO_ROOT,
    validate_anti_sprawl,
    validate_hooks,
    validate_manifests,
    validate_markdown_links,
    validate_repository,
    validate_skills,
    validate_subagents,
)


def test_live_repository_passes_validation() -> None:
    """Verify that the live repository checkout passes every validation gate."""
    assert validate_repository(REPO_ROOT) == []


def test_manifest_version_mismatch_detected(tmp_path: Path) -> None:
    """Verify that manifest version drift is reported."""
    _write_minimal_repo(tmp_path)
    (tmp_path / "plugin.json").write_text(
        json.dumps(
            {
                "$schema": "https://example.com/schema.json",
                "name": PLUGIN_ID,
                "displayName": "Litestar",
                "version": "9.9.9",
                "description": "Drift",
            }
        ),
        encoding="utf-8",
    )
    errors: list[str] = []
    validate_manifests(tmp_path, errors)
    assert any("plugin.json version" in err for err in errors)


def test_skill_validation_catches_size_and_description_violations(tmp_path: Path) -> None:
    """Verify skill byte cap, description prefix, and forbidden terms."""
    _write_minimal_repo(tmp_path)
    bad_skill = tmp_path / "skills" / "litestar" / "SKILL.md"
    bad_skill.write_text(
        '---\nname: litestar\ndescription: "Auto-activate for Litestar."\n---\n\n' + ("x" * MAX_SKILL_BYTES),
        encoding="utf-8",
    )
    errors: list[str] = []
    validate_skills(tmp_path, errors)
    assert any("exceeds" in err for err in errors)
    assert any("must start with 'Use when'" in err for err in errors)
    assert any("forbidden phrase 'Auto-activate'" in err for err in errors)


def test_subagent_validation_catches_h2_headings_and_codex_tools(tmp_path: Path) -> None:
    """Verify that H2 headings in agents/*.md and top-level tools in Codex TOML fail."""
    _write_minimal_repo(tmp_path)
    md_agent = tmp_path / "agents" / "litestar-reviewer.md"
    md_agent.write_text(
        md_agent.read_text(encoding="utf-8") + "\n## Forbidden H2\n",
        encoding="utf-8",
    )
    toml_agent = tmp_path / ".codex" / "agents" / "litestar-reviewer.toml"
    toml_agent.write_text(
        toml_agent.read_text(encoding="utf-8") + '\ntools = ["read_file"]\n',
        encoding="utf-8",
    )
    errors: list[str] = []
    validate_subagents(tmp_path, errors)
    assert any("H1 headings" in err for err in errors)
    assert any("must not declare top-level 'tools'" in err for err in errors)


def test_anti_sprawl_and_markdown_links(tmp_path: Path) -> None:
    """Verify that retired paths and broken Markdown links are reported."""
    _write_minimal_repo(tmp_path)
    (tmp_path / "plugins").mkdir()
    (tmp_path / "README.md").write_text("Broken [link](missing/file.md).\n", encoding="utf-8")
    errors: list[str] = []
    validate_anti_sprawl(tmp_path, errors)
    validate_markdown_links(tmp_path, errors)
    assert any("Retired sprawl path" in err for err in errors)
    assert any("broken relative link" in err for err in errors)


def test_hooks_validation_catches_nested_agy_hooks(tmp_path: Path) -> None:
    """Verify that nested hooks in root hooks.json are rejected."""
    _write_minimal_repo(tmp_path)
    (tmp_path / "hooks.json").write_text(json.dumps({"hooks": {}}), encoding="utf-8")
    errors: list[str] = []
    validate_hooks(tmp_path, errors)
    assert any("top-level 'hooks' key" in err for err in errors)


def test_session_start_sh_emits_valid_envelopes(tmp_path: Path) -> None:
    """Verify that hooks/session-start.sh detects Litestar signals and emits per-harness JSON."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = ["litestar", "sqlspec", "litestar-vite"]\n',
        encoding="utf-8",
    )
    script = REPO_ROOT / "hooks" / "session-start.sh"

    res_json = subprocess.run(
        [str(script), "--harness", "json", "--project", str(tmp_path)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload_json = json.loads(res_json.stdout)
    assert "litestar" in payload_json["detected_skills"]
    assert "sqlspec" in payload_json["detected_skills"]
    assert "litestar-vite" in payload_json["detected_skills"]

    res_agy = subprocess.run(
        [str(script), "--harness", "agy", "--project", str(tmp_path)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload_agy = json.loads(res_agy.stdout)
    assert "systemMessage" in payload_agy["injectSteps"][0]

    res_claude = subprocess.run(
        [str(script), "--harness", "claude", "--project", str(tmp_path)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload_claude = json.loads(res_claude.stdout)
    assert payload_claude["hookSpecificOutput"]["hookEventName"] == "SessionStart"

    res_cursor = subprocess.run(
        [str(script), "--harness", "cursor", "--project", str(tmp_path)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload_cursor = json.loads(res_cursor.stdout)
    assert "sqlspec" in payload_cursor["additional_context"]


def _write_minimal_repo(root: Path, version: str = "0.10.0") -> None:
    """Create a minimal valid single-root repository fixture in root."""
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "litestar-skills"\nversion = "{version}"\n\n'
        '[[tool.bumpversion.files]]\nfilename = "package.json"\n'
        '[[tool.bumpversion.files]]\nfilename = "plugin.json"\n'
        '[[tool.bumpversion.files]]\nfilename = ".claude-plugin/plugin.json"\n'
        '[[tool.bumpversion.files]]\nfilename = ".claude-plugin/marketplace.json"\n'
        '[[tool.bumpversion.files]]\nfilename = ".codex-plugin/plugin.json"\n'
        '[[tool.bumpversion.files]]\nfilename = ".cursor-plugin/plugin.json"\n'
        '[[tool.bumpversion.files]]\nfilename = ".agents/plugins/marketplace.json"\n',
        encoding="utf-8",
    )
    (root / "package.json").write_text(
        json.dumps({"name": "litestar-skills", "version": version}),
        encoding="utf-8",
    )
    (root / "plugin.json").write_text(
        json.dumps(
            {
                "$schema": "https://raw.githubusercontent.com/anthropics/claude-code/main/.claude-plugin/plugin.schema.json",
                "name": PLUGIN_ID,
                "displayName": "Litestar",
                "version": version,
                "description": "Litestar skills",
            }
        ),
        encoding="utf-8",
    )
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": PLUGIN_ID, "version": version}),
        encoding="utf-8",
    )
    (root / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(
            {
                "name": "litestar-skills",
                "plugins": [{"name": PLUGIN_ID, "source": "./", "version": version}],
            }
        ),
        encoding="utf-8",
    )
    (root / ".codex-plugin").mkdir(parents=True)
    (root / ".codex-plugin" / "plugin.json").write_text(
        json.dumps({"name": PLUGIN_ID, "version": version, "skills": "./skills/"}),
        encoding="utf-8",
    )
    (root / ".cursor-plugin").mkdir(parents=True)
    (root / ".cursor-plugin" / "plugin.json").write_text(
        json.dumps(
            {
                "name": PLUGIN_ID,
                "version": version,
                "hooks": "./hooks/hooks-cursor.json",
            }
        ),
        encoding="utf-8",
    )
    (root / ".agents" / "plugins").mkdir(parents=True)
    (root / ".agents" / "plugins" / "marketplace.json").write_text(
        json.dumps(
            {
                "name": "litestar-skills",
                "plugins": [
                    {
                        "name": PLUGIN_ID,
                        "source": {"source": "local", "path": "./"},
                        "version": version,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / "hooks.json").write_text(
        json.dumps(
            {
                "litestar-priming": {
                    "SessionStart": [
                        {
                            "type": "command",
                            "command": "sh ./hooks/session-start.sh --harness agy",
                            "timeout": 15,
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    (root / "hooks").mkdir(parents=True)
    (root / "hooks" / "hooks-claude.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "startup|clear|compact",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": (
                                        'sh "${CLAUDE_PLUGIN_ROOT:-${PLUGIN_ROOT:-.}}'
                                        '/hooks/session-start.sh" --harness claude'
                                    ),
                                    "commandWindows": (
                                        "powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass "
                                        '-File "${CLAUDE_PLUGIN_ROOT:-${PLUGIN_ROOT:-.}}'
                                        '/hooks/session-start.ps1" --harness claude'
                                    ),
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    (root / "hooks" / "hooks-cursor.json").write_text(
        json.dumps(
            {
                "version": 1,
                "hooks": {"sessionStart": [{"command": "sh ./hooks/session-start.sh --harness cursor"}]},
            }
        ),
        encoding="utf-8",
    )
    sh_path = root / "hooks" / "session-start.sh"
    sh_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    sh_path.chmod(0o755)
    (root / "hooks" / "session-start.ps1").write_text("exit 0\n", encoding="utf-8")
    (root / ".opencode" / "plugins").mkdir(parents=True)
    (root / ".opencode" / "plugins" / "litestar.js").write_text(
        'import fs from "node:fs";\nimport path from "node:path";\n',
        encoding="utf-8",
    )
    (root / "rules").mkdir(parents=True)
    (root / "rules" / "litestar-antigravity.md").write_text("# Rules\n", encoding="utf-8")

    skill_dir = root / "skills" / "litestar"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        '---\nname: litestar\ndescription: "Use when building Litestar routes."\n---\n\n'
        "# Litestar\n\n<workflow>\nW\n</workflow>\n<guardrails>\nG\n</guardrails>\n"
        "<validation>\nV\n</validation>\n<example>\nE\n</example>\n",
        encoding="utf-8",
    )

    (root / "agents").mkdir(parents=True)
    (root / "agents" / "litestar-reviewer.md").write_text(
        "---\n"
        "name: litestar-reviewer\n"
        'description: "Use when reviewing Litestar code."\n'
        "model: inherit\n"
        "mainAgent: false\n"
        "subagent: true\n"
        "readonly: true\n"
        "commandExecutionPolicy: off\n"
        "disallowedTools:\n"
        "  - write_file\n"
        "skills:\n"
        "  - litestar\n"
        "---\n\n"
        "# Role\n\nReview code.\n",
        encoding="utf-8",
    )
    (root / ".codex" / "agents").mkdir(parents=True)
    (root / ".codex" / "agents" / "litestar-reviewer.toml").write_text(
        'name = "litestar-reviewer"\n'
        'description = "Use when reviewing Litestar code."\n'
        'developer_instructions = """# Role"""\n',
        encoding="utf-8",
    )
