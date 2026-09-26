---
name: litestar-queues
description: "Auto-activate for litestar_queues, QueuePlugin, QueueConfig, WorkerConfig, QueueService, @task, QueuedBackgroundTask, QueueEventsConfig, or SQLSpecBackendConfig. Not for litestar-saq, Celery, or Dramatiq."
---

# litestar-queues

`litestar-queues` 0.12.0 is the first-party Litestar worker abstraction for task registration, durable queue state, worker lifecycle, schedules, uniqueness, bounded maintenance, execution dispatch, and application-facing task events.

Keep persistence and placement separate:

- A **queue backend** stores task records, identities, maintenance coordination, and optional event history.
- An **execution backend** decides where a claimed task runs.
- **Worker wakeups** are delivery hints. Persisted queue records remain the source of truth.

## Code Style Rules

- Use `QueuePlugin` to wire lifecycle, application state, DI, task discovery, schedules, workers, and CLI commands.
- Put worker settings under `QueueConfig(worker=WorkerConfig(...))`.
- Inject `QueueService` with `NamedDependency[QueueService]`; never use a module-level service from handlers.
- Import public core types from `litestar_queues`. Import optional backend configuration from its backend submodule (`.sqlspec`, `.advanced_alchemy`, `.redis`, `.valkey`) and execution configs from `litestar_queues` or their respective submodules.
- Keep persistent-backend arguments and metadata JSON-serializable. Pass stable object IDs instead of large payloads.
- Use PEP 604 unions (`T | None`) and async I/O. Prefer `msgspec` for event/client DTOs unless the project already uses Pydantic.

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
            QueueConfig(worker=WorkerConfig(placement="server")),
        ),
    ],
)
```

`QueueConfig()` with no arguments defaults to `queue_backend="ephemeral"`, `execution_backend="local"`, and `placement="server"` — a private per-invocation SQLite database plus one CLI-owned worker process, with no broker, port, or extra dependency. Keep that shape for tests, development, and small single-process deployments only.

Process-local `"memory"` storage must be asked for explicitly, together with a placement that shares the process:

```python
from litestar_queues import QueueConfig, WorkerConfig

config = QueueConfig(queue_backend="memory", worker=WorkerConfig(placement="asgi"))
```

Storage, execution, and placement combinations that cannot work are rejected at startup with a message naming the fix, rather than failing at first claim.

### Task Options, Scheduling, and Uniqueness

```python
from datetime import timedelta

from litestar_queues import QueueEventActor, QueueService, RetryBackoff, non_retryable, task


@task(
    "reports.render",
    queue="reports",
    priority=10,
    retries=3,
    retry_backoff=RetryBackoff(initial_delay=2.0, multiplier=2.0, max_delay=60.0),
    timeout=120,
    run_after=30,
    expires_in=timedelta(minutes=30),
    unique_by="arguments",
    unique_until="terminal",
    actor=QueueEventActor(type="service", id="reports-worker", name="Reports Worker"),
)
async def render_report(report_id: str, *, format: str = "pdf") -> str:
    if report_id == "invalid":
        non_retryable("Report ID does not exist")
    return f"{report_id}.{format}"


@task("reports.refresh", interval=timedelta(minutes=15), jitter=30, retries=2)
async def refresh_reports() -> None:
    pass


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

In addition to `await queue_service.enqueue(render_report, ...)` (the primary DI pattern in route handlers), decorated tasks expose `await render_report.enqueue(report_id)` and `await render_report.using(priority=20, run_after=60).enqueue(report_id)`. `Task.enqueue()` uses the active default `QueueService` registered by `QueuePlugin`, or falls back to an inline `"memory"` + `"immediate"` service when called in unit tests with no application wired. `result.record` holds the `QueuedTaskRecord` returned at enqueue time.

When enqueueing against an external execution backend such as Cloud Tasks, catch `QueueDispatchError` (`from litestar_queues.exceptions import QueueDispatchError`) and inspect `exc.committed`: when `True`, the record (`exc.task_id`) is already durably committed in SQL and bounded maintenance will repair the lost delivery.

Identity precedence is strict:

1. Explicit enqueue `key`.
2. Configured task `key`.
3. `unique_by="task"`.
4. `unique_by="arguments"`.
5. No identity.

