---
name: litestar-queues
description: "Auto-activate for litestar_queues, QueuePlugin, QueueConfig, WorkerConfig, QueueService, @task, QueuedBackgroundTask, QueueEventsConfig, SQLAlchemyBackendConfig, SQLSpecBackendConfig, litestar queues run/run-task/run-maintenance/status/scheduler-health, queue backends, workers, schedules, uniqueness, maintenance, or task progress events. Not for litestar-saq/SAQ, Celery, RQ, or Dramatiq — those use different APIs and worker lifecycles."
---

# litestar-queues

`litestar-queues` 0.5.0 is the first-party Litestar worker abstraction for task registration, durable queue state, worker lifecycle, schedules, uniqueness, bounded maintenance, and application-facing task events.

Keep persistence and placement separate:

- A **queue backend** stores task records, identities, maintenance coordination, and optional event history.
- An **execution backend** decides where a claimed task runs.
- **Worker wakeups** are delivery hints. Persisted queue records remain the source of truth.

## Code Style Rules

- Use `QueuePlugin` to wire lifecycle, application state, DI, task discovery, schedules, workers, and CLI commands.
- Put worker settings under `QueueConfig(worker=WorkerConfig(...))`.
- Inject `QueueService` with `NamedDependency[QueueService]`; never use a module-level service from handlers.
- Import public core types from `litestar_queues`. Import optional backend configuration from its backend submodule.
- Keep persistent-backend arguments and metadata JSON-serializable. Pass stable object IDs instead of large payloads.
- Use PEP 604 unions and async I/O. Prefer `msgspec` for event/client DTOs unless the project already uses Pydantic.

## Quick Reference

### Minimal Plugin Setup

```python
from litestar import Litestar, post
from litestar.di import NamedDependency
from litestar_queues import QueueConfig, QueuePlugin, QueueService, WorkerConfig, task


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
    plugins=[
        QueuePlugin(
            QueueConfig(worker=WorkerConfig(run_in_app=True)),
        ),
    ],
)
```

The defaults use memory persistence, local execution, and an in-app worker. Keep that shape for tests, development, and small single-process deployments only.

### Task Options, Scheduling, and Uniqueness

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
    unique_by="arguments",
)
async def render_report(report_id: str, *, format: str = "pdf") -> str:
    return f"{report_id}.{format}"


@task("reports.refresh", interval=timedelta(minutes=15), jitter=30)
async def refresh_reports() -> None:
    ...


async def queue_report(queue_service: QueueService, report_id: str) -> str:
    result = await queue_service.enqueue(
        render_report,
        report_id,
        timeout=600,
        metadata={"requested_by": "system"},
    )
    await result.wait(timeout=30)
    return result.status or "unknown"
```

Identity precedence is strict:

1. Explicit enqueue `key`.
2. Configured task `key`.
3. `unique_by="task"`.
4. `unique_by="arguments"`.
5. No identity.

`unique_until="terminal"` is the default and releases the identity after completion, failure, or cancellation. `unique_until="forever"` stores a permanent reservation until `await queue_service.reset_task_identity(effective_key)` removes it.

Do not combine a configured `key` with `unique_by`. Do not set `unique_until="forever"` without a configured `key` or `unique_by`. Use `QueueConfig.max_argument_identity_bytes` to bound canonical payloads hashed by `unique_by="arguments"`.

Use `interval` or five-field `cron`, never both. Use `task_modules=("app.tasks",)` or `discover_tasks("app.domain")` before string enqueueing or schedule initialization.

### Worker Configuration and CLI

```python
from litestar_queues import QueueConfig, WorkerConfig


