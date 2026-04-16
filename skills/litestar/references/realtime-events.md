# Realtime Events

This file documents the realtime event contract, scope ACL, channel factories, and the
`RealtimePublisher` abstraction. For WebSocket guard composition see [guards.md](guards.md); for
the Channels backend configuration and the `stream_pubsub` subscriber helper see
[websockets.md](websockets.md). Together, the three files cover the full realtime stack used by
Litestar applications with multi-scope pub/sub.

## Event envelope (`RealtimeEvent`)

`RealtimeEvent` is the canonical typed envelope for every realtime message. All scope variants
(workspace, user, global) share the same struct — the `scope` field drives routing, and
`__post_init__` enforces that the matching ID field is present.

Adapted from `dma/accelerator/src/py/dma/lib/realtime/_contract.py:L60–81`.

```python
import msgspec
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

RealtimeScope = Literal["workspace", "user", "global"]
RealtimeEventType = str  # open-ended; narrow with Literal in domain modules

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
stays snake_case. Do NOT add `from __future__ import annotations` in modules that define
`msgspec.Struct` subclasses — it breaks runtime field resolution.

## Scope ACL table

`REALTIME_SCOPE_ACL` maps each scope to the access-control policy enforced by the corresponding
WS guard. Adapted from `_contract.py:L20–24`.

| Scope       | Access policy                     | Guard                               |
|-------------|-----------------------------------|-------------------------------------|
| `workspace` | Workspace member or superuser     | `requires_websocket_workspace_member` |
| `user`      | Authenticated subject only        | `requires_websocket_user_subject`   |
| `global`    | Role/policy-authorized users only | `requires_websocket_global_access`  |

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
    """Reference to the domain object the event concerns."""

    type: str   # e.g. "order", "post", "task"
    id: str     # stringified primary key
```

## Channel naming factories

Use static factory methods for consistent, namespaced channel names. `RealtimeChannels` provides
the canonical three-scope pattern; domain modules extend it with topic-specific factories.

Adapted from `_contract.py:L27–43` (canonical factories) and
`domain/workspaces/channels.py:L6–25` (domain-specific extension pattern — accelerator uses
`WorkspaceChannels.etl/.files/.job_logs`; the neutral equivalent below uses `OrderChannels`).

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
publishes during startup before the Litestar lifespan has run). Adapted from
`dma/accelerator/src/py/dma/lib/realtime/_publisher.py:L17–116`.

The `to_json(event, as_bytes=True)` call uses the Ch2 `to_json` wrapper — see
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
        return "backend not yet initialized" in str(exc).lower()
```

## Publishing from domain services (examples)

Call `publish_workspace_event` from any service that has a `RealtimePublisher` injected. The
publisher is lightweight — inject it via `Provide()` or Dishka and call it after the DB write.
Call sites in the accelerator: `domain/notifications/services/_notification.py:L184–189`
(per-user notification) and `domain/workspaces/services/_workspace_file.py:L255–260`
(workspace file events).

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

- WebSocket guard chain: [guards.md](guards.md)
- Channels backend config + `stream_pubsub` subscriber: [websockets.md](websockets.md)
- `to_json` serializer import choice (sqlspec vs hand-rolled): [`../../msgspec/references/litestar-patterns.md`](../../msgspec/references/litestar-patterns.md)
- SQL-observer publishing pattern: `../../sqlspec/references/observability.md` (TODO(Ch5))

## Shared Styleguide Baseline

Generic language and framework conventions:

- [`../../litestar-styleguide/references/python.md`](../../litestar-styleguide/references/python.md)
