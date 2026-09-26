# Channels Plugin, Server-Sent Events, and Realtime Event Envelopes

## Server-Sent Events (`ServerSentEvent`, `ServerSentEventMessage`, `Stream`)

Use `ServerSentEvent` (`from litestar.response import ServerSentEvent, ServerSentEventMessage, Stream`) for unidirectional HTTP streaming (`text/event-stream`). `ServerSentEvent` subclasses `Stream` and automatically sets `media_type="text/event-stream"`, `Cache-Control: no-cache`, `Connection: keep-alive`, and `X-Accel-Buffering: no`. Both `Stream` and `ServerSentEvent` listen concurrently for `http.disconnect` and cancel the generator when the client disconnects.

Items yielded by the generator (`SSEData`) can be:

- `ServerSentEventMessage(data=..., event=..., id=..., retry=..., comment=..., sep="\r\n")` for per-frame event names, IDs, retry intervals, or keep-alive comments.
- `dict[str, Any]` with keys matching `ServerSentEventMessage` (`data`, `event`, `id`, `retry`, `comment`).
- `str | int | bytes`, which are wrapped using the default `event_type`, `event_id`, and `retry_duration` configured on `ServerSentEvent(...)`.

```python
from collections.abc import AsyncGenerator
from uuid import UUID

import msgspec
from litestar import get
from litestar.channels import ChannelsPlugin
from litestar.response import ServerSentEvent, ServerSentEventMessage, Stream


@get("/api/workspaces/{workspace_id:uuid}/events/sse", sync_to_thread=False)
def sse_workspace_events(
    workspace_id: UUID,
    channels: ChannelsPlugin,
) -> ServerSentEvent:
    """Stream a ChannelsPlugin subscription over Server-Sent Events."""

    async def event_generator() -> AsyncGenerator[ServerSentEventMessage, None]:
        channel_name = f"workspace:{workspace_id}:events"
        async with channels.start_subscription([channel_name], history=10) as subscriber:
            async for payload in subscriber.iter_events():
                yield ServerSentEventMessage(
                    event="workspace.event",
                    data=payload,
                    retry=3000,
                )

    return ServerSentEvent(
        event_generator(),
        event_type="workspace.event",
        retry_duration=3000,
        comment_message="connected",
    )


@get("/api/exports/{export_id:uuid}/download", sync_to_thread=False)
def stream_export_ndjson(export_id: UUID) -> Stream:
    """Stream raw NDJSON chunks over HTTP using Stream."""

    async def chunk_generator() -> AsyncGenerator[bytes, None]:
        for row in range(3):
            yield msgspec.json.encode({"export_id": str(export_id), "row": row}) + b"\n"

    return Stream(chunk_generator(), media_type="application/x-ndjson")
```

---

## Channels Plugin (Real-time Broadcasting)

### Plugin Configuration & Lifecycle

`ChannelsPlugin` (`from litestar.channels import ChannelsBackend, ChannelsPlugin, Subscriber`) is an `InitPlugin` and an `AbstractAsyncContextManager`. When registered in `Litestar(plugins=[channels])`, it registers itself in `app_config.lifespan` and exposes the `channels: ChannelsPlugin` dependency via DI.

Key `ChannelsPlugin` parameters:

- `backend: ChannelsBackend`: Storage/pub-sub broker instance.
- `channels: Iterable[str] | None = None`: Explicit allowlist of exact channel names. You must specify either `channels` or `arbitrary_channels_allowed=True` (otherwise `ImproperlyConfiguredException` is raised).
- `arbitrary_channels_allowed: bool = False`: Allow dynamic channel creation at runtime (e.g., `f"workspace:{workspace_id}"`).
- `create_ws_route_handlers: bool = False`: Auto-register WebSocket route handlers at `ws_handler_base_path` (`"{base_path}/{channel_name:str}"` when `arbitrary_channels_allowed=True`, or one route per declared channel in `channels`).
- `ws_handler_send_history: int = 0`: Number of history entries replayed by auto-generated WS route handlers on connect (`0` disables history; negative values fetch unbounded history).
- `ws_handler_base_path: str = "/"`: Base path prefix for generated WS handlers.
- `ws_send_mode: WebSocketMode = "text"`: `"text"` or `"binary"` mode used by generated handlers.
- `subscriber_max_backlog: int | None = None`: Bounded in-memory queue size per `Subscriber`.
- `subscriber_backlog_strategy: BacklogStrategy = "backoff"`: `"backoff"` drops new incoming events when `subscriber_max_backlog` is full; `"dropleft"` evicts the oldest queued events in favor of new ones.
- `subscriber_class: type[Subscriber] = Subscriber`: Custom `Subscriber` subclass.
- `type_encoders: TypeEncodersMap | None = None`: Custom type encoders passed to `msgspec.json.Encoder` when encoding non-`bytes`/`str` payloads.

