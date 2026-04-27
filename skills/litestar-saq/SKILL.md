---
name: litestar-saq
description: "Auto-activate for litestar_saq imports, SAQPlugin, SAQConfig, QueueConfig, TaskQueues, CronJob, litestar workers run, background jobs, scheduled jobs, or SAQ web UI. Use when adding first-party SAQ background work to Litestar. Not for Celery, RQ, Dramatiq, raw SAQ outside Litestar, or custom PostgreSQL-native queues unless explicitly chosen."
---

# litestar-saq

`litestar-saq` is the first-party plugin that integrates [SAQ (Simple Async Queue)](https://github.com/tobymao/saq) with Litestar. It provides:

- `SAQPlugin` — registers queues, workers, lifespan management, and DI for `TaskQueues`
- `SAQConfig` / `QueueConfig` — declarative queue + worker configuration
- `litestar workers run` — CLI to start workers in-process or as a separate process
- Optional web UI mounted under the Litestar app
- DI injection of `TaskQueues` into route handlers for ergonomic enqueueing

## Code Style Rules

- Use PEP 604 unions: `T | None`, never `Optional[T]`
- Consumer Litestar app modules MAY use `from __future__ import annotations` — canonical Litestar apps do.
- Async all I/O — task bodies and enqueue calls are `async def`.
- First positional arg of every task is `ctx: dict` (the SAQ context dict).
- Task params after `*` are keyword-only.

## Quick Reference

### Plugin Setup (canonical pattern)

The canonical pattern from [litestar-fullstack](https://github.com/litestar-org/litestar-fullstack) (`src/py/app/server/plugins.py`) uses lazy initialization and `use_server_lifespan=True` so workers share the app's lifespan with the web process:

```python
# Branch A — SAQ with Redis as the broker (pick when Redis is already in-stack
# for cache / sessions, or when you want the SAQ web UI + multi-queue fanout).
from litestar_saq import SAQConfig, SAQPlugin, QueueConfig, CronJob

from app.lib.settings import get_settings


def create_saq_plugin() -> SAQPlugin:
    settings = get_settings()
    return SAQPlugin(
        config=SAQConfig(
            dsn=settings.redis.url,              # redis://... — Redis broker
            use_server_lifespan=True,            # workers run inside web process by default
            web_enabled=settings.saq.web_enabled,
            queue_configs=[
                QueueConfig(
                    name="default",
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
# Branch B — SAQ with PostgreSQL as the broker (pick when the project is
# PG-only, you want one less piece of infra, or throughput is moderate).
def create_saq_plugin_pg() -> SAQPlugin:
    settings = get_settings()
    return SAQPlugin(
        config=SAQConfig(
            dsn=settings.database.url,           # postgresql+asyncpg://... — PG broker
            use_server_lifespan=True,
            web_enabled=settings.saq.web_enabled,
            queue_configs=[
                QueueConfig(
                    name="default",
                    tasks=["app.domain.system.tasks.send_email"],
                ),
            ],
        ),
    )
```

**Pick Branch A (SAQ + Redis) when:** Redis is already in-stack (cache, sessions, Channels), you need multi-queue fanout across many workers, want the SAQ web UI and dead-letter dashboards, or have high throughput (>1k jobs/s per queue).

**Pick Branch B (SAQ + PostgreSQL) when:** PG-only deployment (Cloud SQL, AlloyDB, self-hosted single DB), avoiding extra infra, moderate throughput (<1k jobs/s), or you want jobs and business data in the same transactional boundary.

**Pick Branch C (custom PG-native, no SAQ) when:** you need `pg_notify` wake-ups with zero polling lag, `FOR UPDATE SKIP LOCKED` atomic task claim, or multi-target execution routing (`local` / `cloudrun` / `immediate`) — and you're willing to own a thin `TaskService + WorkerPlugin` pair. See below.

**Anti-pattern:** hard-coding `dsn=settings.redis.url` in a PG-only project just because Redis is the "default" example. Match the broker to the stack.

### Branch C — Custom PostgreSQL-native queue (no SAQ)

Some projects reject SAQ entirely in favor of a thin `TaskService + WorkerPlugin` pair directly over PostgreSQL. This wins when you want `FOR UPDATE SKIP LOCKED` for atomic task claiming, `pg_notify` wake-ups (no polling lag), and multi-target execution routing (`local` / `cloudrun` / `immediate`) with zero extra dependencies beyond your existing Postgres connection.

In this pattern, the `WorkerPlugin` wires task discovery and the in-process worker into the Litestar app lifecycle; the `@task` decorator registers callables and optional cron schedules; `TaskService.create_task` persists tasks to a `job` table.

See [references/postgresql-native.md](references/postgresql-native.md) for the full pattern.

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
        ctx: SAQ context dict (queue, job, app-state).
        recipient: To address.
        subject: Email subject.
        body: Email body.
    """
    email_service = ctx["state"]["email_service"]
    await email_service.send(recipient, subject, body)
```

### Enqueue from a Handler (DI of TaskQueues)

```python
from litestar import Controller, post
from litestar_saq import TaskQueues


class NotificationController(Controller):
    path = "/api/notifications"

    @post("/")
    async def queue_notification(
        self,
        data: NotificationCreate,
        task_queues: TaskQueues,
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

# Run workers in a separate process (production)
litestar --app app:app workers run --process

# Inspect queues
litestar --app app:app workers status
```

### Web UI

When `web_enabled=True`, the SAQ web UI is mounted under the Litestar app for queue introspection and job retry.

### Job Options

| Option | Default | Use |
| --- | --- | --- |
| `timeout` | `None` | **Always set** — bound how long a job can run |
| `retries` | `0` | Retry count on exception |
| `ttl` | `600` | Seconds to retain result after completion |
| `key` | `None` | Deduplication key — skip if already queued |
| `heartbeat` | `0` | Heartbeat interval for long-running jobs |
| `scheduled` | `0` | Unix timestamp to delay start |

<workflow>

## Workflow

### Step 1: Install

```bash
pip install litestar-saq
```

### Step 2: Define Queues

Build `QueueConfig` instances for each logical queue (`"default"`, `"emails"`, `"reports"`). Reference task functions by dotted path; the plugin imports them at startup.

### Step 3: Configure Plugin

Wrap `QueueConfig`s in `SAQConfig` with the broker DSN. Pick Redis (`redis://...`) when Redis is already in the stack; pick PostgreSQL (`postgresql+asyncpg://...`) when the project is PG-only. Both brokers are fully supported — see Plugin Setup above for both patterns. Set `use_server_lifespan=True` so workers run inside the web process by default. Toggle `web_enabled` for the introspection UI.

### Step 4: Define Tasks

Place task functions in `app/domain/<domain>/tasks.py`. First arg `ctx: dict`, rest keyword-only. Pull shared resources (DB, HTTP client, email service) from `ctx["state"]`.

### Step 5: Schedule Cron Work

Add `CronJob` entries to `QueueConfig.scheduled_tasks` for recurring work. Always set `timeout`. Do not use external cron tools for work that belongs in the queue.

### Step 6: Enqueue from Handlers

Inject `TaskQueues` into route handlers. Use `task_queues.get("name")` then `await queue.enqueue("task_name", ...)`. Use `key=` for deduplication.

### Step 7: Publish to Channels (optional)

For real-time updates after a job completes, publish to Litestar Channels from inside the task. See `../litestar-realtime/references/websockets.md`.

### Step 8: Run

For dev: `litestar run` (workers + web in one process via `use_server_lifespan=True`).
For production: `litestar workers run --process` separately from `litestar run`.

</workflow>

<guardrails>

## Guardrails

- **Use `litestar-saq`, not raw SAQ, in Litestar apps** — the plugin handles DI, lifespan, CLI, and the web UI. Raw SAQ misses all of that.
- **Always set `timeout`** on tasks and CronJobs — default is no timeout; a hung task pins a worker slot forever.
- **Use `heartbeat`** for jobs that run longer than ~30s, otherwise SAQ may mark them stuck and re-queue.
- **Inject `TaskQueues` via DI** — don't import a global queue inside handlers. The plugin owns the queue lifecycle.
- **Use `CronJob` for scheduled work** — not external cron. CronJobs participate in retries, timeouts, and observability.
- **Use `key=` for deduplication** — same logical job (per-user sync, per-resource refresh) should not stack.
- **`use_server_lifespan=True`** for dev and small-to-mid apps (workers inside the web process). Switch to `--process` for high-throughput production.
- **Publish to Litestar Channels from tasks** when the job result must update connected websocket clients. See `../litestar-realtime/references/websockets.md`.
- **Pull shared resources from `ctx["state"]`**, not module-level globals — keeps tests deterministic and supports per-worker init.
- **Reach for a custom PG-native queue instead of SAQ when** you need `pg_notify` wake-ups, `FOR UPDATE SKIP LOCKED` atomic claim, or execution-target routing across Cloud Run / local. For every other PG-only case, SAQ+PG is the simpler default. See [references/postgresql-native.md](references/postgresql-native.md).

</guardrails>

<validation>

### Validation Checkpoint

Before delivering Litestar + SAQ code, verify:

- [ ] `SAQPlugin` is in `app.plugins`
- [ ] `SAQConfig.use_server_lifespan` is set explicitly
- [ ] Each `QueueConfig` lists tasks by dotted path; the imports resolve
- [ ] All tasks have `ctx: dict` as the first positional arg, keyword-only params after `*`
- [ ] Every task has `timeout` set
- [ ] Long-running jobs (>30s) have `heartbeat` set
- [ ] CronJobs have `timeout` and a sensible `cron` expression
- [ ] Handlers enqueue via injected `TaskQueues`, not module globals
- [ ] Job dedup uses `key=` where applicable
- [ ] Production deploys run workers as a separate process (`litestar workers run --process`)

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
            dsn=settings.redis.url,          # Redis broker — swap for settings.database.url in PG-only stacks
            use_server_lifespan=True,
            web_enabled=settings.saq.web_enabled,
            queue_configs=[
                QueueConfig(
                    name="default",
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
async def send_email(ctx: dict, *, recipient: str, subject: str, body: str) -> None:
    """Send an email as a background job."""
    email = ctx["state"]["email_service"]
    await email.send(recipient, subject, body)


async def cleanup_sessions(ctx: dict) -> None:
    """Purge expired sessions every 15 minutes."""
    db = ctx["state"]["db"]
    await db.execute("DELETE FROM session WHERE expires_at < now()")
```

```python
# app/domain/notifications/controllers.py
from litestar import Controller, post
from litestar_saq import TaskQueues

from app.domain.notifications.schemas import NotificationCreate


class NotificationController(Controller):
    path = "/api/notifications"
    tags = ["Notifications"]

    @post("/")
    async def queue_notification(
        self,
        data: NotificationCreate,
        task_queues: TaskQueues,
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
# Dev: workers + web in one process
litestar --app app:app run

# Prod: separate worker process
litestar --app app:app workers run --process
```

</example>

---

## References Index

- **[Advanced Patterns](references/patterns.md)** — Heartbeat tuning, dead-letter handling, job chaining, queue priorities, worker lifecycle hooks, Postgres backend.
- **[PostgreSQL-Native Queue (no SAQ)](references/postgresql-native.md)** — TaskService + WorkerPlugin pattern: FOR UPDATE SKIP LOCKED claim, pg_notify wake-ups, @task decorator + ScheduleConfig cron registry, execution_target routing (local / cloudrun / immediate).

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
