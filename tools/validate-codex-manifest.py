#!/usr/bin/env python3
"""Validate Codex marketplace + plugin manifests for compatibility with Codex CLI 0.125.0+.

Codex 0.125+ enforces:

* Local marketplace ``source.path`` MUST start with ``./``, MUST NOT contain ``..``,
  MUST NOT be empty/``./`` alone.
* ``source.path`` is resolved RELATIVE TO THE MARKETPLACE ROOT (the repo), not
  relative to the ``marketplace.json`` file. The resolved directory MUST exist
  and MUST contain a ``.codex-plugin/plugin.json``.
* ``userConfig`` keys MUST be camelCase; entries need a valid ``type`` and ``title``.
* ``interface.defaultPrompt`` is silently capped at 3 entries — anything beyond is
  dropped with a WARN in the TUI log.

Additionally verifies that ``plugins/litestar/`` is assembled with the expected
symlinks back to the repo-root canonical sources. Drift fails CI; the fix is
``make sync-codex-package``.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[1]

PACKAGE_ROOT = Path("plugins/litestar")
PACKAGE_DIR_SYMLINKS: tuple[tuple[str, str], ...] = (
    (".codex-plugin", "../../.codex-plugin"),
    ("skills", "../../skills"),
    ("commands", "../../commands"),
    (".codex", "../../.codex"),
    ("hooks", "../../hooks"),
)


def _validate_marketplace(path: Path) -> int:
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

        # Codex resolves source.path relative to the marketplace ROOT (the repo),
        # not relative to the marketplace.json file.
        resolved = (REPO_ROOT / normalized).resolve()
        if not resolved.is_dir():
            print(
                f"  ERROR [{name}]: source.path {local_path!r} does not resolve to a directory "
                f"under the repo root ({resolved})"
            )
            errors += 1
        else:
            plugin_manifest = resolved / ".codex-plugin" / "plugin.json"
            if not plugin_manifest.is_file():
                print(
                    f"  ERROR [{name}]: source.path {local_path!r} is missing "
                    f".codex-plugin/plugin.json (looked at {plugin_manifest})"
                )
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

    errors = 0

    user_config_raw = data.get("userConfig")
    if isinstance(user_config_raw, dict):
        user_config = cast("dict[str, Any]", user_config_raw)
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
                    f"  ERROR [userConfig.{key}]: type {type_val!r} must be one of "
                    f"{sorted(valid_types)} (no 'select'/enum)"
                )
                errors += 1
            if not entry_dict.get("title"):
                print(f"  ERROR [userConfig.{key}]: missing required 'title' field")
                errors += 1

    interface = data.get("interface")
    if isinstance(interface, dict):
        interface_dict = cast("dict[str, Any]", interface)
        prompts_raw = interface_dict.get("defaultPrompt", [])
        if isinstance(prompts_raw, list):
            count = sum(1 for _ in prompts_raw)  # pyright: ignore[reportUnknownVariableType]
            if count > 3:
                print(
                    f"  ERROR [interface.defaultPrompt]: {count} entries; Codex caps at 3 and silently drops the rest"
                )
                errors += 1

    return errors


def _validate_codex_package_layout() -> int:
    package = REPO_ROOT / PACKAGE_ROOT
    print(f"Validating Codex package layout: {PACKAGE_ROOT}")
    errors = 0

    if not package.is_dir():
        print(f"  ERROR: package directory '{package}' is missing — run 'make sync-codex-package'")
        return 1

    expected_names = {name for name, _ in PACKAGE_DIR_SYMLINKS}
    actual_names = {p.name for p in package.iterdir()}

    for name, expected_target in PACKAGE_DIR_SYMLINKS:
        link = package / name
        errors += _check_symlink(link, expected_target)

    for stray in sorted(actual_names - expected_names):
        print(f"  ERROR [stray]: {PACKAGE_ROOT}/{stray} (expected only {sorted(expected_names)})")
        errors += 1

    if errors:
        print("  HINT: run 'make sync-codex-package' and commit the result")
    return errors


def _check_symlink(link: Path, expected_target: str) -> int:
    if not link.is_symlink():
        if link.exists():
            print(f"  ERROR [not-a-symlink]: {link} (expected -> {expected_target})")
        else:
            print(f"  ERROR [missing-link]: {link} (expected -> {expected_target})")
        return 1
    actual = os.readlink(link).replace("\\", "/")
    if actual != expected_target:
        print(f"  ERROR [wrong-target]: {link} -> {actual} (expected -> {expected_target})")
        return 1
    if not link.resolve().exists():
        print(f"  ERROR [dangling]: {link} -> {actual}")
        return 1
    return 0


def _iter_codex_marketplaces() -> Iterator[Path]:
    candidate = REPO_ROOT / ".agents" / "plugins" / "marketplace.json"
    if candidate.is_file():
        yield candidate


def _iter_codex_plugins() -> Iterator[Path]:
    root_manifest = REPO_ROOT / ".codex-plugin" / "plugin.json"
    if root_manifest.is_file():
        yield root_manifest


def main() -> int:
    total_errors = 0
    for path in _iter_codex_marketplaces():
        total_errors += _validate_marketplace(path)
    for path in _iter_codex_plugins():
        total_errors += _validate_plugin(path)
    total_errors += _validate_codex_package_layout()

    if total_errors:
        print(f"\nValidation failed: {total_errors} violation(s)", file=sys.stderr)
        return 1
    print("\nAll manifests are valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
