# Plugins (`litestar.plugins`, Built-in Plugins, and First-Party Ecosystem)

Plugins are the canonical extension mechanism in Litestar. A single plugin class can implement one or more plugin base classes (`InitPlugin`, `CLIPlugin`, `SerializationPlugin`, `OpenAPISchemaPlugin`, `ReceiveRoutePlugin`, `DIPlugin`) and is registered via `Litestar(plugins=[...])`.

---

## Plugin Base Classes & Protocols (`litestar.plugins`)

All plugin base classes and protocols are exported from `litestar.plugins`:

```python
from litestar.plugins import (
    CLIPlugin,
    CLIPluginProtocol,
    DIPlugin,
    InitPlugin,
    InitPluginProtocol,
    OpenAPISchemaPlugin,
    OpenAPISchemaPluginProtocol,
    PluginProtocol,
    PluginRegistry,
    ReceiveRoutePlugin,
    SerializationPlugin,
    SerializationPluginProtocol,
)
```

| Base Class / Protocol | Hook Methods | When It Runs |
| --- | --- | --- |
| `InitPlugin` (`InitPluginProtocol` is deprecated since 2.15) | `on_app_init(self, app_config: AppConfig) -> AppConfig` | During `Litestar.__init__`, before routes, middleware, and OpenAPI schemas are finalized |
| `CLIPlugin` / `CLIPluginProtocol` | `on_cli_init(self, cli: Group) -> None` and `@contextmanager def server_lifespan(self, app: Litestar) -> Iterator[None]` (on `CLIPlugin`) | When the `litestar` Click group initializes (`on_cli_init`) and around the ASGI server process started by `litestar run` (`server_lifespan`) |
| `SerializationPlugin` / `SerializationPluginProtocol` | `supports_type(self, field_definition: FieldDefinition) -> bool` and `create_dto_for_type(self, field_definition: FieldDefinition) -> type[AbstractDTO]` | When Litestar resolves request/response annotations into DTO classes |
| `OpenAPISchemaPlugin` / `OpenAPISchemaPluginProtocol` | `is_plugin_supported_field(self, field_definition: FieldDefinition) -> bool`, `to_openapi_schema(self, field_definition: FieldDefinition, schema_creator: SchemaCreator) -> Schema` (plus optional `is_plugin_supported_type`, `is_undefined_sentinel`, `is_constrained_field`) | During OpenAPI `Schema` generation for route parameters, request bodies, and responses |
| `ReceiveRoutePlugin` | `receive_route(self, route: BaseRoute) -> None` | Every time an `HTTPRoute`, `WebSocketRoute`, or `ASGIRoute` is registered on the application |
| `DIPlugin` | `has_typed_init(self, type_: Any) -> bool` and `get_typed_init(self, type_: Any) -> tuple[Signature, dict[str, Any]]` | When Litestar inspects a class constructor whose type hints are not exposed on `__init__` (such as `msgspec.Struct` or Pydantic models used as dependencies) |

### `PluginRegistry` (`app.plugins`)

At runtime, `app.plugins` is a `PluginRegistry` instance storing all registered plugins categorized by hook type:

- `app.plugins.get(MyPlugin)` or `app.plugins.get("MyPlugin")` — returns the registered plugin instance or raises `KeyError` (`get_plugin` on `Litestar` is deprecated; always use `app.plugins.get(...)`).
- `app.plugins.init: tuple[InitPluginProtocol, ...]`
- `app.plugins.cli: tuple[CLIPluginProtocol, ...]`
- `app.plugins.serialization: tuple[SerializationPluginProtocol, ...]`
- `app.plugins.openapi: tuple[OpenAPISchemaPluginProtocol, ...]`
- `app.plugins.receive_route: tuple[ReceiveRoutePlugin, ...]`
- `app.plugins.di: tuple[DIPlugin, ...]`

---

## Authoring Custom Plugins

### `InitPlugin` and `CLIPlugin`

Subclass `InitPlugin` to mutate `AppConfig` (routes, middleware, dependencies, lifespan context managers, signature namespace, state) and `CLIPlugin` to add `litestar` subcommands or wrap the `litestar run` server lifespan:

