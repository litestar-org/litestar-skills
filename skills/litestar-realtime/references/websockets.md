# WebSockets & Real-time Broadcasting

WebSocket handlers, the Litestar Channels plugin, multi-tenant authorization, cross-process publishing from SAQ workers and CLI scripts, and a decision matrix for when to use plain WS + Redis pub/sub vs the Channels plugin.

## WebSocket Handlers

### The `@websocket()` Decorator

```python
from __future__ import annotations

from uuid import UUID

from litestar import Controller, WebSocket, websocket


class StreamController(Controller):
    path = "/api/workspaces"
    tags = ["Workspaces"]
    guards = [requires_websocket_auth, requires_websocket_membership]

    @websocket(
        path="/{workspace_id:uuid}/events/stream",
        name="workspaces:events-stream",
        summary="Stream Workspace Events",
        opt={"exclude_from_csrf": True, "exclude_from_auth": True},
    )
    async def stream_events(self, socket: WebSocket, workspace_id: UUID) -> None:
        await socket.accept()
        await stream_pubsub(socket, [Channels.events(workspace_id)], history=10)
```

Key points:

- WebSocket handlers use `opt={"exclude_from_csrf": True, "exclude_from_auth": True}` to bypass HTTP-oriented middleware. Authentication is handled by WebSocket-specific guards instead.
- Path parameters (e.g., `workspace_id: UUID`) work the same as HTTP route handlers.
- The handler receives a `WebSocket` object (not `Request`).

### WebSocket Lifecycle

```python
from litestar import WebSocket
from litestar.exceptions import WebSocketDisconnect


async def handle_websocket(socket: WebSocket) -> None:
    # 1. Accept the connection
    await socket.accept()

    try:
        # 2. Send/receive loop
        while True:
            data = await socket.receive_json()       # receive from client
            await socket.send_json({"status": "ok"}) # send to client
    except WebSocketDisconnect:
        # 3. Client closed connection - normal, no logging needed
        pass
    finally:
        # 4. Cleanup happens automatically when handler returns
        pass
```

### Dishka DI in WS handlers

WebSocket connections live at SESSION scope in Dishka — the container is created once per
connection and stored at `connection.state.dishka_container`. REQUEST-scoped services (e.g., a
database session or unit-of-work) need a child container created per operation. Use a context
manager to open a transient REQUEST-scope child for each receive/send cycle.

The helper below is shown as `enter_request_scope` — open a per-operation REQUEST-scoped child
container, then close it when the operation completes.

```python
from contextlib import asynccontextmanager
from typing import AsyncIterator

from dishka import AsyncContainer
from litestar import WebSocket


@asynccontextmanager
async def enter_request_scope(socket: WebSocket) -> AsyncIterator[AsyncContainer]:
    """Open a REQUEST-scoped child container for one WS operation."""
    session_container: AsyncContainer = socket.state.dishka_container
    async with session_container() as request_container:
        yield request_container


@websocket("/ws/workspace/{workspace_id:uuid}/stream")
async def workspace_stream(socket: WebSocket, workspace_id: UUID) -> None:
    await socket.accept()
    async for message in receive_messages(socket):
        async with enter_request_scope(socket) as container:
            svc = await container.get(OrderService)
            await svc.process(message, workspace_id)
```

**Branch note — `Provide`-only stacks:** Litestar's built-in DI attaches services via `Provide`
in the handler signature. The REQUEST-scope child container pattern is Dishka-specific — on
`Provide`-only stacks, inject services directly at the handler signature as usual:

```python
@websocket("/ws/workspace/{workspace_id:uuid}/stream")
async def workspace_stream(
    socket: WebSocket,
    workspace_id: UUID,
    order_service: OrderService,  # injected via Provide() in app dependencies
) -> None:
    await socket.accept()
    ...
```

### Authentication in WebSocket Connections

WebSocket connections cannot use HTTP `Authorization` headers during the initial handshake. Authenticate via a `token` query parameter instead.

