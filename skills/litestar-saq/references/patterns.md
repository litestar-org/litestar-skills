# SAQ Advanced Patterns

## Heartbeat Management

SAQ uses the job's touched timestamp to detect stuck work. When a job is active and the time since its last touch exceeds `heartbeat`, SAQ considers it stuck and may re-queue it. A `heartbeat` value of `0` disables this stale check.

`heartbeat` is the maximum silence before a job is stale, not the interval at which SAQ updates it. `Worker` starts a background `HeartbeatManager` (`enable_heartbeat_manager=True`, `heartbeat_flush_interval=30.0`s by default) and injects it as `ctx["heartbeat_manager"]`. Set `heartbeat` longer than both the decorator's signal interval and `HeartbeatManager`'s 30s flush cadence (at least `60`s; `120`s is a safe baseline).

Enqueueing a long-running job with an explicit 120s heartbeat stale threshold:

```python
await queue.enqueue(
    "process_large_file",
    file_id=42,
    timeout=700,
    heartbeat=120,
)
```

Use `monitored_job()` so the plugin registers the current job and periodically signals its batched `HeartbeatManager`. With no explicit decorator interval, v0.8.0 uses half the job's `heartbeat` threshold, floored at one second (`MIN_HEARTBEAT_INTERVAL = 1.0`); a disabled or unavailable threshold falls back to five seconds (`DEFAULT_HEARTBEAT_INTERVAL = 5.0`). Use manual updates only when task progress itself defines the correct touch points:

```python
async def process_large_file(ctx: dict, *, file_id: int) -> None:
    job = ctx["job"]

    async for chunk in read_chunks(file_id):
        await process_chunk(chunk)
        await job.update()
```

## @monitored_job Decorator Pattern

Use `litestar_saq.monitored_job` to auto-calculate and refresh heartbeat intervals for long-running tasks:

```python
from litestar_saq import monitored_job


@monitored_job()
async def long_running_export(ctx: dict, *, export_id: int) -> dict: ...
```

## Dead Letter / Failed Job Handling

```python
from saq import Job, Queue, Status


async def get_failed_jobs(queue: Queue) -> list[Job]:
    return [job async for job in queue.iter_jobs(statuses=[Status.FAILED])]


async def retry_job(queue: Queue, job_id: str) -> None:
    job = await queue.job(job_id)
    if job and job.status == Status.FAILED:
        await job.retry("manual retry")


async def retry_all_failed(queue: Queue) -> int:
    failed = [job async for job in queue.iter_jobs(statuses=[Status.FAILED])]
    for job in failed:
        await job.retry("manual retry")
    return len(failed)
```

### Native Retry and Exponential Backoff

```python
job = await queue.enqueue(
    "send_notification",
    user_id=user_id,
    timeout=30,
    retries=5,
    retry_delay=2.0,
    retry_backoff=60.0,
)
```

Let SAQ retry task exceptions. `retry_delay` sets the first delay. Set `retry_backoff=True` for exponential backoff with jitter, or use a number such as `60.0` to cap the calculated delay. Do not implement a second attempt counter inside task kwargs.

## Job Chaining and Multi-Step Orchestration

By default, SAQ populates `ctx["worker"]` and `ctx["job"]` (and `litestar-saq` injects `ctx["heartbeat_manager"]`); `ctx["queue"]` is not set unless a `startup` hook adds it. Access the active queue via `ctx["worker"].queue` or `ctx["job"].queue`:

```python
async def step_one(ctx: dict, *, record_id: int) -> None:
    queue = ctx["worker"].queue
    result = await process_step_one(record_id)
    await queue.enqueue(
        "step_two",
        record_id=record_id,
        step_one_result=result,
        timeout=120,
    )


async def step_two(ctx: dict, *, record_id: int, step_one_result: dict) -> None:
    queue = ctx["worker"].queue
    await process_step_two(record_id, step_one_result)
    await queue.enqueue("step_three", record_id=record_id, timeout=60)
```

### Multi-Step Orchestration, Superseding In-Flight Jobs, and Fan-Out Polling

When an orchestrator job coordinates sequential stages or a fan-out batch of child jobs, use `queue.job(key)` + `queue.abort()` to supersede stale runs, and poll `await child_job.refresh()` against `TERMINAL_STATUSES` (`{Status.COMPLETE, Status.FAILED, Status.ABORTED}`):

