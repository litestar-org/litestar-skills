"""Tests for hooks/lib/detect-env.sh — bash detection library.

The library is invoked as `bash hooks/lib/detect-env.sh <project_root>` and emits
a JSON object with: detected_skills (list of skill ids), context (the assembled
reminder text), project_root (resolved path).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.hooks._subproc import bash_executable, subprocess_env

REPO_ROOT = Path(__file__).resolve().parents[2]
DETECT_ENV = REPO_ROOT / "hooks" / "lib" / "detect-env.sh"
SKILL_MAP = REPO_ROOT / "hooks" / "lib" / "skill-map.json"


def _run(project_root: Path, *, env_overrides: dict[str, str] | None = None) -> dict[str, Any]:
    """Run detect-env.sh against a project root and return the parsed JSON."""
    assert DETECT_ENV.exists(), f"detect-env.sh missing: {DETECT_ENV}"
    result = subprocess.run(
        [bash_executable(), str(DETECT_ENV), str(project_root)],
        capture_output=True,
        text=True,
        env=subprocess_env(overrides=env_overrides),
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, f"detect-env.sh failed with {result.returncode}: stderr={result.stderr!r}"
    parsed: dict[str, Any] = json.loads(result.stdout)
    return parsed


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Empty project root."""
    return tmp_path


@pytest.fixture
def litestar_project(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "myapp"\ndependencies = ["litestar>=2.0", "msgspec"]\n')
    return tmp_path


@pytest.fixture
def litestar_sqlspec_project(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "api"\ndependencies = ["litestar", "sqlspec[asyncpg]"]\n'
    )
    return tmp_path


@pytest.fixture
def deployment_project(tmp_path: Path) -> Path:
    (tmp_path / "Dockerfile").write_text("FROM python:3.13-slim\n")
    return tmp_path


@pytest.fixture
def import_only_project(tmp_path: Path) -> Path:
    """Project with no pyproject.toml but with .py files importing litestar."""
    src = tmp_path / "src" / "myapp"
    src.mkdir(parents=True)
    (src / "main.py").write_text("from litestar import Litestar, get\n\napp = Litestar([])\n")
    return tmp_path


def test_skill_map_exists() -> None:
    """skill-map.json must exist and be valid JSON with required structure."""
    assert SKILL_MAP.exists(), f"skill-map.json missing: {SKILL_MAP}"
    data = json.loads(SKILL_MAP.read_text())
    assert isinstance(data.get("matchers"), list)
    assert isinstance(data.get("static_intro"), str)
    assert all("skill" in m and "signals" in m and "reminder" in m for m in data["matchers"])


def test_empty_project_detects_nothing(tmp_project: Path) -> None:
    """An empty cwd should produce no detected skills, but still emit the static intro."""
    out = _run(tmp_project)
    assert out["detected_skills"] == []
    assert isinstance(out["context"], str)
    assert "litestar-skills loaded" in out["context"]


def test_litestar_pyproject_dep_detected(litestar_project: Path) -> None:
    """A pyproject.toml with `litestar` in dependencies should trigger the litestar skill."""
    out = _run(litestar_project)
    assert "litestar" in out["detected_skills"]
    assert "msgspec" in out["detected_skills"]
    assert "litestar-skills:litestar" in out["context"]


def test_litestar_plus_sqlspec(litestar_sqlspec_project: Path) -> None:
    """Both litestar and sqlspec should be detected and named in context."""
    out = _run(litestar_sqlspec_project)
    assert "litestar" in out["detected_skills"]
    assert "sqlspec" in out["detected_skills"]
    ctx = str(out["context"])
    assert "litestar-skills:litestar" in ctx
    assert "litestar-skills:sqlspec" in ctx


def test_dockerfile_triggers_deployment(deployment_project: Path) -> None:
    """Dockerfile presence should trigger litestar-deployment skill."""
    out = _run(deployment_project)
    assert "litestar-deployment" in out["detected_skills"]


def test_python_import_signal(import_only_project: Path) -> None:
    """A .py file importing litestar should trigger the skill even without pyproject.toml."""
    out = _run(import_only_project)
    assert "litestar" in out["detected_skills"]


def test_disable_env_var_short_circuits(litestar_project: Path) -> None:
    """LITESTAR_SKILLS_HOOK_DISABLE=1 should yield empty JSON object."""
    out = _run(litestar_project, env_overrides={"LITESTAR_SKILLS_HOOK_DISABLE": "1"})
    assert out == {}


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
def test_detection_order_uses_priority(litestar_sqlspec_project: Path) -> None:
    """Higher-priority skills should appear first in detected_skills order."""
    out = _run(litestar_sqlspec_project)
    skills = list(out["detected_skills"])
    assert skills.index("litestar") < skills.index("sqlspec")


def test_context_includes_static_intro(litestar_project: Path) -> None:
    """Static intro must always be included when at least one skill matches."""
    out = _run(litestar_project)
    ctx = str(out["context"])
    assert "litestar-skills loaded" in ctx


def test_pyproject_section_signal(tmp_path: Path) -> None:
    """A `[tool.sqlspec]` section in pyproject.toml triggers the sqlspec skill."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = []\n\n[tool.sqlspec]\ndefault_adapter = "asyncpg"\n'
    )
    out = _run(tmp_path)
    assert "sqlspec" in out["detected_skills"]


def test_pyproject_section_dotted(tmp_path: Path) -> None:
    """A `[tool.litestar.app]`-style nested section also triggers the skill."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = []\n\n[tool.litestar.app]\napp_factory = "myapp:create_app"\n'
    )
    out = _run(tmp_path)
    assert "litestar" in out["detected_skills"]


def test_hatch_binary_triggers_litestar_build(tmp_path: Path) -> None:
    """A `[tool.hatch.build.targets.binary]` section triggers litestar-build."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1.0"\ndependencies = []\n'
        '\n[tool.hatch.build.targets.binary]\npy-version = "3.13"\n'
    )
    out = _run(tmp_path)
    assert "litestar-build" in out["detected_skills"]
