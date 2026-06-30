---
name: litestar-queues
description: "Auto-activate for litestar_queues, QueuePlugin, QueueConfig, QueueService, @task, QueuedBackgroundTask, TaskResult, litestar queues run/status/scheduler-health, queue backends, execution backends, schedules, or task progress events. Not for litestar-saq/SAQ, Celery, RQ, or Dramatiq — those use different APIs and worker lifecycles."
---

# litestar-queues

`litestar-queues` is the first-party Litestar worker abstraction for task registration, queue persistence, worker lifecycle, schedules, and application-facing queue events.

Use it when a Litestar app needs its own queue layer with explicit queue backend selection, local or Cloud Run execution, `QueueService` DI, and task progress events. Keep queue storage and execution separate:

- **Queue backend** stores task records and state.
- **Execution backend** decides where claimed work runs.

## Code Style Rules

- Use PEP 604 unions: `T | None`, never `Optional[T]`.
- Use `async def` for route handlers, dependency resolvers, task I/O, and event publishing.
- Inject `QueueService` with `NamedDependency[QueueService]`; do not import a module-level queue service in handlers.
- Import core APIs from `litestar_queues`. Import optional backend config classes from their documented backend submodules.
- Keep task payloads JSON-serializable when using Redis, Valkey, SQLSpec, Advanced Alchemy, or Cloud Run backends.
- Prefer `msgspec` for event/client DTOs in Litestar apps unless the project already standardizes on Pydantic.

## Quick Reference

### Minimal Plugin Setup

```python
from litestar import Litestar, post
from litestar.di import NamedDependency
from litestar_queues import QueueConfig, QueuePlugin, QueueService, task


@task("accounts.sync", queue="accounts", retries=3, timeout=300)
async def sync_account(account_id: str) -> dict[str, str]:
    return {"account_id": account_id, "status": "synced"}


@post("/accounts/{account_id:str}/sync")
async def create_sync_job(
    account_id: str,
    queue_service: NamedDependency[QueueService],
) -> dict[str, str]:
    result = await queue_service.enqueue(sync_account, account_id)
    return {"task_id": str(result.id), "status": result.status or "queued"}


app = Litestar(
    route_handlers=[create_sync_job],
    plugins=[QueuePlugin(config=QueueConfig())],
)
```

### Task Registration and Enqueueing

```python
from datetime import timedelta

from litestar_queues import QueueService, task


@task(
    "reports.render",
    queue="reports",
    priority=10,
    retries=2,
    timeout=120,
    run_after=30,
)
async def render_report(report_id: str) -> str:
    return report_id


async def queue_report(queue_service: QueueService, report_id: str) -> str:
    result = await queue_service.enqueue(
        render_report,
        report_id,
        key=f"report:{report_id}",
        timeout=600,
        metadata={"requested_by": "system"},
    )
    await result.wait(timeout=30)
    return result.status or "unknown"


@task("reports.refresh", interval=timedelta(minutes=15), jitter=30)
async def refresh_reports() -> None:
    ...


@task("billing.close-day", cron="0 0 * * *", timezone="UTC")
async def close_billing_day() -> None:
    ...
```

`QueueService.enqueue()` accepts a decorated `Task` object or registered task name. Use `task_modules=("app.tasks",)` or `discover_tasks("app.domain")` so string-enqueued tasks and schedules are imported during startup.

`TaskResult` is a handle over the queued record. Use `await result.refresh()` to reload state and `await result.wait(timeout=30)` to poll until `completed`, `failed`, or `cancelled`.

### Background Responses

```python
from litestar import Response, post
from litestar_queues import QueuedBackgroundTask, task


@task("imports.process")
async def process_import(path: str) -> None:
    ...


@post("/imports")
async def create_import() -> Response[dict[str, str]]:
    return Response(
        {"status": "queued"},
        background=QueuedBackgroundTask(process_import, "/tmp/data.csv"),
    )
```

Use `QueuedBackgroundTask` when a response should be sent before enqueueing. It resolves the active `QueueService` from `QueuePlugin`; pass `service=queue_service` when using a custom service.

