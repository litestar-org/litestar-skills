# Postgres-native sidecar worker

This reference documents a project-owned sidecar worker directly over PostgreSQL: one project-owned `job` table, SQLSpec-backed state transitions, a `@task` registry, a dedicated sidecar for wakeups, heartbeats, and channel publishing, and optional execution-target routing.

<!-- NOTE: do NOT use `from __future__ import annotations` in modules that define
@task-decorated functions when the decorator inspects signatures at registration time. -->

## When this fits

| Factor | SAQ wins | Custom PG-native wins |
| --- | --- | --- |
| Maintained queue behavior | Yes | No, project-owned |
| Web dashboard / job retry UI | Yes (`web_enabled=True`) | No, build your own |
| Postgres NOTIFY wake-ups | Yes with SAQ PostgreSQL broker | Yes |
| `FOR UPDATE SKIP LOCKED` atomic claim | Yes with SAQ PostgreSQL broker | Yes |
| Same-transaction outbox with business data | No | Yes |
| Project-owned job table/schema | No | Yes |
| Multi-target execution routing | No | Yes (`local` / `cloudrun` / `immediate`) |
| Minimal dependency surface | Queue package + broker | Existing PostgreSQL stack |
| Cron scheduling | Yes (`CronJob`) | Yes (`@task(cron=...)` + schedule registry) |
| High-throughput general queue | Yes | Usually no; PG row contention is the limit |

**Bottom line:** stay with the standard queue path when dashboards, maintained retry behavior, and upstream queue semantics matter. Choose this sidecar worker path only when the app needs outbox coupling, project-owned schema semantics, frontend channel updates from running jobs, or execution-target routing strongly enough to own the worker runtime.

## Component Split

Keep responsibilities explicit:

- `TaskService` owns SQL state transitions: enqueue, dedupe, claim, complete, fail, cancel, stale requeue, schedule successor creation, and task wakeup notifications.
- `Worker` owns execution: job discovery, polling fallback, `FOR UPDATE SKIP LOCKED` claim flow, retry decisions, timeout enforcement, log flushing, and graceful shutdown.
- `WorkerSidecar` owns off-loop infrastructure: LISTEN/NOTIFY listeners, batched heartbeat/progress publishing, frontend channel publishing, claim-loss detection, realtime publisher rebinding, reconnect/backoff, and connection operation serialization.
- `WorkerPlugin` owns Litestar integration only: dependency registration, task discovery, schedule sync, and optional in-process worker startup on dedicated worker replicas.
- Execution backends own external dispatch: for example, a Cloud Run backend stores the row first, dispatches a one-shot job, and records an execution reference in `job.metadata`.

Do not collapse these into one plugin class. The sidecar exists because worker execution can block or saturate the main event loop; heartbeats, wakeups, and frontend channel updates still need a dedicated connection that keeps moving.

## Schema

The pattern uses a single `job` table. Add indexes for your hot paths, especially `(status, execution_target, scheduled_at, priority, created_at)`, `key`, and stale-running lookup by `heartbeat_at`.

```sql
CREATE TABLE job (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key              TEXT UNIQUE,
    function         TEXT NOT NULL,
    data             JSONB NOT NULL DEFAULT '{}'::jsonb,
    status           TEXT NOT NULL DEFAULT 'pending',
    priority         INT NOT NULL DEFAULT 0,
    retry_count      INT NOT NULL DEFAULT 0,
    max_retries      INT NOT NULL DEFAULT 3,
    execution_target TEXT NOT NULL DEFAULT 'local',
    scheduled_at     TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at       TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    heartbeat_at     TIMESTAMPTZ,
    error            TEXT,
    result           JSONB,
    metadata         JSONB NOT NULL DEFAULT '{}'::jsonb
);
```

```python
from typing import Literal

JobStatus = Literal["pending", "scheduled", "running", "completed", "failed", "cancelled"]
ExecutionTarget = Literal["local", "cloudrun", "immediate"]
```

## TaskService Contract

The service should sit on the project SQLSpec service layer. It must fence state changes with the current `retry_count`; late completion or failure from an old worker must not overwrite a newer retry.

### `create_task`

