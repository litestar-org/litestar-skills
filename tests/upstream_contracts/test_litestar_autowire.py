"""Upstream contract verification for litestar-autowire 0.2.0."""

import sys
from importlib.metadata import version
from pathlib import Path

import pytest
from litestar import Litestar
from litestar.testing import TestClient
from litestar_autowire import (
    AutowireConfig,
    AutowireContext,
    AutowireIntegration,
    AutowireLoader,
    AutowirePlugin,
    DishkaIntegration,
    QueuesIntegration,
    clear_autowire_cache,
    discover_controllers,
    discover_feature_packages,
    discover_listeners,
    discover_queue_tasks,
    find_controllers_in_module,
    find_listeners_in_module,
)


def test_litestar_autowire_020_version_and_exports() -> None:
    """Verify installed version and public symbol exports for litestar-autowire 0.2.0."""
    assert version("litestar-autowire") == "0.2.0"
    assert all(
        symbol is not None
        for symbol in (
            AutowireConfig,
            AutowireContext,
            AutowireIntegration,
            AutowireLoader,
            AutowirePlugin,
            DishkaIntegration,
            QueuesIntegration,
            clear_autowire_cache,
            discover_controllers,
            discover_feature_packages,
            discover_listeners,
            discover_queue_tasks,
            find_controllers_in_module,
            find_listeners_in_module,
        )
    )


def test_litestar_autowire_020_config_and_error_contract() -> None:
    """Verify AutowireConfig normalization, defaults, integration helpers, and validation errors."""
    config = AutowireConfig(
        domain_packages="app.domain",
        integrations=["dishka", "queues"],
    )
    assert config.domain_packages == ("app.domain",)
    assert config.discover_controllers is True
    assert config.discover_listeners is True
    assert config.controller_modules == ("controllers", "routes", "controller", "route")
    assert config.listener_modules == ("events", "listeners")
    assert config.task_modules == ("jobs",)
    assert config.router_class is None
    assert config.before_request is None
    assert config.after_response is None
    assert config.force_reload_tasks is False
    assert config.log_discovered is True
    assert config.integration_enabled("dishka") is True
    assert config.integration_enabled("queues") is True
    assert config.integration_enabled("custom") is False
    assert isinstance(config.integrations[0], DishkaIntegration)
    assert isinstance(config.integrations[1], QueuesIntegration)

    with pytest.raises(TypeError, match="renamed to integrations"):
        AutowireConfig(extensions=["dishka"])
    with pytest.raises(ValueError, match="Unsupported Autowire integration"):
        AutowireConfig(integrations=["unknown"])
    with pytest.raises(ValueError, match="Duplicate Autowire integration name"):
        AutowireConfig(integrations=["dishka", "dishka"])
    with pytest.raises(ValueError, match="non-empty name"):
        AutowireLoader(name="", modules="jobs", loader=lambda _mod: None)
    with pytest.raises(ValueError, match="conflict with built-in integration"):
        AutowireConfig(
            integrations=[
                AutowireLoader(name="dishka", modules="jobs", loader=lambda _mod: None),
            ]
        )


def test_litestar_autowire_020_plugin_discovery_and_loader_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify end-to-end controller, listener, and AutowireLoader discovery via AutowirePlugin."""
    clear_autowire_cache()
    domain_dir = tmp_path / "autowire_contract_app" / "domains" / "accounts"
    domain_dir.mkdir(parents=True)

    (domain_dir / "controllers.py").write_text(
        """
from litestar import Controller, get


class AccountController(Controller):
    path = "/accounts"

    @get()
    async def list_accounts(self) -> dict[str, str]:
        return {"domain": "accounts"}
""",
        encoding="utf-8",
    )
    (domain_dir / "events.py").write_text(
        """
from litestar.events import listener


@listener("account.created")
async def on_account_created() -> None:
    return None
""",
        encoding="utf-8",
    )
    (domain_dir / "handlers.py").write_text(
        "HANDLER_COUNT = 2\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "path", [str(tmp_path), *sys.path])
    loaded_modules: list[str] = []

    def record_module(module_path: str) -> int:
        loaded_modules.append(module_path)
        return 2

    try:
        plugin = AutowirePlugin(
            AutowireConfig(
                domain_packages=["autowire_contract_app.domains"],
                integrations=[
                    AutowireLoader(
                        name="handlers",
                        modules="handlers",
                        loader=record_module,
                    )
                ],
            )
        )
        app = Litestar(plugins=[plugin])
        with TestClient(app=app) as client:
            response = client.get("/accounts")
        assert response.status_code == 200
        assert response.json() == {"domain": "accounts"}
        assert loaded_modules == ["autowire_contract_app.domains.accounts.handlers"]
    finally:
        clear_autowire_cache()
