"""Tests for hooks/session-start.sh — host-correct JSON emission."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.hooks._subproc import bash_executable, subprocess_env

REPO_ROOT = Path(__file__).resolve().parents[2]
SESSION_START = REPO_ROOT / "hooks" / "session-start.sh"


def _run(cwd: Path, env_overrides: dict[str, str]) -> dict[str, Any]:
    overrides = {"PWD": str(cwd), **env_overrides}
    result = subprocess.run(
        [bash_executable(), str(SESSION_START)],
        capture_output=True,
        text=True,
        env=subprocess_env(overrides=overrides),
        cwd=str(cwd),
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, f"session-start failed: {result.stderr!r}"
    parsed: dict[str, Any] = json.loads(result.stdout)
    return parsed


@pytest.fixture
def litestar_cwd(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "myapp"\ndependencies = ["litestar"]\n')
    return tmp_path


def test_claude_shape(litestar_cwd: Path) -> None:
    out = _run(litestar_cwd, {"CLAUDE_PLUGIN_ROOT": "/fake/path"})
    assert "hookSpecificOutput" in out
    hs = out["hookSpecificOutput"]
    assert isinstance(hs, dict)
    assert hs["hookEventName"] == "SessionStart"
    assert "additionalContext" in hs
    assert "litestar-skills:litestar" in hs["additionalContext"]
    assert "additional_context" not in out
    assert "systemMessage" not in out


def test_codex_shape(litestar_cwd: Path) -> None:
    out = _run(litestar_cwd, {"CODEX_PLUGIN_ROOT": "/fake/path"})
    assert "hookSpecificOutput" in out
    assert isinstance(out["hookSpecificOutput"], dict)
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "systemMessage" not in out


def test_cursor_shape(litestar_cwd: Path) -> None:
    out = _run(litestar_cwd, {"CURSOR_PLUGIN_ROOT": "/fake/path"})
    assert "additional_context" in out
    assert "hookSpecificOutput" not in out
    assert "litestar-skills:litestar" in str(out["additional_context"])


def test_gemini_shape(litestar_cwd: Path) -> None:
    out = _run(litestar_cwd, {"GEMINI_CLI": "1"})
    assert "hookSpecificOutput" in out
    assert "systemMessage" in out
    hs = out["hookSpecificOutput"]
    assert isinstance(hs, dict)
    assert hs["hookEventName"] == "SessionStart"
    assert hs["additionalContext"] == out["systemMessage"]


def test_unknown_host_falls_back_to_cursor_shape(litestar_cwd: Path) -> None:
    out = _run(litestar_cwd, {})
    assert "additional_context" in out
    assert "hookSpecificOutput" not in out


def test_disable_env_var(litestar_cwd: Path) -> None:
    out = _run(
        litestar_cwd,
        {"CLAUDE_PLUGIN_ROOT": "/fake", "LITESTAR_SKILLS_HOOK_DISABLE": "1"},
    )
    assert out == {}


def test_emission_is_valid_json(litestar_cwd: Path) -> None:
    """All emitted JSON must round-trip through json.loads + json.dumps."""
    for env in (
        {"CLAUDE_PLUGIN_ROOT": "/x"},
        {"CODEX_PLUGIN_ROOT": "/x"},
        {"CURSOR_PLUGIN_ROOT": "/x"},
        {"GEMINI_CLI": "1"},
        {},
    ):
        out = _run(litestar_cwd, env)
        # Round-trip via json.dumps then json.loads to confirm structure is JSON-clean.
        json.loads(json.dumps(out))