Persist the row before dispatching external work. Clear reusable dedupe keys on terminal rows, handle `UniqueViolationError` by re-reading the winning row, and notify the worker after commit when the row is visible.

```python
async def create_task(
    self,
    function: str,
    data: dict[str, object] | None = None,
    *,
    key: str | None = None,
    priority: int = 0,
    scheduled_at: datetime | None = None,
    max_retries: int = 3,
    execution_target: ExecutionTarget = "local",
) -> UUID:
    """Persist a task row and return its id."""
    ...
```

### `get_pending_tasks`

Read ready rows without locking. Claiming happens in `claim_task` so multiple workers can inspect the same candidate list without holding locks while they decide.

```sql
SELECT id, function, data, retry_count, max_retries, execution_target
FROM job
WHERE status IN ('pending', 'scheduled')
  AND execution_target = :execution_target
  AND (scheduled_at IS NULL OR scheduled_at <= :now)
ORDER BY priority DESC, created_at ASC
LIMIT :limit
```

### `claim_task`

Use a transaction and `FOR UPDATE SKIP LOCKED`; return the claimed job row with the updated `retry_count`.

```python
async def claim_task(self, task_id: UUID) -> Job | None:
    """Transition pending/scheduled to running, or return None on a race loss."""
    ...
```

The SQL shape:

```sql
SELECT id, function, data, retry_count
FROM job
WHERE id = :task_id AND status IN ('pending', 'scheduled')
FOR UPDATE SKIP LOCKED;

UPDATE job
SET status = 'running',
    started_at = NOW(),
    heartbeat_at = NOW()
WHERE id = :task_id;
```

### `complete_task`

Fence by both status and `retry_count`.

```python
async def complete_task(
    self,
    task_id: UUID,
    expected_retry_count: int,
    result: dict[str, object] | None = None,
) -> None:
    """Mark the running task complete if this worker still owns the claim."""
    ...
```

### `fail_task`

Retry only when the row is still the same running attempt.

```python
async def fail_task(
    self,
    task_id: UUID,
    expected_retry_count: int,
    error: str,
    *,
    retry: bool = True,
) -> None:
    """Fail the running task, optionally requeueing under the retry cap."""
    ...
```

Use one atomic update:

```sql
UPDATE job
SET status = CASE
        WHEN retry_count < max_retries AND :retry THEN 'pending'
        ELSE 'failed'
    END,
    retry_count = CASE
        WHEN retry_count < max_retries AND :retry THEN retry_count + 1
        ELSE retry_count
    END,
    started_at = CASE
        WHEN retry_count < max_retries AND :retry THEN NULL
        ELSE started_at
    END,
    completed_at = CASE
        WHEN retry_count >= max_retries OR NOT :retry THEN NOW()
        ELSE completed_at
    END,
    error = :error
WHERE id = :task_id
  AND status = 'running'
  AND retry_count = :expected_retry_count;
```

### Stale Recovery

Run `requeue_stale_running()` on worker startup and periodically from the worker loop. Treat `heartbeat_at IS NULL` or an old heartbeat as stale. Increment `retry_count` when requeueing, and mark terminal failure when the task is no longer requeueable or retry budget is exhausted.

On shutdown, stop the sidecar before nulling active heartbeats. Otherwise the sidecar can rewrite a fresh heartbeat after shutdown cleanup.

## WorkerSidecar

The sidecar is a dedicated daemon thread with its own asyncio loop and one raw asyncpg connection. It is not a job executor.

Required responsibilities:

- Register active jobs with `(job_id, retry_count)`.
- Tick heartbeats on a fixed interval by snapshotting every active `(job_id, retry_count)` pair and updating the whole batch in one query.
- Store optional progress metadata from a `beat("message")` helper.
- Detect claim loss from the batched heartbeat result set: any registered job id not returned by the fenced update missed ownership for that tick; invoke claim-loss callbacks after repeated misses.
- Install LISTEN callbacks for the task notification channel and wake the worker loop with `loop.call_soon_threadsafe(...)`.
- Publish channel event bytes through the same sidecar connection when the worker job needs to update the frontend.
- Serialize operations on the single asyncpg connection with an `asyncio.Lock`; `add_listener`, `fetch`, and `pg_notify` must not race on the connection.
- Supervise reconnects with exponential backoff, degraded-state logging, and listener reinstallation after reconnect.