Publishing and subscribing methods on `ChannelsPlugin`:

- `channels.publish(data, channels)`: Synchronous non-blocking enqueue into the internal publish worker queue (`_pub_queue`). Raises `RuntimeError` if called before startup.
- `await channels.wait_published(data, channels)`: Asynchronous publish that encodes `data` and directly awaits `backend.publish(data, channels)`.
- `async with channels.start_subscription(channels, history=None) as subscriber:`: Subscribes for the duration of the context block and automatically calls `await channels.unsubscribe(subscriber, channels)` on exit.
- `subscriber.iter_events() -> AsyncGenerator[bytes, None]`: Yields encoded `bytes` payloads from subscribed channels.
- `async with subscriber.run_in_background(on_event, join=True):`: Runs a background task invoking `await on_event(event_bytes)` (such as `socket.send_text` or `socket.send_bytes`) while the foreground coroutine awaits `socket.receive()` for disconnect.

```python
from dataclasses import dataclass
from litestar.channels import ChannelsPlugin
from litestar.channels.backends.memory import MemoryChannelsBackend


@dataclass
class ChannelSettings:
    """Configuration for Litestar Channels."""

    BACKEND_URL: str = "memory"
    HISTORY_LIMIT: int = 60

    def get_config(self) -> ChannelsPlugin:
        return ChannelsPlugin(
            backend=MemoryChannelsBackend(history=self.HISTORY_LIMIT),
            arbitrary_channels_allowed=True,
        )
```

### Backend options — pick the branch for your stack

Pick a Channels backend based on what is already in the project's dependency graph and whether history replay is required:

| Backend | History Support | Pick when | Avoid when |
| --- | --- | --- | --- |
| `MemoryChannelsBackend` | Yes (`history=N` in-memory deque) | Dev, tests, single-process apps | Multi-process deploys (workers do not share state) |
| `RedisChannelsPubSubBackend` | No (`get_history` raises `NotImplementedError`) | Redis is already in stack and low-overhead fire-and-forget fan-out is sufficient | History replay is needed (`ws_handler_send_history > 0` or `history=N`), or stack is PG-only |
| `RedisChannelsStreamBackend` | Yes (Redis Streams `XADD`/`XREAD` with `history` `MAXLEN` and `stream_ttl`) | Redis is in stack and bounded history replay across processes is required | Ephemeral pub/sub without stream storage is preferred |
| `AsyncPgChannelsBackend` | No (`get_history` raises `NotImplementedError`) | App already uses `asyncpg` and only needs ephemeral PostgreSQL `LISTEN`/`NOTIFY` | History replay or durable queue semantics are required |
| `PsycoPgChannelsBackend` | No (`get_history` raises `NotImplementedError`) | App already uses `psycopg` v3 (`AsyncConnection`) and needs ephemeral PG `LISTEN`/`NOTIFY` | History replay or durable queue semantics are required |
| `SQLSpecChannelsBackend` | Safe no-op (`get_history` returns `[]`) | Project uses SQLSpec's `events` extension (`listen_notify`, `table_queue`, etc.) | The app does not use SQLSpec's events extension |

**Anti-patterns:**

- Calling `start_subscription(..., history=10)` or setting `ws_handler_send_history=10` with `RedisChannelsPubSubBackend`, `AsyncPgChannelsBackend`, or `PsycoPgChannelsBackend` — their `get_history()` methods raise `NotImplementedError`. Use `RedisChannelsStreamBackend` or `MemoryChannelsBackend` when history replay is required.
- Passing glob patterns like `"workspace:*"` in `ChannelsPlugin(channels=[...])` expecting wildcard matching — `ChannelsPlugin` matches channel names by exact string equality and requires `arbitrary_channels_allowed=True` for dynamic channel names.
- Wiring a PG-LISTEN backend when Redis is already handling SAQ queues and session cache, or forcing Redis into a single-Postgres deployment.