```python
from litestar.connection import ASGIConnection
from litestar.exceptions import NotAuthorizedException, WebSocketException
from litestar.handlers import BaseRouteHandler
from litestar.security.jwt import Token


async def requires_websocket_auth(
    connection: ASGIConnection, _: BaseRouteHandler,
) -> None:
    """Authenticate WebSocket via query param token."""
    token_str = connection.query_params.get("token")
    if not token_str:
        raise WebSocketException(code=4001, detail="Missing token")

    try:
        token = Token.decode(
            encoded_token=token_str,
            secret=settings.app.SECRET_KEY,
            algorithm="HS256",
        )
        user_id = UUID(token.sub)
    except (NotAuthorizedException, ValueError, KeyError) as e:
        raise WebSocketException(code=4001, detail="Invalid token") from e

    # Load user and attach to connection state
    user = await user_service.get_user(user_id)
    if user is None or not user.is_active:
        raise WebSocketException(code=4001, detail="Unauthorized")
    connection.state.user = user
```

WebSocket error codes:

- `4001` - Authentication failure (missing/invalid token, inactive user)
- `4003` - Authorization failure (not a member, wrong subject, insufficient role)

### Multi-tenant Authorization Guards

Layer guards to enforce tenant isolation. Each guard checks a different level of access.

```python
async def requires_websocket_membership(
    connection: ASGIConnection, _: BaseRouteHandler,
) -> None:
    """Verify user is a member of the workspace in the path."""
    user = getattr(connection.state, "user", None)
    if user is None:
        raise WebSocketException(code=4001, detail="Unauthorized")

    # Superusers bypass membership checks
    if has_full_access_role(user):
        return

    workspace_id = connection.path_params.get("workspace_id")
    if workspace_id is None:
        raise WebSocketException(code=4003, detail="Missing workspace_id")

    is_member = await workspace_member_service.is_member(workspace_id, user.id)
    if not is_member:
        raise WebSocketException(code=4003, detail="Forbidden")


async def requires_websocket_subject(
    connection: ASGIConnection, _: BaseRouteHandler,
) -> None:
    """Restrict user stream subscriptions to the authenticated subject."""
    user = getattr(connection.state, "user", None)
    if user is None:
        raise WebSocketException(code=4001, detail="Unauthorized")

    user_id = connection.path_params.get("user_id")
    if str(user.id) != str(user_id):
        raise WebSocketException(code=4003, detail="Forbidden")
```

Apply guards at controller level for shared auth, and per-handler for route-specific checks:

```python
class WorkspaceStreamController(Controller):
    guards = [requires_websocket_auth, requires_websocket_membership]  # shared
    # ...

class RealtimeStreamController(Controller):
    guards = [requires_websocket_auth]  # shared base auth

    @websocket(
        path="/users/{user_id:uuid}/stream",
        guards=[requires_websocket_subject],  # per-handler
    )
    async def stream_user_events(self, socket: WebSocket, user_id: UUID) -> None:
        ...

    @websocket(
        path="/global/stream",
        guards=[requires_websocket_global_access],  # per-handler
    )
    async def stream_global_events(self, socket: WebSocket) -> None:
        ...
```

---

## Channels Plugin (Real-time Broadcasting)

### Plugin Configuration

```python
from dataclasses import dataclass, field
from litestar.channels import ChannelsPlugin
from litestar.channels.backends.memory import MemoryChannelsBackend


@dataclass
class ChannelSettings:
    """Configuration for Litestar Channels."""

    BACKEND_URL: str = "memory"
    HISTORY_TTL: int = 60

    def get_config(self) -> ChannelsPlugin:
        return ChannelsPlugin(
            backend=MemoryChannelsBackend(history=self.HISTORY_TTL),
            arbitrary_channels_allowed=True,
        )
```

Register the plugin in your application plugins list. The `ChannelsPlugin` instance is used directly as a Litestar plugin.

### Backend options — pick the branch for your stack

There are four supported Channels backends. Pick based on what's already in the project's dependency graph — do not introduce Redis just for Channels if the stack is PostgreSQL-only, and do not use a PG-LISTEN backend if Redis is already present for cache / SAQ / sessions.

| Backend | Pick when | Avoid when |
| --- | --- | --- |
| `MemoryChannelsBackend` | Dev / tests / single-process CLIs; no persistence needed | Multi-process deploys (workers do not share state) |
| `RedisChannelsPubSubBackend` | Redis is already in the stack (SAQ+Redis, cache, sessions) | The project is PostgreSQL-only and Redis would be purely for Channels |
| `sqlspec` PG `LISTEN` / `NOTIFY` backend | Project is `sqlspec` + PostgreSQL; SAQ runs on PG; no Redis | Project uses `advanced-alchemy` (prefer its session-aware backend) or Redis is already present |
| `advanced-alchemy` session-aware backend | Project is `advanced-alchemy` + PostgreSQL; reuse the same engine / session factory | Project is `sqlspec` or has an independent Redis broker |

