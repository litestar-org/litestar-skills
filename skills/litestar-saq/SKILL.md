---
name: litestar-saq
description: "Auto-activate for litestar_saq imports, SAQPlugin, SAQConfig, QueueConfig, TaskQueues. The first-party Litestar plugin around SAQ (Simple Async Queue): background tasks, cron jobs, queue web UI, `litestar workers run` CLI, DI of `TaskQueues`. Produces SAQPlugin configs, QueueConfig definitions, task functions, CronJobs, and DI-injected enqueue patterns. Use when: adding background jobs to a Litestar app, scheduling cron work, exposing the SAQ web UI, or running workers via the Litestar CLI. Not for Celery, RQ, or Dramatiq — Litestar's first-party choice is SAQ. For raw SAQ patterns outside Litestar, see standalone SAQ docs."
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

The canonical pattern from `litestar-fullstack-spa/src/py/app/server/plugins.py` uses lazy initialization and `use_server_lifespan=True` so workers share the app's lifespan with the web process:

```python
from litestar_saq import SAQConfig, SAQPlugin, QueueConfig, CronJob

from app.lib.settings import get_settings


def create_saq_plugin() -> SAQPlugin:
    settings = get_settings()
    return SAQPlugin(
        config=SAQConfig(
            dsn=settings.redis.url,
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
|---|---|---|
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

Wrap `QueueConfig`s in `SAQConfig` with the broker DSN (Redis or PostgreSQL). Set `use_server_lifespan=True` so workers run inside the web process by default. Toggle `web_enabled` for the introspection UI.

### Step 4: Define Tasks

Place task functions in `app/domain/<domain>/tasks.py`. First arg `ctx: dict`, rest keyword-only. Pull shared resources (DB, HTTP client, email service) from `ctx["state"]`.

### Step 5: Schedule Cron Work

Add `CronJob` entries to `QueueConfig.scheduled_tasks` for recurring work. Always set `timeout`. Do not use external cron tools for work that belongs in the queue.

### Step 6: Enqueue from Handlers

Inject `TaskQueues` into route handlers. Use `task_queues.get("name")` then `await queue.enqueue("task_name", ...)`. Use `key=` for deduplication.

### Step 7: Publish to Channels (optional)

For real-time updates after a job completes, publish to Litestar Channels from inside the task. See `../litestar/references/websockets.md`.

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
- **Publish to Litestar Channels from tasks** when the job result must update connected websocket clients. See `../litestar/references/websockets.md`.
- **Pull shared resources from `ctx["state"]`**, not module-level globals — keeps tests deterministic and supports per-worker init.

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

**Task:** A Litestar app with a default queue, an email task, a cleanup CronJob, and a handler that enqueues notifications.

```python
# app/server/plugins.py
from litestar_saq import SAQConfig, SAQPlugin, QueueConfig, CronJob

from app.lib.settings import get_settings


def create_saq_plugin() -> SAQPlugin:
    settings = get_settings()
    return SAQPlugin(
        config=SAQConfig(
            dsn=settings.redis.url,
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

## Cross-References

- **[litestar](../litestar/SKILL.md)** — Litestar app initialization, plugins, and lifespan.
- **[litestar websockets reference](../litestar/references/websockets.md)** — Publish from a SAQ task to Litestar Channels for real-time UI updates.

## Official References

- <https://github.com/litestar-org/litestar-saq>
- <https://github.com/tobymao/saq>
- <https://saq-py.readthedocs.io/en/latest/>

## Shared Styleguide Baseline

- Use shared styleguides for generic language/framework rules to reduce duplication in this skill.
- [General Principles](../../../.agents/code-styleguides/general.md)
- [Python](../../../.agents/code-styleguides/python.md)
- [Litestar](../../../.agents/code-styleguides/litestar.md)
- Keep this skill focused on tool-specific workflows, edge cases, and integration details.
