"""Performance budgets for hooks.

Loose budgets — these are guardrails, not benchmarks. They flag clear
regressions without flaking on a busy CI runner.

Cold (first invocation, fresh fixture): <= 1500ms.
Warm (immediate re-invocation, same fixture): <= 500ms.

(Targets in PRD are 200ms / 50ms; CI runners are noisy enough that
we use 7.5x headroom to avoid false positives. Tighten locally if needed.)
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from tests.hooks._subproc import bash_executable, subprocess_env

REPO_ROOT = Path(__file__).resolve().parents[2]
SESSION_START = REPO_ROOT / "hooks" / "session-start.sh"

COLD_BUDGET_MS = 1500
WARM_BUDGET_MS = 500


@pytest.fixture
def litestar_cwd(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "myapp"\ndependencies = ["litestar", "msgspec"]\n')
    return tmp_path


def _run_once(cwd: Path) -> float:
    env = subprocess_env(overrides={"PWD": str(cwd), "CLAUDE_PLUGIN_ROOT": "/x"})
    start = time.perf_counter()
    result = subprocess.run(
        [bash_executable(), str(SESSION_START)],
        capture_output=True,
        env=env,
        cwd=str(cwd),
        check=True,
        timeout=10,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert result.returncode == 0
    return elapsed_ms


@pytest.mark.slow
def test_cold_warm_latency(litestar_cwd: Path) -> None:
    cold = _run_once(litestar_cwd)
    warm = _run_once(litestar_cwd)
    assert cold < COLD_BUDGET_MS, f"cold={cold:.0f}ms exceeded {COLD_BUDGET_MS}ms budget"
    assert warm < WARM_BUDGET_MS, f"warm={warm:.0f}ms exceeded {WARM_BUDGET_MS}ms budget"