`unique_until="terminal"` is the default and releases the identity after completion, failure, or cancellation. `unique_until="forever"` stores a permanent reservation until `await queue_service.reset_task_identity(effective_key)` removes it.

Do not combine a configured `key` with `unique_by`. Do not set `unique_until="forever"` without a configured `key` or `unique_by`. Use `QueueConfig.max_argument_identity_bytes` to bound canonical payloads hashed by `unique_by="arguments"`.

Use `interval` or five-field `cron`, never both. Recurring tasks inherit configured `retries` on startup and succession, and persisted occurrences retain their retry budget and backoff until completion. Use `task_modules=("app.domain.reports.jobs",)`, `discover_tasks("app.domain", "jobs")`, or `AutowirePlugin(AutowireConfig(domain_packages=["app.domain"], integrations=["dishka", "queues"]))` before string enqueueing or schedule initialization.

To mark a failure permanent and bypass retries, call `non_retryable("message")` or raise `NonRetryableError`. To cooperatively cancel execution from within a handler, call `job_cancelled("message")` or raise `JobCancelledError`. Calling `await queue_service.cancel_task(task_id, include_running=True)` cancels any active remote provider execution (Cloud Run Jobs or Cloud Tasks) first before writing durable cancellation state.

### Dependency Injection and Error Sanitization

Supply attempt-scoped dependencies to task handlers through `task_dependency_resolver` or `task_dependency_provider`:

```python
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any

from litestar_queues import QueueConfig, Task, TaskExecutionContext, QueuedTaskRecord


@asynccontextmanager
async def provide_task_dependencies(
    task: Task[Any, Any],
    record: QueuedTaskRecord,
    context: TaskExecutionContext,
) -> AsyncIterator[Mapping[str, Any]]:
    yield {"attempt_id": str(record.id)}


def sanitize_task_error(exc: BaseException, record: QueuedTaskRecord) -> str:
    return "An internal error occurred during task processing"


queue_config = QueueConfig(
    queue_backend="sqlspec",
    task_dependency_provider=provide_task_dependencies,
    error_sanitizer=sanitize_task_error,
    stale_requeue_priority="preserve",
)
```

`task_dependency_provider` enters an async context manager for each attempt, merges the yielded mapping into task keyword arguments, and guarantees clean exit on success, error, timeout, or cancellation.

When the application uses **Dishka**, task handlers can either receive dependencies from `task_dependency_provider` or resolve an async `Scope.REQUEST` container that reuses an active in-process request container (`request_container_var.get()`) when running inline and opens a fresh worker scope when running in an external worker:

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dishka import AsyncContainer, Scope

from app.config.ioc import get_worker_container, request_container_var


@asynccontextmanager
async def resolve_task_container() -> AsyncIterator[AsyncContainer]:
    active = request_container_var.get()
    if active is not None:
        yield active
        return
    container = get_worker_container()
    async with container(scope=Scope.REQUEST) as request_container:
        token = request_container_var.set(request_container)
        try:
            yield request_container
        finally:
            request_container_var.reset(token)
```

`error_sanitizer` converts a raw exception into the task's persisted error string.

`stale_requeue_priority` controls priority on stale task recovery (`"preserve"`, an `int`, or a `Callable[[int], int]`).

### Worker Configuration, Role-Aware Factory, and CLI

```python
from typing import Any, Literal

from litestar.connection import ASGIConnection
from litestar.exceptions import PermissionDeniedException

from litestar_queues import (
    CloudTasksExecutionConfig,
    EventDeliveryConfig,
    EventHistoryConfig,
    EventStreamConfig,
    QueueConfig,
    QueueEventsConfig,
    WorkerConfig,
)
from litestar_queues.backends.sqlspec import SQLSpecBackendConfig, SQLSpecWorkerWakeupConfig

RuntimeRole = Literal["web", "consumer", "cli"]


def deny_cloud_tasks_delivery_guard(connection: ASGIConnection[Any, Any, Any, Any], _: Any) -> None:
    raise PermissionDeniedException("Cloud Tasks push delivery is disabled on this runtime role")


