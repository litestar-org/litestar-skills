# Backends, Worker Configuration, Events, and Maintenance

## Dependency Injection and Error Sanitization

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

`error_sanitizer` converts a raw exception into the task's persisted error string. `stale_requeue_priority` controls priority on stale task recovery (`"preserve"`, an `int`, or a `Callable[[int], int]`).

## Worker Configuration, Role-Aware Factory, and CLI

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

## SQLSpec Backend

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

When `manage_schema=True` (the default), `QueuePlugin` registers the consolidated `0001_create_queue_tasks` migration revision (including `dispatch_checked_at`) with the supplied SQLSpec configuration. When `manage_schema=False`, register `"litestar_queues"` in `migration_config={"include_extensions": ["events", "litestar_queues"]}` and wire `configure_queue_migration_extension(...)` from `litestar_queues.backends.sqlspec.extension`.

`SQLSpecBackendConfig.worker_wakeups` defaults to native wakeups (`SQLSpecWorkerWakeupConfig`). Capable PostgreSQL adapters use `notify_queue`, DuckDB uses `poll_queue`, and other adapters fall back to polling. Set `worker_wakeups=None` when using `CloudTasksExecutionConfig`.

## Advanced Alchemy Backend

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

Compose mixins from `litestar_queues.backends.advanced_alchemy` into adopter-owned models when custom bases, table names, or binds are required:

- `model_class` (`QueueTaskModelMixin`, default `QueueTaskModel`)
- `event_history_model_class` (`QueueEventHistoryModelMixin`, default `QueueEventHistoryModel`)
- `maintenance_model_class` (`QueueMaintenanceModelMixin`, default `QueueMaintenanceModel`)
- `task_reservation_model_class` (`QueueTaskReservationModelMixin`, default `QueueTaskReservationModel`)

## Redis and Valkey Backends

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

Use `ValkeyBackendConfig` from `litestar_queues.backends.valkey` for Valkey.

## Events, Logging, Progress, and Event History Queries

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
        event_payload = dict(payload or {})
        if stage is not None:
            event_payload["stage"] = stage
        await context.progress(
            current=current,
            total=total,
            message=message,
            entity=entity,
            payload=event_payload,
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
        event_payload = dict(payload or {})
        if stage is not None:
            event_payload["stage"] = stage
        await context.log(
            message,
            level=level,
            entity=entity,
            payload=event_payload,
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

## Observability and Bounded Maintenance

```python
from litestar_queues import QueueConfig, QueueMaintenanceConfig
from litestar_queues.events import QueueEventQuery, QueueEventRetentionRule
from litestar_queues.observability import ObservabilityConfig

queue_config = QueueConfig(
    queue_backend="sqlspec",
    observability=ObservabilityConfig(
        enable_otel=True,
        enable_prometheus=True,
        enable_sqlcommenter=True,
    ),
    scheduler_canary_task="health.canary",
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