### Branch A — `MemoryChannelsBackend` (dev / single-process)

```python
from litestar.channels import ChannelsPlugin
from litestar.channels.backends.memory import MemoryChannelsBackend

channels = ChannelsPlugin(
    backend=MemoryChannelsBackend(history=60),
    arbitrary_channels_allowed=True,
)
```

### Branch B1 — `RedisChannelsPubSubBackend` (Redis Pub/Sub, no history)

```python
from litestar import Litestar
from litestar.channels import ChannelsPlugin
from litestar.channels.backends.redis import RedisChannelsPubSubBackend
from redis.asyncio import Redis

channels = ChannelsPlugin(
    backend=RedisChannelsPubSubBackend(
        redis=Redis.from_url("redis://localhost:6379/0"),
        key_prefix="LITESTAR_CHANNELS",
        stream_sleep_no_subscriptions=1,
    ),
    channels=["notifications", "system"],
    arbitrary_channels_allowed=True,
    create_ws_route_handlers=True,
    ws_handler_base_path="/ws",
    subscriber_max_backlog=1000,
    subscriber_backlog_strategy="backoff",
)

app = Litestar(plugins=[channels])
```

When both `create_ws_route_handlers=True` and `arbitrary_channels_allowed=True` are set, `ChannelsPlugin` registers a WebSocket handler at `/ws/{channel_name:str}`.

### Branch B2 — `RedisChannelsStreamBackend` (Redis Streams with history replay)

Use `RedisChannelsStreamBackend` when cross-process subscribers need `history` replay (`XREAD` / `XREVRANGE` with `MAXLEN` capping and `PEXPIRE` TTL per publish).

```python
from datetime import timedelta

from litestar.channels import ChannelsPlugin
from litestar.channels.backends.redis import RedisChannelsStreamBackend
from redis.asyncio import Redis

channels = ChannelsPlugin(
    backend=RedisChannelsStreamBackend(
        history=100,
        redis=Redis.from_url("redis://localhost:6379/0"),
        cap_streams_approximate=True,
        stream_ttl=timedelta(seconds=60),
        key_prefix="LITESTAR_CHANNELS",
    ),
    arbitrary_channels_allowed=True,
    create_ws_route_handlers=True,
    ws_handler_send_history=20,
    ws_handler_base_path="/ws",
    subscriber_max_backlog=500,
    subscriber_backlog_strategy="dropleft",
)
```

Note: `RedisChannelsStreamBackend.flush_all()` deletes all stream keys matching `f"{key_prefix}*"` via a Lua script, which is incompatible with Redis Cluster.

### Branch C — Litestar PostgreSQL `LISTEN` / `NOTIFY` (`AsyncPgChannelsBackend` / `PsycoPgChannelsBackend`)

Use when the app already depends on `asyncpg` or `psycopg` v3 and only needs ephemeral cross-process fan-out (`get_history` is not supported). `AsyncPgChannelsBackend` accepts either `dsn: str` or a keyword-only `make_connection: Callable[[], Awaitable[asyncpg.Connection]]` factory. Note the capital `P` in `PsycoPgChannelsBackend` (imported from `litestar.channels.backends.psycopg`, sometimes informally referred to as `PsycopgChannelsBackend`).

```python
from litestar.channels import ChannelsPlugin
from litestar.channels.backends.asyncpg import AsyncPgChannelsBackend
from litestar.channels.backends.psycopg import PsycoPgChannelsBackend

asyncpg_channels = ChannelsPlugin(
    backend=AsyncPgChannelsBackend(dsn=settings.database_url),
    arbitrary_channels_allowed=True,
    create_ws_route_handlers=True,
)

psycopg_channels = ChannelsPlugin(
    backend=PsycoPgChannelsBackend(pg_dsn=settings.database_url),
    arbitrary_channels_allowed=True,
    create_ws_route_handlers=True,
)
```

### Branch D — `SQLSpecChannelsBackend` (SQLSpec events extension)

Use when the project already uses SQLSpec's events extension (`listen_notify`, durable `table_queue`, etc.). Configure event behavior in `extension_config["events"]` and pass `spec.event_channel(config)` to `SQLSpecChannelsBackend`. See [`../../sqlspec/SKILL.md`](../../sqlspec/SKILL.md) for SQLSpec config patterns.