def create_queue_config(
    *,
    sqlspec_config: Any,
    channels_backend: Any,
    target: Literal["local", "cloudtasks"] = "local",
    role: RuntimeRole = "web",
) -> QueueConfig:
    is_consumer = role == "consumer"
    use_cloud_tasks = target == "cloudtasks"
    execution_backend: Literal["local"] | CloudTasksExecutionConfig = (
        CloudTasksExecutionConfig(
            project_id="my-gcp-project",
            location="us-central1",
            queue_id="app-tasks",
            service_url="https://consumer.example.com",
            service_account_email="tasks-invoker@my-gcp-project.iam.gserviceaccount.com",
            trust_platform_auth=is_consumer,
            guards=() if is_consumer else (deny_cloud_tasks_delivery_guard,),
        )
        if use_cloud_tasks
        else "local"
    )
    return QueueConfig(
        queue_backend=SQLSpecBackendConfig(
            sqlspec_config=sqlspec_config,
            queue_table_name="queue_task",
            event_history_table_name="queue_task_event_history",
            worker_wakeups=None if use_cloud_tasks else SQLSpecWorkerWakeupConfig(queue_table_name="event_queue"),
            manage_schema=False,
        ),
        execution_backend=execution_backend,
        worker=WorkerConfig(
            placement="asgi" if (target == "local" and role == "web") else "external",
            batch_size=10,
            max_concurrency=8,
            queue_concurrency={"high_priority": 4, "default": 4},
            queues=("high_priority", "default"),
            poll_interval=0.25,
            heartbeat_interval=30,
            heartbeat_miss_threshold=2,
            graceful_shutdown_timeout=60,
            requeue_on_shutdown=False,
        ),
        events=QueueEventsConfig(
            channels=channels_backend,
            delivery=EventDeliveryConfig(publish_task_channel=True, publish_global_lifecycle=True),
            stream=EventStreamConfig(path="/queues/events", transports={"sse", "websocket"}) if role == "web" else None,
            history=EventHistoryConfig(batch_size=1),
        ),
    )
```

```bash
LITESTAR_APP=app:app litestar queues run --queue default --max-concurrency 4 --drain-timeout 60
LITESTAR_APP=app:app litestar queues run-consumer --backend sqs --max-concurrency 4 --drain-timeout 60
LITESTAR_APP=app:app litestar queues status --json
LITESTAR_APP=app:app litestar queues scheduler-health --minutes 5
LITESTAR_APP=app:app litestar queues run-maintenance --json
```

`WorkerConfig.placement` decides which process owns the worker:

- `"server"` (the default): exactly one worker in the CLI server lifespan (`litestar run`).
- `"asgi"`: starts one worker per ASGI worker in the application lifespan (for example, when `target == "local" and role == "web"`).
- `"external"`: starts nothing automatically; managed processes run `litestar queues run` or `litestar queues run-consumer` (or receive push deliveries on `role == "consumer"`).

Mount `EventStreamConfig` only on the `"web"` role (`None` on `"consumer"` and `"cli"`), and harden `CloudTasksExecutionConfig` by enabling `trust_platform_auth=is_consumer` and attaching a deny guard when `not is_consumer`.

The worker adaptively backs off empty polling from `poll_interval` toward `poll_backoff_max`, using `poll_backoff_multiplier` and `poll_jitter`. Backend notifications can end the wait early; they never replace polling or durable state checks.

### Backend Selection

Queue backends own persistence:

| Existing stack or need | Queue backend | Import |
| --- | --- | --- |
| Default; dev and single-invocation apps | `"ephemeral"` | Core package (stdlib `sqlite3`) |
| Process-local tests, shared-process placement only | `"memory"` (`InMemoryQueueBackend`) | Core package (`litestar_queues`) |
| SQLSpec-managed SQL persistence | `SQLSpecBackendConfig(...)` | `litestar_queues.backends.sqlspec` |
| Advanced Alchemy / SQLAlchemy models | `SQLAlchemyBackendConfig(...)` | `litestar_queues.backends.advanced_alchemy` |
| Existing Redis infrastructure | `RedisBackendConfig(...)` | `litestar_queues.backends.redis` |
| Existing Valkey infrastructure | `ValkeyBackendConfig(...)` | `litestar_queues.backends.valkey` |

Execution backends decide where a claimed task runs, and never own queue state:

| Need | Execution backend | Import |
| --- | --- | --- |
| Default in-process workers | `"local"` | Core package |
| Inline completion in tests/scripts | `"immediate"` | Core package |
| Isolated Google Cloud Run Jobs | `CloudRunExecutionConfig(...)` | `litestar_queues.execution.cloudrun` |
| Serverless delivery with no worker process | `CloudTasksExecutionConfig(...)` | `litestar_queues.execution.cloudtasks` |
| Apache Kafka continuous consumer fleet | `KafkaExecutionConfig(...)` | `litestar_queues.execution.kafka` |
| GCP Pub/Sub continuous consumer fleet | `PubSubExecutionConfig(...)` | `litestar_queues.execution.pubsub` |
| RabbitMQ continuous consumer fleet (Python 3.11+) | `RabbitMQExecutionConfig(...)` | `litestar_queues.execution.rabbitmq` |
| Amazon SQS continuous consumer fleet | `SqsExecutionConfig(...)` | `litestar_queues.execution.sqs` |

Match the project's existing data stack. Memory cannot coordinate separate processes and has no `MemoryBackendConfig` class — pass `queue_backend="memory"` or an `InMemoryQueueBackend` instance. See [Execution Backends](references/execution-backends.md) for the managed transports.

### SQLSpec Backend

Choose between **migration-managed** (`manage_schema=False`) and **auto-managed** (`manage_schema=True`) SQLSpec schema strategies:

```python
from sqlspec.adapters.asyncpg import AsyncpgConfig

