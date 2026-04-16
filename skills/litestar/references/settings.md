# Settings (`@dataclass` + `get_env()` + `@lru_cache`)

Canonical Litestar apps use plain `@dataclass(frozen=True)` for settings — not Pydantic Settings, not `msgspec.Struct`. The pattern is environment-driven defaults, immutable values, single-process caching via `@lru_cache`.

## Why `@dataclass` over Pydantic Settings

- **Zero runtime dependency.** `dataclasses` is stdlib; Pydantic Settings adds a heavy import path before app startup.
- **Canonical Litestar apps don't use it.** `litestar-fullstack-spa`, `litestar-fullstack-inertia`, and the `dma/accelerator` reference all use `@dataclass(frozen=True)` with `get_env` helpers.
- **Validation belongs in DTOs**, not in config. Settings represent process-level wiring; DTOs validate per-request data.
- **Immutability via `frozen=True`** prevents accidental mutation in handlers — config is read-only after process start.

## Pattern (`app/lib/settings.py`)

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

## Nested Config

Group related settings into their own `@dataclass` (e.g. `DatabaseSettings`, `RedisSettings`, `AuthSettings`) and compose them on `AppSettings` via `field(default_factory=...)`. This keeps imports tidy:

```python
from app.lib.settings import get_settings

settings = get_settings()
print(settings.database.url)        # nested access
print(settings.redis.url)
```

## `@lru_cache` Guarantee

`@lru_cache(maxsize=1)` ensures `get_settings()` evaluates once per process. Every call site gets the same frozen instance — no env re-reads, no race conditions. For tests that need to override settings, `get_settings.cache_clear()` is the escape hatch.

## Anti-patterns

- Reading `os.environ` inside handlers or services. Always go through `get_settings()`.
- Mutable settings (`@dataclass` without `frozen=True`). Hides bugs.
- Pydantic Settings for new projects. The canonical apps don't use it; pick this pattern instead.
