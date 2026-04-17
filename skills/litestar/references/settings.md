# Settings — Per-Stack Patterns

Litestar apps use one of two settings patterns depending on the project's ecosystem:

- **`@dataclass(frozen=True)` + `get_env()` + `@lru_cache`** — zero extra deps; used by first-party canonical apps (`litestar-fullstack-spa`, `litestar-fullstack-inertia`, and other reference implementations). Pick this for fresh projects.
- **`pydantic_settings.BaseSettings`** — fully supported and recommended when the project already has Pydantic in its dependency graph (e.g., DTOs shared with non-Litestar microservices, or an existing Pydantic-heavy codebase). Pick this to avoid a split validation stack.

Both patterns share the same call-site shape: a cached `get_settings()` function returning an immutable, nested settings object with env-driven defaults.

## When `@dataclass` fits

- Zero runtime dependency — `dataclasses` is stdlib. Leaner startup, leaner wheel.
- Fresh project with no existing Pydantic usage — don't introduce a heavy import path just for config.
- Canonical Litestar reference apps use this pattern — copy-paste familiarity across the ecosystem.
- You prefer validation concentrated in request / response DTOs (msgspec), leaving config as pure process wiring.

## When `pydantic_settings` fits

- Pydantic is already a dep — shared DTOs with non-Litestar services, an older SQLModel layer, or a migration from FastAPI.
- You want `BaseSettings`' built-in env-parsing affordances (dotenv loaders, nested env delimiters, CLI integration, secret stores).
- Your team already reads Pydantic validation errors fluently; adopting a second validation stack adds friction.
- You need field-level validation on config values (e.g., "DATABASE_URL must be `postgresql+asyncpg://`"). `@dataclass` + `get_env` can do this in `__post_init__`, but `BaseSettings` validators are more ergonomic.

Neither path is more "canonical" than the other — they're two valid branches of the same tree.

## Pattern A — `@dataclass(frozen=True)` + `get_env()`

```python
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


def get_env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


@dataclass(frozen=True)
class DatabaseSettings:
    url: str = field(default_factory=lambda: get_env("DATABASE_URL", "postgresql+asyncpg://localhost/app"))
    pool_size: int = field(default_factory=lambda: int(get_env("DATABASE_POOL_SIZE", "10")))
    echo: bool = field(default_factory=lambda: get_env("DATABASE_ECHO", "false").lower() == "true")


@dataclass(frozen=True)
class RedisSettings:
    url: str = field(default_factory=lambda: get_env("REDIS_URL", "redis://localhost:6379/0"))


@dataclass(frozen=True)
class AppSettings:
    name: str = field(default_factory=lambda: get_env("APP_NAME", "My App"))
    debug: bool = field(default_factory=lambda: get_env("APP_DEBUG", "false").lower() == "true")
    secret_key: str = field(default_factory=lambda: get_env("APP_SECRET_KEY", ""))
    database: DatabaseSettings = field(default_factory=DatabaseSettings)
    redis: RedisSettings = field(default_factory=RedisSettings)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings()
```

### Nested config (Pattern A)

Group related settings into their own `@dataclass` (e.g. `DatabaseSettings`, `RedisSettings`, `AuthSettings`) and compose them on `AppSettings` via `field(default_factory=...)`. This keeps imports tidy:

```python
from app.lib.settings import get_settings

settings = get_settings()
print(settings.database.url)        # nested access
print(settings.redis.url)
```

### `@lru_cache` guarantee (Pattern A)

`@lru_cache(maxsize=1)` ensures `get_settings()` evaluates once per process. Every call site gets the same frozen instance — no env re-reads, no race conditions. For tests that need to override settings, `get_settings.cache_clear()` is the escape hatch.

## Pattern B — `pydantic_settings.BaseSettings`

```python
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATABASE_")

    url: str = Field(default="postgresql+asyncpg://localhost/app")
    pool_size: int = 10
    echo: bool = False


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REDIS_")

    url: str = Field(default="redis://localhost:6379/0")


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
    )

    name: str = "My App"
    debug: bool = False
    secret_key: str = ""
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings()
```

Same call-site shape — `settings = get_settings(); settings.database.url`. `BaseSettings` adds `env_file` loading and `env_nested_delimiter` so `APP_DATABASE__URL` populates `settings.database.url` automatically. Mutability is controlled via `model_config = SettingsConfigDict(frozen=True)` if you want `@dataclass`-style immutability.

## Anti-patterns (apply to both branches)

- **Reading `os.environ` inside handlers or services.** Always go through `get_settings()`.
- **Mutable settings object** (`@dataclass` without `frozen=True`, or `BaseSettings` without `frozen=True` in `model_config`). Hides bugs — a handler writing to config "works" locally and breaks under concurrency.
- **Mixing both patterns in one project.** Pick a branch and stay there. Half-migrations produce split validation stacks that future agents have to reconcile.
- **Using `msgspec.Struct` for config.** msgspec is optimized for DTOs; it lacks first-class env-loading affordances. Reserve it for request / response shapes.

## Decision guide