from litestar_queues import QueueConfig
from litestar_queues.backends.sqlspec import SQLSpecBackendConfig, SQLSpecWorkerWakeupConfig
from litestar_queues.backends.sqlspec.extension import configure_queue_migration_extension

sqlspec_config = AsyncpgConfig(
    connection_config={"dsn": "postgresql://postgres:postgres@127.0.0.1:5432/app"},
    migration_config={
        "script_location": "migrations",
        "include_extensions": ["events", "litestar_queues"],
    },
    extension_config={
        "events": {"queue_table_name": "event_queue"},
    },
)
configure_queue_migration_extension(
    sqlspec_config,
    queue_table_name="queue_task",
    event_history_enabled=True,
    event_history_table_name="queue_task_event_history",
)

migration_managed_config = QueueConfig(
    queue_backend=SQLSpecBackendConfig(
        sqlspec_config=sqlspec_config,
        queue_table_name="queue_task",
        event_history_table_name="queue_task_event_history",
        worker_wakeups=SQLSpecWorkerWakeupConfig(queue_table_name="event_queue"),
        manage_schema=False,
    ),
    execution_backend="local",
)

auto_managed_config = QueueConfig(
    queue_backend=SQLSpecBackendConfig(
        sqlspec_config=AsyncpgConfig(
            connection_config={"dsn": "postgresql://postgres:postgres@127.0.0.1:5432/app"},
        ),
        manage_schema=True,
    ),
    execution_backend="local",
)
```

When `manage_schema=True` (the default), `QueuePlugin` registers the consolidated `0001_create_queue_tasks` migration revision (including `dispatch_checked_at`) with the supplied SQLSpec configuration. When `manage_schema=False` (when SQLSpec migrations are owned directly on `AsyncpgConfig`), register `"litestar_queues"` in `migration_config={"include_extensions": ["events", "litestar_queues"]}` and wire `configure_queue_migration_extension(...)` (alongside `queue_migration_directory()`) from `litestar_queues.backends.sqlspec.extension`. Opening the backend never migrates the database; use `create_schema()` only for local bootstrap.

`SQLSpecBackendConfig.worker_wakeups` defaults to native wakeups (`SQLSpecWorkerWakeupConfig`). Capable PostgreSQL adapters use `notify_queue`, DuckDB uses `poll_queue`, and other adapters fall back to polling. Set `worker_wakeups=None` when using `CloudTasksExecutionConfig` (no polling worker exists). SQLSpec wakeup transports validate that their events queue table exists before first use and raise `QueueConfigurationError` when missing.

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

Use the application's Advanced Alchemy metadata and migration lifecycle. Compose the package mixins into adopter-owned models when custom bases, table names, or binds are required, then pass all matching model classes:

- `model_class`
- `event_history_model_class`
- `maintenance_model_class`
- `task_reservation_model_class`

Set `worker_wakeups=True` only for a supported PostgreSQL dialect.

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

SQL-backed deployments use queue records, maintenance coordination, and
forever-uniqueness reservations. Add durable event history only when
`QueueEventsConfig.history` is configured:

| Concern | Default table | Override setting (`SQLSpecBackendConfig`) |
| --- | --- | --- |
| Queue records | `queue_task` | `queue_table_name` |
| Distributed maintenance coordination | `queue_maintenance` | `maintenance_table_name` |
| Forever-uniqueness reservations | `queue_task_reservation` | `task_reservation_table_name` |
| Durable event history (when enabled) | `queue_task_event_history` | `event_history_table_name` |

SQLSpec's packaged `0001_create_queue_tasks` migration provisions the enabled tables and supports explicit table-name overrides and promoted event-history columns (`event_history_extra_columns`). Advanced Alchemy applications own equivalent models and Alembic migrations. Redis and Valkey use namespaced keys and require no SQL migration.

Do not delete the reservation table during ordinary task or event retention. Forever identities are removed only through `QueueService.reset_task_identity()`.

### Events, Logging, Progress, and Event History Queries

```python
from typing import Any

