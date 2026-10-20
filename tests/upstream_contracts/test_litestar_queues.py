import asyncio
import dataclasses
import inspect
from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from importlib.metadata import version
from typing import Any

import litestar_queues
import pytest
from litestar_queues import (
    CloudRunExecutionConfig,
    CloudTasksExecutionConfig,
    EventBufferConfig,
    EventDeliveryConfig,
    EventHistoryConfig,
    EventStreamConfig,
    InMemoryQueueBackend,
    JobCancelledError,
    KafkaExecutionConfig,
    NonRetryableError,
    PubSubExecutionConfig,
    QueueConfig,
    QueueConfigurationError,
    QueuedBackgroundTask,
    QueueDispatchError,
    QueuedTaskRecord,
    QueueEventActor,
    QueueEventEntityRef,
    QueueEventLogRecord,
    QueueEventsConfig,
    QueueEventStageSummary,
    QueueMaintenanceConfig,
    QueueMaintenanceService,
    QueueMaintenanceSummary,
    QueuePlugin,
    QueueService,
    RabbitMQExecutionConfig,
    RetryBackoff,
    ScheduleConfig,
    SqsExecutionConfig,
    Task,
    TaskDependencyProvider,
    TaskDependencyResolver,
    TaskExecutionContext,
    TaskExitCode,
    TaskReservation,
    TaskStatus,
    Worker,
    WorkerConfig,
    consume_one,
    discover_tasks,
    get_current_task_context,
    job_cancelled,
    list_execution_backends,
    list_queue_backends,
    non_retryable,
    publish_task_event,
    publish_task_log,
    publish_task_progress,
    require_current_task_context,
    run_task,
    task,
)
from litestar_queues._cli import queues_group
from litestar_queues.backends.advanced_alchemy import (
    QueueEventHistoryModel,
    QueueEventHistoryModelMixin,
    QueueMaintenanceModel,
    QueueMaintenanceModelMixin,
    QueueTaskModel,
    QueueTaskModelMixin,
    QueueTaskReservationModel,
    QueueTaskReservationModelMixin,
    SQLAlchemyBackendConfig,
)
from litestar_queues.backends.redis import RedisBackendConfig
from litestar_queues.backends.valkey import ValkeyBackendConfig
from litestar_queues.events import (
    EventHistoryExtraColumn,
    QueueEvent,
    QueueEventProducer,
    QueueEventQuery,
    QueueEventRetentionRule,
    bind_beat_sink,
    bind_task_context,
    create_event_producer,
)
from litestar_queues.events._log_records import event_log_record_from_event
from litestar_queues.observability import ObservabilityConfig
from litestar_queues.task import clear_task_registry, get_default_service


