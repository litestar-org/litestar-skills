# PostgreSQL-native worker queue (no SAQ)

Some projects reject SAQ entirely and implement a thin `TaskService + WorkerPlugin` pair directly over PostgreSQL. If your project uses SAQ (Redis or PG broker), see [`../SKILL.md`](../SKILL.md) for those paths. This reference documents the **zero-extra-deps alternative**: one `job` table, `FOR UPDATE SKIP LOCKED` for atomic claiming, `pg_notify` for wake-ups, and a `@task` decorator that registers callables with optional cron schedules and execution-target routing.

<!-- NOTE: do NOT use `from __future__ import annotations` in modules that define
@task-decorated functions — the decorator inspects signatures at registration time. -->

## When this fits

| Factor | SAQ (Redis or PG) wins | Custom PG-native wins |
| --- | --- | --- |
| Dashboards / job introspection | ✓ (`web_enabled=True`) | — (would need to build) |
| `pg_notify` wake-ups (no polling lag) | — | ✓ |
| `FOR UPDATE SKIP LOCKED` atomic claim | — | ✓ |
| Multi-target execution routing | — | ✓ (local / cloudrun / immediate) |
| Dead-letter + retry dashboards | ✓ | — (log-only) |
| Zero extra deps beyond Postgres | — (SAQ + broker) | ✓ |
| Existing community patterns | ✓ | — (project-owned) |
| Cron scheduling with registry | ✓ (`CronJob`) | ✓ (`@task(cron=...)` + schedule registry) |
| Built-in ≥1k jobs/s per queue | ✓ | Moderate (PG row contention) |

**Bottom line:** if you need dashboards or you're already on Redis, stay with SAQ. If the app is PG-only AND you want `pg_notify` + `SKIP LOCKED` + multi-target execution, this is the canonical alternative.

## Schema

The pattern uses a single `job` table:

```sql
CREATE TABLE job (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key             TEXT UNIQUE,                 -- deduplication key; NULL on terminal jobs
    function        TEXT NOT NULL,               -- dotted name, e.g. "app.jobs.tasks.send_report"
    data            JSONB,                       -- keyword arguments
    status          TEXT NOT NULL DEFAULT 'pending',
    priority        INT  NOT NULL DEFAULT 0,
    retry_count     INT  NOT NULL DEFAULT 0,
    max_retries     INT  NOT NULL DEFAULT 3,
    execution_target TEXT NOT NULL DEFAULT 'local',
    scheduled_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    heartbeat_at    TIMESTAMPTZ,
    error           TEXT,
    result          JSONB,
    metadata        JSONB
);
```

## Status + execution target literals

```python
from typing import Literal

JobStatus = Literal["pending", "running", "completed", "failed", "cancelled", "scheduled"]
ExecutionTarget = Literal["local", "cloudrun", "immediate"]
```

## `TaskService` — core CRUD

The service inherits from `SQLSpecAsyncService` (see [`../../sqlspec/references/service-patterns.md`](../../sqlspec/references/service-patterns.md)).

### `create_task`

Persists a new task and returns its UUID. Accepts a `key` for deduplication (skips insert if the key is already in a non-terminal state).

```python
async def create_task(
    self,
    function: str,
    data: dict | None = None,
    *,
    key: str | None = None,
    priority: int = 0,
    scheduled_at: "datetime | None" = None,
    max_retries: int = 3,
    execution_target: ExecutionTarget = "local",
) -> "UUID":
    """Persist a task and return its UUID7 task id."""
    ...
```

### `get_pending_tasks`

Fetches up to `limit` tasks ready for execution. Does **not** lock rows here — locking happens in `claim_task`. Raw SQL: `SELECT ... FROM job WHERE status IN ('pending','scheduled') AND execution_target = :execution_target AND (scheduled_at IS NULL OR scheduled_at <= :now) ORDER BY priority DESC, created_at ASC LIMIT :limit`.

### `claim_task`

