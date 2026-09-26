# Stores Registry and Response Caching

## Key-Value Stores and `StoreRegistry`

Litestar provides a unified async key-value `Store` interface (`litestar.stores`) used by response caching, server-side sessions, rate-limiting middleware, and application code. Registered stores are automatically managed as part of the `Litestar` lifespan.

| Store Class | Import Path | Best For |
| --- | --- | --- |
| `MemoryStore` | `litestar.stores.memory.MemoryStore` | Single-worker development or ephemeral tests. |
| `FileStore` | `litestar.stores.file.FileStore` | Local single-host persistence across restarts (`create_directories=True`). |
| `RedisStore` | `litestar.stores.redis.RedisStore` | Multi-worker production deployments backed by Redis (`litestar[redis]`). |
| `ValkeyStore` | `litestar.stores.valkey.ValkeyStore` | Multi-worker production deployments backed by Valkey (`litestar[valkey]`). |

### Configuring `StoreRegistry` with Namespaced Redis / Valkey Stores

Use `RedisStore.with_client(...)` or `ValkeyStore.with_client(...)` when Litestar should own the client connection and close it on shutdown (`handle_client_shutdown=True`). Use `default_factory=root_store.with_namespace` on `StoreRegistry` so every named store (`"sessions"`, `"response_cache"`, `"rate_limit"`) automatically gets an isolated key prefix (`LITESTAR_SESSIONS:...`, `LITESTAR_RESPONSE_CACHE:...`):

```python
from pathlib import Path

from litestar import Litestar, Request, get
from litestar.datastructures import State
from litestar.stores.file import FileStore
from litestar.stores.memory import MemoryStore
from litestar.stores.redis import RedisStore
from litestar.stores.registry import StoreRegistry
from litestar.stores.valkey import ValkeyStore


redis_root_store = RedisStore.with_client(
    url="redis://localhost:6379/0",
    namespace="LITESTAR",
)

valkey_root_store = ValkeyStore.with_client(
    url="valkey://localhost:6379/0",
    namespace="LITESTAR",
)

store_registry = StoreRegistry(
    stores={
        "memory": MemoryStore(),
        "local_files": FileStore(path=Path("/tmp/litestar-store"), create_directories=True),
        "valkey": valkey_root_store,
    },
    default_factory=redis_root_store.with_namespace,
)


@get("/cache-probe")
async def cache_probe(
    request: Request[object, object, State],
) -> dict[str, str | None]:
    """Read and write bytes/strings through a named Store from app.stores."""
    custom_store = request.app.stores.get("custom_feature")
    await custom_store.set("probe", "active", expires_in=60)
    raw_value = await custom_store.get("probe", renew_for=30)
    return {"value": raw_value.decode("utf-8") if raw_value else None}


app = Litestar(
    route_handlers=[cache_probe],
    stores=store_registry,
)
```

### `Store` Operations

- `await store.set(key, value, expires_in=60)`: Store `str | bytes` with an optional TTL (`int | timedelta`).
- `await store.get(key, renew_for=30)`: Fetch `bytes | None` and optionally extend TTL on read.
- `await store.delete(key)`: Remove a single key.
- `await store.delete_all()`: Remove all keys in the current namespace (`MemoryStore`, `FileStore`, or namespaced `RedisStore` / `ValkeyStore`).
- `await store.expires_in(key)`: Return remaining TTL in seconds (`int | None`, `-1` when no expiry is set).

When passing a pre-existing `Redis` or `Valkey` client via `RedisStore(redis=client)` directly, `handle_client_shutdown` defaults to `False` so your lifespan hook retains ownership of closing the client.

## HTTP Response Caching (`ResponseCacheConfig`)

`ResponseCacheConfig` (`from litestar.config.response_cache import CACHE_FOREVER, ResponseCacheConfig, default_cache_key_builder`) caches route responses in the store named by `store` (default `"response_cache"`):

```python
from litestar import Litestar, Request, get
from litestar.config.response_cache import (
    CACHE_FOREVER,
    ResponseCacheConfig,
    default_cache_key_builder,
)
from litestar.params import FromPath
from litestar.stores.memory import MemoryStore


def tenant_cache_key_builder(request: Request[object, object, object]) -> str:
    """Include the X-Tenant-ID header in the response cache key."""
    tenant = request.headers.get("x-tenant-id", "public")
    return f"{tenant}:{default_cache_key_builder(request)}"


response_cache_config = ResponseCacheConfig(
    default_expiration=120,
    key_builder=tenant_cache_key_builder,
    store="response_cache",
)


@get("/catalog", cache=True)
async def list_catalog() -> list[str]:
    """Cache response for ResponseCacheConfig.default_expiration (120s)."""
    return ["item-a", "item-b"]


@get("/catalog/{slug:str}", cache=300, cache_key_builder=default_cache_key_builder)
async def get_catalog_item(slug: FromPath[str]) -> dict[str, str]:
    """Cache response for 300 seconds with an explicit per-route key builder."""
    return {"slug": slug}


@get("/static-manifest", cache=CACHE_FOREVER)
async def get_static_manifest() -> dict[str, str]:
    """Cache response indefinitely until the backing store is cleared."""
    return {"version": "1"}


app = Litestar(
    route_handlers=[list_catalog, get_catalog_item, get_static_manifest],
    stores={"response_cache": MemoryStore()},
    response_cache_config=response_cache_config,
)
```

### Response Caching Rules

- Use `MemoryStore` only for single-process deployments or tests; configure `"response_cache"` with `RedisStore` or `ValkeyStore` in multi-worker production.
- By default, `ResponseCacheConfig.cache_response_filter` only caches `2xx` responses.
- Always include tenant, user, or locale headers in `key_builder` when a cached endpoint returns tenant- or user-scoped payloads.