```python
import asyncio
from typing import Any, cast

from saq import Job, Queue
from saq.job import TERMINAL_STATUSES, Status
from saq.types import Context


async def orchestrate_pipeline(ctx: Context, *, data: dict[str, Any]) -> None:
    workspace_id = data["workspace_id"]
    report_id = data["report_id"]
    job_instance = ctx.get("job")
    if job_instance is None:
        msg = "Missing 'job' in SAQ context."
        raise RuntimeError(msg)

    queue = cast("Queue", job_instance.queue)

    stage_one_key = f"stage-workspace-{workspace_id}"
    existing = await queue.job(stage_one_key)
    if existing and existing.status not in TERMINAL_STATUSES:
        await queue.abort(existing, error="Superseded by a new pipeline request.")
        await asyncio.sleep(2)

    stage_one_job = await queue.enqueue(
        "stage_workspace_inputs",
        data={"workspace_id": workspace_id, "report_id": report_id},
        key=stage_one_key,
        timeout=3600,
        ttl=7200,
        retries=0,
    )
    if stage_one_job is None:
        msg = f"Failed to enqueue stage_workspace_inputs for {workspace_id}"
        raise RuntimeError(msg)

    while True:
        await stage_one_job.refresh()
        if stage_one_job.status in TERMINAL_STATUSES or stage_one_job.completed:
            break
        await asyncio.sleep(5)

    if stage_one_job.status != Status.COMPLETE:
        msg = f"Stage 1 failed with status: {stage_one_job.status}"
        raise RuntimeError(msg)

    pending_children: list[Job] = []
    for item_id in data.get("item_ids", []):
        child = await queue.enqueue(
            "process_workspace_item",
            data={"item_id": item_id, "workspace_id": workspace_id},
            timeout=1800,
        )
        if child is not None:
            pending_children.append(child)

    while pending_children:
        for active_job in pending_children.copy():
            await active_job.refresh()
            if active_job.status in TERMINAL_STATUSES or active_job.completed:
                pending_children.remove(active_job)
        if pending_children:
            await asyncio.sleep(5)
```

For lightweight in-band fan-out where every child can wait via `apply()`:

```python
import asyncio
from saq import Queue


async def fan_out_coordinator(ctx: dict, *, batch_ids: list[int]) -> None:
    queue: Queue = ctx["worker"].queue
    await asyncio.gather(*[queue.apply("process_item", item_id=item_id, timeout=60) for item_id in batch_ids])
```

## Abandoned Job Reaper (`CronJob` + `UNSUCCESSFUL_TERMINAL_STATUSES`)

When application database rows mirror background execution state (such as `ReportStatus.EXECUTING`), a worker crash or job abort can leave domain records stuck in an executing state. Schedule a periodic `CronJob` that opens a standalone service session (`Service.new(config=config.alchemy)`) and reconciles domain rows against `UNSUCCESSFUL_TERMINAL_STATUSES` (`{Status.FAILED, Status.ABORTED}`):

```python
from typing import cast

from saq import Queue
from saq.job import UNSUCCESSFUL_TERMINAL_STATUSES
from saq.types import Context

from app import config
from app.db import models as m
from app.domain.reports.services import ReportService


async def reap_abandoned_reports(ctx: Context) -> None:
    job_instance = ctx.get("job")
    if job_instance is None:
        return

    queue = cast("Queue", job_instance.queue)
    async with ReportService.new(config=config.alchemy) as reports_service:
        running_reports = await reports_service.get_many(
            status=m.ReportStatus.EXECUTING.value,
        )
        for report in running_reports:
            job = await queue.job(f"workspace-report-{report.id}")
            if job is None or job.status in UNSUCCESSFUL_TERMINAL_STATUSES:
                report.status = m.ReportStatus.ERROR
        await reports_service.update_many(data=list(running_reports), auto_commit=True)
```

## Multiple Queues and Priorities

```python
from saq import Queue

high = Queue.from_url("redis://localhost", name="high")
low = Queue.from_url("redis://localhost", name="low")
```

In a Litestar app with `litestar-saq`:

```python
from litestar_saq import QueueConfig, SAQConfig

SAQConfig(
    queue_configs=[
        QueueConfig(name="high", dsn=settings.redis.url, tasks=[...]),
        QueueConfig(name="low", dsn=settings.redis.url, tasks=[...]),
    ],
)
```

