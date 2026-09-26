# SQLSpec Event Channels

SQLSpec exposes synchronous and asynchronous database-backed event channels. Choose a transport by delivery semantics.

## Transport Matrix

| Transport | Delivery | Adapters |
| --- | --- | --- |
| `notify` | Transient native notification; no replay or retry | `asyncpg`, `psycopg`, `psqlpy` |
| `notify_queue` | Durable competing-consumer queue with a native wakeup hint | `asyncpg`, `psycopg`, `psqlpy` |
| `poll_queue` | Durable competing-consumer queue discovered by polling | All adapters with an event store |
| `aq` | Oracle Advanced Queuing | `oracledb` |
| `txeventq` | Oracle Transactional Event Queues | `oracledb` |

PostgreSQL-family adapters default to `notify`. Other adapters default to `poll_queue`.

The names `listen_notify`, `listen_notify_durable`, and `table_queue` were removed. SQLSpec raises `ImproperConfigurationError` and names the canonical replacement; it does not silently change delivery semantics.

## Configuration

```python
from sqlspec.adapters.asyncpg import AsyncpgConfig


config = AsyncpgConfig(
    connection_config={
        "dsn": "postgresql://localhost/app",
        "max_size": 5,
    },
    extension_config={
        "events": {
            "backend": "notify_queue",
            "event_poll_interval": 1.0,
        },
    },
)
```

`event_poll_interval` controls durable reconciliation when no wakeup arrives. `poll_interval` remains a compatibility input; `event_poll_interval` wins when both are set.

Native PostgreSQL listeners hold one dedicated pool connection for the backend lifetime. Configure at least two connections so publishing cannot deadlock behind the listener: `max_size >= 2` for asyncpg and psycopg, and `max_db_pool_size >= 2` for psqlpy.

## Publish and Consume

`AsyncEventChannel` is not an async context manager and has no `subscribe()` API. Construct it, use `iter_events()` or `listen()`, and call `shutdown()`.

```python
from sqlspec.extensions.events import AsyncEventChannel


channel = AsyncEventChannel(config)

try:
    event_id = await channel.publish(
        "user_events",
        {"type": "user.created", "user_id": "abc-123"},
        {"source": "accounts"},
    )

    async for event in channel.iter_events("user_events"):
        await handle_event(event)
        await channel.ack(event.event_id)
finally:
    await channel.shutdown()
```

`iter_events()` leaves acknowledgement to the caller. `listen(channel, handler, auto_ack=True)` starts a managed listener task and acknowledges successful handler calls by default. Use `nack(event_id)` to return a durable event for redelivery.

## Batch Publication

```python
event_ids = await channel.publish_many(
    [
        ("orders", {"type": "order.created", "id": "o-1"}, None),
        ("orders", {"type": "order.created", "id": "o-2"}, None),
    ]
)
```

Each item is `(channel, payload, metadata)`. Returned IDs preserve input order. Batch-capable backends publish a grouped call atomically. Backends without `publish_many()`, including Oracle native transports, use an ordered per-event fallback that is not atomic across the batch.

For `notify_queue`, the durable queue is the source of truth. PostgreSQL emits compact per-channel wakeup markers and reconciles missed markers on `event_poll_interval`.

## Event Model

`EventMessage` fields are:

| Field | Type |
| --- | --- |
| `event_id` | `str` |
| `channel` | `str` |
| `payload` | `dict[str, Any]` |
| `metadata` | `dict[str, Any] \| None` |
| `attempts` | `int` |
| `available_at` | `datetime` |
| `lease_expires_at` | `datetime \| None` |
| `created_at` | `datetime` |

There is no `message_id` or `timestamp` field.

## Oracle Native Backends

Oracle defaults to `poll_queue`. `aq` and `txeventq` are opt-in and attach to an existing queue; SQLSpec does not provision it.

- Both native transports work in python-oracledb Thin mode.
- JSON payloads require Oracle Database 21c or newer.
- The user needs the required `DBMS_AQADM`, AQ role, and `DBMS_AQ` privileges.
- `aq_queue` defaults to `SQLSPEC_EVENTS_QUEUE` and can include `{channel}` when physical per-channel queues are pre-provisioned.

## Durable Queue Schema & Claim Primitives

Durable queues support additive schema reconciliation:

- `manage_schema=False` leaves schema ownership to external migrations.
- `create_schema=False` refuses to create a missing queue table.
- Unknown or unsupported adapter-specific storage settings raise `ImproperConfigurationError`.

Column renames, drops, and type changes require explicit migrations. See [storage.md](storage.md) for backend-specific table tuning.

For custom queue stores or extensions, `sqlspec.extensions.events` exports dialect-aware table-queue SQL and claim verification primitives (`from sqlspec.extensions.events import claim_verified, lock_clause, row_limit_clause, select_limit_prefix`):

- `lock_clause(select_for_update=True, skip_locked=True)` renders `FOR UPDATE SKIP LOCKED` or `FOR UPDATE`.
- `row_limit_clause(dialect, n)` and `select_limit_prefix(dialect, n)` render `LIMIT n`, `FETCH FIRST n ROWS ONLY` (Oracle), or `TOP n` (MSSQL/T-SQL).
- `claim_verified(row, leased_until)` verifies lease ownership after a claim `UPDATE` even on drivers that do not report `rows_affected`.

## Framework Fan-Out (`SQLSpecChannelsBackend`)

Database event queues are competing-consumer transports, not browser broadcast buses. When a Litestar application needs WebSocket or SSE fan-out backed by SQLSpec's event channel (`notify`, `notify_queue`, or `poll_queue`), wrap `AsyncEventChannel(config)` in `SQLSpecChannelsBackend` from `sqlspec.extensions.litestar.channels`:

```python
from litestar.channels import ChannelsPlugin
from sqlspec.extensions.events import AsyncEventChannel
from sqlspec.extensions.litestar.channels import SQLSpecChannelsBackend

channels_plugin = ChannelsPlugin(
    backend=SQLSpecChannelsBackend(
        AsyncEventChannel(channels_db_config),
        output_queue_capacity=1024,
    ),
    arbitrary_channels_allowed=True,
    create_ws_route_handlers=False,
)
```

## Cross References

- [storage.md](storage.md) — durable schema controls and backend tuning.
- [adapters.md](adapters.md) — adapter capability matrix.
- [observability.md](observability.md) — event metrics and tracing.