```python
from litestar.channels import ChannelsPlugin
from sqlspec import SQLSpec
from sqlspec.adapters.asyncpg import AsyncpgConfig
from sqlspec.extensions.litestar.channels import SQLSpecChannelsBackend

spec = SQLSpec()
config = spec.add_config(
    AsyncpgConfig(
        connection_config={"dsn": settings.database_url},
        extension_config={"events": {"backend": "listen_notify"}},
    )
)

backend = SQLSpecChannelsBackend(
    spec.event_channel(config),
    channel_prefix="litestar",
    poll_interval=0.2,
    output_queue_capacity=1000,
)

channels = ChannelsPlugin(
    backend=backend,
    arbitrary_channels_allowed=True,
    create_ws_route_handlers=True,
)
```

`SQLSpecChannelsBackend` capabilities and helpers:

- `channel_prefix`: Must be a valid identifier (`^[A-Za-z_][A-Za-z0-9_]*$`); hashes arbitrary Litestar channel names into safe DB channel identifiers (`{channel_prefix}_{sha256[:24]}`).
- `poll_interval`: Poll interval in seconds (`> 0`, default `0.2`) when the underlying SQLSpec event backend polls a table queue.
- `output_queue_capacity`: Optional bounded local queue capacity; overflow increments `backend.dropped_message_count`.
- `await backend.publish_many(data: Sequence[bytes], channels: Iterable[str])`: Publishes multiple payloads in a single `event_channel.publish_many(...)` batch.
- Payload budget helpers for PostgreSQL `NOTIFY` (`8000`-byte limit): `backend.notify_budget` (`MAX_NOTIFY_BYTES` when `backend_name == "notify"`, else `None`), `backend.measure(data: bytes) -> int` (measures the base64-wrapped envelope size), and `backend.fits(data: bytes) -> bool`.
- Observability: `backend.output_queue_depth`, `backend.dropped_message_count`, and `backend.metrics_snapshot() -> dict[str, float]`.
- `await backend.get_history(channel, limit)` safely returns `[]` rather than raising `NotImplementedError`.

### Channel Naming Patterns

Use static factory methods for consistent, scoped channel names:

```python
from uuid import UUID


class Channels:
    """Channel name factories for pub/sub topics."""

    @staticmethod
    def workspace(workspace_id: UUID, topic: str = "events") -> str:
        return f"workspace:{workspace_id}:{topic}"

    @staticmethod
    def user(user_id: UUID, topic: str = "events") -> str:
        return f"user:{user_id}:{topic}"

    @staticmethod
    def global_channel(topic: str = "events") -> str:
        return f"global:{topic}"
```

Domain-specific channel factories for targeted streams:

```python
class WorkspaceChannels:
    """Channel factories for workspace-specific pub/sub topics."""

    @staticmethod
    def etl(workspace_id: UUID) -> str:
        return f"workspace:{workspace_id}:etl"

    @staticmethod
    def files(workspace_id: UUID) -> str:
        return f"workspace:{workspace_id}:files"

    @staticmethod
    def job_logs(workspace_id: UUID) -> str:
        return f"workspace:{workspace_id}:job_logs"
```

Channel name convention: `{scope}:{id}:{topic}`

- `workspace:{uuid}:events` - General workspace events
- `workspace:{uuid}:etl` - ETL processing logs
- `workspace:{uuid}:files` - File upload/processing events
- `user:{uuid}:events` - User-scoped notifications
- `global:events` - System-wide broadcasts

### Publishing to Channels from Route Handlers and Services

Subscription-side code uses the `RealtimePublisher` class to publish typed `RealtimeEvent`
objects to named channels. The publisher wraps the `ChannelsBackend`, provides scope-specific
helpers (`publish_workspace_event`, `publish_user_event`, `publish_global_event`), and handles
the case where the backend is not yet initialized gracefully (no-op + debug log).

> See the `Realtime Events Contract` section below for the full `RealtimePublisher` abstraction,
> scope-specific publish helpers, channel factory classes, and neutral-domain publishing examples, and [websockets.md](websockets.md) for WebSocket subscription streaming (`stream_pubsub`).

---