queue_config = QueueConfig(
    queue_backend=...,  # shared persistent backend
    worker=WorkerConfig(
        run_in_app=False,
        batch_size=10,
        max_concurrency=4,
        queues=("accounts", "reports"),
        poll_interval=0.25,
        heartbeat_interval=30,
        heartbeat_miss_threshold=2,
        graceful_shutdown_timeout=60,
    ),
)
```

```bash
LITESTAR_APP=app:app litestar queues run --queue reports --max-concurrency 4 --drain-timeout 60
LITESTAR_APP=app:app litestar queues status --json
LITESTAR_APP=app:app litestar queues scheduler-health --minutes 5
```

`WorkerConfig.run_in_app=True` starts a worker in the Litestar lifespan. Set it to `False` when web and worker processes scale separately. Standalone workers use `WorkerConfig.queues`, `max_concurrency`, and `graceful_shutdown_timeout` unless CLI flags override them.

The worker adaptively backs off empty polling from `poll_interval` toward `poll_backoff_max`, using `poll_backoff_multiplier` and `poll_jitter`. Backend notifications can end the wait early; they never replace polling or durable state checks.

### Backend Selection

| Existing stack or need | Queue backend | Import |
| --- | --- | --- |
| Tests and single-process local apps | `"memory"` | Core package |
| SQLSpec-managed SQL persistence | `SQLSpecBackendConfig(...)` | `litestar_queues.backends.sqlspec` |
| Advanced Alchemy / SQLAlchemy models | `SQLAlchemyBackendConfig(...)` | `litestar_queues.backends.advanced_alchemy` |
| Existing Redis infrastructure | `RedisBackendConfig(...)` | `litestar_queues.backends.redis` |
| Existing Valkey infrastructure | `ValkeyBackendConfig(...)` | `litestar_queues.backends.valkey` |
| Inline completion in tests/scripts | Any queue backend + `"immediate"` execution | Core package |
| Isolated Google Cloud Run Jobs | Persistent queue backend + `CloudRunExecutionConfig(...)` | `litestar_queues.execution.cloudrun` |

Match the project's existing data stack. Memory cannot coordinate separate processes. Cloud Run is an execution backend, never queue persistence.

### SQLSpec Backend

```python
from sqlspec.adapters.aiosqlite import AiosqliteConfig

from litestar_queues import QueueConfig
from litestar_queues.backends.sqlspec import SQLSpecBackendConfig


sqlspec_config = AiosqliteConfig(
    connection_config={"database": "queue.db"},
)

queue_config = QueueConfig(
    queue_backend=SQLSpecBackendConfig(
        sqlspec_config=sqlspec_config,
        manage_schema=True,
    ),
    execution_backend="local",
)
```

`QueuePlugin` registers the package migration with the supplied SQLSpec configuration. Run it through the application's normal SQLSpec migration workflow; opening the backend does not migrate the database. Use explicit `create_schema()` only for local bootstrap.

`SQLSpecBackendConfig.worker_wakeups` defaults to `SQLSpecWorkerWakeupConfig()`. Capable PostgreSQL adapters use `notify_queue`, DuckDB uses `poll_queue`, and other adapters fall back to polling. Set `worker_wakeups=None` to disable native wakeups. Override `transport`, `channel_name`, `queue_table_name`, or `poll_interval` only when the project's infrastructure requires it.

### Advanced Alchemy Backend

```python
from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig

from litestar_queues import QueueConfig
from litestar_queues.backends.advanced_alchemy import SQLAlchemyBackendConfig


alchemy_config = SQLAlchemyAsyncConfig(
    connection_string="sqlite+aiosqlite:///queue.db",
)

queue_config = QueueConfig(
    queue_backend=SQLAlchemyBackendConfig(
        sqlalchemy_config=alchemy_config,
        worker_wakeups=False,
    ),
    execution_backend="local",
)
```

Use the application's Advanced Alchemy metadata and migration lifecycle. The backend does not create its four tables. Compose the package mixins into adopter-owned models when custom bases, table names, or binds are required, then pass all matching model classes:

- `model_class`
- `event_history_model_class`
- `maintenance_model_class`
- `task_reservation_model_class`

Set `worker_wakeups=True` only for a supported PostgreSQL dialect. `heartbeat_session_maker` may isolate heartbeat writes while targeting the same database.

### Redis and Valkey Backends

```python
from litestar_queues import QueueConfig
from litestar_queues.backends.redis import RedisBackendConfig