**Anti-patterns:**

- Dropping in the `SQLAlchemy`-based Channels backend when the project is `sqlspec`-only — drags an ORM dep into a project that explicitly avoided one.
- Wiring a PG-LISTEN backend when Redis is already handling SAQ queues and session cache — pay the connection overhead twice for no gain.
- Forcing Redis as a "canonical" Channels backend when the deploy target is a single Postgres + app image (extra infra, extra failure surface).

### Branch A — `MemoryChannelsBackend` (dev / single-process)

```python
from litestar.channels import ChannelsPlugin
from litestar.channels.backends.memory import MemoryChannelsBackend


channels = ChannelsPlugin(
    backend=MemoryChannelsBackend(history=60),
    arbitrary_channels_allowed=True,
)
```

### Branch B — `RedisChannelsPubSubBackend` (Redis already in stack)

```python
from litestar.channels import ChannelsPlugin
from litestar.channels.backends.redis import RedisChannelsPubSubBackend
from redis.asyncio import Redis


channels = ChannelsPlugin(
    backend=RedisChannelsPubSubBackend(redis=Redis.from_url("redis://localhost:6379/0")),
    channels=["notifications", "workspace:*"],   # subscribable channel names / globs
    arbitrary_channels_allowed=True,             # allow dynamic channels
    create_ws_route_handlers=True,               # exposes /ws/{channel} automatically
    ws_handler_base_path="/ws",
    subscriber_max_backlog=1000,                 # buffer messages during slow consumers
    subscriber_backlog_strategy="backoff",
)

app = Litestar(plugins=[channels])
```

Auto-creates a WS handler at `/ws/{channel}` that relays published messages.

### Branch C — `sqlspec` PG `LISTEN` / `NOTIFY` backend

Use when the project is `sqlspec` + PostgreSQL and you want Channels without introducing Redis. The sqlspec extension for Litestar Channels reuses the same Postgres connection pool. See [`../../sqlspec/SKILL.md`](../../sqlspec/SKILL.md) for the extension config.

```python
from sqlspec.extensions.litestar.channels import SQLSpecChannelsBackend

channels = ChannelsPlugin(
    backend=SQLSpecChannelsBackend(config=sqlspec_config),
    arbitrary_channels_allowed=True,
    create_ws_route_handlers=True,
)
```

`SQLSpecChannelsBackend` accepts any sqlspec config that exposes a Postgres-compatible adapter; it sets up `LISTEN` / `NOTIFY` on the same connection pool used by your queries.

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

> See [realtime-events.md](realtime-events.md) for the full `RealtimePublisher` abstraction,
> scope-specific publish helpers, channel factory classes, and neutral-domain publishing examples.

### Subscribing from WebSocket Handlers

The `stream_pubsub` helper manages subscription lifecycle, message decoding, bounded-LRU
deduplication, per-session metrics, and error handling.

```python
from litestar import WebSocket
from litestar.exceptions import WebSocketDisconnect

_MAX_DEDUP_KEYS = 1024


def _extract_idempotency_key(payload: dict) -> str | None:
    """Accept both snake_case and camelCase idempotency key."""
    return payload.get("idempotency_key") or payload.get("idempotencyKey")


async def stream_pubsub(
    socket: WebSocket,
    channels: list[str],
    history: int = 0,
    metrics: RealtimeStreamMetrics | None = None,
) -> None:
    """Stream pub/sub messages to a WebSocket client.

    Args:
        socket: The WebSocket connection (must already be accepted).
        channels: List of channel names to subscribe to.
        history: Number of historical messages to replay.
        metrics: Optional per-session metrics collector.
    """
    m = metrics or RealtimeStreamMetrics()
    seen_keys: list[str] = []
    seen_key_set: set[str] = set()

    try:
        async with config.channels.start_subscription(channels, history=history) as subscriber:
            async for message in subscriber.iter_events():
                m.messages_received += 1
                payload = decode_message(message, channels)
                if payload is None:
                    m.messages_malformed += 1
                    continue

                idem_key = _extract_idempotency_key(payload)
                if idem_key is not None:
                    if idem_key in seen_key_set:
                        m.messages_deduplicated += 1
                        continue
                    seen_keys.append(idem_key)
                    seen_key_set.add(idem_key)
                    if len(seen_keys) > _MAX_DEDUP_KEYS:
                        evicted = seen_keys.pop(0)
                        seen_key_set.discard(evicted)

                await socket.send_json(payload)
                m.messages_delivered += 1

    except WebSocketDisconnect:
        m.disconnects += 1
    except Exception:
        m.stream_errors += 1
        await logger.aexception("WebSocket stream error", channels=channels)
    finally:
        await logger.adebug(
            "Realtime stream session summary",
            **m.snapshot(),
            channels=channels,
        )
```

