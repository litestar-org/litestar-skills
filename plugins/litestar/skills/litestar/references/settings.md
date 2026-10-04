# Settings — Per-Stack Patterns

Litestar applications use one of two settings patterns depending on the project's dependency graph:

- **Pattern A: `@dataclass(slots=True)` + `get_env()` factory + `@lru_cache`** — stdlib dataclasses + `python-dotenv`; used by first-party canonical reference apps ([`litestar-fullstack`](https://github.com/litestar-org/litestar-fullstack) and [`litestar-sqlstack`](https://github.com/cofin/litestar-sqlstack)). Pick this for fresh projects and `msgspec`-first codebases.
- **Pattern B: `pydantic_settings.BaseSettings` + `@lru_cache`** — recommended when the project already depends on Pydantic for schemas, SQLModel, or shared microservice libraries. Pick this to keep a single validation stack.

Both patterns expose the same call-site contract: a cached `get_settings()` function returning a nested settings object with environment-driven defaults.

## Decision Guide

| If your project… | Pick |
| --- | --- |
| Is a fresh Litestar app using `msgspec` DTOs and no Pydantic dependency | Pattern A (`@dataclass(slots=True)` + `get_env`) |
| Already imports Pydantic for DTOs, ORM models, or third-party SDK schemas | Pattern B (`pydantic_settings.BaseSettings`) |
| Wants zero validation-library overhead on startup and follow `litestar-fullstack` / `litestar-sqlstack` | Pattern A |
| Needs Pydantic validators, secret-directory loaders, or nested delimiter parsing (`APP_DB__URL`) out of the box | Pattern B |
| Is migrating from FastAPI or SQLModel | Pattern B |

## Pattern A — `@dataclass(slots=True)` + Typed `get_env()` Factory

In [`litestar-fullstack`](https://github.com/litestar-org/litestar-fullstack) and [`litestar-sqlstack`](https://github.com/cofin/litestar-sqlstack), `get_env(key, default, type_hint=...)` returns a **zero-argument callable** (`Callable[[], T]`) rather than evaluating immediately. Passing `get_env(...)` directly to `field(default_factory=get_env("KEY", default))` defers environment variable lookup until `Settings.from_env()` runs (after `.env` is loaded) without repeating `lambda:` on every field.

### Step 1: Typed `app/utils/env.py` parser

```python
from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final, TypeVar, cast, overload

from typing_extensions import TypeAlias

T = TypeVar("T")
ParseTypes: TypeAlias = bool | int | str | list[str] | Path | list[Path] | dict[str, Any] | None


class UnsetType:
    """Placeholder sentinel for the Unset type."""


_UNSET = UnsetType()

TRUE_VALUES: Final[frozenset[str]] = frozenset({"True", "true", "1", "yes", "YES", "Y", "y", "T", "t"})


@overload
def get_config_val(key: str, default: bool, type_hint: type[ParseTypes] | UnsetType = _UNSET) -> bool: ...


@overload
def get_config_val(key: str, default: int, type_hint: type[ParseTypes] | UnsetType = _UNSET) -> int: ...


@overload
def get_config_val(key: str, default: str, type_hint: type[ParseTypes] | UnsetType = _UNSET) -> str: ...


@overload
def get_config_val(key: str, default: Path, type_hint: type[ParseTypes] | UnsetType = _UNSET) -> Path: ...


@overload
def get_config_val(key: str, default: list[Path], type_hint: type[ParseTypes] | UnsetType = _UNSET) -> list[Path]: ...


@overload
def get_config_val(key: str, default: list[str], type_hint: type[ParseTypes] | UnsetType = _UNSET) -> list[str]: ...


@overload
def get_config_val(key: str, default: None, type_hint: type[ParseTypes] | UnsetType = _UNSET) -> Any: ...


@overload
def get_config_val(key: str, default: ParseTypes, type_hint: type[T]) -> T: ...


def get_config_val(
    key: str,
    default: ParseTypes = None,
    type_hint: type[T] | UnsetType = _UNSET,
) -> Any:
    """Parse environment variable ``key`` into the type of ``default`` or ``type_hint``."""
    str_value = os.getenv(key)
    if str_value is None:
        return default
    value: Any = str_value
    if isinstance(default, bool) or type_hint is bool:
        return value in TRUE_VALUES
    if isinstance(default, int) or type_hint is int:
        return int(value)
    if isinstance(default, Path) or type_hint is Path:
        return Path(value)
    if (isinstance(default, list) and all(isinstance(v, Path) for v in default)) or type_hint == list[Path]:
        if value.startswith("[") and value.endswith("]"):
            try:
                return [Path(s) for s in json.loads(value)]
            except (ValueError, TypeError) as exc:
                msg = f"{key} is not a valid list[Path] representation."
                raise ValueError(msg) from exc
        return [Path(host_str.strip()) for host_str in value.split(",")]
    if (isinstance(default, list) and all(isinstance(v, str) for v in default)) or type_hint == list[str]:
        if value.startswith("[") and value.endswith("]"):
            try:
                return cast("list[str]", json.loads(value))
            except (ValueError, TypeError) as exc:
                msg = f"{key} is not a valid list[str] representation."
                raise ValueError(msg) from exc
        return [host_str.strip() for host_str in value.split(",")]
    if isinstance(default, dict) or type_hint == dict[str, Any]:
        if value.startswith("{") and value.endswith("}"):
            try:
                return cast("dict[str, Any]", json.loads(value))
            except (ValueError, TypeError) as exc:
                msg = f"{key} is not a valid dict representation."
                raise ValueError(msg) from exc
        return dict(pair.strip().split("=", 1) for pair in value.split(",") if "=" in pair)
    return value


@overload
def get_env(key: str, default: bool, type_hint: type[ParseTypes] | UnsetType = _UNSET) -> Callable[[], bool]: ...


@overload
def get_env(key: str, default: int, type_hint: type[ParseTypes] | UnsetType = _UNSET) -> Callable[[], int]: ...


@overload
def get_env(key: str, default: str, type_hint: type[ParseTypes] | UnsetType = _UNSET) -> Callable[[], str]: ...


@overload
def get_env(key: str, default: Path, type_hint: type[ParseTypes] | UnsetType = _UNSET) -> Callable[[], Path]: ...


@overload
def get_env(
    key: str, default: list[Path], type_hint: type[ParseTypes] | UnsetType = _UNSET
) -> Callable[[], list[Path]]: ...


@overload
def get_env(
    key: str, default: list[str], type_hint: type[ParseTypes] | UnsetType = _UNSET
) -> Callable[[], list[str]]: ...


@overload
def get_env(key: str, default: None, type_hint: type[ParseTypes] | UnsetType = _UNSET) -> Callable[[], Any]: ...


@overload
def get_env(key: str, default: ParseTypes, type_hint: type[T]) -> Callable[[], T]: ...


def get_env(
    key: str,
    default: ParseTypes = None,
    type_hint: type[T] | UnsetType = _UNSET,
) -> Callable[[], Any]:
    """Return a zero-argument callable for ``dataclasses.field(default_factory=...)``."""
    return lambda: get_config_val(key=key, default=default, type_hint=type_hint)
```

### Step 2: Nested `@dataclass(slots=True)` settings and `.env` loading in `app/lib/settings.py`

Group related configuration into nested `@dataclass(slots=True)` classes (`AppSettings`, `ServerSettings`, `DatabaseSettings`, `RedisSettings`, `LogSettings`) and compose them on a root `Settings` dataclass. Use `@classmethod @lru_cache(maxsize=1, typed=True)` on `Settings.from_env` to load `.env` via `python-dotenv` and set `LITESTAR_*` runtime defaults once per process:

```python
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

from app.utils.env import get_env


@dataclass(slots=True)
class ServerSettings:
    """ASGI server configuration."""

    APP_LOC: str = "app.asgi:create_app"
    HOST: str = field(default_factory=get_env("LITESTAR_HOST", "0.0.0.0"))
    PORT: int = field(default_factory=get_env("LITESTAR_PORT", 8000))
    KEEPALIVE: int = field(default_factory=get_env("LITESTAR_KEEPALIVE", 65))
    RELOAD: bool = field(default_factory=get_env("LITESTAR_RELOAD", False))


@dataclass(slots=True)
class AppSettings:
    """Core application configuration."""

    NAME: str = field(default_factory=get_env("LITESTAR_APP_NAME", "My App"))
    URL: str = field(default_factory=get_env("APP_URL", "http://localhost:8000"))
    DEBUG: bool = field(default_factory=get_env("LITESTAR_DEBUG", False))
    SECRET_KEY: str = field(default_factory=get_env("SECRET_KEY", ""))
    ALLOWED_CORS_ORIGINS: list[str] = field(default_factory=get_env("ALLOWED_CORS_ORIGINS", ["*"]))
    CSRF_COOKIE_NAME: str = field(default_factory=get_env("CSRF_COOKIE_NAME", "XSRF-TOKEN"))


@dataclass(slots=True)
class DatabaseSettings:
    """Database connection pool configuration."""

    URL: str = field(default_factory=get_env("DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/app"))
    ECHO: bool = field(default_factory=get_env("DATABASE_ECHO", False))
    POOL_MIN_SIZE: int = field(default_factory=get_env("DATABASE_POOL_MIN_SIZE", 2))
    POOL_MAX_SIZE: int = field(default_factory=get_env("DATABASE_POOL_MAX_SIZE", 10))
    POOL_OVERFLOW: int = field(default_factory=get_env("DATABASE_MAX_POOL_OVERFLOW", 5))


@dataclass(slots=True)
class RedisSettings:
    """Redis / Valkey configuration."""

    URL: str = field(default_factory=get_env("REDIS_URL", "redis://localhost:6379/0"))
    SOCKET_CONNECT_TIMEOUT: int = field(default_factory=get_env("REDIS_CONNECT_TIMEOUT", 5))


@dataclass(slots=True)
class Settings:
    """Root application settings container."""

    app: AppSettings = field(default_factory=AppSettings)
    server: ServerSettings = field(default_factory=ServerSettings)
    db: DatabaseSettings = field(default_factory=DatabaseSettings)
    redis: RedisSettings = field(default_factory=RedisSettings)

    @classmethod
    @lru_cache(maxsize=1, typed=True)
    def from_env(cls, dotenv_filename: str = ".env") -> Settings:
        """Load ``.env`` file if present and materialize cached ``Settings``."""
        env_file = Path(f"{os.curdir}/{dotenv_filename}")
        if env_file.is_file():
            load_dotenv(env_file, override=True)
        os.environ.setdefault("LITESTAR_WARN_IMPLICIT_SYNC_TO_THREAD", "0")
        os.environ.setdefault("LITESTAR_GRANIAN_IN_SUBPROCESS", "false")
        os.environ.setdefault("LITESTAR_GRANIAN_USE_LITESTAR_LOGGER", "true")
        settings = cls()
        if "LITESTAR_APP" not in os.environ:
            os.environ["LITESTAR_APP"] = settings.server.APP_LOC
        if "LITESTAR_APP_NAME" not in os.environ:
            os.environ["LITESTAR_APP_NAME"] = settings.app.NAME
        return settings


def get_settings() -> Settings:
    """Return the cached ``Settings`` singleton."""
    return Settings.from_env()
```

### Minimal inline alternative (single-file services)

For small services that do not need `app/utils/env.py`, use `@dataclass(frozen=True, slots=True)` with `os.getenv` inside `default_factory` and `@lru_cache(maxsize=1)` on `get_settings()`.

## Pattern B — `pydantic_settings.BaseSettings`

```python
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database configuration parsed from DATABASE_* environment variables."""

    model_config = SettingsConfigDict(env_prefix="DATABASE_", frozen=True)

    url: str = Field(default="postgresql+asyncpg://localhost/app")
    pool_size: int = 10
    echo: bool = False


class RedisSettings(BaseSettings):
    """Redis configuration parsed from REDIS_* environment variables."""

    model_config = SettingsConfigDict(env_prefix="REDIS_", frozen=True)

    url: str = Field(default="redis://localhost:6379/0")


class AppSettings(BaseSettings):
    """Root application settings parsed from APP_* and .env."""

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
        frozen=True,
    )

    name: str = "My App"
    debug: bool = False
    secret_key: str = ""
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return the cached Pydantic settings instance."""
    return AppSettings()
```

`BaseSettings` supports `env_file=".env"` and `env_nested_delimiter="__"` so `APP_DATABASE__URL` populates `settings.database.url` automatically.

## `LITESTAR_APP` and CLI Environment Variables

Litestar's CLI (`litestar run`, `litestar routes`, `litestar database`, `litestar workers`) resolves the application factory from `LITESTAR_APP` when `--app` is not passed on the command line. Setting defaults inside `Settings.from_env()` ensures every CLI entry point and Granian worker inherits consistent runtime variables:

| Environment Variable | Typical Value | Purpose |
| --- | --- | --- |
| `LITESTAR_APP` | `"app.asgi:create_app"` | Module and factory path discovered by `litestar` CLI |
| `LITESTAR_APP_NAME` | `"My App"` | Displayed in CLI banner and OpenAPI metadata |
| `LITESTAR_HOST` / `LITESTAR_PORT` | `"0.0.0.0"` / `"8000"` | Bind address and port for `litestar run` |
| `LITESTAR_RELOAD` | `"false"` (`"true"` in dev) | Enable hot reload during local development |
| `LITESTAR_GRANIAN_IN_SUBPROCESS` | `"false"` | Run Granian in-process when managed by containers/systemd |
| `LITESTAR_GRANIAN_USE_LITESTAR_LOGGER` | `"true"` | Route Granian worker logs through Litestar's structured logger |
| `LITESTAR_WARN_IMPLICIT_SYNC_TO_THREAD` | `"0"` | Suppress sync-to-thread warnings when sync providers are intentional |

## Wiring Settings into `app.state` and Dependency Injection

Store the `Settings` instance on `app.state` at application creation time and register a DI provider so handlers, guards, middleware, and lifespan hooks can access settings cleanly without importing globals or reading `os.environ`.

### 1. Native Litestar `State` + `Provide`

```python
from litestar import Controller, Litestar, Request, get
from litestar.datastructures import State
from litestar.di import NamedDependency, Provide

from app.lib.settings import Settings, get_settings


class SystemController(Controller):
    """System status endpoints."""

    path = "/api/system"

    @get("/info")
    async def app_info(
        self,
        settings: NamedDependency[Settings],
        request: Request,
    ) -> dict[str, str | bool]:
        """Read settings via DI or from request.app.state."""
        state_settings: Settings = request.app.state.settings
        return {
            "name": settings.app.NAME,
            "debug": state_settings.app.DEBUG,
        }


def create_app() -> Litestar:
    """Create the Litestar application with settings wired into state and DI."""
    settings = get_settings()
    return Litestar(
        route_handlers=[SystemController],
        debug=settings.app.DEBUG,
        state=State({"settings": settings}),
        dependencies={
            "settings": Provide(get_settings, sync_to_thread=False),
        },
    )
```

### 2. Dishka `Scope.APP` context wiring

When the project uses Dishka (`dishka.integrations.litestar`), declare `Settings` as an app-scoped context value on your `Provider` via `from_context(provides=Settings, scope=Scope.APP)` and pass `context={Settings: settings}` to `make_async_container(...)`.

## Lazy Materialization in `app/config.py` (PEP 562)

Settings classes define *what* configuration values look like. Module-level PEP 562 (`__getattr__`) in `app/config.py` controls *when* heavyweight infrastructure singletons (database pools, `SQLSpec` instances, Redis clients, `ChannelsPlugin`, SAQ queues) are materialized.

### Why defer infrastructure instantiation?

When `channels = ChannelsPlugin(backend=RedisChannelsPubSubBackend(...))` runs eagerly at module scope in `app/config.py`, importing `app.config` immediately constructs backend objects and reads environment variables. Deferring initialization until first attribute access prevents three common failure modes:

- **Docker image builds** that run `uv sync` or `litestar assets build` before Redis or PostgreSQL containers exist.
- **Pytest suites** that override environment variables with `monkeypatch.setenv(...)` after test collection has already imported application modules.
- **CLI commands** (`litestar database upgrade`, `litestar routes`) that only need a subset of configuration and should not initialize unrelated subsystems.

### Implementation (`app/config.py`)

```python
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from litestar.channels import ChannelsPlugin
    from sqlspec import SQLSpec

_initialized: bool = False

db_manager: SQLSpec
channels: ChannelsPlugin


def _initialize() -> None:
    """Materialize application-level infrastructure singletons on first access."""
    global _initialized, db_manager, channels

    from litestar.channels import ChannelsPlugin
    from litestar.channels.backends.redis import RedisChannelsPubSubBackend
    from redis.asyncio import Redis
    from sqlspec import SQLSpec
    from sqlspec.observability import ObservabilityConfig

    from app.lib.settings import get_settings

    settings = get_settings()

    channels = ChannelsPlugin(
        backend=RedisChannelsPubSubBackend(redis=Redis.from_url(settings.redis.URL)),
        arbitrary_channels_allowed=True,
    )
    observability = ObservabilityConfig(print_sql=settings.db.ECHO)
    db_manager = SQLSpec(observability_config=observability)

    _initialized = True


def _reset() -> None:
    """Clear lazy singletons and settings cache between tests."""
    global _initialized

    from app.lib.settings import Settings

    Settings.from_env.cache_clear()
    g = globals()
    for name in ("db_manager", "channels"):
        g.pop(name, None)
    _initialized = False


def __getattr__(name: str) -> Any:
    """Lazily initialize module attributes on first access (PEP 562)."""
    if not _initialized:
        _initialize()
        if name in globals():
            return globals()[name]
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
```

### Lazy Materialization Guardrails

- **Set `_initialized = True` last in `_initialize()`.** If an earlier statement raises, `_initialized` remains `False` so subsequent access retries cleanly instead of returning partially initialized globals.
- **Clear both `Settings.from_env.cache_clear()` and downstream module caches in `_reset()`.** In pytest fixtures that mutate environment variables, call `config._reset()` before and after yielding.
- **Avoid top-level `from app.config import db_manager` in modules imported before app startup.** Use `from app import config` and access `config.db_manager` inside functions, or import only after `create_app()` has initialized settings.

## Anti-Patterns

- **Reading `os.environ` or `os.getenv` inside route handlers or services.** Always read from `get_settings()` or an injected `Settings` dependency.
- **Using `msgspec.Struct` to parse environment variables.** `msgspec` is purpose-built for wire serialization and DTOs, not `.env` and environment coercion.
- **Mixing `@dataclass` settings and `pydantic_settings.BaseSettings` in the same repository.** Pick one pattern for the entire project.