Minimal shape:

```python
class WorkerSidecar:
    def __init__(self, conn_params: dict[str, object], *, interval: float = 30.0) -> None: ...

    def start(self, timeout: float = 10.0) -> None: ...

    def stop(self, timeout: float = 10.0) -> None: ...

    def add_listener(self, channel: str, callback: Callable[[], None]) -> None: ...

    def add_claim_lost_callback(self, callback: Callable[[UUID], None]) -> None: ...

    def register_job(self, job_id: UUID, retry_count: int) -> None: ...

    def unregister_job(self, job_id: UUID) -> None: ...

    def record_beat(self, job_id: UUID, detail: str | None) -> None: ...

    async def publish(self, data: bytes, channels: Iterable[str]) -> None: ...
```

Batched heartbeat SQL:

```sql
UPDATE job
SET heartbeat_at = :now,
    metadata = CASE
        WHEN updates.progress_at IS NULL THEN metadata
        ELSE coalesce(metadata, '{}'::jsonb) ||
             jsonb_build_object(
                 'progress',
                 jsonb_build_object('at', updates.progress_at, 'detail', updates.progress_detail)
             )
    END
FROM (
    SELECT unnest(:job_ids::uuid[]) AS id,
           unnest(:retry_counts::int[]) AS retry_count,
           unnest(:progress_ats::timestamptz[]) AS progress_at,
           unnest(:progress_details::text[]) AS progress_detail
) AS updates
WHERE job.id = updates.id
  AND job.retry_count = updates.retry_count
  AND status = 'running'
RETURNING job.id;
```

Sidecar tick contract:

1. Copy active jobs and progress beats under a thread lock.
2. Build parallel arrays: `job_ids`, `retry_counts`, `progress_ats`, `progress_details`.
3. Run one fenced `UPDATE ... FROM unnest(...) RETURNING job.id`.
4. Clear only progress beats that were included in the submitted snapshot.
5. Compare returned ids to the submitted ids.
6. Increment miss counts for non-returned ids and fire claim-loss callbacks after repeated misses.
7. Clear miss counts for ids that returned successfully.

This batching is the point of the sidecar: many running jobs share one off-loop heartbeat tick and one database round trip instead of each job competing for its own heartbeat query.

## Frontend Channel Updates

The sidecar should also act as the worker-side channel backend. A long-running job can emit progress or result events while the web process streams those events to WebSocket or SSE clients through Litestar Channels.

Use the same channel serialization and channel names as the web app. Do not invent a second pub/sub format just for workers.

Minimal backend adapter:

```python
from collections.abc import Iterable


class SidecarChannelsBackend:
    """Channels backend adapter that publishes through the worker sidecar."""

    def __init__(self, sidecar: WorkerSidecar) -> None:
        self.sidecar = sidecar

    async def publish(self, data: bytes, channels: Iterable[str]) -> None:
        await self.sidecar.publish(data, channels)
```

Worker startup binds the app's worker-scoped publisher to the sidecar-backed backend:

```python
sidecar = WorkerSidecar(settings.database.connection_params, interval=settings.worker.heartbeat_interval)
channel_backend = SidecarChannelsBackend(sidecar)
realtime_publisher.backend = channel_backend
job_observer.backend = channel_backend
sidecar.start()
```

Task code publishes typed progress events through the normal publisher. The frontend subscribes to the same channel through the app's WebSocket or SSE route:

```python
async def process_import(*, import_id: str) -> None:
    await realtime_publisher.publish_event(
        channel=f"jobs:{import_id}",
        event_type="job.progress",
        payload={"stage": "extract", "percent": 25},
    )
    beat("extract complete")

    await realtime_publisher.publish_event(
        channel=f"jobs:{import_id}",
        event_type="job.progress",
        payload={"stage": "load", "percent": 75},
    )
```

One-shot external workers need the same binding before task execution and must restore or discard it in `finally` with the sidecar shutdown. That keeps local workers and external workers behaviorally identical: both heartbeat, detect claim loss, and publish frontend updates through the same channel contract.

## Worker Loop

The worker loop owns execution and uses the sidecar only for infrastructure signals.

