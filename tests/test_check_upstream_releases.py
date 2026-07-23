"""Tests for tools/check-upstream-releases.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "tools" / "check-upstream-releases.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("check_upstream_releases", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_upstream_releases"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_select_latest_final_ignores_prereleases_and_fully_yanked_releases() -> None:
    mod = _load_module()
    releases = {
        "1.0.0": [{"yanked": False}],
        "1.1.0rc1": [{"yanked": False}],
        "1.1.0": [{"yanked": True}, {"yanked": True}],
        "1.0.1": [{"yanked": True}, {"yanked": False}],
    }
    assert str(mod.select_latest_final(releases)) == "1.0.1"


def test_validation_floor_requires_the_audited_version() -> None:
    mod = _load_module()
    assert mod.validation_floor('demo[extra]>=1.2.3; python_version >= "3.10"') == "1.2.3"
    assert mod.validation_floor("demo>=1.0") == "1.0"
    assert mod.validation_floor("demo") is None


def test_check_package_reports_pypi_floor_and_lock_drift(tmp_path: Path) -> None:
    mod = _load_module()
    package = mod.UpstreamPackage(
        pypi="demo",
        version="1.2.3",
        date="2026-07-23",
        tag="v1.2.3",
        skills=("skills/demo",),
        imports=("demo",),
    )
    (tmp_path / "skills" / "demo").mkdir(parents=True)
    errors = mod.check_package(
        package,
        root=tmp_path,
        pypi_releases={"1.2.3": [{"yanked": False}], "1.3.0": [{"yanked": False}]},
        validation_requirements={"demo": "demo>=1.0"},
        locked_versions={"demo": "1.2.2"},
    )
    assert any("PyPI latest final is 1.3.0" in error for error in errors)
    assert any("validation floor is 1.0" in error for error in errors)
    assert any("lock version is 1.2.2" in error for error in errors)


def test_check_package_accepts_matching_release_floor_lock_and_skill(tmp_path: Path) -> None:
    mod = _load_module()
    package = mod.UpstreamPackage(
        pypi="demo",
        version="1.2.3",
        date="2026-07-23",
        tag="v1.2.3",
        skills=("skills/demo",),
        imports=("demo",),
    )
    (tmp_path / "skills" / "demo").mkdir(parents=True)
    errors = mod.check_package(
        package,
        root=tmp_path,
        pypi_releases={"1.2.3": [{"yanked": False}]},
        validation_requirements={"demo": "demo>=1.2.3"},
        locked_versions={"demo": "1.2.3"},
    )
    assert errors == []