```python
from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from click import Group, command, echo
from litestar import Controller, Litestar, get
from litestar.di import Provide
from litestar.plugins import CLIPlugin, InitPlugin

if TYPE_CHECKING:
    from litestar.config.app import AppConfig


@dataclass
class FeaturePluginConfig:
    """Configuration for FeaturePlugin."""

    enabled: bool = True
    api_key: str | None = None


class FeaturePlugin(InitPlugin, CLIPlugin):
    """Custom plugin combining app initialization, lifespan, and CLI hooks."""

    __slots__ = ("config",)

    def __init__(self, config: FeaturePluginConfig | None = None) -> None:
        self.config = config or FeaturePluginConfig()

    @asynccontextmanager
    async def _lifespan(self, app: Litestar) -> AsyncGenerator[None, None]:
        app.state["feature_ready"] = True
        try:
            yield
        finally:
            app.state["feature_ready"] = False

    def on_app_init(self, app_config: AppConfig) -> AppConfig:
        if not self.config.enabled:
            return app_config
        app_config.state["feature_plugin"] = self
        app_config.dependencies["feature_plugin"] = Provide(
            lambda: self,
            sync_to_thread=False,
        )
        app_config.signature_types.append(FeaturePlugin)
        app_config.lifespan.append(self._lifespan)
        return app_config

    def on_cli_init(self, cli: Group) -> None:
        @command(name="feature-status")
        def feature_status() -> None:
            """Print whether the feature plugin is enabled."""
            echo(f"enabled={self.config.enabled}")

        cli.add_command(feature_status)

    @contextmanager
    def server_lifespan(self, app: Litestar) -> Iterator[None]:
        yield
```

Handlers can then inject `FeaturePlugin` directly as a typed dependency or look it up via `request.app.plugins.get(FeaturePlugin)`:

```python
class FeatureController(Controller):
    """Controller consuming FeaturePlugin via DI."""

    @get("/feature")
    async def status(self, feature_plugin: FeaturePlugin) -> dict[str, bool]:
        return {"key_set": feature_plugin.config.api_key is not None}
```

### `SerializationPlugin` and `OpenAPISchemaPlugin`

When integrating a custom model or value type that needs automatic DTO conversion and OpenAPI schema generation, subclass `SerializationPlugin` and `OpenAPISchemaPlugin`. Prefer `OpenAPISchemaPlugin` over `OpenAPISchemaPluginProtocol` because `OpenAPISchemaPlugin` implements `is_plugin_supported_field(field_definition)` directly:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from litestar.openapi.spec import OpenAPIFormat, OpenAPIType, Schema
from litestar.plugins import OpenAPISchemaPlugin, SerializationPlugin

if TYPE_CHECKING:
    from litestar._openapi.schema_generation import SchemaCreator
    from litestar.dto import AbstractDTO
    from litestar.typing import FieldDefinition


class CustomMoneySchemaPlugin(OpenAPISchemaPlugin):
    """Render Money fields as formatted string schemas in OpenAPI."""

    def is_plugin_supported_field(self, field_definition: FieldDefinition) -> bool:
        return field_definition.annotation is Money

    def to_openapi_schema(
        self,
        field_definition: FieldDefinition,
        schema_creator: SchemaCreator,
    ) -> Schema:
        return Schema(
            type=OpenAPIType.STRING,
            format=OpenAPIFormat.DECIMAL,
            examples=["19.99 USD"],
        )


class CustomModelSerializationPlugin(SerializationPlugin):
    """Attach a custom AbstractDTO subclass to supported model types."""

    def supports_type(self, field_definition: FieldDefinition) -> bool:
        return field_definition.is_subclass_of(CustomBaseModel)

    def create_dto_for_type(
        self,
        field_definition: FieldDefinition,
    ) -> type[AbstractDTO]:
        return CustomModelDTO[field_definition.annotation]