### Worker Placement

```python
# Local development, tests, and lightweight deployments.
queue_config = QueueConfig(in_app_worker=True)

# Production sidecar/worker service.
queue_config = QueueConfig(in_app_worker=False)
```

```bash
LITESTAR_APP=app:app litestar queues run --drain-timeout 30
LITESTAR_APP=app:app litestar queues run --queue accounts --max-concurrency 4
LITESTAR_APP=app:app litestar queues status --json
LITESTAR_APP=app:app litestar queues scheduler-health --minutes 5
```

In-app workers share the web process and are the default. Standalone workers load the same Litestar app, open the plugin service, and process all queues unless `--queue` is repeated.

### Backend and Execution Selection

| Need | Queue backend | Execution backend | Install / import |
| --- | --- | --- | --- |
| Unit tests, examples, one-process local apps | `queue_backend="memory"` | `"local"` or `"immediate"` | Core package |
| SQLSpec-first app or SQL-backed persistence without SQLAlchemy ORM | `SQLSpecBackendConfig(...)` | `"local"` | `litestar-queues[sqlspec]`; `from litestar_queues.backends.sqlspec import SQLSpecBackendConfig` |
| Advanced Alchemy / SQLAlchemy app with Alembic-owned models | `AdvancedAlchemyBackendConfig(...)` | `"local"` | `litestar-queues[advanced-alchemy]`; `from litestar_queues.backends.advanced_alchemy import AdvancedAlchemyBackendConfig` |
| Redis already in the stack for cache, pub/sub, or shared infra | `RedisBackendConfig(...)` | `"local"` | `litestar-queues[redis]`; `from litestar_queues.backends.redis import RedisBackendConfig` |
| Valkey is the chosen Redis-compatible service | `ValkeyBackendConfig(...)` | `"local"` | `litestar-queues[valkey]`; `from litestar_queues.backends.valkey import ValkeyBackendConfig` |
| Inline test/script execution with completed results immediately | Any backend | `"immediate"` | Core package |
| Heavy or isolated jobs on Google Cloud Run Jobs | Persistent queue backend | `CloudRunExecutionConfig(...)` | `litestar-queues[cloudrun]`; `from litestar_queues.execution.cloudrun import CloudRunExecutionConfig` |

Pick the backend that matches the project:

- Use `memory` only for same-process work; it does not coordinate separate worker processes.
- Use `SQLSpecBackendConfig` when the app already uses SQLSpec or wants adapter-level SQL persistence.
- Use `AdvancedAlchemyBackendConfig` when the app already uses Advanced Alchemy / SQLAlchemy models and migrations; import the queue model into Alembic when the app owns schema.
- Use `RedisBackendConfig` or `ValkeyBackendConfig` when that service already exists and task payloads can stay JSON-serializable.
- Use `CloudRunExecutionConfig` only for execution; keep queue persistence on memory only for local experiments and on a shared persistent backend for real deployments.

### SQLSpec Queue Backend

```python
from sqlspec.adapters.aiosqlite import AiosqliteConfig

from litestar_queues import QueueConfig
from litestar_queues.backends.sqlspec import SQLSpecBackendConfig


queue_config = QueueConfig(
    queue_backend=SQLSpecBackendConfig(
        config=AiosqliteConfig(connection_config={"database": "queue.db"}),
        create_schema=False,
        run_migrations=True,
    ),
    execution_backend="local",
    in_app_worker=False,
)
```

### Advanced Alchemy Queue Backend

```python
from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig
from litestar_queues import QueueConfig
from litestar_queues.backends.advanced_alchemy import AdvancedAlchemyBackendConfig


alchemy_config = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///queue.db")

queue_config = QueueConfig(
    queue_backend=AdvancedAlchemyBackendConfig(
        sqlalchemy_config=alchemy_config,
        create_schema=False,
    ),
    execution_backend="local",
)
```

