# WebSocket Handlers, Lifecycle, Authentication, and Stream Helpers

## WebSocket Handlers

| Decorator / Class | Signature Requirements | Lifecycle & Serialization | Best For |
| --- | --- | --- | --- |
| `@websocket` (`WebsocketRouteHandler`) | `async def`, returns `None`, requires `socket: WebSocket`; forbids `request`, `body`, `data` | Manual `await socket.accept()`, receive/send loop, and `WebSocketDisconnect` handling | Bidirectional streams, custom `ChannelsPlugin` subscriptions, multiplexed protocols |
| `@websocket_listener` (`WebsocketListenerRouteHandler`) / `WebsocketListener` | Sync or async, requires `data` parameter (`socket: WebSocket` optional); forbids `request`, `body` | Auto-accepts, catches `WebSocketDisconnect`, decodes `data` (via `dto` / `msgspec`), serializes return value (if non-`None` via `return_dto` / `msgspec`), runs `on_accept` / `on_disconnect` or `connection_lifespan` | Request/response RPC or chat message loops over WebSocket |
| `@websocket_stream` (`WebsocketRouteHandler` via `WebSocketStreamHandler`) / `send_websocket_stream` | Async generator returning `AsyncGenerator[T, None]` (`socket: WebSocket` optional) | Auto-accepts, iterates generator, sends yielded items (`str`/`bytes` raw or JSON via `return_dto` / `msgspec`), cancels on client disconnect when `listen_for_disconnect=True` | Unidirectional server-to-client WebSocket push streams (ticks, telemetry, logs) |

### The `@websocket()` Decorator

```python
from __future__ import annotations

from uuid import UUID

from litestar import Controller, WebSocket, websocket
from litestar.params import FromPath


class StreamController(Controller):
    path = "/api/workspaces"
    tags = ["Workspaces"]
    guards = [requires_websocket_auth, requires_websocket_membership]

    @websocket(
        path="/{workspace_id:uuid}/events/stream",
        name="workspaces:events-stream",
        opt={"exclude_from_csrf": True, "exclude_from_auth": True},
    )
    async def stream_events(self, socket: WebSocket, workspace_id: FromPath[UUID]) -> None:
        await socket.accept()
        await stream_pubsub(socket, [Channels.events(workspace_id)], history=10)
```

Key points:

- WebSocket handlers use `opt={"exclude_from_csrf": True, "exclude_from_auth": True}` to bypass HTTP-oriented middleware. Authentication is handled by WebSocket-specific guards instead.
- Path parameters (e.g., `workspace_id: FromPath[UUID]`) and DI dependencies (`NamedDependency[T]`) work the same as HTTP route handlers.
- The handler must be `async`, return `None`, and accept `socket: WebSocket` (never `request`, `body`, or `data`).
- Pass `websocket_class=` on `@websocket`, `Controller`, `Router`, or `Litestar` to use a custom `WebSocket` subclass.

### `WebSocket` Connection API & Lifecycle

`WebSocket` inherits from `ASGIConnection` and tracks `socket.connection_state` (`"init" | "connect" | "receive" | "disconnect"`).

- **Handshake & closure**:
  - `await socket.accept(subprotocols=None, headers=None)`
  - `await socket.close(code=WS_1000_NORMAL_CLOSURE, reason=None)`
- **Single-frame receive** (raises `WebSocketDisconnect` when the client closes):
  - `await socket.receive_data(mode="text" | "binary") -> str | bytes`
  - `await socket.receive_text() -> str`
  - `await socket.receive_bytes() -> bytes`
  - `await socket.receive_json(mode="text") -> Any`
  - `await socket.receive_msgpack() -> Any` (always receives in `"binary"` mode)
- **Continuous async iterators** (catch `WebSocketDisconnect` automatically and exit the loop cleanly):
  - `socket.iter_data(mode="text" | "binary") -> AsyncGenerator[str | bytes, None]`
  - `socket.iter_json(mode="text" | "binary") -> AsyncGenerator[Any, None]`
  - `socket.iter_msgpack() -> AsyncGenerator[Any, None]`