## Cross-Process Publishing

The Channels plugin gives you `await channels.wait_published(data, channels)` — usable from SAQ workers, background tasks, shell scripts, or any module that can import your app's channels instance. The same backend is shared across the Litestar app, workers, and out-of-process scripts. Any of them can publish; only subscribed WS clients receive.

### From a SAQ Worker

In `app/domain/workspaces/jobs.py`, import the shared `ChannelsPlugin` instance from your server plugins module and call `await channels.wait_published(...)`:

```python
from __future__ import annotations

from saq.types import Context

from app.server.plugins import channels


async def import_finished_job(ctx: Context, *, workspace_id: str, job_id: str) -> None:
    """Broadcast import completion to all WS clients subscribed to this workspace."""
    await channels.wait_published(
        {"type": "import.finished", "jobId": job_id},
        f"workspace:{workspace_id}",
    )
```

### From a CLI / One-off Script

In standalone scripts (such as `tools/broadcast.py`), enter `async with channels:` to open and close the backend lifespan around `wait_published`:

```python
from __future__ import annotations

import asyncio

from litestar.channels import ChannelsPlugin
from litestar.channels.backends.redis import RedisChannelsPubSubBackend
from redis.asyncio import Redis


async def main() -> None:
    """Open the Redis pub/sub backend lifespan and publish a one-off event."""
    backend = RedisChannelsPubSubBackend(redis=Redis.from_url("redis://localhost:6379/0"))
    channels = ChannelsPlugin(backend=backend, channels=[], arbitrary_channels_allowed=True)
    async with channels:
        await channels.wait_published({"type": "deploy.finished"}, "notifications")


asyncio.run(main())
```

### From Database Observers

SQL statement observers can intercept writes and broadcast events directly to channels, providing low-latency real-time updates without modifying service code:

```python
class SqlExecutionLogObserver:
    """Intercept ETL log inserts and broadcast to workspace channels."""

    def __init__(self, backend: ChannelsBackend) -> None:
        self.backend = backend

    def __call__(self, event: StatementEvent) -> None:
        if "processing_log" not in event.sql:
            return
        loop = asyncio.get_running_loop()
        loop.create_task(self._process_and_publish(event))

    async def _process_and_publish(self, event: StatementEvent) -> None:
        payload, workspace_id = await self._normalize_payload(event.parameters)
        if not payload or workspace_id is None:
            return
        channel = f"workspace:{workspace_id}:etl"
        await self.backend.publish(
            to_json(payload, as_bytes=True),
            channels=[channel],
        )
```

---

---

## Realtime Events Contract (`RealtimeEvent` & `RealtimePublisher`)

This file documents the realtime event contract, scope ACL, channel factories, and the
`RealtimePublisher` abstraction. For WebSocket guard composition see [auth-and-guards.md](auth-and-guards.md); for
the Channels backend configuration and the `stream_pubsub` subscriber helper see
[websockets.md](websockets.md). Together, the three files cover the full realtime stack used by
Litestar applications with multi-scope pub/sub.

## Event envelope (`RealtimeEvent`)

`RealtimeEvent` is the canonical typed envelope for every realtime message. All scope variants
(workspace, user, global) share the same struct — the `scope` field drives routing, and
`__post_init__` enforces that the matching ID field is present.

```python
import msgspec
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

RealtimeScope = Literal["workspace", "user", "global"]
RealtimeEventType = str

REALTIME_SCHEMA_VERSION = "1.0"


class RealtimeEvent(CamelizedBaseStruct, kw_only=True):
    """Canonical realtime event envelope."""

    schema_version: str = REALTIME_SCHEMA_VERSION
    event_type: RealtimeEventType | str
    scope: RealtimeScope
    published_at: datetime = msgspec.field(default_factory=lambda: datetime.now(UTC))
    workspace_id: UUID | None = None
    user_id: UUID | None = None
    actor: RealtimeActor | None = None
    entity: RealtimeEntityRef | None = None
    payload: dict[str, Any] = msgspec.field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.scope == "workspace" and self.workspace_id is None:
            msg = "workspace_id is required for workspace scope events"
            raise ValueError(msg)
        if self.scope == "user" and self.user_id is None:
            msg = "user_id is required for user scope events"
            raise ValueError(msg)
```

