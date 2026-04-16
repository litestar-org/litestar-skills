# SAQ Advanced Patterns

> **See also:** [PostgreSQL-Native Queue (no SAQ)](postgresql-native.md) — `TaskService + WorkerPlugin` pattern with `FOR UPDATE SKIP LOCKED`, `pg_notify`, and execution-target routing when SAQ is not wanted.

## Heartbeat Management

SAQ uses heartbeats to detect stuck jobs. When a job is `active`, the worker periodically updates a heartbeat timestamp. If the timestamp goes stale (beyond the `heartbeat` interval), SAQ considers the job stuck and may re-queue it.

**Rule of thumb:** set `heartbeat` to ~1/3 of expected job duration.

```python
# A job expected to run ~10 minutes
await queue.enqueue(
    "process_large_file",
    file_id=42,
    timeout=700,      # 700s hard timeout
    heartbeat=200,    # update heartbeat every ~3 minutes
)
```

For tasks where duration is variable, manually trigger heartbeat updates from within the task:

```python
async def process_large_file(ctx: dict, *, file_id: int) -> None:
    job = ctx["job"]
    queue: Queue = ctx["queue"]

    for chunk in read_chunks(file_id):
        await process_chunk(chunk)
        # Manually extend the heartbeat after each chunk
        await queue.update(job, heartbeat=time.time())
```

## @monitored_job Decorator Pattern

A reusable decorator that auto-calculates and refreshes heartbeat intervals for long-running tasks:

```python
import asyncio
import functools
import time
from collections.abc import Callable
from typing import Any

from saq import Queue


def monitored_job(heartbeat_fraction: float = 0.3) -> Callable:
    """Decorator that auto-manages heartbeat for long-running SAQ tasks."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(ctx: dict, **kwargs: Any) -> Any:
            job = ctx["job"]
            queue: Queue = ctx["queue"]
            timeout = job.timeout or 300
            interval = max(10, int(timeout * heartbeat_fraction))

            async def _heartbeat_loop() -> None:
                while True:
                    await asyncio.sleep(interval)
                    await queue.update(job, heartbeat=time.time())

            task = asyncio.create_task(_heartbeat_loop())
            try:
                return await func(ctx, **kwargs)
            finally:
                task.cancel()

        return wrapper
    return decorator


@monitored_job(heartbeat_fraction=0.25)
async def long_running_export(ctx: dict, *, export_id: int) -> dict:
    ...
```

## Dead Letter / Failed Job Handling

```python
from saq import Job, Status

async def get_failed_jobs(queue: Queue) -> list[Job]:
    return await queue.jobs(status=Status.FAILED)

async def retry_job(queue: Queue, job_id: str) -> None:
    job = await queue.job(job_id)
    if job and job.status == Status.FAILED:
        await queue.retry(job)

async def retry_all_failed(queue: Queue) -> int:
    failed = await queue.jobs(status=Status.FAILED)
    for job in failed:
        await queue.retry(job)
    return len(failed)
```

### Exponential Backoff via `scheduled`

```python
import time

async def send_notification(ctx: dict, *, user_id: int, attempt: int = 0) -> None:
    try:
        await _send(user_id)
    except TransientError:
        max_attempts = 5
        if attempt < max_attempts:
            backoff = 2 ** attempt  # 1, 2, 4, 8, 16 seconds
            await ctx["queue"].enqueue(
                "send_notification",
                user_id=user_id,
                attempt=attempt + 1,
                scheduled=int(time.time()) + backoff,
                timeout=30,
            )
```

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
        queue.apply("process_item", item_id=item_id, timeout=60)
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
SAQConfig(
    dsn=...,
    queue_configs=[
        QueueConfig(name="high", tasks=[...]),
        QueueConfig(name="low",  tasks=[...]),
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
- Need transactional enqueue (enqueue inside a DB transaction)

```python
queue = Queue.from_url("postgresql+asyncpg://user:pass@localhost/mydb")
```

| Aspect | Redis | Postgres |
|---|---|---|
| Persistence | In-memory (AOF/RDB optional) | Durable by default |
| Job history | Limited | Full SQL access |
| Throughput | Higher | Lower (row locking) |
| Infra | Redis | Existing Postgres |
| Transactional enqueue | No | Yes |

```python
async def create_order_and_enqueue(session: AsyncSession, order_data: dict) -> None:
    async with session.begin():
        order = Order(**order_data)
        session.add(order)
        await session.flush()
        await queue.enqueue("process_order", order_id=order.id, timeout=120)
```

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