- **Sending frames**:
  - `await socket.send_data(data: str | bytes, mode="text", encoding="utf-8")`
  - `await socket.send_text(data: str | bytes, encoding="utf-8")`
  - `await socket.send_bytes(data: str | bytes, encoding="utf-8")`
  - `await socket.send_json(data: Any, mode="text", encoding="utf-8", serializer=default_serializer)`
  - `await socket.send_msgpack(data: Any, encoding="utf-8", serializer=default_serializer)`

```python
from litestar import WebSocket
from litestar.exceptions import WebSocketDisconnect


async def handle_websocket(socket: WebSocket) -> None:
    """Accept the socket and echo JSON payloads until client disconnect."""
    await socket.accept()
    async for payload in socket.iter_json():
        await socket.send_json({"status": "ok", "echo": payload})
```

If you need explicit low-level loop control rather than `iter_json()`, catch `WebSocketDisconnect` around `receive_json()`:

```python
from litestar import WebSocket
from litestar.exceptions import WebSocketDisconnect


async def handle_websocket_manual(socket: WebSocket) -> None:
    """Manual receive loop with explicit WebSocketDisconnect handling."""
    await socket.accept()
    try:
        while True:
            data = await socket.receive_json()
            await socket.send_json({"status": "ok", "received": data})
    except WebSocketDisconnect:
        pass
```

### `@websocket_listener` and `WebsocketListener`

Use `@websocket_listener` (or the class-based `WebsocketListener`) when the handler receives messages in a loop, parses `data` into a typed parameter (including `msgspec.Struct`, dataclasses, or DTO-backed models), and optionally sends each return value back to the client.

```python
import msgspec
from litestar import WebSocket
from litestar.handlers import WebsocketListener, websocket_listener


class ChatIn(msgspec.Struct):
    text: str


class ChatOut(msgspec.Struct):
    reply: str


async def on_client_connect(socket: WebSocket) -> None:
    """Hook invoked after the WebSocket connection is accepted."""
    await socket.send_json({"type": "connected"})


async def on_client_disconnect(socket: WebSocket) -> None:
    """Hook invoked after the WebSocket connection closes."""


@websocket_listener(
    "/ws/chat",
    receive_mode="text",
    send_mode="text",
    on_accept=on_client_connect,
    on_disconnect=on_client_disconnect,
)
async def chat_handler(data: ChatIn, socket: WebSocket) -> ChatOut:
    """Receive typed ChatIn payloads and send serialized ChatOut responses."""
    return ChatOut(reply=f"ack: {data.text}")


class EchoListener(WebsocketListener):
    """Class-based WebSocket listener."""

    path = "/ws/echo"
    receive_mode = "text"
    send_mode = "text"

    async def on_accept(self, socket: WebSocket) -> None:
        await socket.send_text("ready")

    async def on_receive(self, data: str) -> str:
        return data

    async def on_disconnect(self, socket: WebSocket) -> None:
        return None
```

Key `@websocket_listener` rules:

- The callback must declare a `data` parameter and must not declare `request` or `body`.
- If the return annotation is `None`, nothing is sent back after `on_receive`; otherwise the return value is sent (`str`/`bytes` directly, or JSON-encoded via `return_dto` / `msgspec`).
- `on_accept`, `on_disconnect`, and `connection_lifespan` all support full Litestar dependency injection (e.g., `socket: WebSocket`, `state: State`, or `Provide` dependencies).
- Do not pass `connection_lifespan` together with `on_accept`, `on_disconnect`, or a custom `connection_accept_handler` — Litestar raises `ImproperlyConfiguredException`.

### `@websocket_stream` and `send_websocket_stream`

Use `@websocket_stream` when a route pushes an `AsyncGenerator` stream to the client without reading application messages from the socket.

```python
import asyncio
from collections.abc import AsyncGenerator

from litestar import WebSocket, websocket
from litestar.handlers import send_websocket_stream, websocket_stream


@websocket_stream("/ws/ticks", mode="text", listen_for_disconnect=True)
async def tick_stream() -> AsyncGenerator[dict[str, int], None]:
    """Stream periodic tick payloads until the client disconnects."""
    seq = 0
    while True:
        seq += 1
        yield {"seq": seq}
        await asyncio.sleep(1.0)


@websocket("/ws/custom-ticks")
async def custom_tick_handler(socket: WebSocket) -> None:
    """Stream an async generator inside a manual @websocket handler."""
    await socket.accept()
    await send_websocket_stream(
        socket,
        tick_stream(),
        mode="text",
        close=True,
        listen_for_disconnect=True,
    )
```