`CamelizedBaseStruct` sets `rename="camel"` so the wire format ships camelCase JSON while Python
stays snake_case. `RealtimeEventType` defaults to `str` so domain modules can narrow it with
`Literal` unions. Do NOT add `from __future__ import annotations` in modules that define
`msgspec.Struct` subclasses — it breaks runtime field resolution.

## Scope ACL table

`REALTIME_SCOPE_ACL` maps each scope to the access-control policy enforced by the corresponding
WS guard. Adapted from `_contract.py:L20–24`.

| Scope | Access policy | Guard |
| --- | --- | --- |
| `workspace` | Workspace member or superuser | `requires_websocket_workspace_member` |
| `user` | Authenticated subject only | `requires_websocket_user_subject` |
| `global` | Role/policy-authorized users only | `requires_websocket_global_access` |

```python
REALTIME_SCOPE_ACL: dict[RealtimeScope, str] = {
    "workspace": "workspace-member-or-superuser",
    "user": "authenticated-subject-only",
    "global": "role-policy-authorized",
}
```

## Actor and entity refs

Supporting structs for tracing who triggered the event and which domain object it concerns.
Adapted from `_contract.py:L46–57`.

```python
from typing import Literal
from uuid import UUID

import msgspec


class RealtimeActor(CamelizedBaseStruct, kw_only=True):
    """Who or what triggered the event."""

    user_id: UUID | None = None
    source: Literal["user", "system"] = "system"


class RealtimeEntityRef(CamelizedBaseStruct, kw_only=True):
    """Reference to the domain object the event concerns (type name and stringified primary key)."""

    type: str
    id: str
```

## Channel naming factories

Use static factory methods for consistent, namespaced channel names. `RealtimeChannels` provides
the canonical three-scope pattern; domain modules extend it with topic-specific factories.

Adapted from `_contract.py:L27–43` (canonical factories) and
`domain/workspaces/channels.py:L6–25` (domain-specific extension pattern — the neutral
equivalent below uses `OrderChannels`).

```python
from uuid import UUID


class RealtimeChannels:
    """Canonical channel name factories for the three realtime scopes."""

    @staticmethod
    def workspace(workspace_id: UUID, topic: str = "events") -> str:
        return f"workspace:{workspace_id}:{topic}"

    @staticmethod
    def user(user_id: UUID, topic: str = "events") -> str:
        return f"user:{user_id}:{topic}"

    @staticmethod
    def global_channel(topic: str = "events") -> str:
        return f"global:{topic}"
```

Domain-specific factories narrow the topic:

```python
class OrderChannels:
    """Channel factories for order-domain pub/sub topics."""

    @staticmethod
    def status(order_id: UUID) -> str:
        return f"orders:{order_id}:status"

    @staticmethod
    def shipments(order_id: UUID) -> str:
        return f"orders:{order_id}:shipments"

    @staticmethod
    def audit(order_id: UUID) -> str:
        return f"orders:{order_id}:audit"
```

Channel name convention: `{scope}:{id}:{topic}` — matches `RealtimeChannels` workspace/user
scopes and the domain factory pattern above.

## RealtimePublisher

`RealtimePublisher` wraps the `ChannelsBackend` with scope-specific publish helpers and a graceful
no-op for the case where the backend is not yet initialized (e.g., a background worker that
publishes during startup before the Litestar lifespan has run).

The `to_json(event, as_bytes=True)` call uses the project's serialization wrapper — see
[`../../msgspec/references/litestar-patterns.md`](../../msgspec/references/litestar-patterns.md)
for the import choice (`sqlspec.utils.serializers.to_json` vs a hand-rolled `msgspec.json.Encoder`).