def test_litestar_queues_0120_contract() -> None:
    """Verify litestar-queues 0.12.0 package metadata, configs, and CLI contract."""
    assert version("litestar-queues") == "0.12.0"

    config = QueueConfig()
    assert config.worker == WorkerConfig()
    assert config.worker.placement == "server"
    assert config.queue_backend == "ephemeral"
    assert config.execution_backend == "local"
    assert config.stale_requeue_priority == "preserve"
    assert {
        "task_dependency_resolver",
        "task_dependency_provider",
        "error_sanitizer",
        "observability",
        "stale_requeue_priority",
    } <= {field.name for field in dataclasses.fields(QueueConfig)}

    assert SQLAlchemyBackendConfig().worker_wakeups is False
    assert QueueTaskModel is not None
    assert QueueTaskModelMixin is not None
    assert QueueEventHistoryModel is not None
    assert QueueEventHistoryModelMixin is not None
    assert QueueMaintenanceModel is not None
    assert QueueMaintenanceModelMixin is not None
    assert QueueTaskReservationModel is not None
    assert QueueTaskReservationModelMixin is not None
    try:
        from litestar_queues.backends.sqlspec import (
            SQLSpecBackendConfig,
            SQLSpecWorkerWakeupConfig,
        )
        from litestar_queues.backends.sqlspec.extension import (
            configure_queue_migration_extension,
            queue_migration_directory,
        )

        sqlspec_backend = SQLSpecBackendConfig()
        assert sqlspec_backend.manage_schema is True
        assert sqlspec_backend.queue_table_name is None
        assert sqlspec_backend.event_history_table_name is None
        assert sqlspec_backend.maintenance_table_name is None
        assert sqlspec_backend.task_reservation_table_name is None
        assert isinstance(sqlspec_backend.worker_wakeups, SQLSpecWorkerWakeupConfig)
        assert callable(configure_queue_migration_extension)
        assert queue_migration_directory().is_dir()
    except ImportError:
        pass
    assert RedisBackendConfig().worker_wakeups is True
    assert ValkeyBackendConfig().worker_wakeups is True
    assert InMemoryQueueBackend is not None

    assert QueueEventsConfig is not None
    assert QueueMaintenanceConfig is not None
    maintenance_config = QueueMaintenanceConfig()
    assert maintenance_config.external_limit == 100
    assert maintenance_config.event_retention_rules == ()
    assert QueueMaintenanceService is not None
    assert QueueMaintenanceSummary is not None
    assert ObservabilityConfig is not None
    assert {"enable_otel", "enable_prometheus", "enable_sqlcommenter"} <= {
        field.name for field in dataclasses.fields(ObservabilityConfig)
    }
    assert EventBufferConfig is not None
    assert EventDeliveryConfig is not None
    assert EventStreamConfig is not None
    assert EventHistoryConfig is not None
    history_config = EventHistoryConfig()
    assert history_config.strict is False
    assert history_config.max_pending == 2000
    assert history_config.extra_columns == ()
    assert EventHistoryExtraColumn is not None
    assert QueueEventActor is not None
    assert QueueEventEntityRef is not None
    assert QueueEventLogRecord is not None
    assert QueueEventProducer is not None
    assert QueueEventQuery is not None
    assert QueueEventRetentionRule is not None
    assert QueueEventStageSummary is not None
    assert callable(create_event_producer)
    assert callable(bind_task_context)
    assert callable(bind_beat_sink)
    assert callable(get_current_task_context)
    assert callable(require_current_task_context)
    assert callable(publish_task_event)
    assert callable(publish_task_log)
    assert callable(publish_task_progress)

    sample_event = QueueEvent(
        type="task.progress",
        scope="task",
        task_id="task-1",
        task_name="imports.process",
        progress_current=50,
        progress_total=100,
        progress_percent=50.0,
        payload={"stage": "importing", "duration_ms": 120.0},
    )
    history_record = event_log_record_from_event(sample_event)
    assert history_record.stage == "importing"
    assert history_record.duration_ms == 120.0

    record_fields = {field.name for field in dataclasses.fields(QueuedTaskRecord)}
    assert "dispatch_checked_at" in record_fields

    assert set(list_queue_backends()) == {
        "advanced-alchemy",
        "ephemeral",
        "memory",
        "redis",
        "sqlspec",
        "valkey",
    }
    assert set(list_execution_backends()) == {
        "cloudrun",
        "cloudtasks",
        "immediate",
        "kafka",
        "local",
        "pubsub",
        "rabbitmq",
        "sqs",
    }
    assert set(queues_group.commands) == {
        "run",
        "run-consumer",
        "status",
        "scheduler-health",
        "run-task",
        "run-maintenance",
    }

    assert KafkaExecutionConfig is not None
    assert PubSubExecutionConfig is not None
    assert RabbitMQExecutionConfig is not None
    assert SqsExecutionConfig is not None
    assert CloudRunExecutionConfig is not None
    assert CloudTasksExecutionConfig is not None

    for non_existent_symbol in (
        "AdvancedAlchemyAsyncBackendConfig",
        "AdvancedAlchemySyncBackendConfig",
        "MemoryBackendConfig",
        "CloudRunExecutorConfig",
        "JobStatus",
        "TaskPriority",
        "BackoffStrategy",
        "ConcurrencyLock",
        "RateLimit",
        "Schedule",
    ):
        assert not hasattr(litestar_queues, non_existent_symbol)

    assert issubclass(NonRetryableError, Exception)
    assert issubclass(JobCancelledError, Exception)
    assert issubclass(QueueConfigurationError, Exception)
    assert issubclass(QueueDispatchError, Exception)
    assert callable(non_retryable)
    assert callable(job_cancelled)
    assert callable(task)
    assert callable(discover_tasks)
    assert callable(consume_one)
    assert callable(run_task)
    assert Task is not None
    assert TaskDependencyProvider is not None
    assert TaskDependencyResolver is not None
    assert TaskExecutionContext is not None
    assert TaskExitCode is not None
    assert TaskReservation is not None
    assert TaskStatus is not None
    assert Worker is not None
    assert QueuedBackgroundTask is not None
    assert ScheduleConfig is not None
    assert RetryBackoff is not None
    assert QueuePlugin is not None
    assert QueueService is not None

    enqueue_sig = inspect.signature(QueueService.enqueue)
    keyword_only_params = {
        name for name, param in enqueue_sig.parameters.items() if param.kind == inspect.Parameter.KEYWORD_ONLY
    }
    assert keyword_only_params == {
        "scheduled_at",
        "run_after",
        "expires_in",
        "expires_at",
        "key",
        "queue",
        "priority",
        "retries",
        "timeout",
        "execution_backend",
        "execution_profile",
        "description",
        "log_level",
        "log_success",
        "requeue_on_stale",
        "metadata",
    }


