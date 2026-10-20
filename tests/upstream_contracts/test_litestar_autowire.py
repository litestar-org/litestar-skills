"""Upstream contract verification for litestar-autowire 0.2.0."""

import inspect
import sys
from importlib.metadata import version
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import litestar_autowire
import pytest
from dishka import Provider, Scope, make_async_container
from dishka.integrations.litestar import DishkaRouter, setup_dishka
from litestar import Litestar, Router
from litestar.config.app import AppConfig
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


class _ContractAuditIntegration:
    """Custom integration verifying the AutowireIntegration protocol."""

    name = "audit"

    def on_autowire(self, context: AutowireContext) -> None:
        """Record discovered feature packages on AppConfig state."""
        context.app_config.state["autowire_domains"] = context.feature_packages


NON_CALLABLE_ATTR = "not-a-callable"
RECORDED_DOTTED_LOADS: list[str] = []


def dotted_loader_target(module_path: str) -> int:
    """Callable resolved via dotted string by AutowireLoader tests."""
    RECORDED_DOTTED_LOADS.append(module_path)
    return 3


def _make_contract_greeting_provider() -> Provider:
    """Build a request-scoped Dishka provider for _ContractGreetingService."""
    provider = Provider(scope=Scope.REQUEST)
    provider.provide(_ContractGreetingService)
    return provider


def test_litestar_autowire_020_version_and_exports() -> None:
    """Verify installed version and exact public symbol exports for litestar-autowire 0.2.0."""
    assert version("litestar-autowire") == "0.2.0"
    assert litestar_autowire.__version__ == "0.2.0"
    assert litestar_autowire.__project__ == "litestar-autowire"
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