Key `@websocket_stream` / `send_websocket_stream` rules:

- The decorated function must have an `AsyncGenerator[T, Any]` return annotation (raises `ImproperlyConfiguredException` otherwise).
- `listen_for_disconnect` defaults to `True` on `@websocket_stream` and `False` on `send_websocket_stream`.
- Never set `listen_for_disconnect=True` if you also read from `socket` concurrently — the background disconnect listener reads from `socket.receive_data("text")`, discards any incoming client frames, and emits a `LitestarWarning` (controlled by `warn_on_data_discard=True`).

### Dishka DI in WS handlers

WebSocket connections live at SESSION scope in Dishka — the container is created once per
connection and stored at `connection.state.dishka_container`. REQUEST-scoped services (e.g., a
database session or unit-of-work) need a child container created per operation. Use a context
manager to open a transient REQUEST-scope child for each receive/send cycle.

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from dishka import AsyncContainer
from litestar import WebSocket, websocket
from litestar.params import FromPath


@asynccontextmanager
async def enter_request_scope(socket: WebSocket) -> AsyncIterator[AsyncContainer]:
    """Open a REQUEST-scoped child container for one WS operation."""
    session_container: AsyncContainer = socket.state.dishka_container
    async with session_container() as request_container:
        yield request_container


@websocket("/ws/workspace/{workspace_id:uuid}/stream")
async def workspace_stream(socket: WebSocket, workspace_id: FromPath[UUID]) -> None:
    await socket.accept()
    async for message in socket.iter_json():
        async with enter_request_scope(socket) as container:
            svc = await container.get(OrderService)
            await svc.process(message, workspace_id)
```

**Branch note — `Provide`-only stacks:** Litestar's built-in DI attaches services via `Provide`
in the handler signature. The REQUEST-scope child container pattern is Dishka-specific — on
`Provide`-only stacks, inject services directly at the handler signature as usual:

```python
from uuid import UUID

from litestar import WebSocket, websocket
from litestar.di import NamedDependency
from litestar.params import FromPath


@websocket("/ws/workspace/{workspace_id:uuid}/stream")
async def workspace_stream(
    socket: WebSocket,
    workspace_id: FromPath[UUID],
    order_service: NamedDependency[OrderService],
) -> None:
    """Handle workspace stream with Litestar Provide-injected service."""
    await socket.accept()
```

### Authentication in WebSocket Connections

Browser WebSocket clients cannot attach custom `Authorization` headers during the initial handshake. Authenticate via cookies/session or a `token` query parameter in a guard.

```python
from uuid import UUID

from litestar.connection import ASGIConnection
from litestar.exceptions import NotAuthorizedException, WebSocketException
from litestar.handlers import BaseRouteHandler
from litestar.security.jwt import Token


async def requires_websocket_auth(
    connection: ASGIConnection,
    _: BaseRouteHandler,
) -> None:
    """Authenticate WebSocket via query param token and attach user to connection.state."""
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
from litestar.connection import ASGIConnection
from litestar.exceptions import WebSocketException
from litestar.handlers import BaseRouteHandler


async def requires_websocket_membership(
    connection: ASGIConnection,
    _: BaseRouteHandler,
) -> None:
    """Verify user is a member of the workspace in the path, or a superuser."""
    user = getattr(connection.state, "user", None)
    if user is None:
        raise WebSocketException(code=4001, detail="Unauthorized")

    if has_full_access_role(user):
        return

    workspace_id = connection.path_params.get("workspace_id")
    if workspace_id is None:
        raise WebSocketException(code=4003, detail="Missing workspace_id")

    is_member = await workspace_member_service.is_member(workspace_id, user.id)
    if not is_member:
        raise WebSocketException(code=4003, detail="Forbidden")


