"""Smoke tests for .opencode/plugins/litestar-skills.js.

These tests exercise the plugin module in a Node subprocess, asserting:

1. The default export is a function (the OpenCode plugin contract).
2. Calling it returns an object containing `experimental.chat.system.transform`
   and `shell.env` handlers.
3. The transform handler pushes a Litestar reminder into `output.system` when
   the cwd looks like a Litestar project.
4. The transform handler is a no-op when `output.system` is missing.
5. Managed-config (`disabledPlugins`/`allowedPlugins`) early-returns to `{}`.
6. `shell.env` returns `LITESTAR_SKILLS_PLUGIN_ROOT`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_PATH = REPO_ROOT / ".opencode" / "plugins" / "litestar-skills.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not available")


def _run_node(script: str, cwd: Path) -> dict[str, Any]:
    """Eval a small Node script that imports the plugin and returns JSON to stdout."""
    plugin_url = PLUGIN_PATH.as_uri()
    full = f"""
import('{plugin_url}').then(async (mod) => {{
  {script}
}}).catch(err => {{
  process.stdout.write(JSON.stringify({{error: String(err), stack: err?.stack}}));
  process.exit(0);
}});
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", full],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(cwd),
        timeout=60,
    )
    parsed: dict[str, Any] = json.loads(result.stdout) if result.stdout else {}
    return parsed


@pytest.fixture
def litestar_cwd(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "myapp"\ndependencies = ["litestar", "sqlspec"]\n')
    return tmp_path


def test_default_export_is_a_function(tmp_path: Path) -> None:
    out = _run_node(
        "process.stdout.write(JSON.stringify({type: typeof mod.default}));",
        tmp_path,
    )
    assert out == {"type": "function"}


def test_returns_handler_object(tmp_path: Path) -> None:
    out = _run_node(
        """
        const handlers = await mod.default({});
        process.stdout.write(JSON.stringify({keys: Object.keys(handlers)}));
        """,
        tmp_path,
    )
    keys = out.get("keys", [])
    assert "experimental.chat.system.transform" in keys
    assert "shell.env" in keys


def test_transform_pushes_reminder(litestar_cwd: Path) -> None:
    out = _run_node(
        """
        const handlers = await mod.default({});
        const output = {system: []};
        await handlers['experimental.chat.system.transform']({}, output);
        process.stdout.write(JSON.stringify({system: output.system}));
        """,
        litestar_cwd,
    )
    system: list[str] = out.get("system", [])
    assert isinstance(system, list)
    assert len(system) == 1
    assert "litestar-skills:litestar" in system[0]
    assert "litestar-skills:sqlspec" in system[0]


def test_transform_noops_when_output_shape_unrecognised(tmp_path: Path) -> None:
    out = _run_node(
        """
        const handlers = await mod.default({});
        await handlers['experimental.chat.system.transform']({}, undefined);
        await handlers['experimental.chat.system.transform']({}, {});
        process.stdout.write(JSON.stringify({ok: true}));
        """,
        tmp_path,
    )
    assert out == {"ok": True}


def test_managed_config_disabled_plugins_returns_empty(tmp_path: Path) -> None:
    out = _run_node(
        """
        const handlers = await mod.default({
            config: { managedConfig: { disabledPlugins: ['litestar-skills'] } }
        });
        process.stdout.write(JSON.stringify({keys: Object.keys(handlers)}));
        """,
        tmp_path,
    )
    assert out == {"keys": []}


def test_managed_config_allowed_plugins_excludes_us(tmp_path: Path) -> None:
    out = _run_node(
        """
        const handlers = await mod.default({
            config: { managedConfig: { allowedPlugins: ['some-other-plugin'] } }
        });
        process.stdout.write(JSON.stringify({keys: Object.keys(handlers)}));
        """,
        tmp_path,
    )
    assert out == {"keys": []}


def test_managed_config_allowed_plugins_includes_us(tmp_path: Path) -> None:
    out = _run_node(
        """
        const handlers = await mod.default({
            config: { managedConfig: { allowedPlugins: ['litestar-skills'] } }
        });
        process.stdout.write(JSON.stringify({keys: Object.keys(handlers)}));
        """,
        tmp_path,
    )
    keys = out.get("keys", [])
    assert "experimental.chat.system.transform" in keys


def test_shell_env_exposes_plugin_root(tmp_path: Path) -> None:
    out = _run_node(
        """
        const handlers = await mod.default({});
        const result = await handlers['shell.env']();
        process.stdout.write(JSON.stringify(result));
        """,
        tmp_path,
    )
    env: dict[str, str] = out.get("env", {})
    assert isinstance(env, dict)
    plugin_root: str = env.get("LITESTAR_SKILLS_PLUGIN_ROOT", "")
    assert isinstance(plugin_root, str)
    assert plugin_root.endswith("litestar-skills")