With the PostgreSQL backend, a single queue also supports native `priority` ordering (lower integer values dequeue first within `PostgresQueueOptions.priorities`, default `(0, 32767)`) and per-group concurrency serialization via `group_key` (at most one active job per `group_key` at a time):

```python
await queue.enqueue(
    "sync_tenant",
    tenant_id=tenant_id,
    priority=10,
    group_key=f"tenant:{tenant_id}",
    timeout=300,
)
```

## Worker Lifecycle Hooks, Timers, and Shutdown

### Built-in Hooks

`litestar-saq` exports ready-to-use logging and timing hooks from both `litestar_saq` and `litestar_saq.hooks`:

```python
from litestar_saq import (
    QueueConfig,
    after_process_logger,
    before_process_logger,
    shutdown_logger,
    startup_logger,
    timing_after_process,
    timing_before_process,
)

queue_config = QueueConfig(
    dsn="redis://localhost:6379/0",
    startup=[startup_logger],
    shutdown=[shutdown_logger],
    before_process=[timing_before_process, before_process_logger],
    after_process=[timing_after_process, after_process_logger],
)
```

### Composing Built-in Hooks with Custom Application Hooks

Compose `litestar_saq.hooks` with custom hooks in `app/lib/worker.py` to initialize logging in spawned worker processes, clear `structlog.contextvars` between jobs, log failed/aborted jobs at `ERROR`/`WARNING` (built-in `after_process_logger` logs at `DEBUG`), and clean up per-job scratch directories stored in `ctx["working_path"]`:

```python
import functools
import shutil
from pathlib import Path

import structlog
from anyio import to_thread
from saq import Job, Status
from saq.types import Context

from app.lib.settings import get_settings

logger = structlog.get_logger()


async def on_startup(ctx: Context) -> None:
    settings = get_settings()
    settings.log.configure_logging()


async def on_shutdown(ctx: Context) -> None:
    return None


async def before_process(ctx: Context) -> None:
    structlog.contextvars.clear_contextvars()


async def after_process(ctx: Context) -> None:
    job: Job | None = ctx.get("job")
    if job is not None:
        if job.status == Status.FAILED:
            await logger.aerror("Job failed", job_name=job.function, job_id=job.id, error=job.error)
        elif job.status == Status.ABORTED:
            await logger.awarning("Job aborted", job_name=job.function, job_id=job.id)

    structlog.contextvars.clear_contextvars()

    working_path: Path | None = ctx.get("working_path")
    if working_path is not None and not ctx.get("preserve_working_path", False):
        await to_thread.run_sync(functools.partial(shutil.rmtree, working_path, ignore_errors=True))
```

With `litestar-saq`, the plugin manages startup/shutdown via the Litestar app lifespan; per-job hooks are still available via `QueueConfig.before_process` / `after_process`. When referencing hooks by dotted import path, always wrap them in a list (`startup=["app.domain.system.tasks.startup"]`); passing a bare `str` fails because `str` is a `Collection` and gets iterated character-by-character.

### Timers, Shutdown, and Burst Mode

`QueueConfig` forwards worker scheduling, upkeep, and shutdown controls to `saq.Worker`:

- `timers`: `PartialTimersDict` with keys `"schedule"` (default `1`s), `"worker_info"` (default `10`s), `"sweep"` (default `60`s), and `"abort"` (default `1`s).
- `shutdown_grace_period_s`: seconds to let active jobs finish before cancelling on shutdown.
- `cancellation_hard_deadline_s`: seconds to wait for cancelled tasks before forced termination (SAQ default `1.0`s).
- `poll_interval`: when `> 0.0` on PostgreSQL, dequeue uses polling instead of `LISTEN/NOTIFY` (default `0.0`).
- `burst=True`: stops the worker once the queue drains (or `max_burst_jobs` is reached); requires `dequeue_timeout > 0`.

### OpenTelemetry and Structlog Integration

