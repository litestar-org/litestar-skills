#!/usr/bin/env python3
"""Validate Codex marketplace + plugin manifests for compatibility with Codex CLI 0.125.0+.

Mirrors the validator shipped by ~/code/c/flow's `tools/validate-codex-manifest.py`.

Codex 0.125+ enforces:

* Local marketplace ``source.path`` MUST start with ``./``.
* MUST be a non-empty subdirectory (``./`` alone is rejected).
* MUST NOT contain ``..``.
* ``userConfig`` keys (Claude Code only) MUST be camelCase.

Walks every ``marketplace.json`` and ``plugin.json`` under the repo (excluding
``.git``, ``.venv``, ``node_modules``, etc.) and reports violations.

Exit 0 on clean; exit 1 with per-file violation list otherwise.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[1]

_SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "dist",
    "build",
}


def _iter_codex_marketplaces() -> list[Path]:
    """Codex marketplaces live under `.agents/plugins/`. Claude's marketplace
    (`.claude-plugin/marketplace.json`) uses a DIFFERENT resolver (path is
    relative to marketplace root, `./` is fine) and is intentionally excluded.
    """
    candidate = REPO_ROOT / ".agents" / "plugins" / "marketplace.json"
    return [candidate] if candidate.is_file() else []


def _iter_codex_plugins() -> list[Path]:
    """Codex plugin manifests live under `.agents/plugins/plugins/<name>/.codex-plugin/`.
    The Claude plugin manifest (`.claude-plugin/plugin.json`) is also userConfig-validated
    (Claude's own schema) but not by THIS validator — `validate-skills.py` covers it.
    """
    out: list[Path] = []
    plugins_root = REPO_ROOT / ".agents" / "plugins" / "plugins"
    if plugins_root.is_dir():
        out.extend(sorted(plugins_root.glob("*/.codex-plugin/plugin.json")))
    # Also validate the root .claude-plugin/plugin.json for camelCase userConfig keys.
    claude = REPO_ROOT / ".claude-plugin" / "plugin.json"
    if claude.is_file():
        out.append(claude)
    return out


def _validate_marketplace(path: Path) -> int:
    """Return number of violations (0 means clean)."""
    print(f"Validating marketplace: {path.relative_to(REPO_ROOT)}")
    try:
        data_raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  ERROR: invalid JSON: {exc}")
        return 1
    if not isinstance(data_raw, dict):
        print("  ERROR: top-level must be an object")
        return 1
    data = cast("dict[str, Any]", data_raw)
    plugins_raw = data.get("plugins", [])
    if not isinstance(plugins_raw, list):
        return 0
    errors = 0
    for plugin in plugins_raw:  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(plugin, dict):
            continue
        plugin_dict = cast("dict[str, Any]", plugin)
        name = str(plugin_dict.get("name", "<unnamed>"))
        source_field = plugin_dict.get("source")
        local_path = ""
        is_local = False
        if isinstance(source_field, str):
            local_path = source_field
            is_local = True
        elif isinstance(source_field, dict):
            source_dict = cast("dict[str, Any]", source_field)
            if source_dict.get("source") == "local":
                local_path = str(source_dict.get("path", ""))
                is_local = True
        if not is_local:
            continue
        if not local_path.startswith("./"):
            print(f"  ERROR [{name}]: source.path {local_path!r} must start with './'")
            errors += 1
        normalized = local_path[2:] if local_path.startswith("./") else local_path
        if not normalized or normalized.strip("/") == "":
            print(
                f"  ERROR [{name}]: source.path {local_path!r} must be a non-empty subdirectory "
                "(Codex 0.125+ rejects './')"
            )
            errors += 1
        if ".." in local_path:
            print(f"  ERROR [{name}]: source.path {local_path!r} must not contain '..'")
            errors += 1
    return errors


def _validate_plugin(path: Path) -> int:
    print(f"Validating plugin manifest: {path.relative_to(REPO_ROOT)}")
    try:
        data_raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  ERROR: invalid JSON: {exc}")
        return 1
    if not isinstance(data_raw, dict):
        return 0
    data = cast("dict[str, Any]", data_raw)
    user_config_raw = data.get("userConfig")
    if not isinstance(user_config_raw, dict):
        return 0
    user_config = cast("dict[str, Any]", user_config_raw)
    errors = 0
    valid_types = {"string", "number", "boolean", "directory", "file"}
    for key, entry in user_config.items():
        if not re.match(r"^[a-z][a-zA-Z0-9]*$", key):
            print(f"  ERROR [userConfig]: key {key!r} must be camelCase (no hyphens/underscores)")
            errors += 1
        if not isinstance(entry, dict):
            continue
        entry_dict = cast("dict[str, Any]", entry)
        type_val = entry_dict.get("type")
        if type_val not in valid_types:
            print(
                f"  ERROR [userConfig.{key}]: type {type_val!r} must be one of {sorted(valid_types)} (no 'select'/enum)"
            )
            errors += 1
        if not entry_dict.get("title"):
            print(f"  ERROR [userConfig.{key}]: missing required 'title' field")
            errors += 1
    return errors


def main() -> int:
    total_errors = 0
    for path in _iter_codex_marketplaces():
        total_errors += _validate_marketplace(path)
    for path in _iter_codex_plugins():
        total_errors += _validate_plugin(path)
    if total_errors:
        print(f"\nValidation failed: {total_errors} violation(s)", file=sys.stderr)
        return 1
    print("\nAll manifests are valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