```

### `ReceiveRoutePlugin` and `DIPlugin`

Use `ReceiveRoutePlugin` to inspect or index routes as they are added to the app, and `DIPlugin` to teach Litestar how to inspect constructor signatures for custom classes that do not expose standard `__init__` annotations:

```python
from __future__ import annotations

from inspect import Signature
from typing import TYPE_CHECKING, Any

from litestar.plugins import DIPlugin, ReceiveRoutePlugin

if TYPE_CHECKING:
    from litestar.routes import BaseRoute


class RouteAuditPlugin(ReceiveRoutePlugin):
    """Collect all registered route paths at startup."""

    def __init__(self) -> None:
        self.paths: list[str] = []

    def receive_route(self, route: BaseRoute) -> None:
        self.paths.append(route.path)


class CustomStructDIPlugin(DIPlugin):
    """Provide constructor signature metadata for custom struct types."""

    def has_typed_init(self, type_: Any) -> bool:
        return isinstance(type_, type) and issubclass(type_, CustomStruct)

    def get_typed_init(self, type_: Any) -> tuple[Signature, dict[str, Any]]:
        return build_struct_signature(type_)
```

---

## Built-in Litestar Plugins (`litestar.plugins.*`)

Litestar ships several built-in plugins under `litestar.plugins.*`:

### `PydanticPlugin` (`litestar.plugins.pydantic`)

When `pydantic` is installed, Litestar automatically registers default Pydantic support (`PydanticInitPlugin`, `PydanticSchemaPlugin`, `PydanticDIPlugin`). Pass `PydanticPlugin` explicitly in `Litestar(plugins=[...])` when you need to customize global serialization or validation flags (or use `PydanticDTO` for per-route DTO config):

```python
from litestar import Litestar
from litestar.plugins.pydantic import PydanticDTO, PydanticPlugin

app = Litestar(
    plugins=[
        PydanticPlugin(
            prefer_alias=True,
            validate_strict=False,
            round_trip=False,
            exclude_none=True,
            exclude_unset=False,
            exclude_defaults=False,
        ),
    ],
)
```

### `StructlogPlugin` (`litestar.plugins.structlog`)

Configures `structlog` logging (`StructLoggingConfig`) and optionally attaches Litestar's request/response logging middleware (`LoggingMiddlewareConfig` when `enable_middleware_logging=True`, the default):

```python
from litestar import Litestar
from litestar.logging.config import StructLoggingConfig
from litestar.middleware.logging import LoggingMiddlewareConfig
from litestar.plugins.structlog import StructlogConfig, StructlogPlugin

structlog_plugin = StructlogPlugin(
    config=StructlogConfig(
        structlog_logging_config=StructLoggingConfig(log_exceptions="always"),
        middleware_logging_config=LoggingMiddlewareConfig(
            response_log_fields=["status_code"],
        ),
        enable_middleware_logging=True,
    ),
)

app = Litestar(plugins=[structlog_plugin])
```

### `ProblemDetailsPlugin` (`litestar.plugins.problem_details`)

Converts `ProblemDetailsException` (and optionally all `HTTPException` subclasses or mapped custom exceptions) into RFC 9457 `application/problem+json` responses:

```python
from litestar import Litestar, Request
from litestar.plugins.problem_details import (
    ProblemDetailsConfig,
    ProblemDetailsException,
    ProblemDetailsPlugin,
)


def domain_error_to_problem_details(
    request: Request,
    exc: ValueError,
) -> ProblemDetailsException:
    """Map a ValueError into an RFC 9457 ProblemDetailsException."""
    return ProblemDetailsException(
        status_code=422,
        title="Invalid domain value",
        detail=str(exc),
        type_="https://example.com/probs/invalid-value",
        instance=request.url.path,
    )


app = Litestar(
    plugins=[
        ProblemDetailsPlugin(
            config=ProblemDetailsConfig(
                enable_for_all_http_exceptions=True,
                exception_to_problem_detail_map={
                    ValueError: domain_error_to_problem_details,
                },
            ),
        ),
    ],
)
```

### `FlashPlugin` (`litestar.plugins.flash`)

Provides session-backed flash messaging for server-rendered templates (`JinjaTemplateEngine`, `MiniJinjaTemplateEngine`, `MakoTemplateEngine`).

> **Important:** `FlashPlugin.on_app_init` checks that `SessionMiddleware` (via `ServerSideSessionConfig` or `CookieBackendConfig`) or `SessionAuth` middleware is already present in `app_config.middleware`, and raises `ImproperlyConfiguredException` if missing.

```python
from pathlib import Path