def test_litestar_autowire_020_config_context_and_error_contract() -> None:
    """Verify AutowireConfig/AutowireLoader signatures, AutowireContext, and validation errors."""
    config_params = list(inspect.signature(AutowireConfig.__init__).parameters.values())[1:]
    assert all(param.kind is inspect.Parameter.KEYWORD_ONLY for param in config_params)

    loader_params = list(inspect.signature(AutowireLoader.__init__).parameters.values())[1:]
    assert [param.name for param in loader_params] == ["name", "modules", "loader"]
    assert all(param.kind is inspect.Parameter.KEYWORD_ONLY for param in loader_params)

    config = AutowireConfig(
        domain_packages="app.domain",
        integrations=["dishka", "queues", _ContractAuditIntegration()],
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
    assert config.integration_enabled("audit") is True
    assert config.integration_enabled("custom") is False
    assert isinstance(config.integrations[0], DishkaIntegration)
    assert isinstance(config.integrations[1], QueuesIntegration)
    assert isinstance(config.integrations[2], _ContractAuditIntegration)

    context = AutowireContext(
        app_config=AppConfig(),
        config=config,
        feature_packages=("app.domain",),
        controllers=[],
        listeners=[],
    )
    context.task_names.update({"task.a", "task.b"})
    context.record_task_count(3)
    assert context.task_count == 5
    with pytest.raises(ValueError, match="zero or greater"):
        context.record_task_count(-1)

    with pytest.raises(TypeError, match="renamed to integrations"):
        AutowireConfig(extensions=["dishka"])
    with pytest.raises(ValueError, match="Unsupported Autowire integration"):
        AutowireConfig(integrations=["unknown"])
    with pytest.raises(ValueError, match="Duplicate Autowire integration name"):
        AutowireConfig(integrations=["dishka", "dishka"])
    with pytest.raises(TypeError, match="non-empty string 'name'"):
        AutowireConfig(integrations=[cast("Any", object())])
    with pytest.raises(ValueError, match="non-empty name"):
        AutowireLoader(name="", modules="jobs", loader=lambda _mod: None)
    with pytest.raises(ValueError, match="conflict with built-in integration"):
        AutowireConfig(
            integrations=[
                AutowireLoader(name="dishka", modules="jobs", loader=lambda _mod: None),
            ]
        )

    for bad_loader_spec, exc_type in (
        ("invalid_without_sep", ValueError),
        ("nonexistent_autowire_pkg_xyz:func", ValueError),
        (f"{__name__}:missing_callable_xyz", ValueError),
        (f"{__name__}:NON_CALLABLE_ATTR", TypeError),
    ):
        bad_loader = AutowireLoader(name="bad", modules="handlers", loader=bad_loader_spec)
        with pytest.raises(exc_type):
            bad_loader.on_autowire(context)


def test_litestar_autowire_020_plugin_discovery_loader_and_queues_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify end-to-end controller, listener, AutowireLoader, Queues, and fail-fast discovery."""
    clear_autowire_cache()
    RECORDED_DOTTED_LOADS.clear()
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

    broken_dep_dir = tmp_path / "autowire_broken_dep_app" / "domains" / "billing"
    broken_dep_dir.mkdir(parents=True)
    (broken_dep_dir / "controllers.py").write_text(
        "import definitely_missing_internal_dependency_xyz\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "path", [str(tmp_path), *sys.path])
    loaded_modules: list[str] = []

    def record_module(module_path: str) -> int:
        loaded_modules.append(module_path)
        return 2

    try:
        features = discover_feature_packages(["autowire_contract_app.domains"])
        assert features == (
            "autowire_contract_app.domains",
            "autowire_contract_app.domains.accounts",
        )
        controllers = discover_controllers(["autowire_contract_app.domains"])
        listeners = discover_listeners(["autowire_contract_app.domains"])
        assert [cls.__name__ for cls in controllers] == ["AccountController"]
        assert len(listeners) == 1
        controllers_mod = sys.modules["autowire_contract_app.domains.accounts.controllers"]
        events_mod = sys.modules["autowire_contract_app.domains.accounts.events"]
        assert find_controllers_in_module(controllers_mod) == controllers
        assert find_listeners_in_module(events_mod) == listeners

        plugin = AutowirePlugin(
            AutowireConfig(
                domain_packages=["autowire_contract_app.domains"],
                router_class=Router,
                integrations=[
                    _ContractAuditIntegration(),
                    AutowireLoader(
                        name="handlers_callable",
                        modules="handlers",
                        loader=record_module,
                    ),
                    AutowireLoader(
                        name="handlers_dotted",
                        modules=["handlers"],
                        loader=f"{__name__}:dotted_loader_target",
                    ),
                ],
            )
        )
        app = Litestar(plugins=[plugin])
        with TestClient(app=app) as client:
            response = client.get("/accounts")
        assert response.status_code == 200
        assert response.json() == {"domain": "accounts"}
        assert app.state["autowire_domains"] == features
        assert loaded_modules == ["autowire_contract_app.domains.accounts.handlers"]
        assert RECORDED_DOTTED_LOADS == ["autowire_contract_app.domains.accounts.handlers"]

        queue_calls: list[tuple[str, str, bool]] = []

        def fake_discover_tasks(package_name: str, *, subpackage: str, force_reload: bool) -> list[str]:
            queue_calls.append((package_name, subpackage, force_reload))
            return [f"{package_name}.{subpackage}.send_invoice"]

        monkeypatch.setitem(sys.modules, "litestar_queues", SimpleNamespace(discover_tasks=fake_discover_tasks))
        discovered_tasks = discover_queue_tasks(
            ["autowire_contract_app.domains"],
            module_names=("jobs",),
            force_reload=True,
        )
        assert discovered_tasks == ("autowire_contract_app.domains.jobs.send_invoice",)
        assert queue_calls == [("autowire_contract_app.domains", "jobs", True)]

        monkeypatch.setitem(sys.modules, "litestar_queues", SimpleNamespace())
        with pytest.raises(RuntimeError, match="does not expose discover_tasks"):
            discover_queue_tasks(["autowire_contract_app.domains"])

        with pytest.raises(ModuleNotFoundError) as exc_info:
            discover_controllers(["autowire_broken_dep_app.domains"])
        assert exc_info.value.name == "definitely_missing_internal_dependency_xyz"
    finally:
        clear_autowire_cache()
        RECORDED_DOTTED_LOADS.clear()


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
        preserve_context = AutowireContext(
            app_config=AppConfig(),
            config=AutowireConfig(router_class=Router, integrations=["dishka"]),
            feature_packages=(),
            controllers=[],
            listeners=[],
            router_class=Router,
        )
        DishkaIntegration().on_autowire(preserve_context)
        assert preserve_context.router_class is Router

        default_context = AutowireContext(
            app_config=AppConfig(),
            config=AutowireConfig(integrations=["dishka"]),
            feature_packages=(),
            controllers=[],
            listeners=[],
            router_class=None,
        )
        DishkaIntegration().on_autowire(default_context)
        assert default_context.router_class is DishkaRouter

        discovered = discover_controllers(["autowire_dishka_app.domains"])
        greeting_cls = next(cls for cls in discovered if cls.__name__ == "GreetingController")
        plain_cls = next(cls for cls in discovered if cls.__name__ == "PlainController")
        assert "get_route_handlers" not in greeting_cls.__dict__
        assert "get_route_handlers" not in plain_cls.__dict__

        with pytest.MonkeyPatch.context() as inner_mp:
            inner_mp.setattr(greeting_cls, "get_route_handlers", greeting_cls.get_route_handlers)
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
            assert "get_route_handlers" in greeting_cls.__dict__
            assert "get_route_handlers" in plain_cls.__dict__
            with TestClient(app=dishka_app) as client:
                assert client.get("/greetings").json() == {"greeting": "hello"}
                assert client.get("/plain").json() == {"plain": "ok"}

            unconfigured_app = Litestar(
                route_handlers=[greeting_cls],
                debug=True,
            )
            with TestClient(app=unconfigured_app, raise_server_exceptions=False) as unconfigured_client:
                unconfigured_res = unconfigured_client.get("/greetings")
                assert unconfigured_res.status_code == 500
                assert "dishka_container" in unconfigured_res.text

        assert "get_route_handlers" not in greeting_cls.__dict__
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