```python
from litestar.channels import ChannelsBackend

from app.lib.serialization import to_json


class RealtimePublisher:
    """Publish typed events through the channels backend."""

    def __init__(self, backend: ChannelsBackend) -> None:
        self.backend = backend

    async def publish_event(
        self,
        event: RealtimeEvent,
        channel: str | None = None,
    ) -> None:
        resolved = channel or self._resolve_channel(event)
        try:
            await self.backend.publish(
                data=to_json(event, as_bytes=True),
                channels=[resolved],
            )
        except RuntimeError as exc:
            if self._is_backend_not_initialized_error(exc):
                logger.debug("Channels backend not ready — skipping publish", event_type=event.event_type)
                return
            raise

    async def publish_workspace_event(
        self,
        workspace_id: UUID,
        event_type: str,
        payload: dict[str, Any],
        *,
        topic: str = "events",
        actor: RealtimeActor | None = None,
        entity: RealtimeEntityRef | None = None,
        user_id: UUID | None = None,
    ) -> RealtimeEvent:
        event = RealtimeEvent(
            event_type=event_type,
            scope="workspace",
            workspace_id=workspace_id,
            user_id=user_id,
            actor=actor,
            entity=entity,
            payload=payload,
        )
        await self.publish_event(event, channel=RealtimeChannels.workspace(workspace_id, topic))
        return event

    async def publish_user_event(
        self,
        user_id: UUID,
        event_type: str,
        payload: dict[str, Any],
        *,
        topic: str = "events",
        actor: RealtimeActor | None = None,
        entity: RealtimeEntityRef | None = None,
    ) -> RealtimeEvent:
        event = RealtimeEvent(
            event_type=event_type,
            scope="user",
            user_id=user_id,
            actor=actor,
            entity=entity,
            payload=payload,
        )
        await self.publish_event(event, channel=RealtimeChannels.user(user_id, topic))
        return event

    async def publish_global_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        topic: str = "events",
        actor: RealtimeActor | None = None,
        entity: RealtimeEntityRef | None = None,
    ) -> RealtimeEvent:
        event = RealtimeEvent(
            event_type=event_type,
            scope="global",
            actor=actor,
            entity=entity,
            payload=payload,
        )
        await self.publish_event(event, channel=RealtimeChannels.global_channel(topic))
        return event

    @staticmethod
    def _resolve_channel(event: RealtimeEvent) -> str:
        if event.scope == "workspace" and event.workspace_id is not None:
            return RealtimeChannels.workspace(event.workspace_id)
        if event.scope == "user" and event.user_id is not None:
            return RealtimeChannels.user(event.user_id)
        return RealtimeChannels.global_channel()

    @staticmethod
    def _is_backend_not_initialized_error(exc: RuntimeError) -> bool:
        msg = str(exc).lower()
        return "backend not yet initialized" in msg or "plugin not yet initialized" in msg or "not started" in msg
```

## Publishing from domain services (examples)

Call `publish_workspace_event` from any service that has a `RealtimePublisher` injected. The
publisher is lightweight — inject it via `Provide()` or Dishka and call it after the DB write.

Order status change (workspace-scoped):

```python
class OrderService:
    def __init__(self, publisher: RealtimePublisher) -> None:
        self.publisher = publisher

    async def place_order(self, order: Order) -> Order:
        saved = await self.repo.create(order)
        await self.publisher.publish_workspace_event(
            workspace_id=saved.workspace_id,
            event_type="order.placed",
            payload={"order_id": str(saved.id), "total": saved.total},
            entity=RealtimeEntityRef(type="order", id=str(saved.id)),
        )
        return saved
```

Per-user notification (user-scoped):

```python
async def send_notification(
    self,
    user_id: UUID,
    message: str,
) -> None:
    await self.publisher.publish_user_event(
        user_id=user_id,
        event_type="user.notification.created",
        payload={"message": message},
    )
```

Global broadcast (system-scoped — use `publish_global_event` for events not tied to a specific
workspace or user, such as maintenance announcements or feature flag changes):

```python
await self.publisher.publish_global_event(
    event_type="system.maintenance.scheduled",
    payload={"window_start": "2026-05-01T02:00:00Z", "duration_minutes": 30},
)
```

## Cross-references

- WebSocket guard chain: [auth-and-guards.md](auth-and-guards.md)
- Channels backend config + `stream_pubsub` subscriber: [websockets.md](websockets.md)
- `to_json` serializer import choice (sqlspec vs hand-rolled): [`../../msgspec/references/litestar-patterns.md`](../../msgspec/references/litestar-patterns.md)
- SQL-observer publishing pattern: [`../../sqlspec/references/observability.md`](../../sqlspec/references/observability.md) — StatementObserver → Channels bridge for broadcasting DB writes to WebSocket clients.

## Shared Styleguide Baseline

Generic language and framework conventions:

- [`../../litestar-styleguide/references/python.md`](../../litestar-styleguide/references/python.md)