from litestar import Litestar, Request, post
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.middleware.session.server_side import ServerSideSessionConfig
from litestar.plugins.flash import FlashConfig, FlashPlugin, flash, get_flashes
from litestar.response import Redirect
from litestar.template import TemplateConfig

template_config = TemplateConfig(
    directory=Path("templates"),
    engine=JinjaTemplateEngine,
)


@post("/items")
async def create_item(request: Request) -> Redirect:
    """Set a flash message in the session and redirect."""
    flash(request, message="Item created successfully.", category="success")
    return Redirect(path="/items")


app = Litestar(
    route_handlers=[create_item],
    middleware=[ServerSideSessionConfig().middleware],
    template_config=template_config,
    plugins=[FlashPlugin(config=FlashConfig(template_config=template_config))],
)
```

### `OpenTelemetryPlugin` (`litestar.plugins.opentelemetry`)

Requires `pip install "litestar[opentelemetry]"`. Wraps the ASGI application in `OpenTelemetryInstrumentationMiddleware` for distributed tracing and meter metrics:

```python
from litestar import Litestar
from litestar.plugins.opentelemetry import OpenTelemetryConfig, OpenTelemetryPlugin

app = Litestar(
    plugins=[
        OpenTelemetryPlugin(
            config=OpenTelemetryConfig(
                exclude=["/health", "/metrics"],
            ),
        ),
    ],
)
```

### Prometheus Metrics (`litestar.plugins.prometheus`) — No `PrometheusPlugin` Class

Requires `pip install "litestar[prometheus]"`. Unlike `OpenTelemetryPlugin`, `litestar.plugins.prometheus` **does not define a `PrometheusPlugin` class** — its public exports are `PrometheusConfig`, `PrometheusController`, and `PrometheusMiddleware`. Wire `PrometheusConfig.middleware` into `middleware=[...]` and `PrometheusController` into `route_handlers=[...]`:

```python
from litestar import Litestar
from litestar.plugins.prometheus import PrometheusConfig, PrometheusController

prometheus_config = PrometheusConfig(
    app_name="my-service",
    prefix="litestar",
    group_path=True,
)

