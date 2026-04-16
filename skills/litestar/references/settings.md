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