```python
class Worker:
    def __init__(
        self,
        *,
        poll_interval: float = 30.0,
        batch_size: int = 10,
        max_concurrent_jobs: int = 4,
        shutdown_timeout: float = 30.0,
        graceful_shutdown_timeout: float = 10.0,
        register_signals: bool = True,
    ) -> None: ...
```

Startup sequence:

1. Build a worker-scoped DI container and SQLSpec driver/session config.
2. Add a sidecar listener on the task channel. The callback sets an `asyncio.Event` on the worker loop.
3. Start the sidecar.
4. Load the task registry.
5. Requeue stale running jobs.
6. Enter the loop: process candidates, reconcile external jobs, flush logs, then wait for shutdown, notification, or fallback poll timeout.

Execution sequence:

1. `get_pending_tasks(limit=...)`.
2. `claim_task(task_id)`.
3. `sidecar.register_job(task_id, retry_count)`.
4. Set a context-local `beat()` sink that calls `sidecar.record_beat(...)`; the next batched heartbeat flushes the latest progress detail.
5. Execute the task with `asyncio.wait_for(..., timeout=task_timeout)`.
6. On success, call `complete_task(task_id, retry_count, result=...)`.
7. On failure, call `fail_task(task_id, retry_count, error=..., retry=...)`.
8. Always unregister the job, flush logs, and clear context.

Shutdown sequence:

1. Stop the sidecar.
2. Null heartbeats for jobs still owned by this worker.
3. Allow graceful completion.
4. Cancel remaining tasks after the graceful deadline.
5. Flush logs and close the worker DI container.

## WorkerPlugin

The Litestar plugin should stay thin. It wires app startup/shutdown and dependency registration; it should not own the sidecar logic.

```python
from litestar.config.app import AppConfig
from litestar.plugins import InitPluginProtocol


class WorkerPlugin(InitPluginProtocol):
    def __init__(
        self,
        *,
        start_worker: bool = False,
        domain_packages: list[str] | None = None,
        job_submodules: list[str] | None = None,
        auto_discover: bool = True,
        shutdown_timeout: float = 30.0,
        graceful_shutdown_timeout: float = 10.0,
    ) -> None: ...

    def on_app_init(self, app_config: AppConfig) -> AppConfig:
        app_config.dependencies = app_config.dependencies or {}
        app_config.dependencies["task_service"] = provide_task_service
        app_config.on_startup = [*(app_config.on_startup or []), self._on_startup]
        app_config.on_shutdown = [*(app_config.on_shutdown or []), self._on_shutdown]
        return app_config
```

Set `start_worker=True` only for a dedicated worker process or replica. Keep web replicas from accidentally running the queue loop.

## `@task` Decorator + Registry

The decorator registers callables into `_job_registry` and scheduled definitions into `_schedule_registry`. Return a `Task` wrapper that stays callable for foreground tests and exposes `.enqueue()` for background execution.

```python
from app.worker.jobs import task


@task(cron="0 2 * * *", timeout=120)
async def nightly_cleanup() -> None:
    """Purge expired records every night at 02:00 UTC."""
    ...


@task(priority=5, retries=1, timeout=300)
async def generate_report(*, report_id: int) -> None:
    """Generate and store a report."""
    ...


@task(execution_target="cloudrun", profile="heavy", timeout=900, retries=3)
async def process_large_file(*, file_id: int) -> None:
    """Process a large file in an external worker target."""
    ...
```

Decorator contract:

```python
def task(
    name: str | None = None,
    *,
    priority: int = 0,
    timeout: int = 300,
    retries: int = 3,
    execution_target: ExecutionTarget | None = None,
    profile: str | None = None,
    cron: str | None = None,
    interval: int | None = None,
    timezone: str = "UTC",
    initial_delay: int = 0,
    jitter: int = 0,
    max_instances: int = 1,
    requeue: bool = True,
    on_stale_failure: Callable[[dict[str, object]], Awaitable[None]] | None = None,
) -> Callable[[Callable[..., Awaitable[object]]], Task]: ...
```

`Task.enqueue()` should resolve `explicit target > runtime override > decorator default > settings default`, then:

