"""Upstream contract verification for litestar-autowire 0.2.0."""

import sys
from importlib.metadata import version
from pathlib import Path

import litestar_autowire
import pytest
from dishka import Provider, Scope, make_async_container
from dishka.integrations.litestar import setup_dishka
from litestar import Litestar, Router
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


class _ContractGreetingService:
    """Simple runtime service used to verify Dishka controller wiring."""

    def greet(self) -> str:
        """Return a static greeting payload."""
        return "hello"


def _make_contract_greeting_provider() -> Provider:
    """Build a request-scoped Dishka provider for _ContractGreetingService."""
    provider = Provider(scope=Scope.REQUEST)
    provider.provide(_ContractGreetingService)
    return provider


def test_litestar_autowire_020_version_and_exports() -> None:
    """Verify installed version and exact public symbol exports for litestar-autowire 0.2.0."""
    assert version("litestar-autowire") == "0.2.0"
    assert set(litestar_autowire.__all__) == {
        "AutowireConfig",
        "AutowireContext",
        "AutowireIntegration",
        "AutowireLoader",
        "AutowirePlugin",
        "DishkaIntegration",
        "QueuesIntegration",
        "__project__",
        "__version__",
        "clear_autowire_cache",
        "discover_controllers",
        "discover_feature_packages",
        "discover_listeners",
        "discover_queue_tasks",
        "find_controllers_in_module",
        "find_listeners_in_module",
    }
    for absent_symbol in (
        "AutowireRegistry",
        "DomainMetadata",
        "DiscoveredCLI",
        "DiscoveredController",
        "DiscoveredJob",
        "DiscoveredProvider",
        "DiscoveredSchema",
        "DiscoveredSignal",
        "LitestarQueuesIntegration",
        "SAQIntegration",
    ):
        assert not hasattr(litestar_autowire, absent_symbol)
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


def test_litestar_autowire_020_dishka_router_mutation_and_future_annotations_gotchas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify DishkaIntegration router selection, get_route_handlers mutation, and future annotations behavior."""
    clear_autowire_cache()
    domain_dir = tmp_path / "autowire_dishka_app" / "domains" / "greetings"
    domain_dir.mkdir(parents=True)

    (domain_dir / "controllers.py").write_text(
        f"""
from __future__ import annotations

from dishka import FromDishka
from litestar import Controller, get
from {__name__} import _ContractGreetingService


class GreetingController(Controller):
    path = "/greetings"

    @get()
    async def greet(self, service: FromDishka[_ContractGreetingService]) -> dict[str, str]:
        return {{"greeting": service.greet()}}


class PlainController(Controller):
    path = "/plain"

    @get()
    async def index(self) -> dict[str, str]:
        return {{"plain": "ok"}}
""",
        encoding="utf-8",
    )

    broken_dir = tmp_path / "autowire_broken_dishka_app" / "domains" / "broken"
    broken_dir.mkdir(parents=True)
    (broken_dir / "controllers.py").write_text(
        """
from __future__ import annotations

from typing import TYPE_CHECKING
from dishka import FromDishka
from litestar import Controller, get

if TYPE_CHECKING:
    class TypeCheckingOnlyService:
        pass


class BrokenController(Controller):
    path = "/broken"

    @get()
    async def broken(self, service: FromDishka[TypeCheckingOnlyService]) -> dict[str, str]:
        return {"broken": "never"}
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "path", [str(tmp_path), *sys.path])

    try:
        discovered = discover_controllers(["autowire_dishka_app.domains"])
        plain_cls = next(cls for cls in discovered if cls.__name__ == "PlainController")
        assert "get_route_handlers" not in plain_cls.__dict__

        with pytest.MonkeyPatch.context() as inner_mp:
            inner_mp.setattr(plain_cls, "get_route_handlers", plain_cls.get_route_handlers)
            dishka_app = Litestar(
                plugins=[
                    AutowirePlugin(
                        AutowireConfig(
                            domain_packages=["autowire_dishka_app.domains"],
                            integrations=["dishka"],
                        )
                    )
                ]
            )
            setup_dishka(make_async_container(_make_contract_greeting_provider()), dishka_app)
            assert "get_route_handlers" in plain_cls.__dict__
            with TestClient(app=dishka_app) as client:
                assert client.get("/greetings").json() == {"greeting": "hello"}
                assert client.get("/plain").json() == {"plain": "ok"}

        assert "get_route_handlers" not in plain_cls.__dict__
        plain_app = Litestar(
            route_handlers=[Router(path="/", route_handlers=[plain_cls])],
        )
        with TestClient(app=plain_app) as client:
            assert client.get("/plain").json() == {"plain": "ok"}

        with pytest.raises(NameError, match="TypeCheckingOnlyService"):
            Litestar(
                plugins=[
                    AutowirePlugin(
                        AutowireConfig(
                            domain_packages=["autowire_broken_dishka_app.domains"],
                            integrations=["dishka"],
                        )
                    )
                ]
            )
    finally:
        clear_autowire_cache()
