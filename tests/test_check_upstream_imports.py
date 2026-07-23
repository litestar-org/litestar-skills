"""Tests for tools/check-upstream-imports.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "tools" / "check-upstream-imports.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("check_upstream_imports", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_upstream_imports"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_iter_skill_sources_includes_command_toml(tmp_path: Path) -> None:
    mod = _load_module()
    mod.SKILLS_DIR = tmp_path / "skills"
    mod.COMMANDS_DIR = tmp_path / "commands"
    (mod.SKILLS_DIR / "demo").mkdir(parents=True)
    (mod.COMMANDS_DIR / "litestar").mkdir(parents=True)
    skill = mod.SKILLS_DIR / "demo" / "SKILL.md"
    command = mod.COMMANDS_DIR / "litestar" / "demo.toml"
    skill.write_text("```python\nimport demo\n```\n")
    command.write_text('prompt = """\n```python\nfrom demo import Thing\n```\n"""\n')
    assert list(mod.iter_skill_sources()) == [command, skill]


def test_manifest_import_roots_are_targets(tmp_path: Path) -> None:
    mod = _load_module()
    manifest = tmp_path / "upstream-releases.toml"
    manifest.write_text(
        '[[package]]\npypi = "demo-package"\nversion = "1.0.0"\n'
        'date = "2026-07-23"\ntag = "v1.0.0"\nskills = ["skills/demo"]\nimports = ["demo_root"]\n'
    )
    assert mod.load_manifest_import_roots(manifest) == frozenset({"demo_root"})


def test_strict_missing_package_turns_warning_into_violation(monkeypatch: Any) -> None:
    mod = _load_module()
    ref = mod.ImportRef(
        file=Path("demo.md"),
        line_in_file=1,
        module="definitely_missing_package",
        name=None,
        raw="import definitely_missing_package",
    )

    def _missing(_name: str) -> object:
        exc = ModuleNotFoundError("missing")
        exc.name = "definitely_missing_package"
        raise exc

    monkeypatch.setattr(mod.importlib, "import_module", _missing)
    result = mod.classify_import(ref, {}, strict_missing=False)
    assert result == ("missing", "definitely_missing_package")
    strict_result = mod.classify_import(ref, {}, strict_missing=True)
    assert strict_result[0] == "violation"
