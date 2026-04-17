"""Tests for tools/sync-manifests.py."""

import importlib.util
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "tools" / "sync-manifests.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("sync_manifests", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sync_manifests"] = mod
    spec.loader.exec_module(mod)
    return mod


def _write_pyproject(root: Path, files: list[tuple[str, str]], version: str) -> None:
    """Emit a minimal pyproject.toml with [[tool.bumpversion.files]] entries."""
    lines = [
        "[tool.bumpversion]",
        f'current_version = "{version}"',
        "",
    ]
    for filename, search in files:
        lines.extend(
            [
                "[[tool.bumpversion.files]]",
                f'filename = "{filename}"',
                f"search = '{search}'",
                "",
            ]
        )
    (root / "pyproject.toml").write_text("\n".join(lines))


class TestCheck:
    def test_happy_path_returns_empty(self, tmp_path: Path) -> None:
        mod = _load_module()
        _write_pyproject(
            tmp_path,
            [
                ("a.json", '"version": "{current_version}"'),
                ("b.txt", 'VERSION="{current_version}"'),
            ],
            "1.2.3",
        )
        (tmp_path / "a.json").write_text('{"version": "1.2.3"}\n')
        (tmp_path / "b.txt").write_text('VERSION="1.2.3"\n')
        errors = mod.check(tmp_path)
        assert errors == []

    def test_mismatched_version_yields_error(self, tmp_path: Path) -> None:
        mod = _load_module()
        _write_pyproject(
            tmp_path,
            [("a.json", '"version": "{current_version}"')],
            "1.2.3",
        )
        (tmp_path / "a.json").write_text('{"version": "1.2.2"}\n')
        errors = mod.check(tmp_path)
        assert len(errors) == 1
        assert "a.json" in errors[0]
        assert "1.2.3" in errors[0]

    def test_missing_target_file_yields_error(self, tmp_path: Path) -> None:
        mod = _load_module()
        _write_pyproject(
            tmp_path,
            [("missing.json", '"version": "{current_version}"')],
            "1.2.3",
        )
        errors = mod.check(tmp_path)
        assert len(errors) == 1
        assert "missing" in errors[0]

    def test_missing_pyproject_yields_error(self, tmp_path: Path) -> None:
        mod = _load_module()
        errors = mod.check(tmp_path)
        assert len(errors) == 1
        assert "pyproject.toml" in errors[0]

    def test_no_bumpversion_section_yields_error(self, tmp_path: Path) -> None:
        mod = _load_module()
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
        errors = mod.check(tmp_path)
        assert errors == ["pyproject.toml: no [tool.bumpversion] section"]

    def test_missing_current_version_yields_error(self, tmp_path: Path) -> None:
        mod = _load_module()
        (tmp_path / "pyproject.toml").write_text("[tool.bumpversion]\nother = true\n")
        errors = mod.check(tmp_path)
        assert len(errors) == 1
        assert "current_version" in errors[0]

    def test_no_files_entries_yields_error(self, tmp_path: Path) -> None:
        mod = _load_module()
        (tmp_path / "pyproject.toml").write_text('[tool.bumpversion]\ncurrent_version = "1.0.0"\n')
        errors = mod.check(tmp_path)
        assert len(errors) == 1
        assert "files" in errors[0].lower()

    def test_entry_without_filename_yields_error(self, tmp_path: Path) -> None:
        mod = _load_module()
        (tmp_path / "pyproject.toml").write_text(
            '[tool.bumpversion]\ncurrent_version = "1.0.0"\n\n'
            "[[tool.bumpversion.files]]\n"
            "search = 'v{current_version}'\n"
        )
        errors = mod.check(tmp_path)
        assert len(errors) == 1
        assert "filename" in errors[0].lower()

    def test_entry_without_search_yields_error(self, tmp_path: Path) -> None:
        mod = _load_module()
        (tmp_path / "pyproject.toml").write_text(
            "[tool.bumpversion]\ncurrent_version = \"1.0.0\"\n\n[[tool.bumpversion.files]]\nfilename = 'x.json'\n"
        )
        (tmp_path / "x.json").write_text("{}")
        errors = mod.check(tmp_path)
        assert len(errors) == 1
        assert "search" in errors[0].lower()


def test_main_exits_zero_on_real_repo() -> None:
    """Integration: the real repo's 8 tracked files must be in sync."""
    mod = _load_module()
    rc = mod.main()
    assert rc == 0


def test_main_returns_one_on_drift(tmp_path: Path, monkeypatch: "Any", capsys: Any) -> None:
    mod = _load_module()
    _write_pyproject(tmp_path, [("a.json", '"version": "{current_version}"')], "9.9.9")
    (tmp_path / "a.json").write_text('{"version": "1.0.0"}\n')
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    rc = mod.main()
    assert rc == 1
    captured = capsys.readouterr()
    assert "FAIL" in captured.err