Set `create_schema=True` only for local bootstrap or tests. Production apps that manage schema with Alembic should import the queue model into the Alembic environment. Use `QueueTaskModelMixin` plus `model_class=` when the app needs its own table name, base class, bind metadata, or migration ownership.

### Redis or Valkey Queue Backend

```python
from litestar_queues import QueueConfig
from litestar_queues.backends.redis import RedisBackendConfig


queue_config = QueueConfig(
    queue_backend=RedisBackendConfig(
        url="redis://localhost:6379/0",
        key_prefix="litestar_queues",
        notifications=True,
    ),
    execution_backend="local",
)
```

Swap `RedisBackendConfig` for `ValkeyBackendConfig` from `litestar_queues.backends.valkey` when the project uses Valkey.

### Cloud Run Execution

```python
from litestar_queues import QueueConfig, task
from litestar_queues.backends.sqlspec import SQLSpecBackendConfig
from litestar_queues.execution.cloudrun import CloudRunExecutionConfig


@task("reports.render", execution_backend="cloudrun", execution_profile="heavy")
async def render_report(report_id: str) -> None:
    ...


queue_config = QueueConfig(
    queue_backend=SQLSpecBackendConfig(config=...),
    execution_backend=CloudRunExecutionConfig(
        project_id="example-project",
        region="us-central1",
        job_name="queue-worker",
        profiles={"heavy": "queue-worker-heavy"},
        extra_env={
            "LITESTAR_QUEUES_CONFIG_FACTORY": "app.queue:create_queue_config",
            "LITESTAR_QUEUES_TASK_MODULES": "app.tasks",
        },
    ),
)
```

Run the Cloud Run container with `litestar-queues-cloudrun-worker` or `python -m litestar_queues.execution.cloudrun.entrypoint`. The entrypoint reads `LITESTAR_QUEUES_TASK_ID`, loads `LITESTAR_QUEUES_CONFIG_FACTORY` and `LITESTAR_QUEUES_TASK_MODULES`, claims the persisted record, heartbeats, executes, and returns deterministic exit codes. The config factory must return the same `QueueConfig`, `QueueService`, or async context manager used by the dispatch worker; otherwise the entrypoint falls back to an isolated default `QueueConfig()`.

### Events and Progress

```python
from litestar_queues import QueueConfig, task
from litestar_queues.events import QueueEventConfig, publish_task_log, publish_task_progress


queue_config = QueueConfig(
    event_config=QueueEventConfig(
        enabled=True,
        channels_backend=channels,
        publish_global_lifecycle=True,
    ),
)


@task("imports.process")
async def process_import(path: str) -> None:
    await publish_task_log("Import started", payload={"path": path})
    await publish_task_progress(current=5, total=10, message="Halfway done")
```

Queue events are application-facing envelopes. They are separate from queue backend wakeup notifications. Use `TaskExecutionContext` via `_task_context` when a task needs direct access to `progress()`, `log()`, or `event()`.

### Dependency Resolver

```python
from typing import Any

from litestar_queues import QueueConfig, QueuedTaskRecord, Task, TaskExecutionContext, task


async def resolve_task_dependencies(
    _task: Task[Any, Any],
    _record: QueuedTaskRecord,
    _context: TaskExecutionContext,
) -> dict[str, Any]:
    return {"settings": {"environment": "production"}}


@task("reports.generate")
async def generate_report(*, settings: dict[str, Any]) -> str:
    return f"generated for {settings['environment']}"


queue_config = QueueConfig(task_dependency_resolver=resolve_task_dependencies)
```

Resolvers run once per attempt after `task.started` and before the task body. Return kwargs that match task parameters. Resolver exceptions follow the normal retry/failure path.

<workflow>

## Workflow

### Step 1: Identify the Work Shape

Use `litestar-queues` when the app needs durable task state, scheduled jobs, progress events, or worker placement choices. Use `QueuedBackgroundTask` only when the Litestar response lifecycle is the trigger and the actual work should still go through the queue.

### Step 2: Pick Queue Backend