### Stream metrics

`RealtimeStreamMetrics` tracks per-session counters for observability.

```python
from dataclasses import dataclass, field


@dataclass
class RealtimeStreamMetrics:
    """Per-session counters for a stream_pubsub call."""

    active_subscriptions: int = 0
    messages_received: int = 0
    messages_delivered: int = 0
    messages_malformed: int = 0
    messages_deduplicated: int = 0
    disconnects: int = 0
    stream_errors: int = 0

    def snapshot(self) -> dict[str, int]:
        """Return an immutable copy of all counters."""
        return {
            "active_subscriptions": self.active_subscriptions,
            "messages_received": self.messages_received,
            "messages_delivered": self.messages_delivered,
            "messages_malformed": self.messages_malformed,
            "messages_deduplicated": self.messages_deduplicated,
            "disconnects": self.disconnects,
            "stream_errors": self.stream_errors,
        }

    def reset(self) -> None:
        """Zero all counters (e.g., between test runs)."""
        for f in self.__dataclass_fields__:
            setattr(self, f, 0)
```

Usage in a handler:

```python
@websocket(path="/{workspace_id:uuid}/stream")
async def stream_workspace_events(self, socket: WebSocket, workspace_id: UUID) -> None:
    await socket.accept()
    await stream_pubsub(
        socket,
        [RealtimeChannels.workspace(workspace_id)],
        history=10,
    )
```

### Custom WebSocket Handler with Channels (typed payloads, auth, per-connection state)

```python
from __future__ import annotations

from litestar import WebSocket, websocket
from litestar.channels import ChannelsPlugin


@websocket("/ws/workspace/{workspace_id:uuid}")
async def workspace_stream(
    socket: WebSocket,
    workspace_id: "UUID",
    channels: ChannelsPlugin,
) -> None:
    await socket.accept()

    # Auth during handshake (query-param JWT)
    token = socket.query_params.get("token")
    user = await verify_jwt(token) if token else None
    if user is None:
        await socket.close(code=4401, reason="Unauthorized")
        return

    # Subscribe this connection to the workspace's channel
    channel_name = f"workspace:{workspace_id}"
    async with channels.start_subscription([channel_name]) as subscriber:
        async for event in subscriber.iter_events():
            await socket.send_json(event)
```

### Realtime Event Contract

`RealtimeEvent` is the canonical envelope for all realtime messages — a `CamelizedBaseStruct`
with `scope`, `event_type`, optional `actor` / `entity` refs, and a `__post_init__` validator
that enforces the required ID fields per scope.

> See [realtime-events.md](realtime-events.md) for the canonical `RealtimeEvent` contract,
> `REALTIME_SCOPE_ACL`, `RealtimeActor`, `RealtimeEntityRef`, and full scope ACL details.

Quick-reference scope ACL:

| Scope | Access Rule |
| --- | --- |
| `workspace` | Workspace member or superuser |
| `user` | Authenticated subject only |
| `global` | Role/policy-authorized users only |

---

## Cross-Process Publishing

The Channels plugin gives you `channels.wait_published(channel, data)` — usable from SAQ workers, background tasks, shell scripts, or any module that can import your app's channels instance. The **same channel backend** (Redis) is shared across the Litestar app, SAQ workers, and out-of-process scripts. Any of them can publish; only WS subscribers receive.

### From a SAQ Worker