queue_config = QueueConfig(
    queue_backend=RedisBackendConfig(
        url="redis://localhost:6379/0",
        key_prefix="litestar_queues",
        worker_wakeups=True,
    ),
    execution_backend="local",
)
```

Use `ValkeyBackendConfig` from `litestar_queues.backends.valkey` for Valkey. Both use pub/sub wakeup hints by default. Their queue data, wakeup channel, maintenance key, and permanent reservations remain namespaced by the configured prefix.

### Persistent Schema

SQL-backed deployments can require four package-owned concerns:

| Concern | Default table |
| --- | --- |
| Queue records | `queue_task` |
| Durable event history | `queue_task_event_history` |
| Distributed maintenance coordination | `queue_maintenance` |
| Forever-uniqueness reservations | `queue_task_reservation` |

SQLSpec's packaged `0001_create_queue_tasks` migration provisions the enabled tables and supports explicit table-name overrides. Advanced Alchemy applications own equivalent models and Alembic migrations. Redis and Valkey use namespaced keys and require no SQL migration.

Do not delete the reservation table during ordinary task or event retention. Forever identities are removed only through `QueueService.reset_task_identity()`.

### Events and Progress

```python
from litestar_queues import QueueConfig, task
from litestar_queues.events import (
    EventDeliveryConfig,
    QueueEventsConfig,
    publish_task_log,
    publish_task_progress,
)


queue_config = QueueConfig(
    events=QueueEventsConfig(
        channels=channels_backend,
        delivery=EventDeliveryConfig(
            publish_global_lifecycle=True,
        ),
    ),
)


@task("imports.process", timeout=300)
async def process_import(path: str) -> None:
    await publish_task_log("Import started", payload={"path": path})
    await publish_task_progress(current=50, total=100, message="Halfway")
```

`QueueEventsConfig` groups live `delivery`, application `stream`, and durable `history`. It must enable at least one capability. A Channels backend by itself is unused unless delivery or streaming is enabled.

Task events are separate from worker wakeups. Configure a shared Channels backend or explicit sinks for live cross-process delivery. Configure `EventHistoryConfig` when durable history is required.

### Bounded Maintenance

```python
from litestar_queues import QueueConfig, QueueMaintenanceConfig


queue_config = QueueConfig(
    queue_backend=...,  # persistent backend
    maintenance=QueueMaintenanceConfig(
        time_budget=300,
        coordination_timeout=360,
        stale_after=900,
        stale_limit=100,
        terminal_retention=30 * 24 * 60 * 60,
        terminal_limit=1000,
        event_retention=7 * 24 * 60 * 60,
        event_limit=1000,
    ),
)
```

```bash
LITESTAR_APP=app:app litestar queues run-maintenance --json
LITESTAR_APP=app:app litestar queues run-maintenance --phase stale --phase terminal
```

One maintenance invocation runs bounded phases in fixed order: external reconciliation, stale recovery, terminal retention, then event retention. It never starts a worker, executes queued work, or loops to drain a backlog.

Schedule one external six-hour or daily invocation. Retention phases have no destructive defaults: `stale_after`, `terminal_retention`, and `event_retention` remain disabled when `None`. `coordination_timeout` must exceed `time_budget`.

### External One-Task Execution

```bash
LITESTAR_QUEUES_TASK_ID=4d821c46-8c60-4ec3-b884-3f62eb71a03e \
LITESTAR_QUEUES_CONFIG_FACTORY=app.queue:create_queue_config \
litestar queues run-task
```

`run-task` claims and executes one existing record for an external executor. `--task-id`, `--config-factory`, and `--task-modules` override its environment inputs for manual operation. It is not a standalone worker loop.

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
        {"status": "accepted"},
        background=QueuedBackgroundTask(process_import, "/tmp/data.csv"),
    )
```

`QueuedBackgroundTask` enqueues after the response is sent. It resolves the active plugin service at construction; pass `service=queue_service` for a custom service.

<workflow>

## Workflow