| If your project… | Pick |
|---|---|
| Is a fresh Litestar app with no existing Pydantic dep | Pattern A (`@dataclass`) |
| Already imports Pydantic for DTOs, ORM, or shared schemas | Pattern B (`pydantic_settings`) |
| Needs dotenv file loading, CLI arg parsing, or secret-store integration out-of-the-box | Pattern B |
| Wants the leanest possible startup path and smallest dep graph | Pattern A |
| Is migrating from FastAPI / SQLModel | Pattern B (keeps validation stack consistent) |

## Lazy materialization (PEP 562)

Both patterns above define *what* settings look like. This section covers *when* to materialize the rest of the app — the plugin graph, DB pool, Redis client, Channels backend, and so on — and how to defer that work until first use.

### Why defer?

When you write `channels = ChannelsPlugin(backend=RedisChannelLayer(...))` at module scope in `app/config.py`, importing that module triggers a Redis connection attempt at import time. This breaks several common workflows:

- **Docker layer builds** pull and import `config.py` during the `RUN uv sync` step, before the DB/Redis containers are running. Connection errors fail the build.
- **Test suites** that override env vars with `monkeypatch.setenv` or `os.environ[...]` must set those vars *before* the import, which conflicts with pytest's normal import ordering and import caching.
- **CLI invocations** (`litestar db upgrade`, `litestar db dump-schema`, `litestar collectstatic`) usually do not need a live Channels backend, email client, or full plugin graph — forcing their initialization wastes startup time and produces confusing connection errors in migration scripts.

PEP 562 (`__getattr__` at module level, introduced in Python 3.7) lets a module defer all materialization until the first attribute access, while keeping the familiar `import config; config.db` call-site shape unchanged.

### When to use lazy materialization

- Multi-process apps with heavy startup deps: DB connection pool, Redis client, Channels backend, `ObservabilityConfig` building a list of statement observers.
- Test suites that override env vars at runtime — `_reset()` + `cache_clear()` gives a clean slate between tests without restarting the process.
- Monorepos with multiple CLI entry points sharing one `config.py` — only the subset of names actually accessed get initialized.

### When to skip it

- Small single-file apps where import-time init is acceptable (one handler, no workers, no CLI scripts).
- Apps already using a proper DI container (e.g. Dishka with `Scope.APP` providers) that handles lifecycle independently — the container is the lazy initialization layer.

### Implementation

```python
# app/config.py
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlspec import SQLSpec
    from litestar_channels import ChannelsPlugin

_initialized: bool = False

# Lazy handles — populated by _initialize()
db: "SQLSpec"
channels: "ChannelsPlugin"
cache: object
publisher: object


def _initialize() -> None:
    """Materialize all app-level singletons.

    Called once on first attribute access via __getattr__.
    Importing this module does NOT trigger I/O, pool creation,
    or .env file loading.
    """
    global _initialized, db, channels, cache, publisher

    from app.lib.settings import get_settings
    from sqlspec import SQLSpec
    from sqlspec.observability import ObservabilityConfig
    from litestar_channels import ChannelsPlugin
    from litestar_channels.backends.redis import RedisChannelLayer

    settings = get_settings()

    channels = ChannelsPlugin(backend=RedisChannelLayer(url=settings.redis.url))
    publisher = channels._backend  # noqa: SLF001 — required for observer wiring

    observability = ObservabilityConfig(print_sql=settings.database.echo)
    db = SQLSpec(observability_config=observability)

    cache = ...  # wire your cache/session store here

    _initialized = True  # MUST be last — so a failed init stays retryable


def _reset() -> None:
    """Clear all lazy names and sub-module caches.

    Call from test fixtures that need a clean config state:

        @pytest.fixture(autouse=True)
        def reset_config():
            import app.config as config
            config._reset()
            yield
            config._reset()
    """
    global _initialized

    from app.lib.settings import get_settings
    import app.plugins as plugins  # or equivalent sub-module with its own lazy state

    get_settings.cache_clear()
    plugins._reset()  # chain reset into sub-modules that hold their own lazy names

    names = ["db", "channels", "cache", "publisher"]
    g = globals()
    for name in names:
        g.pop(name, None)

    _initialized = False


def __getattr__(name: str) -> object:
    if not _initialized:
        _initialize()
        try:
            return globals()[name]
        except KeyError:
            pass
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
```

Pattern adapted from `dma/accelerator/src/py/dma/config.py:L1–179` (module docstring + `_initialize` at L74–126 + `__getattr__` at L169–179).

### Gotchas

- **`_initialize()` MUST set `_initialized = True` at the very end**, after all assignments. If an early assignment raises (e.g. Redis is unreachable), `_initialized` stays `False` and the next `__getattr__` call will retry initialization cleanly — rather than silently returning `None` for an unset name.
- **`_reset()` must chain into downstream modules.** If `app/plugins.py` has its own lazy names (e.g. a `SAQPlugin` or `VitePlugin` that caches the config object), calling only `config._reset()` leaves those caches stale. Always call `plugins._reset()` (or an equivalent chain) so every cached reference is dropped.
- **`from config import db` defeats laziness.** A `from` import copies the current module-level value of `db` at import time. If that import happens before `_initialize()` runs, the importing module gets `None` or an `AttributeError`. Downstream modules should use `import app.config as config; config.db` at *call time* (e.g. inside a function body), not at module scope. The exception: handler modules that are loaded after app boot can safely use `from config import db` because `_initialize()` will already have run by the time the module is imported.