@pytest.mark.anyio
async def test_litestar_queues_enqueue_options_and_immediate_execution() -> None:
    """Verify Task.__call__, Task.enqueue reserved kwargs, and execution_backend='immediate'."""
    clear_task_registry()
    try:

        @task("accounts.sync", queue="accounts", retries=2, timeout=60)
        async def sync_account(account_id: str, *, user_tag: str = "standard") -> dict[str, str]:
            return {"account_id": account_id, "user_tag": user_tag}

        direct_result = await sync_account("acc-direct", user_tag="inline")
        assert direct_result == {"account_id": "acc-direct", "user_tag": "inline"}
        assert get_default_service() is None

        fallback_handle = await sync_account.enqueue(
            "acc-fallback",
            priority=7,
            description="fallback-run",
            metadata={"origin": "unit-test"},
            user_tag="vip",
        )
        assert fallback_handle.status == "completed"
        assert fallback_handle.result == {"account_id": "acc-fallback", "user_tag": "vip"}
        assert fallback_handle.record is not None
        assert fallback_handle.record.priority == 7
        assert fallback_handle.record.kwargs == {"user_tag": "vip"}
        assert fallback_handle.record.metadata["description"] == "fallback-run"
        assert fallback_handle.record.metadata["origin"] == "unit-test"

        cli_config = QueueConfig(
            queue_backend="memory",
            execution_backend="local",
            worker=WorkerConfig(placement="external"),
        )
        async with QueueService(cli_config) as service:
            cli_handle = await service.enqueue(
                sync_account,
                "acc-cli",
                execution_backend="immediate",
                user_tag="cli",
            )
            await cli_handle.refresh()
            assert cli_handle.status == "completed"
            assert cli_handle.result == {"account_id": "acc-cli", "user_tag": "cli"}
    finally:
        clear_task_registry()


@pytest.mark.anyio
async def test_litestar_queues_forever_uniqueness_and_reset_identity() -> None:
    """Verify unique_until='forever' reservations, collision handling, and reset_task_identity."""
    clear_task_registry()
    try:
        with pytest.raises(ValueError, match="configures both a key and unique_by"):

            @task("invalid.both", key="fixed-key", unique_by="task")
            async def _both() -> None:
                pass

        with pytest.raises(ValueError, match="without any identity"):

            @task("invalid.forever", unique_until="forever")
            async def _forever_without_identity() -> None:
                pass

        invocations: list[str] = []

        @task("bootstrap.seed", key="bootstrap:seed:v1", unique_until="forever")
        async def seed_database(region: str) -> str:
            invocations.append(region)
            return f"seeded:{region}"

        config = QueueConfig(
            queue_backend="memory",
            execution_backend="immediate",
            worker=WorkerConfig(placement="external"),
        )
        async with QueueService(config) as service:
            first = await service.enqueue(seed_database, "us-central1")
            await first.refresh()
            assert first.status == "completed"
            assert first.result == "seeded:us-central1"
            assert invocations == ["us-central1"]

            reservation = await service.get_task_identity("bootstrap:seed:v1")
            assert isinstance(reservation, TaskReservation)
            assert reservation.task_id == first.id

            second = await service.enqueue(seed_database, "europe-west1")
            assert second.id == first.id
            assert invocations == ["us-central1"]

            assert await service.reset_task_identity("bootstrap:seed:v1") is True
            assert await service.get_task_identity("bootstrap:seed:v1") is None

            third = await service.enqueue(seed_database, "europe-west1")
            await third.refresh()
            assert third.id != first.id
            assert third.status == "completed"
            assert third.result == "seeded:europe-west1"
            assert invocations == ["us-central1", "europe-west1"]
    finally:
        clear_task_registry()