app = Litestar(
    route_handlers=[PrometheusController],
    middleware=[prometheus_config.middleware],
)
```

### `SQLAlchemyPlugin` Migration Note (`advanced_alchemy.extensions.litestar`)

`litestar.plugins.sqlalchemy` is **deprecated as of Litestar 2.18.0** and will be removed in Litestar 3.0. Always import `SQLAlchemyPlugin`, `SQLAlchemyAsyncConfig`, `SQLAlchemySyncConfig`, `SQLAlchemyInitPlugin`, `SQLAlchemySerializationPlugin`, and `SQLAlchemyDTO` directly from `advanced_alchemy.extensions.litestar`:

```python
from advanced_alchemy.extensions.litestar import (
    SQLAlchemyAsyncConfig,
    SQLAlchemyDTO,
    SQLAlchemyInitPlugin,
    SQLAlchemyPlugin,
    SQLAlchemySerializationPlugin,
    SQLAlchemySyncConfig,
)
```

### `AttrsSchemaPlugin` (`litestar.plugins.attrs`)

When `attrs` is installed, `AttrsSchemaPlugin` is available in `litestar.plugins.attrs` to generate OpenAPI schemas for `@define` / `@attr.s` classes.

---

## First-Party Ecosystem Plugins

These plugins ship as dedicated first-party packages in the Litestar organization and have focused skills in this repository:

| Package & Plugin | Sibling Skill | Purpose |
| --- | --- | --- |
| `litestar_granian.GranianPlugin` | `../../litestar-granian/SKILL.md` | Granian Rust ASGI/HTTP server CLI integration (`litestar run`) |
| `litestar_saq.SAQPlugin` | `../../litestar-saq/SKILL.md` | Redis-backed SAQ background job queues, cron jobs, and worker CLI |
| `litestar_queues.QueuePlugin` | `../../litestar-queues/SKILL.md` | Database/memory-backed task queues (`SQLSpecBackendConfig`, `SQLAlchemyBackendConfig`) |
| `litestar_vite.VitePlugin` | `../../litestar-vite/SKILL.md` | Vite asset serving, HMR proxy, TypeGen, and Inertia.js SSR/CSR |
| `litestar_mcp.LitestarMCP` | `../../litestar-mcp/SKILL.md` | Model Context Protocol (MCP) tools, resources, and prompts over Streamable HTTP/stdio |
| `litestar_email.EmailPlugin` | `../../litestar-email/SKILL.md` | Async email delivery (SMTP, Resend, SendGrid, Mailgun, SES, InMemory) |
| `litestar_security.SecurityPlugin` | `../../litestar-security/SKILL.md` | Authentication, RBAC/ABAC guards, tenant isolation, and `SecurityContext` |
| `litestar_htmx.HTMXPlugin` | `../../litestar-htmx/SKILL.md` | HTMX request parsing (`HTMXRequest`) and partial HTML response helpers |
| `litestar_autowire.AutowirePlugin` | `../../litestar-autowire/SKILL.md` | Domain-package controller, listener, and task auto-discovery |
| `advanced_alchemy.extensions.litestar.SQLAlchemyPlugin` | `../../advanced-alchemy/SKILL.md` | SQLAlchemy session lifecycle, repositories, services, and Alembic CLI |
| `sqlspec.extensions.litestar.SQLSpecPlugin` | `../../sqlspec/SKILL.md` | SQL-first driver lifecycle, query loader, and Channels pub/sub backend |

---

## Wiring Multiple Plugins

Centralize plugin instantiation in a dedicated module (such as `app/server/plugins.py`) and pass the assembled list into `Litestar(plugins=[...])`:

```python
from __future__ import annotations

from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig, SQLAlchemyPlugin
from litestar import Litestar
from litestar.plugins.problem_details import ProblemDetailsConfig, ProblemDetailsPlugin
from litestar.plugins.structlog import StructlogConfig, StructlogPlugin
from litestar_autowire import AutowireConfig, AutowirePlugin
from litestar_granian import GranianPlugin
from litestar_mcp import LitestarMCP, MCPConfig
from litestar_saq import QueueConfig, SAQConfig, SAQPlugin
from litestar_vite import ViteConfig, VitePlugin

from app.lib.exceptions import ApplicationError, application_exception_handler
from app.lib.settings import get_settings

settings = get_settings()

app = Litestar(
    exception_handlers={ApplicationError: application_exception_handler},
    plugins=[
        GranianPlugin(),
        StructlogPlugin(config=StructlogConfig()),
        ProblemDetailsPlugin(
            config=ProblemDetailsConfig(enable_for_all_http_exceptions=True),
        ),
        SQLAlchemyPlugin(
            config=SQLAlchemyAsyncConfig(connection_string=settings.database.url),
        ),
        SAQPlugin(
            config=SAQConfig(
                use_server_lifespan=True,
                queue_configs=[QueueConfig(name="default", dsn=settings.redis.url)],
            ),
        ),
        VitePlugin(config=ViteConfig(dev_mode=settings.debug)),
        LitestarMCP(MCPConfig(name=settings.name)),
        AutowirePlugin(AutowireConfig(domain_packages=["app.domain"])),
    ],
)
```

## Cross-references

- Channels plugin (`ChannelsPlugin` in `litestar.channels`): [websockets.md](websockets.md)
- Domain-package auto-discovery: [litestar-autowire](../../litestar-autowire/SKILL.md)
- Exception handling & RFC 9457 Problem Details: [exceptions.md](exceptions.md)
- DTOs and OpenAPI schema customization: [dtos.md](dtos.md)