Match the project stack. Start with `memory` only for tests and local single-process apps. Use SQLSpec for SQLSpec apps, Advanced Alchemy for SQLAlchemy/Advanced Alchemy apps, Redis for Redis-backed infrastructure, and Valkey for Valkey infrastructure.

### Step 3: Pick Execution Backend

Use `local` for normal in-process worker execution. Use `immediate` for tests and scripts that need inline completion. Use `CloudRunExecutionConfig` when tasks must run in Google Cloud Run Jobs and the queue backend is shared across web, dispatch worker, and remote worker containers.

### Step 4: Configure `QueuePlugin`

Register `QueuePlugin(config=QueueConfig(...))` in `Litestar(plugins=[...])`. Set `task_modules` when tasks are not otherwise imported before startup. Keep `initialize_schedules=True` unless schedule sync is owned by a separate process.

### Step 5: Define Tasks and Schedules

Decorate callables with `@task("name", ...)`. Put defaults on the decorator (`queue`, `priority`, `retries`, `timeout`, `run_after`, `execution_backend`, `execution_profile`, `key`). Use `interval` or five-field `cron`, not both.

### Step 6: Enqueue from Handlers or Services

Inject `QueueService` with `NamedDependency[QueueService]`. Call `await queue_service.enqueue(task_or_name, *args, **kwargs)` and use `TaskResult.refresh()` or `TaskResult.wait()` only when the caller truly needs observed completion.

### Step 7: Place Workers

Keep `in_app_worker=True` for tests, local development, and lightweight apps. Set `in_app_worker=False` and run `litestar queues run` as a separate service when web and background capacity must scale independently.

### Step 8: Add Events and Resolver Hooks

Enable `QueueEventConfig` only when clients or operators consume lifecycle, progress, log, or custom events. Add `task_dependency_resolver` only when tasks need services from an external DI container.

</workflow>

<guardrails>

## Guardrails

- **Use `QueuePlugin` for Litestar apps** — it wires DI, app state, lifespan, task module imports, schedule initialization, worker startup, and CLI commands.
- **Do not use `memory` for standalone production workers** — memory state is process-local and cannot coordinate web and worker processes.
- **Do not mix queue backend and execution backend concerns** — Cloud Run is execution; Redis, Valkey, SQLSpec, Advanced Alchemy, and memory store queue state.
- **Do not import optional backends from `litestar_queues.backends`** — import config classes from `litestar_queues.backends.sqlspec`, `.advanced_alchemy`, `.redis`, or `.valkey`.
- **Set `task_modules` or call `discover_tasks()`** when enqueueing by string or relying on schedules; decorators register tasks only after modules import.
- **Use `QueueService.enqueue()` in handlers and services** — reserve `Task.enqueue()` for code running under an active `QueuePlugin` default service or for intentional immediate fallback.
- **Always set explicit `timeout` on real tasks** — long-running workers need predictable cancellation and failure behavior.
- **Use `key=` for deduplication** when repeated requests target the same logical job.
- **Treat backend wakeup notifications as hints** — workers still rely on polling and durable queue state.
- **Keep dependency resolvers per-attempt clean** — return fresh request/session handles and let failures participate in normal task retry handling.
- **Use `scheduler-health` only after registering a recurring canary task** matching `QueueConfig.scheduler_canary_task`.

</guardrails>

<validation>

### Validation Checkpoint

Before delivering Litestar Queues code, verify:

- [ ] `QueuePlugin(config=QueueConfig(...))` is registered in `app.plugins`
- [ ] `QueueConfig.queue_backend` matches the project's persistence stack
- [ ] `QueueConfig.execution_backend` matches where tasks should run
- [ ] `in_app_worker` is intentional for the deployment shape
- [ ] Standalone deployments use a shared persistent queue backend
- [ ] `task_modules` or `discover_tasks()` imports all decorated task modules
- [ ] Handlers inject `NamedDependency[QueueService]`
- [ ] Enqueue calls use `QueueService.enqueue()` with explicit `timeout`, `retries`, and `key` where needed
- [ ] Scheduled tasks use either `interval` or five-field `cron`
- [ ] `initialize_schedules` is enabled in exactly one startup path when multiple app processes exist
- [ ] Event publishing is enabled only when a sink or Channels backend is configured
- [ ] Dependency resolver output matches task keyword parameters
- [ ] `litestar queues run/status/scheduler-health` commands load the intended Litestar app through `LITESTAR_APP` or `--app`