from litestar_queues import QueueConfig, get_current_task_context, task
from litestar_queues.events import (
    EventDeliveryConfig,
    EventHistoryConfig,
    EventHistoryExtraColumn,
    EventStreamConfig,
    QueueEventActor,
    QueueEventEntityRef,
    QueueEventQuery,
    QueueEventsConfig,
    beat,
    create_event_producer,
    publish_task_event,
)

queue_config = QueueConfig(
    events=QueueEventsConfig(
        channels=channels_backend,
        delivery=EventDeliveryConfig(
            publish_task_channel=True,
            publish_global_lifecycle=True,
        ),
        stream=EventStreamConfig(
            path="/queues/events",
            transports={"sse", "websocket"},
        ),
        history=EventHistoryConfig(
            batch_size=1,
            strict=True,
            max_pending=2000,
            extra_columns=(EventHistoryExtraColumn("tenant_id", "metadata.tenant_id", indexed=True),),
        ),
    ),
)


async def emit_progress(
    current: int,
    total: int | None,
    *,
    message: str,
    stage: str | None = None,
    entity: QueueEventEntityRef | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    context = get_current_task_context()
    if context is not None:
        await context.progress(
            current,
            total,
            message=message,
            stage=stage,
            entity=entity,
            payload=payload,
        )


async def emit_log(
    message: str,
    *,
    level: str = "info",
    stage: str | None = None,
    entity: QueueEventEntityRef | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    context = get_current_task_context()
    if context is not None:
        await context.log(
            message,
            level=level,
            stage=stage,
            entity=entity,
            payload=payload,
        )


@task("imports.process", timeout=300)
async def process_import(path: str, tenant_id: str) -> None:
    beat("validating")
    entity = QueueEventEntityRef(type="import", id=path, name=path)
    actor = QueueEventActor(type="tenant", id=tenant_id)
    await emit_log("Import started", stage="validating", entity=entity, payload={"path": path})
    await emit_progress(50, 100, message="Halfway", stage="importing", entity=entity)
    if get_current_task_context() is not None:
        await publish_task_event(
            "custom.checkpoint",
            message="Checkpoint reached",
            scope_key=f"tenant:{tenant_id}",
            actor=actor,
            entity=entity,
        )
```

`QueueEventsConfig` groups live `delivery`, application `stream`, and durable `history`. It must enable at least one capability. Task events are separate from worker wakeups.

- **Context-safe emission (`get_current_task_context()`):** Wrap `await context.progress(...)` and `await context.log(...)` in helpers that check `if context is not None:` so `@task` functions execute identically inside queue workers and when called directly in unit tests or CLI commands.
- **Attribution & entities:** Set attempt-scoped default attribution via `@task(..., actor=...)` (`QueueEventActor` or callable) or `TaskExecutionContext.actor`, and override `actor=`, `entity=` (`QueueEventEntityRef`), or `scope_key=` per `publish_task_event`, `publish_task_log`, or `publish_task_progress` call.
- **Durable history queries & stage summaries:** Retrieve the active event log with `event_log = queue_service.get_event_log()`, query persisted events through `await event_log.query_events(QueueEventQuery(task_id=str(record.id), event_type="task.log", order="desc", limit=50), extra={"tenant_id": tenant_id})` (`OffsetPagination[QueueEventLogRecord]`), and aggregate stage durations with `await event_log.summarize_stages(QueueEventQuery(task_id=str(record.id)))` (`list[QueueEventStageSummary]`). Custom `QueueEventLog` implementations must define `publish_event_after_commit()` and `aclose()`.
- **Standalone event producer:** Use `async with create_event_producer(queue_config) as producer:` (alongside `bind_task_context` and `bind_beat_sink`) to emit task events from external processes without starting a full worker or Litestar app.

### Observability and Telemetry

```python
from litestar_queues import QueueConfig
from litestar_queues.observability import ObservabilityConfig

queue_config = QueueConfig(
    queue_backend="sqlspec",
    observability=ObservabilityConfig(
        enable_otel=True,
        enable_prometheus=True,
        enable_sqlcommenter=True,
    ),
    scheduler_canary_task="health.canary",
)
```

`ObservabilityConfig` configures OpenTelemetry tracing and Prometheus metrics. OpenTelemetry trace contexts and correlation IDs propagate across dispatchers, broker execution backends, and workers.

The scheduler health command (`litestar queues scheduler-health --minutes 5`) verifies that the configured canary task completed within the specified window.

### Bounded Maintenance

```python
from litestar_queues import QueueConfig, QueueMaintenanceConfig
from litestar_queues.events import QueueEventQuery, QueueEventRetentionRule

queue_config = QueueConfig(
    queue_backend="sqlspec",
    maintenance=QueueMaintenanceConfig(
        time_budget=300,
        coordination_timeout=360,
        external_limit=100,
        stale_after=900,
        stale_limit=100,
        terminal_retention=30 * 24 * 60 * 60,
        terminal_limit=1000,
        event_retention_rules=(
            QueueEventRetentionRule(
                max_age=7 * 24 * 60 * 60,
                match=QueueEventQuery(event_type="task.log"),
            ),
        ),
        event_limit=1000,
    ),
)
```

```bash
LITESTAR_APP=app:app litestar queues run-maintenance --json
LITESTAR_APP=app:app litestar queues run-maintenance --phase stale --phase terminal
```

One maintenance invocation runs bounded phases in fixed order: external reconciliation (`external_limit`, default `100`), stale recovery, terminal retention, then event retention (`event_retention_rules`). Custom CLI commands can also run phases programmatically via `await QueueMaintenanceService(service, maintenance_config).run(phases=["external", "stale"])` (`from litestar_queues.maintenance import QueueMaintenanceService`) and inspect `summary.outcome` (`"completed"`, `"already_running"`, `"partial"`, or `"failed"`). It never starts a worker, executes queued work, or loops to drain a backlog. Exhausting `time_budget` or reaching `external_limit` reports a `"partial"` outcome (`exit code 2`).

Schedule one external six-hour or daily invocation. Retention phases have no destructive defaults: `stale_after`, `terminal_retention`, and `event_retention_rules` remain disabled when `None` or empty. `coordination_timeout` must exceed `time_budget`.

### External One-Task Execution

```bash
QUEUES_TASK_ID=4d821c46-8c60-4ec3-b884-3f62eb71a03e \
QUEUES_CONFIG_FACTORY=app.queue:create_queue_config \
LITESTAR_QUEUES_TASK_MODULES=app.tasks \
litestar queues run-task
```

`run-task` claims and executes one existing record for an external executor (such as Cloud Run Jobs), reading `QUEUES_TASK_ID`, `QUEUES_CONFIG_FACTORY`, and `LITESTAR_QUEUES_TASK_MODULES` (or `<NAMESPACE>_TASK_MODULES`) by default. `--task-id`, `--config-factory`, and `--task-modules` override those environment variables for manual operation. It is not a standalone worker loop.

### Background Responses

```python
from litestar import Response, post
from litestar_queues import QueuedBackgroundTask, task


@task("imports.process")
async def process_import(path: str) -> None:
    pass


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
3. **Pick execution placement.** Use local workers by default, immediate execution for tests/scripts, broker consumers (Kafka, PubSub, RabbitMQ, SQS) for distributed broker dispatch, Cloud Tasks for serverless push delivery, and Cloud Run for isolated external jobs.
4. **Configure the worker.** Put every worker setting under `WorkerConfig`; decide explicitly whether it runs in the app lifespan.
5. **Provision persistent storage.** Run SQLSpec migrations or add all required Advanced Alchemy models to application-owned migrations.
6. **Define and discover tasks.** Decorate callables with `@task`; import their modules before string enqueueing or schedule initialization.
7. **Enqueue through DI.** Inject `QueueService`, enqueue a decorated task or registered name, and wait only when the caller truly needs the terminal state.
8. **Add optional capabilities separately.** Configure worker wakeups, task-event delivery/history, permanent uniqueness, observability, and maintenance only when their storage and operational lifecycles are owned.
9. **Place operational commands.** Run standalone workers or continuous broker consumers (`run-consumer`) continuously, `run-task` only in external one-task executors, and maintenance from one infrequent external schedule.

</workflow>

<guardrails>

## Guardrails

- **Use `SQLAlchemyBackendConfig` for Advanced Alchemy persistence.** Import it from `litestar_queues.backends.advanced_alchemy`.
- **Use `queue_table_name` on `SQLSpecBackendConfig`.** Do not pass the removed `table_name` parameter.
- **Configure events with `QueueEventsConfig`.** Add `EventDeliveryConfig`, `EventStreamConfig`, and/or `EventHistoryConfig` for the required capabilities.
- **Do not pass flat worker fields to `QueueConfig`.** Use `QueueConfig(worker=WorkerConfig(...))`.
- **Do not use `memory` across processes or look for `MemoryBackendConfig`.** Pass `queue_backend="memory"` or `InMemoryQueueBackend`; it cannot coordinate standalone workers or a separate maintenance command.
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

- [ ] The dependency floor is `litestar-queues>=0.12.0`
- [ ] `QueuePlugin` receives one `QueueConfig`
- [ ] Worker options live under `QueueConfig.worker`
- [ ] `WorkerConfig.placement` matches the deployment topology
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
- [ ] `run`, `run-consumer`, `run-task`, and `run-maintenance` are used for their distinct lifecycles

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
        placement="external",
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

- **[Execution Backends](references/execution-backends.md)** — local, immediate, Cloud Run, Cloud Tasks, Kafka, Pub/Sub, RabbitMQ, SQS, delivery fencing, and lost-delivery repair.
- **[Namespacing and Expiry](references/namespacing.md)** — `namespace=`, not-started deadlines and the `expired` state, event-stream configuration.

## Cross-References

- **[litestar](../litestar/SKILL.md)** — Litestar app setup, plugin lists, DI, and lifespan.
- **[Litestar routing](../litestar/references/handlers.md)** — Route handlers and controllers for enqueue endpoints.
- **[Litestar DI](../litestar/references/di-and-dishka.md)** — `NamedDependency` and service injection.
- **[Litestar plugins](../litestar/references/plugins.md)** — Plugin initialization and lifecycle.
- **[litestar-autowire](../litestar-autowire/SKILL.md)** — Optional task discovery through Autowire integration.
- **[Litestar Channels & SSE](../litestar/references/channels-and-sse.md)** — Channels, SSE, WebSockets, and task-event fan-out.
- **[litestar-testing](../litestar-testing/SKILL.md)** — Application and handler tests.
- **[sqlspec](../sqlspec/SKILL.md)** — SQLSpec adapter and migration configuration.
- **[advanced-alchemy](../advanced-alchemy/SKILL.md)** — SQLAlchemy models, services, and Alembic ownership.

## Official References

- <https://github.com/cofin/litestar-queues/tree/v0.12.0>
- <https://github.com/cofin/litestar-queues/releases/tag/v0.12.0>
- <https://github.com/cofin/litestar-queues/blob/v0.12.0/src/litestar_queues/config.py>
- <https://github.com/cofin/litestar-queues/blob/v0.12.0/src/litestar_queues/task.py>
- <https://github.com/cofin/litestar-queues/blob/v0.12.0/src/litestar_queues/_cli.py>
- <https://github.com/cofin/litestar-queues/blob/v0.12.0/src/litestar_queues/backends/sqlspec/config.py>
- <https://github.com/cofin/litestar-queues/blob/v0.12.0/src/litestar_queues/backends/advanced_alchemy/config.py>
- <https://github.com/cofin/litestar-queues/blob/v0.12.0/src/litestar_queues/maintenance.py>

## Shared Styleguide Baseline

- Use shared styleguides for generic language/framework rules to reduce duplication in this skill.
- [General Principles](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [Litestar](../litestar-styleguide/references/litestar.md)
- Keep this skill focused on `litestar-queues` workflows, backend selection, worker placement, uniqueness, maintenance, and task-event APIs.
