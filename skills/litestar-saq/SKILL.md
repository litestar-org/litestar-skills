---
name: litestar-saq
description: "Auto-activate for litestar_saq, SAQPlugin, SAQConfig, QueueConfig, TaskQueues, CronJob, litestar workers run, background jobs, schedules, or SAQ web UI. Not for Celery/RQ/Dramatiq."
---

# litestar-saq

`litestar-saq` is the first-party plugin that integrates [SAQ (Simple Async Queue)](https://github.com/tobymao/saq) with Litestar. It provides:

- `SAQPlugin` — registers queues, workers, lifespan management, and DI for `TaskQueues`
- `SAQConfig` / `QueueConfig` — declarative plugin, queue, worker, broker, shutdown, polling, and OpenTelemetry configuration
- `litestar workers run` — CLI to start worker processes, optionally filtered by queue
- Optional web UI mounted under the Litestar app
- DI injection of `TaskQueues` into route handlers for ergonomic enqueueing

## Code Style Rules

- Use PEP 604 unions: `T | None`, never `Optional[T]`
- Consumer Litestar app modules MAY use `from __future__ import annotations` — canonical Litestar apps do.
- Async all I/O — task bodies and enqueue calls are `async def`.
- First positional arg of every task is `ctx: dict` (the SAQ context dict).
- Task params after `*` are keyword-only.
- Use `NamedDependency[TaskQueues]` for handler injection. `TaskQueues` is registered under the `task_queues` dependency key, and Litestar 2.24 deprecates implicit DI.

## Quick Reference

### Plugin Setup (canonical pattern)

The canonical pattern from [litestar-fullstack](https://github.com/litestar-org/litestar-fullstack) (`src/py/app/server/plugins.py`) uses lazy initialization and `use_server_lifespan=True` so worker child processes start and stop with the Litestar server lifespan:

```python
# Branch A — SAQ with Redis as the broker (pick when Redis is already in-stack
# for cache / sessions, or when you want the SAQ web UI + multi-queue fanout).
from litestar_saq import SAQConfig, SAQPlugin, QueueConfig, CronJob

from app.lib.settings import get_settings


def create_saq_plugin() -> SAQPlugin:
    settings = get_settings()
    return SAQPlugin(
        config=SAQConfig(
            use_server_lifespan=True,            # worker child processes follow server lifespan
            web_enabled=settings.saq.web_enabled,
            enable_otel=None,                    # auto-detect if OpenTelemetry is installed and configured
            queue_configs=[
                QueueConfig(
                    name="default",
                    dsn=settings.redis.url,      # redis://... — Redis broker
                    tasks=["app.domain.system.tasks.send_email"],
                    scheduled_tasks=[
                        CronJob(
                            function="app.domain.system.tasks.cleanup_sessions",
                            cron="*/15 * * * *",
                            timeout=120,
                        ),
                    ],
                ),
            ],
        ),
    )


saq_plugin = create_saq_plugin()
```

```python
# Branch B — SAQ with PostgreSQL as the broker (install `litestar-saq[psycopg]`;
# pick when the project is
# PG-only, you want one less piece of infra, or throughput is moderate).
def create_saq_plugin_pg() -> SAQPlugin:
    settings = get_settings()
    return SAQPlugin(
        config=SAQConfig(
            use_server_lifespan=True,
            web_enabled=settings.saq.web_enabled,
            queue_configs=[
                QueueConfig(
                    name="default",
                    dsn=settings.database.url,   # postgresql://... — PG broker
                    tasks=["app.domain.system.tasks.send_email"],
                ),
            ],
        ),
    )
```

**Pick Branch A (SAQ + Redis) when:** Redis is already in-stack (cache, sessions, Channels), you need multi-queue fanout across many workers, want the SAQ web UI and dead-letter dashboards, or have high throughput (>1k jobs/s per queue).

**Pick Branch B (SAQ + PostgreSQL) when:** PG-only deployment (Cloud SQL, AlloyDB, self-hosted single DB), avoiding Redis, durable SQL-backed SAQ storage, SQL-queryable job history, or moderate throughput (<1k jobs/s).

**Pick Branch C (sidecar worker) when:** you need same-transaction outbox semantics with business data, a project-owned job schema, frontend progress updates through channels, or multi-target execution routing (`local` / `cloudrun` / `immediate`) — and you're willing to own the `TaskService + Worker + WorkerSidecar + WorkerPlugin` stack. See below.

**Anti-pattern:** hard-coding `dsn=settings.redis.url` in a PG-only project just because Redis is the "default" example. Match the broker to the stack.

`QueueConfig` accepts `redis://...`, `postgresql://...`, or `http://...` / `https://...` DSNs, or a supported `broker_instance`. Redis can use `litestar-saq[hiredis]`; PostgreSQL requires `litestar-saq[psycopg]`. Configure backend-specific knobs with `broker_options` and connection/client knobs with `broker_instance_options`.

### Branch C — Sidecar Worker Pattern

Some projects need a project-owned PostgreSQL worker stack. This wins when you want same-transaction outbox semantics, a project-owned job table, frontend progress updates through channels, and multi-target execution routing (`local` / `cloudrun` / `immediate`).

In this pattern, `TaskService` owns the SQL state transitions, `Worker` owns claim/execution/retry flow, `WorkerSidecar` owns LISTEN/NOTIFY plus batched heartbeat/progress/channel publishing on a dedicated asyncpg connection, and `WorkerPlugin` only wires task discovery, schedule sync, DI, and optional in-process startup into Litestar.

See [references/postgres-native-sidecar-worker.md](references/postgres-native-sidecar-worker.md) for the full pattern.

```python
# NOTE: do NOT use `from __future__ import annotations` in modules that define
# @task-decorated functions — the decorator inspects signatures at registration time.

from app.lib.worker.jobs import task


@task(cron="0 2 * * *", timeout=120)
async def nightly_cleanup() -> None:
    """Purge soft-deleted records every night at 02:00 UTC."""
    ...


@task(priority=5, retries=1, timeout=300, execution_target="cloudrun")
async def generate_report(*, report_id: int) -> None:
    """Export report — runs on Cloud Run for isolation."""
    ...


# Enqueue imperatively (from a handler or service):
await generate_report.enqueue(execution_target="cloudrun", report_id=42)
```

### Wire into Litestar

```python
from litestar import Litestar
from app.server.plugins import saq_plugin

app = Litestar(
    route_handlers=[...],
    plugins=[saq_plugin],
)
```

### Define a Task

```python
# app/domain/system/tasks.py
async def send_email(ctx: dict, *, recipient: str, subject: str, body: str) -> None:
    """Send an email as a background job.

    Args:
        ctx: SAQ context dict populated by worker hooks.
        recipient: To address.
        subject: Email subject.
        body: Email body.
    """
    email_service = ctx["email_service"]
    await email_service.send(recipient, subject, body)
```

For long-running work, decorate the task with `monitored_job()` so heartbeats are sent while the task runs:

```python
from litestar_saq import monitored_job


@monitored_job()
async def rebuild_index(ctx: dict, *, index_name: str) -> dict[str, str]:
    await run_rebuild(index_name)
    return {"status": "complete"}
```

### Enqueue from a Handler (DI of TaskQueues)

```python
from litestar import Controller, post
from litestar.di import NamedDependency
from litestar_saq import TaskQueues


class NotificationController(Controller):
    path = "/api/notifications"

    @post("/")
    async def queue_notification(
        self,
        data: NotificationCreate,
        task_queues: NamedDependency[TaskQueues],
    ) -> dict[str, str]:
        queue = task_queues.get("default")
        await queue.enqueue(
            "send_email",
            recipient=data.email,
            subject=data.subject,
            body=data.body,
            timeout=30,
            retries=2,
            key=f"notify-{data.email}",
        )
        return {"status": "queued"}
```

### CLI

```bash
# Run workers (uses the same Litestar app)
litestar --app app:app workers run

# Run multiple worker processes
litestar --app app:app workers run --workers 4

# Run only selected queues in this worker service
litestar --app app:app workers run --queues emails --queues reports

# Inspect queues
litestar --app app:app workers status
```

### Web UI

When `web_enabled=True`, the SAQ web UI is mounted under the Litestar app for queue introspection and job retry.

### Job Options

| Option | Default | Use |
| --- | --- | --- |
| `timeout` | `10` | **Always set explicitly** — SAQ's default is usually too low or too high for real jobs |
| `retries` | `1` | Retry count on exception |
| `ttl` | `600` | Seconds to retain result after completion |
| `key` | `None` | Deduplication key — skip if already queued |
| `heartbeat` | `0` | Heartbeat interval for long-running jobs |
| `scheduled` | `0` | Unix timestamp to delay start |

<workflow>

## Workflow

### Step 1: Install

```bash
pip install litestar-saq
pip install "litestar-saq[psycopg]"  # PostgreSQL broker
pip install "litestar-saq[otel]"     # OpenTelemetry spans
```

### Step 2: Define Queues

Build `QueueConfig` instances for each logical queue (`"default"`, `"emails"`, `"reports"`). Put the broker `dsn` or `broker_instance` on each `QueueConfig`. Reference task functions by dotted path or callable; the plugin imports dotted paths at startup.

### Step 3: Configure Plugin

Wrap `QueueConfig`s in `SAQConfig`. Pick Redis (`redis://...`) when Redis is already in the stack; pick PostgreSQL (`postgresql://...`) when the project is PG-only. HTTP queues are supported for delegating to a remote SAQ service. Set `use_server_lifespan=True` when the web process should own worker child processes. Toggle `web_enabled` / `web_guards` for the introspection UI and `enable_otel` for tracing.

### Step 4: Define Tasks

Place task functions in `app/domain/<domain>/tasks.py`. First arg `ctx: dict`, rest keyword-only. Add shared resources (DB, HTTP client, email service) in `QueueConfig.startup` / `before_process` hooks and read them from `ctx`.

### Step 5: Schedule Cron Work

Add `CronJob` entries to `QueueConfig.scheduled_tasks` for recurring work. Always set `timeout`. Do not use external cron tools for work that belongs in the queue.

### Step 6: Enqueue from Handlers

Inject `TaskQueues` into route handlers. Use `task_queues.get("name")` then `await queue.enqueue("task_name", ...)`. Use `key=` for deduplication.

### Step 7: Publish to Channels (optional)

For real-time updates after a job completes, publish to Litestar Channels from inside the task. See `../litestar-realtime/references/websockets.md`.

### Step 8: Run

For dev: `litestar run` can start worker child processes when `use_server_lifespan=True`.
For production: run `litestar workers run --workers N` as a separate service/process from `litestar run`. There is no `--process` flag in litestar-saq 0.8.0.

</workflow>

<guardrails>

## Guardrails

- **Use `litestar-saq`, not raw SAQ, in Litestar apps** — the plugin handles DI, lifespan, CLI, and the web UI. Raw SAQ misses all of that.
- **Always set `timeout`** on tasks and CronJobs — SAQ defaults to 10s, which is rarely the correct production value.
- **Use `monitored_job()` or `heartbeat`** for jobs that run longer than ~30s, otherwise SAQ may mark them stuck and re-queue.
- **Inject `TaskQueues` via DI** — don't import a global queue inside handlers. The plugin owns the queue lifecycle.
- **Use `CronJob` for scheduled work** — not external cron. CronJobs participate in retries, timeouts, and observability.
- **Use `key=` for deduplication** — same logical job (per-user sync, per-resource refresh) should not stack.
- **`use_server_lifespan=True`** for dev and small-to-mid apps that should start worker child processes with the web server. For high-throughput production, run `litestar workers run --workers N` as a separate service.
- **Use `dsn` for multi-process workers** — Python 3.14 forkserver/spawn support rebuilds brokers in child processes from `QueueConfig.dsn`; `broker_instance`-only queues cannot be pickled into child workers.
- **Set graceful shutdown controls for long jobs** — use `shutdown_grace_period_s` and, when needed, `cancellation_hard_deadline_s` on `QueueConfig`.
- **Publish to Litestar Channels from tasks** when the job result must update connected websocket clients. See `../litestar-realtime/references/websockets.md`.
- **Pull shared resources from `ctx` populated by `QueueConfig` hooks**, not module-level globals — keeps tests deterministic and supports per-worker init.
- **Reach for the sidecar worker pattern when** you need same-transaction outbox semantics, a project-owned job schema, batched heartbeats for many running jobs, frontend updates through channels, or execution-target routing across Cloud Run / local. Keep the stack explicit: `TaskService` for fenced SQL transitions, `Worker` for execution, `WorkerSidecar` for wakeups/batched heartbeats/channel publishing, and `WorkerPlugin` for Litestar lifecycle wiring. For normal PG-backed queueing, SAQ+PG is the simpler default. See [references/postgres-native-sidecar-worker.md](references/postgres-native-sidecar-worker.md).

</guardrails>

<validation>

### Validation Checkpoint

Before delivering Litestar + SAQ code, verify:

- [ ] `SAQPlugin` is in `app.plugins`
- [ ] `SAQConfig.use_server_lifespan` is set explicitly
- [ ] `SAQConfig.worker_processes` or CLI `--workers` is set intentionally
- [ ] Each `QueueConfig` has a broker `dsn` or `broker_instance`
- [ ] Multi-process worker configs use `dsn`, not `broker_instance` only
- [ ] Each `QueueConfig` lists tasks by dotted path; the imports resolve
- [ ] All tasks have `ctx: dict` as the first positional arg, keyword-only params after `*`
- [ ] Every task has `timeout` set
- [ ] Long-running jobs (>30s) have `heartbeat` set
- [ ] Long-running task functions use `monitored_job()` when they need automatic heartbeats
- [ ] CronJobs have `timeout` and a sensible `cron` expression
- [ ] Handlers enqueue via injected `TaskQueues`, not module globals
- [ ] Job dedup uses `key=` where applicable
- [ ] Production deploys run workers as a separate service (`litestar workers run --workers N`)

</validation>

<example>

## Example

**Task:** A Litestar app with a default queue, an email task, a cleanup CronJob, and a handler that enqueues notifications. This example uses Redis as the SAQ broker; swap `dsn=settings.redis.url` for `dsn=settings.database.url` if the project is PG-only — see Quick Reference above for both patterns.

```python
# app/server/plugins.py
from litestar_saq import SAQConfig, SAQPlugin, QueueConfig, CronJob

from app.lib.settings import get_settings


def create_saq_plugin() -> SAQPlugin:
    settings = get_settings()
    return SAQPlugin(
        config=SAQConfig(
            use_server_lifespan=True,
            web_enabled=settings.saq.web_enabled,
            queue_configs=[
                QueueConfig(
                    name="default",
                    dsn=settings.redis.url,  # Redis broker — swap for settings.database.url in PG-only stacks
                    startup="app.domain.system.tasks.worker_startup",
                    shutdown="app.domain.system.tasks.worker_shutdown",
                    tasks=[
                        "app.domain.system.tasks.send_email",
                        "app.domain.system.tasks.cleanup_sessions",
                    ],
                    scheduled_tasks=[
                        CronJob(
                            function="app.domain.system.tasks.cleanup_sessions",
                            cron="*/15 * * * *",
                            timeout=120,
                        ),
                    ],
                ),
            ],
        ),
    )


saq_plugin = create_saq_plugin()
```

```python
# app/domain/system/tasks.py
async def worker_startup(ctx: dict) -> None:
    """Initialize shared resources for this worker."""
    ctx["email_service"] = create_email_service()
    ctx["db"] = create_database_client()


async def worker_shutdown(ctx: dict) -> None:
    """Dispose shared worker resources."""
    await ctx["db"].close()


async def send_email(ctx: dict, *, recipient: str, subject: str, body: str) -> None:
    """Send an email as a background job."""
    email = ctx["email_service"]
    await email.send(recipient, subject, body)


async def cleanup_sessions(ctx: dict) -> None:
    """Purge expired sessions every 15 minutes."""
    db = ctx["db"]
    await db.execute("DELETE FROM session WHERE expires_at < now()")
```

```python
# app/domain/notifications/controllers.py
from litestar import Controller, post
from litestar.di import NamedDependency
from litestar_saq import TaskQueues

from app.domain.notifications.schemas import NotificationCreate


class NotificationController(Controller):
    path = "/api/notifications"
    tags = ["Notifications"]

    @post("/")
    async def queue_notification(
        self,
        data: NotificationCreate,
        task_queues: NamedDependency[TaskQueues],
    ) -> dict[str, str]:
        queue = task_queues.get("default")
        await queue.enqueue(
            "send_email",
            recipient=data.email,
            subject=data.subject,
            body=data.body,
            timeout=30,
            retries=2,
            key=f"notify-{data.email}",
        )
        return {"status": "queued"}
```

```python
# app.py
from litestar import Litestar

from app.domain.notifications.controllers import NotificationController
from app.server.plugins import saq_plugin


app = Litestar(
    route_handlers=[NotificationController],
    plugins=[saq_plugin],
)
```

```bash
# Dev: workers start with the Litestar server lifespan
litestar --app app:app run

# Prod: separate worker service/process
litestar --app app:app workers run --workers 4
```

</example>

---

## References Index

- **[Advanced Patterns](references/patterns.md)** — Heartbeat tuning, dead-letter handling, job chaining, queue priorities, worker lifecycle hooks, Postgres backend.
- **[Sidecar Worker Pattern](references/postgres-native-sidecar-worker.md)** — TaskService + Worker + WorkerSidecar + WorkerPlugin pattern for same-transaction outbox semantics, project-owned job schema, sidecar batched heartbeats/wakeups, channel publish-back to the frontend, `@task` decorator + ScheduleConfig cron registry, and execution_target routing (local / cloudrun / immediate).

## Cross-References

- **[litestar](../litestar/SKILL.md)** — Litestar app initialization, plugins, and lifespan.
- **[litestar websockets reference](../litestar-realtime/references/websockets.md)** — Publish from a SAQ task to Litestar Channels for real-time UI updates.

## Official References

- <https://github.com/litestar-org/litestar-saq>
- <https://github.com/tobymao/saq>
- <https://saq-py.readthedocs.io/en/latest/>

## Shared Styleguide Baseline

- Use shared styleguides for generic language/framework rules to reduce duplication in this skill.
- [General Principles](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
- Keep this skill focused on tool-specific workflows, edge cases, and integration details.
