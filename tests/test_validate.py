"""Tests for the unified repository validator and SessionStart hook envelopes."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

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


@pytest.mark.parametrize("use_pwsh", [False, True], ids=["sh", "pwsh"])
def test_session_start_sh_emits_valid_envelopes(tmp_path: Path, use_pwsh: bool) -> None:
    """Verify that SessionStart hooks detect Litestar signals and emit per-harness JSON."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = ["litestar", "sqlspec", "litestar-vite"]\n',
        encoding="utf-8",
    )

    res_json = _run_session_hook("json", tmp_path, use_pwsh=use_pwsh)
    payload_json = json.loads(res_json.stdout)
    assert "litestar" in payload_json["detected_skills"]
    assert "sqlspec" in payload_json["detected_skills"]
    assert "litestar-vite" in payload_json["detected_skills"]
    assert "litestar-styleguide" in payload_json["detected_skills"]
    assert "EXTREMELY_IMPORTANT" not in payload_json["context"]

    res_agy = _run_session_hook("agy", tmp_path, use_pwsh=use_pwsh)
    payload_agy = json.loads(res_agy.stdout)
    assert "systemMessage" in payload_agy["injectSteps"][0]
    assert "EXTREMELY_IMPORTANT" not in payload_agy["injectSteps"][0]["systemMessage"]["systemMessage"]

    res_claude = _run_session_hook("claude", tmp_path, use_pwsh=use_pwsh)
    payload_claude = json.loads(res_claude.stdout)
    assert payload_claude["continue"] is True
    assert "systemMessage" not in payload_claude
    assert payload_claude["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "sqlspec" in payload_claude["hookSpecificOutput"]["additionalContext"]
    assert "EXTREMELY_IMPORTANT" not in payload_claude["hookSpecificOutput"]["additionalContext"]

    res_cursor = _run_session_hook("cursor", tmp_path, use_pwsh=use_pwsh)
    payload_cursor = json.loads(res_cursor.stdout)
    assert payload_cursor["continue"] is True
    assert "sqlspec" in payload_cursor["additional_context"]
    assert "EXTREMELY_IMPORTANT" not in payload_cursor["additional_context"]

    res_cursor_guard = _run_session_hook(
        "claude",
        tmp_path,
        env_overrides={"CURSOR_VERSION": "0.48.0"},
        use_pwsh=use_pwsh,
    )
    assert json.loads(res_cursor_guard.stdout) == {"continue": True}


@pytest.mark.parametrize("use_pwsh", [False, True], ids=["sh", "pwsh"])
def test_session_start_quiet_in_non_litestar_workspace_and_upstream_aware(tmp_path: Path, use_pwsh: bool) -> None:
    """Verify non-Litestar workspaces emit quiet no-ops and upstream packages emit authority guidance."""
    non_litestar = tmp_path / "generic-app"
    non_litestar.mkdir()
    (non_litestar / "pyproject.toml").write_text(
        '[project]\nname = "generic-app"\ndependencies = ["pytest", "mkdocstrings"]\n',
        encoding="utf-8",
    )
    (non_litestar / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
    (non_litestar / "vite.config.ts").write_text("export default {}\n", encoding="utf-8")
    (non_litestar / "zensical.toml").write_text("[project]\n", encoding="utf-8")

    assert json.loads(_run_session_hook("json", non_litestar, use_pwsh=use_pwsh).stdout) == {
        "detected_skills": [],
        "context": "",
    }
    assert json.loads(_run_session_hook("agy", non_litestar, use_pwsh=use_pwsh).stdout) == {}
    assert json.loads(_run_session_hook("claude", non_litestar, use_pwsh=use_pwsh).stdout) == {"continue": True}
    assert json.loads(_run_session_hook("cursor", non_litestar, use_pwsh=use_pwsh).stdout) == {"continue": True}
    assert _run_session_hook("opencode", non_litestar, use_pwsh=use_pwsh).stdout.strip() == ""

    upstream_dir = tmp_path / "sqlspec-checkout"
    upstream_dir.mkdir()
    (upstream_dir / "pyproject.toml").write_text(
        '[project]\nname = "sqlspec"\ndependencies = ["msgspec", "pytest"]\n',
        encoding="utf-8",
    )
    upstream_json = json.loads(_run_session_hook("json", upstream_dir, use_pwsh=use_pwsh).stdout)
    assert "sqlspec" not in upstream_json["detected_skills"]
    assert "msgspec" in upstream_json["detected_skills"]
    assert "litestar-testing" in upstream_json["detected_skills"]
    assert "Litestar upstream package workspace ('sqlspec'" in upstream_json["context"]
    assert "authority over its consumer skill" in upstream_json["context"]

    plugin_dir = tmp_path / "plugin-checkout"
    plugin_dir.mkdir()
    (plugin_dir / "pyproject.toml").write_text(
        '[project]\nname = "litestar-skills"\n[project.optional-dependencies]\nvalidation = ["litestar", "sqlspec"]\n',
        encoding="utf-8",
    )
    plugin_json = json.loads(_run_session_hook("json", plugin_dir, use_pwsh=use_pwsh).stdout)
    assert plugin_json["detected_skills"] == ["litestar-styleguide"]
    assert "Litestar skills plugin workspace" in plugin_json["context"]


def _run_session_hook(
    harness: str,
    project_dir: Path,
    *,
    env_overrides: dict[str, str] | None = None,
    use_pwsh: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Execute the POSIX sh or PowerShell SessionStart hook with a clean environment."""
    env = os.environ.copy()
    env.pop("CURSOR_VERSION", None)
    env.pop("LITESTAR_SKILLS_HOOK_DISABLE", None)
    if env_overrides:
        env.update(env_overrides)

    if use_pwsh:
        pwsh_bin = shutil.which("pwsh") or shutil.which("powershell")
        if pwsh_bin is None:
            pytest.skip("PowerShell is not available on this host")
        cmd = [
            pwsh_bin,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(REPO_ROOT / "hooks" / "session-start.ps1"),
            "--harness",
            harness,
            "--project",
            str(project_dir),
        ]
    else:
        sh_bin = shutil.which("sh")
        if sh_bin is None:
            pytest.skip("POSIX sh is not available on this host")
        cmd = [
            sh_bin,
            str(REPO_ROOT / "hooks" / "session-start.sh"),
            "--harness",
            harness,
            "--project",
            str(project_dir),
        ]

    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


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
        json.dumps(
            {
                "name": "litestar-skills",
                "version": version,
                "main": ".opencode/plugins/litestar.js",
            }
        ),
        encoding="utf-8",
    )
    (root / "plugin.json").write_text(
        json.dumps(
            {
                "$schema": "https://antigravity.google/schemas/v1/plugin.json",
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
        json.dumps(
            {
                "name": PLUGIN_ID,
                "version": version,
                "hooks": "./hooks/hooks-claude.json",
            }
        ),
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
        json.dumps(
            {
                "name": PLUGIN_ID,
                "version": version,
                "skills": "./skills/",
                "hooks": "./hooks/hooks-claude.json",
            }
        ),
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
        'import fs from "node:fs";\nimport path from "node:path";\n'
        'export default { id: "litestar", async setup(ctx) {} };\n',
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
        'sandbox_mode = "read-only"\n'
        'developer_instructions = """# Role"""\n',
        encoding="utf-8",
    )
