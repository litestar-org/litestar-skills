# litestar-queues — Namespacing and Expiry Reference

Two surfaces that define how a queue runtime is identified and how queued work times out.

## `QueueConfig(namespace=...)`

`namespace` names the runtime identity the package owns, so two independent queue runtimes can share a process without colliding. The default is `"litestar_queues"`, which preserves every existing identifier.

```python
from litestar_queues import QueueConfig

reports = QueueConfig(namespace="reports", queue_backend="sqlspec")
billing = QueueConfig(namespace="billing", queue_backend="sqlspec")
```

It derives:

- Litestar state, dependency, and route registrations
- Default stream paths and event channels
- Maintenance coordination keys
- Redis and Valkey keys, and backend wakeups
- Cloud Tasks delivery resources
- Task-module discovery environment variable (`<NAMESPACE>_TASK_MODULES`)
- Telemetry and logger hierarchies

Explicit component settings stay authoritative. **SQL table names, ORM model classes, task names, and queue names are untouched** — namespacing is about runtime identity, not storage schema.

## Not-Started Deadlines

Queued work can carry a deadline for being *claimed*, distinct from `timeout` (which bounds execution) and from user cancellation.

```python
from datetime import timedelta

from litestar_queues import QueueService, task


@task("reports.render", expires_in=timedelta(minutes=10))
async def render_report(report_id: str) -> str:
    return f"{report_id}.pdf"


async def queue_report(queue_service: QueueService, report_id: str) -> str:
    result = await queue_service.enqueue(render_report, report_id)
    return result.status or "unknown"
```

Use `expires_in` on the task decorator or at enqueue, or `expires_at` for an absolute instant. A record that passes the deadline without being claimed settles in the terminal `expired` state.

The deadline is enforced **atomically by every backend**. `expired` is reported through task results, events, metrics, CLI status, recurring schedules, and cleanup, and is distinct from cancellation and from a runtime failure.

## Event Streaming Configuration

`stream_queue_events_hardened`, `stream_queue_events_sse`, and `build_stream_router` are private with no aliases. Configure streaming through `EventStreamConfig`, which owns the path, transports, guards, channel authorizer, scopes, heartbeat interval, and replay limit.

Set `replay_limit > 0` (the default is `0`) when browser clients must recover missed events across a reconnect; on the browser side, consume the stream with `createQueueEventStream` from `litestar-vite-plugin/helpers` (covered in [litestar-vite streams](../../litestar-vite/references/streams.md)).

## Cross-References

- **[Execution Backends](execution-backends.md)** — managed transports and repair.
- **[Litestar Channels & SSE](../../litestar/references/channels-and-sse.md)** — Channels backends behind the event stream.

## Official References

- <https://github.com/cofin/litestar-queues/blob/v0.12.0/docs/changelog.rst>
- <https://github.com/cofin/litestar-queues/blob/v0.12.0/src/litestar_queues/config.py>