@pytest.mark.anyio
async def test_litestar_queues_cooperative_cancellation_and_dependencies() -> None:
    """Verify dependency resolver vs provider mutual exclusivity and cooperative task cancellation."""
    clear_task_registry()
    try:

        async def _resolver(
            task: Task[Any, Any],
            record: QueuedTaskRecord,
            context: TaskExecutionContext,
        ) -> Mapping[str, object]:
            if "injected" not in task.signature.parameters:
                return {}
            return {"injected": f"resolved:{record.task_name}:{context.attempt}:{task.name}"}

        closed_attempts: list[str] = []

        @asynccontextmanager
        async def _provider(
            task: Task[Any, Any],
            record: QueuedTaskRecord,
            context: TaskExecutionContext,
        ) -> AsyncGenerator[Mapping[str, object], None]:
            try:
                if "injected" in task.signature.parameters:
                    yield {"injected": f"provided:{task.name}:{context.attempt}"}
                else:
                    yield {}
            finally:
                closed_attempts.append(str(record.id))

        with pytest.raises(QueueConfigurationError, match="task_dependency_resolver and task_dependency_provider"):
            QueueConfig(
                queue_backend="memory",
                worker=WorkerConfig(placement="external"),
                task_dependency_resolver=_resolver,
                task_dependency_provider=_provider,
            )

        @task("deps.check")
        async def check_dep(value: str, *, injected: str = "") -> str:
            return f"{value}|{injected}"

        resolver_config = QueueConfig(
            queue_backend="memory",
            execution_backend="immediate",
            worker=WorkerConfig(placement="external"),
            task_dependency_resolver=_resolver,
        )
        async with QueueService(resolver_config) as resolver_service:
            res_handle = await resolver_service.enqueue(check_dep, "alpha")
            await res_handle.refresh()
            assert res_handle.result == "alpha|resolved:deps.check:1:deps.check"

        started = asyncio.Event()
        observed_cancellation = asyncio.Event()

        @task("long.stream")
        async def run_stream() -> str:
            context = require_current_task_context()
            started.set()
            try:
                await context.wait_cancelled()
            finally:
                if context.is_cancelled:
                    observed_cancellation.set()
            context.raise_if_cancelled()
            return "unreachable"

        @task("long.cooperative")
        async def run_cooperative() -> str:
            context = require_current_task_context()
            context.mark_cancelled()
            await context.wait_cancelled()
            assert context.is_cancelled is True
            context.raise_if_cancelled()
            return "unreachable"

        provider_config = QueueConfig(
            queue_backend="memory",
            execution_backend="local",
            worker=WorkerConfig(
                placement="external",
                poll_interval=0.02,
                cancellation_poll_interval=0.02,
            ),
            task_dependency_provider=_provider,
        )
        async with QueueService(provider_config) as service:
            prov_handle = await service.enqueue(check_dep, "beta", execution_backend="immediate")
            await prov_handle.refresh()
            assert prov_handle.result == "beta|provided:deps.check:1"
            assert closed_attempts == [str(prov_handle.id)]

            coop_handle = await service.enqueue(run_cooperative, execution_backend="immediate")
            await coop_handle.refresh()
            assert coop_handle.status == "cancelled"
            assert str(coop_handle.id) in closed_attempts

            stream_handle = await service.enqueue(run_stream)
            worker = Worker(service, provider_config.worker)
            worker_task = asyncio.create_task(worker.start())
            try:
                await asyncio.wait_for(started.wait(), timeout=2.0)
                assert await service.cancel_task(stream_handle.id, include_running=True) is True
                assert await service.cancel_task(stream_handle.id, include_running=True) is False
                await asyncio.wait_for(observed_cancellation.wait(), timeout=2.0)
                await stream_handle.wait(timeout=2.0)
                assert stream_handle.status == "cancelled"
            finally:
                await worker.stop()
                await worker_task
            assert str(stream_handle.id) in closed_attempts
    finally:
        clear_task_registry()