- **OpenTelemetry (`litestar-saq[otel]`)**: Set `SAQConfig(enable_otel=True, otel_tracer_name="litestar_saq")` to create `CONSUMER` spans around job processing. To create `PRODUCER` spans on `enqueue()` / `apply()` and propagate W3C trace context (`job.meta["_otel_context"]`), wrap the queue with `InstrumentedQueue` from `litestar_saq.instrumentation` or call `inject_trace_context(job)` in a `queue.register_before_enqueue` hook.
- **Structlog and `LoggingConfig`**: When `structlog` is installed, `Worker` automatically binds `worker_id`, `queue_name`, `concurrency`, `separate_process`, and any `QueueConfig.metadata` keys (prefixed as `worker_meta_<key>`) into `structlog.contextvars`. Route `litestar_saq` and `saq` loggers through Litestar's `queue_listener` handler in `LoggingConfig`:

```python
loggers = {
    "litestar_saq.decorators": {"propagate": False, "level": "INFO", "handlers": ["queue_listener"]},
    "litestar_saq.hooks": {"propagate": False, "level": "INFO", "handlers": ["queue_listener"]},
    "saq": {"propagate": False, "level": "WARNING", "handlers": ["queue_listener"]},
}
```

## Postgres and Redis Backend Options

### Postgres Backend (`PostgresQueueOptions`)

Use Postgres when:

- Durable persistence is required
- SQL-queryable job history is desired
- No Redis is in infra
- SQL-backed queue storage is preferred

```python
from litestar_saq import QueueConfig

queue_config = QueueConfig(
    name="default",
    dsn="postgresql://user:pass@localhost/mydb",
    broker_options={
        "jobs_table": "saq_jobs",
        "stats_table": "saq_stats",
        "versions_table": "saq_versions",
        "manage_pool_lifecycle": True,
        "min_size": 2,
        "max_size": 10,
        "saq_lock_keyspace": 1,
        "priorities": (0, 32767),
        "swept_error_message": "swept",
    },
    broker_instance_options={
        "max_idle": 300.0,
    },
)
```

Note:

- `QueueConfig.dsn` for PostgreSQL must begin with `postgresql://` (`postgres://` raises `ImproperlyConfiguredException`). When deriving `dsn` from an SQLAlchemy URL (`postgresql+psycopg://` or `postgresql+asyncpg://`), strip the `+driver` suffix first.
- On `saq>=0.24`, `saq.queue.postgres.PostgresQueue.__init__` accepts `jobs_table`, `stats_table`, and `versions_table` (not the legacy `table`, `stats`, and `versions` keys still listed on `litestar_saq.PostgresQueueOptions`).
- `QueueConfig` automatically defaults `manage_pool_lifecycle=True` on PostgreSQL queues and ensures `autocommit=True` on the `psycopg_pool.AsyncConnectionPool`.

### Redis Backend (`RedisQueueOptions`)

```python
from litestar_saq import QueueConfig, RedisQueueOptions

queue_config = QueueConfig(
    name="default",
    dsn="redis://localhost:6379/0",
    broker_options=RedisQueueOptions(
        max_concurrent_ops=20,
        swept_error_message="swept",
    ),
    broker_instance_options={
        "socket_connect_timeout": 5,
    },
)
```

Multi-process workers must be able to rebuild brokers in child processes. Configure a `dsn` for portable forkserver/spawn workers. Do not pass both `dsn` and `broker_instance`: `QueueConfig` rejects that construction. A `broker_instance`-only queue is limited to a parent worker or a platform using `fork`.

| Aspect | Redis | Postgres |
| --- | --- | --- |
| Persistence | In-memory (AOF/RDB optional) | Durable by default |
| Job history | Limited | Full SQL access |
| Throughput | Higher | Lower (row locking) |
| Infra | Redis | Existing Postgres |

The PostgreSQL broker persists jobs in PostgreSQL, but `queue.enqueue()` uses the broker's own pool and transaction. It does not share an application ORM session or atomically commit business data and the job. Use a project-owned outbox when those writes must commit together.

## Job Deduplication

Per-user sync deduplication:

```python
await queue.enqueue(
    "sync_user_data",
    user_id=user_id,
    key=f"sync-user-{user_id}",
    timeout=300,
)
```

Per-resource version deduplication:

```python
await queue.enqueue(
    "reindex_document",
    doc_id=doc_id,
    key=f"reindex-doc-{doc_id}",
    timeout=60,
)
```

Time-windowed deduplication (e.g. one report per hour):

```python
from datetime import datetime, timezone

hour = datetime.now(timezone.utc).strftime("%Y%m%d%H")
await queue.enqueue(
    "generate_hourly_report",
    org_id=org_id,
    key=f"report-{org_id}-{hour}",
    timeout=120,
)
```