1. **Identify the work shape.** Use Litestar Queues for durable task state, worker placement, schedules, progress/events, task uniqueness, or bounded maintenance.
2. **Match the queue backend.** Use memory for same-process tests, SQLSpec for SQLSpec apps, Advanced Alchemy for SQLAlchemy apps, Redis for Redis infrastructure, or Valkey for Valkey infrastructure.
3. **Pick execution placement.** Use local workers by default, immediate execution for tests/scripts, and Cloud Run only for isolated external jobs.
4. **Configure the worker.** Put every worker setting under `WorkerConfig`; decide explicitly whether it runs in the app lifespan.
5. **Provision persistent storage.** Run SQLSpec migrations or add all required Advanced Alchemy models to application-owned migrations.
6. **Define and discover tasks.** Decorate callables with `@task`; import their modules before string enqueueing or schedule initialization.
7. **Enqueue through DI.** Inject `QueueService`, enqueue a decorated task or registered name, and wait only when the caller truly needs the terminal state.
8. **Add optional capabilities separately.** Configure worker wakeups, task-event delivery/history, permanent uniqueness, and maintenance only when their storage and operational lifecycles are owned.
9. **Place operational commands.** Run standalone workers continuously, `run-task` only in external one-task executors, and maintenance from one infrequent external schedule.

</workflow>

<guardrails>

## Guardrails

- **Use `SQLAlchemyBackendConfig` for Advanced Alchemy persistence.** Import it from `litestar_queues.backends.advanced_alchemy`.
- **Configure events with `QueueEventsConfig`.** Add `EventDeliveryConfig`, `EventStreamConfig`, and/or `EventHistoryConfig` for the required capabilities.
- **Do not pass flat worker fields to `QueueConfig`.** Use `QueueConfig(worker=WorkerConfig(...))`.
- **Do not use `memory` across processes.** It cannot coordinate standalone workers or a separate maintenance command.
- **Do not confuse wakeups with task events.** Wakeups hint that work may exist; task events serve application and operator consumers.
- **Do not rely on wakeups for correctness.** Notifications may be delayed or lost; poll and claim durable state.
- **Do not let the backend open path own migrations.** Run SQLSpec migrations explicitly or manage Advanced Alchemy schema in the application.
- **Do not omit maintenance or reservation storage.** Provision all four SQL concerns used by the deployment.
- **Do not enable retention implicitly.** Leave each destructive threshold at `None` until an explicit policy exists.
- **Do not run maintenance as a minute-level task.** Use one bounded external invocation every six hours or daily.
- **Do not combine `key` and `unique_by`.** Select one identity source.
- **Do not assume `run-task` starts a worker.** It consumes one already-persisted record and exits.
- **Do not import optional configs from `litestar_queues.backends`.** Use the concrete `.sqlspec`, `.advanced_alchemy`, `.redis`, or `.valkey` module.
- **Do not enqueue by string before task discovery.** Import task modules or call `discover_tasks()`.

</guardrails>

<validation>

## Validation Checkpoint

- [ ] The dependency floor is `litestar-queues>=0.5.0`
- [ ] `QueuePlugin` receives one `QueueConfig`
- [ ] Worker options live under `QueueConfig.worker`
- [ ] `WorkerConfig.run_in_app` matches the deployment topology
- [ ] Standalone workers use a shared persistent queue backend
- [ ] The backend matches the project's SQLSpec, Advanced Alchemy, Redis, or Valkey stack
- [ ] SQLSpec uses `sqlspec_config` and the normal migration workflow
- [ ] Advanced Alchemy uses `SQLAlchemyBackendConfig` and application-owned migrations
- [ ] All enabled SQL concerns have queue, event-history, maintenance, and reservation tables
- [ ] Worker wakeups are configured independently from application task events
- [ ] `QueueEventsConfig` enables delivery, stream, or history
- [ ] Task modules are loaded before string enqueueing and schedule initialization
- [ ] Handlers inject `NamedDependency[QueueService]`
- [ ] Uniqueness uses one identity source and the intended lifetime
- [ ] `max_argument_identity_bytes` bounds untrusted argument-derived identity inputs
- [ ] Maintenance thresholds and one external schedule are explicit
- [ ] `run`, `run-task`, and `run-maintenance` are used for their distinct lifecycles

</validation>

<example>

## Example

