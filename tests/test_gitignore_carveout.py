"""Verify the .agents/plugins/marketplace.json carve-out.

The Codex CLI reads its marketplace catalog from `.agents/plugins/marketplace.json`
at the repo root. The rest of `.agents/` is Flow authoring (gitignored, never
shipped). This test enforces both halves of the carve-out:

1. `.agents/plugins/marketplace.json` is committed and tracked.
2. Other `.agents/` paths (`specs/`, `patterns.md`, `flows.md`, etc.) remain
   ignored — i.e., the carve-out does NOT leak the framework authoring tree.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _is_tracked(rel_path: str) -> bool:
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", rel_path],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _is_trackable(rel_path: str) -> bool:
    """A path is trackable if `git check-ignore -v` indicates the matching rule is a negation."""
    result = subprocess.run(
        ["git", "check-ignore", "-v", "--no-index", rel_path],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return True  # nothing matched -> not ignored -> trackable
    line = result.stdout.strip().split("\n")[0] if result.stdout.strip() else ""
    rule = line.split(":")[-1].split("\t")[0] if ":" in line else ""
    return rule.startswith("!")


def test_codex_marketplace_is_committed() -> None:
    assert _is_tracked(".agents/plugins/marketplace.json"), (
        ".agents/plugins/marketplace.json must be committed — Codex CLI reads from this exact path"
    )


def test_codex_plugin_package_is_committed() -> None:
    """Codex 0.125+ resolves `source.path` against the repo root, so the plugin
    package lives at `<repo>/plugins/litestar/`. The package itself is composed
    of symlinks back to the canonical sources (`.codex-plugin`, `skills`,
    `commands`, `.codex`, `hooks`) — every symlink and the canonical manifest
    must be tracked by git."""
    assert _is_tracked(".codex-plugin/plugin.json"), (
        ".codex-plugin/plugin.json must be committed — it is the canonical Codex plugin manifest"
    )
    for entry in (".codex-plugin", "skills", "commands", ".codex", "hooks"):
        assert _is_tracked(f"plugins/litestar/{entry}"), (
            f"plugins/litestar/{entry} symlink must be committed — Codex 0.125+ resolves "
            '`source.path: "./plugins/litestar"` against the repo root'
        )


def test_codex_marketplace_is_trackable() -> None:
    assert _is_trackable(".agents/plugins/marketplace.json"), (
        "carve-out broken — file must be re-included via `!.agents/plugins/marketplace.json`"
    )


def test_other_agents_paths_remain_ignored() -> None:
    """Sanity: `.agents/specs/` and `.agents/patterns.md` should still be Flow-authoring (ignored)."""
    for path in (".agents/specs/host-modernization/prd.md", ".agents/patterns.md"):
        result = subprocess.run(
            ["git", "check-ignore", "-v", path],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"{path} should be ignored (Flow authoring); the carve-out leaked: {result.stdout!r}"
        )