```python
# app/domain/workspaces/jobs.py
from __future__ import annotations

from saq import Context

from app.server.plugins import channels  # the same ChannelsPlugin instance


async def import_finished_job(ctx: Context, *, workspace_id: str, job_id: str) -> None:
    # ... do work ...

    # Broadcast to all WS clients subscribed to this workspace
    await channels.wait_published(
        f"workspace:{workspace_id}",
        {"type": "import.finished", "jobId": job_id},
    )
```

### From a CLI / One-off Script

```python
# tools/broadcast.py
from __future__ import annotations

import asyncio

from litestar.channels import ChannelsPlugin
from litestar.channels.backends.redis import RedisChannelsPubSubBackend
from redis.asyncio import Redis


async def main() -> None:
    backend = RedisChannelsPubSubBackend(redis=Redis.from_url("redis://localhost:6379/0"))
    channels = ChannelsPlugin(backend=backend, channels=[], arbitrary_channels_allowed=True)
    async with channels:                          # lifespan context — opens pub/sub
        await channels.wait_published("notifications", {"type": "deploy.finished"})


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
            to_json(payload, as_bytes=True), channels=[channel],
        )
```

---

## WS-vs-Channels Decision Matrix

"Broker" below means whatever pub/sub backend the project is on: Redis, PostgreSQL LISTEN/NOTIFY via sqlspec, advanced-alchemy session-aware, or in-memory for dev.

| Use case | Plain WS + hand-rolled broker | Channels plugin |
| --- | --- | --- |
| One-off streaming, few channel names | ✓ — simpler, fewer moving parts | — |
| Typed channels, automatic history / backlog | — | ✓ |
| Publishing from SAQ / CLI to WS clients | Works but you own the broker client | ✓ — shared backend across app + workers |
| Dynamic channel names (`workspace:{uuid}`) | ✓ — any string is a channel | ✓ — via `arbitrary_channels_allowed=True` |
| Auto-generated `/ws/{channel}` handlers | — | ✓ |
| Per-connection auth and state | ✓ — write your own | ✓ — via `@websocket` + `channels.start_subscription` |
| Multi-process / multi-node deployments | ✓ if you wire the broker explicitly | ✓ — built in (Redis / PG / AA backends) |

Canonical apps use the hand-rolled path for simple single-stream cases and Channels for broader pub/sub where multiple consumers + backlog tolerance matter. Don't run both in parallel for the same channel namespace — pick one. **Channels backend choice is orthogonal to this matrix** — see "Backend options" above for how to pick the backend based on your data-access stack.

---

## Patterns

### Event Broadcasting from Background Workers

Background tasks (ETL jobs, file processing) publish events to workspace channels. Connected WebSocket clients receive updates in real time.

```text
[Background Worker] --publish--> [ChannelsBackend] --subscribe--> [WebSocket Handler] --> [Client]
```

The publisher gracefully handles the case where the channels backend is not yet initialized (e.g., during startup), skipping the publish rather than raising.

### Multi-tenant Channel Isolation

- Each workspace gets its own set of channels (`workspace:{id}:etl`, `workspace:{id}:events`).
- WebSocket guards verify workspace membership before allowing subscription.
- Superusers can subscribe to any workspace stream.
- User-scoped streams (`user:{id}:events`) are restricted to the authenticated subject.
- Global streams require an explicit role policy check.

### Connection Lifecycle Management

1. Client connects with JWT in query parameter: `ws://host/path?token=<jwt>`
2. Guards validate token, load user, verify authorization.
3. Handler calls `socket.accept()` to complete the handshake.
4. `stream_pubsub` subscribes to channels and streams messages until disconnect.
5. `WebSocketDisconnect` is caught silently -- client disconnects are normal.
6. Subscription cleanup is automatic via `async with` context manager.
7. Stream metrics track active subscriptions, messages delivered, errors, and deduplication counts.

### Idempotency and Deduplication

Messages can carry an `idempotency_key` in their payload. The stream helper maintains a sliding window of seen keys (bounded to prevent memory growth) and skips duplicate deliveries. This is useful for at-least-once publish semantics from background workers.

## Cross-references

- WebSocket auth guards: [guards.md](../../litestar-auth-guards/references/guards.md)
- SAQ worker setup: `../../litestar-saq/SKILL.md`
- App wiring with Channels + plugins: [example.md](../../litestar-routing/references/example.md)
