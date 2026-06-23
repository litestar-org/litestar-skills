"""Drift gate for the canonical agent generator.

Asserts that ``python3 tools/generate-agents.py --check`` exits 0 — i.e., the
4 host-dialect files match what the generator would produce from the canonical
``tools/agent-sources/*.yaml`` source. If a contributor edits a generated file
by hand, this test fails and the contributor must instead edit the source and
run ``make agents``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = REPO_ROOT / "tools" / "generate-agents.py"
SOURCES_DIR = REPO_ROOT / "tools" / "agent-sources"


def test_generator_exists() -> None:
    assert GENERATOR.is_file(), f"missing {GENERATOR}"


def test_at_least_one_canonical_source_present() -> None:
    sources = sorted(SOURCES_DIR.glob("*.yaml"))
    assert sources, f"no agent sources in {SOURCES_DIR}"


def test_no_agent_dialect_drift() -> None:
    """If this fails: contributor edited a generated file directly. Run `make agents`."""
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert result.returncode == 0, (
        "agent dialect drift detected — edit tools/agent-sources/<name>.yaml and run `make agents`.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


@pytest.mark.parametrize(
    ("relative", "must_contain"),
    [
        ("agents/litestar-reviewer.md", ("view_file", "grep_search", "find_by_name", "run_command")),
        (".claude-plugin/agents/litestar-reviewer.md", ("Read,", "Grep,", "Glob,", "Bash")),
        (".opencode/agents/litestar-reviewer.md", ("mode: subagent", "read: true", "bash: true")),
        (".codex/agents/litestar-reviewer.toml", ('developer_instructions = """', "name = ")),
    ],
)
def test_per_host_dialect_signatures(relative: str, must_contain: tuple[str, ...]) -> None:
    """Spot-check that each generated dialect carries its host-specific frontmatter shape."""
    text = (REPO_ROOT / relative).read_text(encoding="utf-8")
    for needle in must_contain:
        assert needle in text, f"{relative} missing {needle!r}"