Atomically transitions `pending|scheduled → running` using `FOR UPDATE SKIP LOCKED` inside a transaction. Returns `False` on a race loss (another worker already claimed the task).

```python
async def claim_task(self, task_id: "UUID") -> bool:
    """Claim a task for execution; returns False if already taken."""
    # SELECT id FROM job WHERE id = :task_id AND status IN ('pending','scheduled')
    # FOR UPDATE SKIP LOCKED
    # → UPDATE job SET status='running', started_at=NOW(), heartbeat_at=NOW()
    ...
```

### `complete_task`

```python
async def complete_task(self, task_id: "UUID", result: dict | None = None) -> None:
    """Mark a task completed and store its result."""
    # UPDATE job SET status='completed', completed_at=NOW(), result=:result
    ...
```

### `fail_task`

Uses a CTE-based update: if `retry_count < max_retries` and `retry=True`, resets to `pending` with `retry_count += 1` and `started_at = NULL`; otherwise marks `failed` with `completed_at = NOW()`.

```python
async def fail_task(
    self,
    task_id: "UUID",
    error: str,
    retry: bool = True,
) -> None:
    """Fail a task; re-queue for retry if under the retry cap."""
    # WITH updated AS (
    #   UPDATE job SET ... WHERE id = :task_id RETURNING retry_count, max_retries
    # )
    # UPDATE job SET status = CASE WHEN retry_count < max_retries AND :retry
    #   THEN 'pending' ELSE 'failed' END, ...
    ...
```

### `reschedule_job`

Used by the scheduler loop. Calls `ScheduleConfig.get_next_run(after=completed_at)` to compute the next fire time, nulls the `key` on the old terminal job (so the key can be reclaimed), then creates the successor task.

## `pg_notify` integration

`_notify_worker` fires a Postgres NOTIFY after each `create_task` call so the in-process worker wakes immediately instead of polling. Pick a channel name for your app (e.g., `"tasks"` or `"{app_name}_tasks"`). Payload format: `"{event}:{task_id}"`.

```python
async def _notify_worker(self, event: str, data: str) -> None:
    """Fire pg_notify so the worker wakes without polling delay."""
    await self._session.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {"channel": "tasks", "payload": f"{event}:{data}"},
    )
```

## `WorkerPlugin` (Litestar integration)

`WorkerPlugin` implements `InitPluginProtocol`.

```python
from litestar.plugins import InitPluginProtocol
from litestar.config.app import AppConfig


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
        # Injects task_service into app_config.dependencies
        # Appends _on_startup and _on_shutdown to lifespan hooks
        ...

    async def _on_startup(self, app: "Litestar") -> None:
        if self.auto_discover:
            load_jobs(self.domain_packages, self.job_submodules)
        if self.start_worker:
            await self._initialize_schedules()
            self._start_worker()

    async def _on_shutdown(self, app: "Litestar") -> None:
        if self._worker_task:
            self._worker_task.cancel()

    def _start_worker(self) -> None:
        import asyncio
        self._worker_task = asyncio.create_task(
            Worker(register_signals=False).start()
        )
```

## `@task` decorator + registry

The `@task` decorator registers async callables into `_job_registry` and, when `cron` or `interval` is specified, into `_schedule_registry`. Wraps the callable in a `Task` object that exposes `.enqueue()`.

```python
# app/jobs/tasks.py
# NOTE: no `from __future__ import annotations` — @task inspects signatures at import time.
from app.lib.worker.jobs import task


@task(cron="0 2 * * *", timeout=120)
async def nightly_cleanup() -> None:
    """Purge soft-deleted records every night at 02:00 UTC."""
    ...


@task(priority=5, retries=1, timeout=300)
async def generate_report(*, report_id: int) -> None:
    """Generate and store a report."""
    ...


@task(execution_target="cloudrun", timeout=600, retries=3)
async def process_uploaded_file(*, file_id: int) -> None:
    """Process a large uploaded file on Cloud Run for isolation."""
    ...
```