**Task:** Persist report jobs with SQLSpec, run a standalone worker, deduplicate equivalent calls, and perform bounded retention.

```python
from litestar import Litestar, post
from litestar.di import NamedDependency
from sqlspec.adapters.aiosqlite import AiosqliteConfig

from litestar_queues import (
    QueueConfig,
    QueueMaintenanceConfig,
    QueuePlugin,
    QueueService,
    WorkerConfig,
    task,
)
from litestar_queues.backends.sqlspec import SQLSpecBackendConfig


@task(
    "reports.render",
    queue="reports",
    retries=2,
    timeout=300,
    unique_by="arguments",
)
async def render_report(report_id: str) -> dict[str, str]:
    return {"report_id": report_id, "status": "rendered"}


@post("/reports/{report_id:str}/render")
async def enqueue_report(
    report_id: str,
    queue_service: NamedDependency[QueueService],
) -> dict[str, str]:
    result = await queue_service.enqueue(render_report, report_id)
    return {"task_id": str(result.id), "status": result.status or "queued"}


sqlspec_config = AiosqliteConfig(
    connection_config={"database": "queue.db"},
)
queue_config = QueueConfig(
    queue_backend=SQLSpecBackendConfig(sqlspec_config=sqlspec_config),
    execution_backend="local",
    worker=WorkerConfig(
        run_in_app=False,
        max_concurrency=4,
        queues=("reports",),
    ),
    maintenance=QueueMaintenanceConfig(
        time_budget=300,
        coordination_timeout=360,
        stale_after=900,
        terminal_retention=30 * 24 * 60 * 60,
    ),
    task_modules=("app.tasks",),
    max_argument_identity_bytes=64 * 1024,
)

app = Litestar(
    route_handlers=[enqueue_report],
    plugins=[QueuePlugin(queue_config)],
)
```

```bash
LITESTAR_APP=app:app litestar queues run
LITESTAR_APP=app:app litestar queues run-maintenance --json
```

</example>

## References Index

- **[litestar](../litestar/SKILL.md)** — Litestar app setup, plugin lists, DI, and lifespan.
- **[litestar-routing](../litestar-routing/SKILL.md)** — Route handlers and controllers for enqueue endpoints.
- **[litestar-di](../litestar-di/SKILL.md)** — `NamedDependency` and service injection.
- **[litestar-plugins](../litestar-plugins/SKILL.md)** — Plugin initialization and lifecycle.
- **[litestar-autowire](../litestar-autowire/SKILL.md)** — Optional task discovery through Autowire integration.
- **[litestar-realtime](../litestar-realtime/SKILL.md)** — Channels, SSE, WebSockets, and task-event fan-out.
- **[litestar-testing](../litestar-testing/SKILL.md)** — Application and handler tests.
- **[sqlspec](../sqlspec/SKILL.md)** — SQLSpec adapter and migration configuration.
- **[advanced-alchemy](../advanced-alchemy/SKILL.md)** — SQLAlchemy models, services, and Alembic ownership.

## Official References

- <https://github.com/cofin/litestar-queues/tree/v0.5.0>
- <https://github.com/cofin/litestar-queues/releases/tag/v0.5.0>
- <https://github.com/cofin/litestar-queues/blob/v0.5.0/src/litestar_queues/config.py>
- <https://github.com/cofin/litestar-queues/blob/v0.5.0/src/litestar_queues/task.py>
- <https://github.com/cofin/litestar-queues/blob/v0.5.0/src/litestar_queues/_cli.py>
- <https://github.com/cofin/litestar-queues/blob/v0.5.0/src/litestar_queues/backends/sqlspec/config.py>
- <https://github.com/cofin/litestar-queues/blob/v0.5.0/src/litestar_queues/backends/advanced_alchemy/config.py>
- <https://github.com/cofin/litestar-queues/blob/v0.5.0/src/litestar_queues/maintenance.py>

## Shared Styleguide Baseline

- Use shared styleguides for generic language/framework rules to reduce duplication in this skill.
- [General Principles](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
- Keep this skill focused on `litestar-queues` workflows, backend selection, worker placement, uniqueness, maintenance, and task-event APIs.
