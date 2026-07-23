# SAQ Advanced Patterns

> **See also:** [Sidecar Worker Pattern](postgres-native-sidecar-worker.md) — `TaskService + Worker + WorkerSidecar + WorkerPlugin` pattern for a project-owned transactional outbox and job schema, frontend channel updates, and execution-target routing.

## Heartbeat Management

SAQ uses the job's touched timestamp to detect stuck work. When a job is active and the time since its last touch exceeds `heartbeat`, SAQ considers it stuck and may re-queue it. A `heartbeat` value of `0` disables this stale check.

`heartbeat` is the maximum silence before a job is stale, not the interval at which SAQ updates it. Set it longer than both the decorator's signal interval and the `HeartbeatManager` flush cadence.

```python
# A job expected to run ~10 minutes
await queue.enqueue(
    "process_large_file",
    file_id=42,
    timeout=700,      # 700s hard timeout
    heartbeat=120,    # stale after 120 seconds without a touch
)
```

Use `monitored_job()` so the plugin registers the current job and periodically signals its batched `HeartbeatManager`. With no explicit decorator interval, v0.8.0 uses half the job's `heartbeat` threshold, floored at one second; a disabled or unavailable threshold falls back to five seconds. Use manual updates only when task progress itself defines the correct touch points:

```python
async def process_large_file(ctx: dict, *, file_id: int) -> None:
    job = ctx["job"]

    for chunk in read_chunks(file_id):
        await process_chunk(chunk)
        # Manually touch the job heartbeat after each chunk
        await job.update()
```

## @monitored_job Decorator Pattern

Use `litestar_saq.monitored_job` to auto-calculate and refresh heartbeat intervals for long-running tasks:

```python
from litestar_saq import monitored_job


@monitored_job()
async def long_running_export(ctx: dict, *, export_id: int) -> dict:
    ...
```

## Dead Letter / Failed Job Handling

```python
from saq import Job, Status

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

## Job Chaining

```python
async def step_one(ctx: dict, *, record_id: int) -> None:
    result = await process_step_one(record_id)
    await ctx["queue"].enqueue(
        "step_two", record_id=record_id, step_one_result=result, timeout=120,
    )

async def step_two(ctx: dict, *, record_id: int, step_one_result: dict) -> None:
    await process_step_two(record_id, step_one_result)
    await ctx["queue"].enqueue("step_three", record_id=record_id, timeout=60)
```

Fan-out:

```python
async def fan_out_coordinator(ctx: dict, *, batch_ids: list[int]) -> None:
    queue: Queue = ctx["queue"]
    results = await asyncio.gather(*[
        queue.apply("process_item", item_id=item_id)
        for item_id in batch_ids
    ])
```

## Queue Priorities (Multiple Queues)

```python
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

## Worker Lifecycle Hooks

```python
async def startup(ctx: dict) -> None:
    ctx["db"] = create_async_engine(...)
    ctx["http"] = httpx.AsyncClient(timeout=10.0)

async def shutdown(ctx: dict) -> None:
    await ctx["db"].dispose()
    await ctx["http"].aclose()

async def before_process(ctx: dict) -> None:
    ctx["session"] = ctx["db"].connect()

async def after_process(ctx: dict) -> None:
    if "session" in ctx:
        await ctx["session"].close()
        del ctx["session"]
```

With `litestar-saq`, the plugin manages startup/shutdown via the Litestar app lifespan; per-job hooks are still available via `QueueConfig.before_process` / `after_process`.

## Postgres Backend

Use Postgres when:

- Durable persistence required
- Want SQL-queryable job history
- No Redis in infra
- Need SQL-backed queue storage

```python
queue = Queue.from_url("postgresql://user:pass@localhost/mydb")
```

In `litestar-saq`, put the PostgreSQL DSN on `QueueConfig` and install the `psycopg` extra:

```python
from litestar_saq import QueueConfig

QueueConfig(
    name="default",
    dsn="postgresql://user:pass@localhost/mydb",
    broker_options={
        "jobs_table": "saq_jobs",
        "stats_table": "saq_stats",
        "manage_pool_lifecycle": True,
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

```python
# Per-user sync
await queue.enqueue(
    "sync_user_data", user_id=user_id,
    key=f"sync-user-{user_id}", timeout=300,
)

# Per-resource version
await queue.enqueue(
    "reindex_document", doc_id=doc_id,
    key=f"reindex-doc-{doc_id}", timeout=60,
)

# Time-windowed (one report per hour)
import datetime
hour = datetime.datetime.utcnow().strftime("%Y%m%d%H")
await queue.enqueue(
    "generate_hourly_report", org_id=org_id,
    key=f"report-{org_id}-{hour}", timeout=120,
)
```