- Execute immediately for `"immediate"` without writing to the database.
- Insert the job row first for `"local"` and any external target.
- Dispatch through the selected backend for external targets.
- Store backend metadata such as `{"backend": "cloudrun", "execution_ref": "...", "profile": "heavy"}` after dispatch.
- Fall back to `"local"` only if that is an intentional policy for dispatch failure.

## Schedule Config

```python
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ScheduleConfig:
    function_name: str
    cron: str | None = None
    interval: int | None = None
    timezone: str = "UTC"
    initial_delay: int = 0
    jitter: int = 0
    max_instances: int = 1
    timeout: int | None = None

    def get_next_run(self, after: datetime | None = None) -> datetime:
        """Compute the next fire time after `after`."""
        ...
```

`WorkerPlugin` should sync schedules on startup. When a schedule definition changes, cancel the old pending scheduled row and create a fresh row with the same schedule key. `reschedule_job()` should clear the old terminal row key before inserting the successor row.

## Execution Target Routing

| Target | Behavior | Best for |
| --- | --- | --- |
| `"local"` | A long-running worker process claims and executes rows | Standard background work |
| `"immediate"` | The task runs in the caller coroutine without a database row | Tests, admin scripts, one-off maintenance |
| `"cloudrun"` | A backend dispatches a one-shot Cloud Run Job after the row exists | Long-running or isolated workloads |

External one-shot workers must preserve local-worker semantics:

- Read the job id from a generic environment variable such as `JOB_ID`.
- Claim the row with `TaskService.claim_task(job_id)`.
- Start a `WorkerSidecar` before executing the task.
- Register a claim-loss callback that cancels execution if heartbeats stop owning the row.
- Rebind realtime publishers or observers to the sidecar backend while the job runs.
- Complete or fail the row through `TaskService` using the claimed `retry_count`.
- Stop the sidecar in `finally`.

## Notification Channel

Use a neutral application channel name such as `app_tasks`. Notify after enqueue:

```python
async def _notify_worker(self, event: str, data: str) -> None:
    try:
        await self.driver.execute(
            "SELECT pg_notify(:channel, :payload)",
            channel="app_tasks",
            payload=f"{event}:{data}",
        )
    except Exception:
        await logger.adebug("Task notification failed", event=event)
```

The worker registers a sidecar listener and wakes its event loop:

```python
loop = asyncio.get_running_loop()
notification_event = asyncio.Event()


def notify_worker() -> None:
    loop.call_soon_threadsafe(notification_event.set)


sidecar.add_listener("app_tasks", notify_worker)
sidecar.start()
```

## Wiring Into Litestar

```python
from litestar import Litestar

from app.server.plugins import worker_plugin


app = Litestar(
    route_handlers=[...],
    plugins=[worker_plugin],
)
```

```python
from app.worker.plugin import WorkerPlugin
from app.settings import get_settings

settings = get_settings()

worker_plugin = WorkerPlugin(
    auto_discover=True,
    start_worker=settings.worker.in_process_worker,  # True only on worker replicas.
)
```

## Guardrails

- Keep SAQ queue guidance and sidecar worker guidance separate. Do not apply SAQ `ctx`, `QueueConfig`, `CronJob`, or `litestar workers run` guidance to this pattern.
- Keep `WorkerPlugin` thin. The sidecar and execution loop belong outside plugin initialization.
- Fence every running-state mutation by `retry_count`.
- Start the sidecar before running a job and stop it before clearing active heartbeats.
- Serialize operations on a single asyncpg sidecar connection with an `asyncio.Lock`.
- Reinstall LISTEN callbacks after sidecar reconnects.
- Keep the fallback poll even with NOTIFY; notifications are an optimization, not the only recovery path.
- Use generic environment names and module names in documentation. Do not leak private app identifiers into reusable guidance.

## Cross-references

- [`../SKILL.md`](../SKILL.md) — SAQ paths (Redis broker and PG broker)
- [`../../litestar-settings/references/settings.md`](../../litestar-settings/references/settings.md) — settings patterns
- [`../../sqlspec/references/service-patterns.md`](../../sqlspec/references/service-patterns.md) — `SQLSpecAsyncService` base class + canonical service patterns

## Shared Styleguide Baseline

- [General Principles](../../litestar-styleguide/references/general.md)
- [Python](../../litestar-styleguide/references/python.md)