Decorator signature:

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
) -> "Callable[..., Task]": ...
```

## Schedule config

`ScheduleConfig` is a dataclass that drives cron and interval-based scheduling:

```python
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ScheduleConfig:
    function_name: str
    cron: str | None = None
    interval: int | None = None       # seconds between runs
    timezone: str = "UTC"
    initial_delay: int = 0
    jitter: int = 0
    max_instances: int = 1
    timeout: int | None = None

    def get_next_run(self, after: datetime | None = None) -> datetime:
        """Compute the next fire time after `after` (defaults to now)."""
        ...
```

`reschedule_job` uses `ScheduleConfig.get_next_run(after=completed_at)` to chain scheduled runs.

## Execution target routing

Three modes:

| Target | Behavior | Best for |
| --- | --- | --- |
| `"local"` | In-process worker picks up via `claim_task` | Standard background work |
| `"immediate"` | Executes synchronously in the calling coroutine | Tests, admin scripts |
| `"cloudrun"` | Dispatches to GCP Cloud Run Jobs via `CloudRunJobDispatcher` | Long-running or isolated workloads |

`Task.enqueue()` resolves `explicit arg > decorator default > "local"`:

```python
# Enqueue imperatively from a handler or service:
await generate_report.enqueue(report_id=42)                          # uses decorator default
await process_uploaded_file.enqueue(execution_target="cloudrun", file_id=99)
```

`CloudRunJobDispatcher.dispatch` stores the job in Postgres (always) then triggers a Cloud Run Job with env vars `JOB_ID`, `FUNCTION`, `KWARGS`, `DATABASE_URL`:

```python
def dispatch(
    self,
    job_id: "UUID",
    function: str,
    kwargs: dict,
    *,
    job_timeout: int = 300,
) -> str:
    """Submit a Cloud Run Job execution and return the operation name."""
    ...
```

## Wiring into Litestar

The `start_worker=False` default prevents web replicas from accidentally running the worker loop — flip to `True` only on dedicated worker replicas:

```python
from app.lib.worker import WorkerPlugin

from app.lib.settings import get_settings

settings = get_settings()

worker_plugin = WorkerPlugin(
    auto_discover=False,
    start_worker=settings.task.INPROCESS_WORKER,  # True only on worker replicas
)
```

```python
from litestar import Litestar
from app.server.plugins import worker_plugin

app = Litestar(
    route_handlers=[...],
    plugins=[worker_plugin],
)
```

## Decision guide — when to choose this over SAQ

- **Zero extra runtime deps** — only Postgres required; no Redis, no SAQ package.
- **`pg_notify` wake-ups** — worker wakes the instant a task is inserted; SAQ polls at a configurable interval.
- **`FOR UPDATE SKIP LOCKED`** — atomic, race-free task claiming from multiple worker processes.
- **Multi-target execution routing** — route tasks to in-process workers, Cloud Run Jobs, or synchronous execution from a single `@task` definition.
- **Project-owned code** — full control over retry logic, CTE updates, and heartbeat strategy; no upstream SAQ releases to track.
- **No built-in dashboard** — if you need a web UI for job introspection and dead-letter management, SAQ's `web_enabled=True` is the easier path.

If you need dashboards or you're already on Redis, stay with SAQ. If the app is PG-only AND you want `pg_notify` + `SKIP LOCKED` + multi-target execution, this is the canonical alternative.

## Cross-references

- [`../SKILL.md`](../SKILL.md) — SAQ paths (Redis broker and PG broker)
- [`../../litestar-settings/references/settings.md`](../../litestar-settings/references/settings.md) — settings patterns (including PEP 562 lazy materialization)
- [`../../sqlspec/references/service-patterns.md`](../../sqlspec/references/service-patterns.md) — `SQLSpecAsyncService` base class + canonical service patterns

## Shared Styleguide Baseline

- [General Principles](../../litestar-styleguide/references/general.md)
- [Python](../../litestar-styleguide/references/python.md)