</validation>

<example>

## Example

**Task:** A Litestar app queues report jobs to SQLSpec, runs workers as a standalone service, publishes progress, and has a scheduler canary.

```python
from datetime import timedelta

from litestar import Litestar, post
from litestar.di import NamedDependency
from sqlspec.adapters.aiosqlite import AiosqliteConfig

from litestar_queues import QueueConfig, QueuePlugin, QueueService, task
from litestar_queues.backends.sqlspec import SQLSpecBackendConfig
from litestar_queues.events import publish_task_log, publish_task_progress


@task("reports.render", queue="reports", retries=2, timeout=300)
async def render_report(report_id: str) -> dict[str, str]:
    await publish_task_log("Report rendering started", payload={"report_id": report_id})
    await publish_task_progress(current=1, total=2, message="Rendering")
    return {"report_id": report_id, "status": "rendered"}


@task("scheduler.heartbeat", interval=timedelta(minutes=1), timeout=10)
async def scheduler_heartbeat() -> None:
    return None


@post("/reports/{report_id:str}/render")
async def enqueue_report(
    report_id: str,
    queue_service: NamedDependency[QueueService],
) -> dict[str, str]:
    result = await queue_service.enqueue(
        render_report,
        report_id,
        key=f"report:{report_id}",
        description="Render report",
    )
    return {"task_id": str(result.id), "status": result.status or "queued"}


queue_config = QueueConfig(
    queue_backend=SQLSpecBackendConfig(
        config=AiosqliteConfig(connection_config={"database": "queue.db"}),
        create_schema=False,
        run_migrations=True,
    ),
    execution_backend="local",
    in_app_worker=False,
    worker_max_concurrency=4,
)

app = Litestar(
    route_handlers=[enqueue_report],
    plugins=[QueuePlugin(config=queue_config)],
)
```

```bash
LITESTAR_APP=app:app litestar queues run --queue reports --max-concurrency 4 --drain-timeout 60
LITESTAR_APP=app:app litestar queues status --json
LITESTAR_APP=app:app litestar queues scheduler-health --minutes 5
```

</example>

## References Index

- **[litestar](../litestar/SKILL.md)** — Litestar app setup, plugin lists, DI, and lifespan.
- **[litestar-routing](../litestar-routing/SKILL.md)** — Controller and route handler patterns for enqueue endpoints.
- **[litestar-realtime](../litestar-realtime/SKILL.md)** — Channels and WebSocket delivery for queue progress streams.
- **[sqlspec](../sqlspec/SKILL.md)** — SQLSpec adapter and extension configuration.
- **[advanced-alchemy](../advanced-alchemy/SKILL.md)** — Advanced Alchemy SQLAlchemy config, repositories, and Alembic ownership.

## Official References

- <https://github.com/cofin/litestar-queues/releases/tag/v0.1.0>
- <https://github.com/cofin/litestar-queues>
- <https://cofin.github.io/litestar-queues/>
- <https://cofin.github.io/litestar-queues/usage/configuration.html>
- <https://cofin.github.io/litestar-queues/usage/backends.html>
- <https://cofin.github.io/litestar-queues/usage/tasks.html>
- <https://cofin.github.io/litestar-queues/usage/workers.html>
- <https://cofin.github.io/litestar-queues/usage/events.html>
- <https://cofin.github.io/litestar-queues/usage/schedules.html>
- <https://cofin.github.io/litestar-queues/usage/cli.html>
- <https://cofin.github.io/litestar-queues/usage/dependency-resolver.html>

## Shared Styleguide Baseline

- Use shared styleguides for generic language/framework rules to reduce duplication in this skill.
- [General Principles](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
- Keep this skill focused on `litestar-queues` workflows, backend selection, worker placement, and task/event APIs.