async def requires_websocket_subject(
    connection: ASGIConnection,
    _: BaseRouteHandler,
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
from uuid import UUID

from litestar import Controller, WebSocket, websocket
from litestar.params import FromPath


class WorkspaceStreamController(Controller):
    guards = [requires_websocket_auth, requires_websocket_membership]


class RealtimeStreamController(Controller):
    guards = [requires_websocket_auth]

    @websocket(
        path="/users/{user_id:uuid}/stream",
        guards=[requires_websocket_subject],
    )
    async def stream_user_events(self, socket: WebSocket, user_id: FromPath[UUID]) -> None: ...

    @websocket(
        path="/global/stream",
        guards=[requires_websocket_global_access],
    )
    async def stream_global_events(self, socket: WebSocket) -> None: ...
```

---

## Subscribing to Channels from WebSocket Handlers

> For `ChannelsPlugin` configuration, backends (`Memory`, `Redis`, `AsyncPg`, `PsycoPg`, `SQLSpec`), SSE streaming, and the `RealtimeEvent` / `RealtimePublisher` contract, see [channels-and-sse.md](channels-and-sse.md).

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
from dataclasses import dataclass


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
async def stream_workspace_events(self, socket: WebSocket, workspace_id: FromPath[UUID]) -> None:
    await socket.accept()
    await stream_pubsub(
        socket,
        [RealtimeChannels.workspace(workspace_id)],
        history=10,
    )
```

### Custom WebSocket Handler with Channels (auth, per-connection state, bidirectional I/O)

`subscriber.iter_events()` yields raw `bytes`. Pass those `bytes` directly to `await socket.send_text(event)` (which accepts `str | bytes` without re-encoding JSON) or decode before calling `socket.send_json(...)`. When the handler must also receive frames from the client while streaming channel events, use `subscriber.run_in_background(socket.send_text)`:

```python
from __future__ import annotations

from uuid import UUID

from litestar import WebSocket, websocket
from litestar.channels import ChannelsPlugin
from litestar.di import NamedDependency
from litestar.exceptions import WebSocketDisconnect
from litestar.params import FromPath


@websocket("/ws/workspace/{workspace_id:uuid}")
async def workspace_stream(
    socket: WebSocket,
    workspace_id: FromPath[UUID],
    channels: NamedDependency[ChannelsPlugin],
) -> None:
    """Authenticate during handshake and stream workspace events."""
    await socket.accept()

    token = socket.query_params.get("token")
    user = await verify_jwt(token) if token else None
    if user is None:
        await socket.close(code=4401, reason="Unauthorized")
        return

    channel_name = f"workspace:{workspace_id}"
    async with (
        channels.start_subscription([channel_name]) as subscriber,
        subscriber.run_in_background(socket.send_text),
    ):
        try:
            while True:
                incoming = await socket.receive_json()
                await channels.wait_published(incoming, channels=[channel_name])
        except WebSocketDisconnect:
            return
```

---

## WS-vs-Channels Decision Matrix

"Broker" below means whatever pub/sub backend the project is on: Redis, PostgreSQL LISTEN/NOTIFY via AsyncPg/PsycoPg, SQLSpec events, or in-memory for dev.

| Use case | Plain WS + hand-rolled broker | Channels plugin |
| --- | --- | --- |
| One-off streaming, few channel names | ✓ — simpler, fewer moving parts | — |
| Typed channels, automatic history / backlog | — | ✓ |
| Publishing from SAQ / CLI to WS clients | Works but you own the broker client | ✓ — shared backend across app + workers |
| Dynamic channel names (`workspace:{uuid}`) | ✓ — any string is a channel | ✓ — via `arbitrary_channels_allowed=True` |
| Auto-generated `/ws/{channel}` handlers | — | ✓ |
| Per-connection auth and state | ✓ — write your own | ✓ — via `@websocket` + `channels.start_subscription` |
| Multi-process / multi-node deployments | ✓ if you wire the broker explicitly | ✓ — built in (Redis / PG / SQLSpec backends) |

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

- WebSocket auth guards: [auth-and-guards.md](auth-and-guards.md)
- SAQ worker setup: `../../litestar-saq/SKILL.md`
- App wiring with Channels + plugins: [layout.md](layout.md)
- Channels & Server-Sent Events: [channels-and-sse.md](channels-and-sse.md)
