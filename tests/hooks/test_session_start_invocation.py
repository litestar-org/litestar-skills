"""Tests for the per-host hook *manifest command strings* — not the script.

`hooks/session-start.sh` is already self-locating (covered by
``test_session_start_emission.py``). The defect class these tests guard against
lives in the manifest ``command`` strings: a host that does not inject its
``*_PLUGIN_ROOT`` variable (Codex) or runs the hook from a foreign CWD (Cursor)
must still resolve the script and exit 0 — never ``bash /hooks/session-start.sh``
(exit 127, GitHub #23).

Each test executes the manifest's real command via ``bash -c`` so a regression in
the command bytes is caught here before it ships.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

from tests.hooks._subproc import bash_executable, subprocess_env

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = REPO_ROOT / "hooks"

# Manifest filename + the JSON event key per host.
MANIFESTS = {
    "claude": ("hooks-claude.json", "SessionStart"),
    "codex": ("hooks-codex.json", "SessionStart"),
    "cursor": ("hooks-cursor.json", "sessionStart"),
}


def _command_for(host: str) -> str:
    filename, event = MANIFESTS[host]
    data = cast("dict[str, Any]", json.loads((HOOKS_DIR / filename).read_text(encoding="utf-8")))
    matcher = data["hooks"][event][0]
    # Claude/Codex nest a "hooks" array under the matcher; Cursor puts "command" on the matcher directly.
    entry = matcher["hooks"][0] if "hooks" in matcher else matcher
    return cast("str", entry["command"])


def _run_command(command: str, *, cwd: Path, overrides: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = subprocess_env(overrides={"PWD": str(cwd), **overrides})
    return subprocess.run(
        [bash_executable(), "-c", command],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd),
        check=False,
        timeout=10,
    )


@pytest.fixture
def litestar_project(tmp_path: Path) -> Path:
    """A foreign working directory that the detector recognizes as a Litestar app."""
    project = tmp_path / "userproject"
    project.mkdir()
    (project / "pyproject.toml").write_text('[project]\nname = "myapp"\ndependencies = ["litestar"]\n')
    return project


@pytest.fixture
def fake_codex_home(tmp_path: Path) -> Path:
    """A HOME whose Codex install cache mirrors the real hooks payload (newest version)."""
    home = tmp_path / "home"
    cache = home / ".codex" / "plugins" / "cache" / "litestar" / "litestar" / "0.2.1"
    cache.mkdir(parents=True)
    (cache / "hooks").symlink_to(HOOKS_DIR)
    return home


@pytest.fixture
def fake_claude_home(tmp_path: Path) -> Path:
    """A HOME whose Claude marketplace install mirrors the real hooks payload."""
    home = tmp_path / "home"
    install = home / ".claude" / "plugins" / "marketplaces" / "litestar"
    install.mkdir(parents=True)
    (install / "hooks").symlink_to(HOOKS_DIR)
    return home


def test_codex_command_resolves_without_plugin_root(litestar_project: Path, fake_codex_home: Path) -> None:
    """Codex injects no plugin-root var: the command must locate the installed script and exit 0."""
    result = _run_command(
        _command_for("codex"),
        cwd=litestar_project,
        overrides={"HOME": str(fake_codex_home)},
    )
    assert result.returncode == 0, f"codex command exited {result.returncode}: {result.stderr!r}"
    out = cast("dict[str, Any]", json.loads(result.stdout))
    assert "hookSpecificOutput" in out, out
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "litestar:litestar" in out["hookSpecificOutput"]["additionalContext"]


def test_codex_command_prefers_plugin_root_when_set(litestar_project: Path) -> None:
    """When Codex (or its alias) does inject the root, the command uses it verbatim."""
    result = _run_command(
        _command_for("codex"),
        cwd=litestar_project,
        overrides={"PLUGIN_ROOT": str(REPO_ROOT)},
    )
    assert result.returncode == 0, f"codex command exited {result.returncode}: {result.stderr!r}"
    out = cast("dict[str, Any]", json.loads(result.stdout))
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"


def test_claude_command_uses_plugin_root_when_set(litestar_project: Path) -> None:
    """Non-regression: the guaranteed CLAUDE_PLUGIN_ROOT path must keep working verbatim."""
    result = _run_command(
        _command_for("claude"),
        cwd=litestar_project,
        overrides={"CLAUDE_PLUGIN_ROOT": str(REPO_ROOT)},
    )
    assert result.returncode == 0, f"claude command exited {result.returncode}: {result.stderr!r}"
    out = cast("dict[str, Any]", json.loads(result.stdout))
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "litestar:litestar" in out["hookSpecificOutput"]["additionalContext"]


def test_claude_command_resolves_with_empty_plugin_root(litestar_project: Path, fake_claude_home: Path) -> None:
    """claude-code#27145: CLAUDE_PLUGIN_ROOT can be empty at SessionStart — must not exit 127."""
    result = _run_command(
        _command_for("claude"),
        cwd=litestar_project,
        overrides={"CLAUDE_PLUGIN_ROOT": "", "HOME": str(fake_claude_home)},
    )
    assert result.returncode == 0, f"claude command exited {result.returncode}: {result.stderr!r}"
    out = cast("dict[str, Any]", json.loads(result.stdout))
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"


def test_cursor_command_uses_plugin_root_not_cwd(litestar_project: Path) -> None:
    """Cursor sets CURSOR_PLUGIN_ROOT but runs from a foreign CWD: the command must honor the var."""
    result = _run_command(
        _command_for("cursor"),
        cwd=litestar_project,
        overrides={"CURSOR_PLUGIN_ROOT": str(REPO_ROOT)},
    )
    assert result.returncode == 0, f"cursor command exited {result.returncode}: {result.stderr!r}"
    out = cast("dict[str, Any]", json.loads(result.stdout))
    assert "additional_context" in out, out
    assert "litestar:litestar" in str(out["additional_context"])
