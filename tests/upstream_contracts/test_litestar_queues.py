import dataclasses
from importlib.metadata import version

import litestar_queues
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
    TaskExecutionContext,
    TaskExitCode,
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
from litestar_queues.backends.redis.config import RedisBackendConfig
from litestar_queues.backends.sqlspec.config import SQLSpecBackendConfig, SQLSpecWorkerWakeupConfig
from litestar_queues.backends.sqlspec.extension import (
    configure_queue_migration_extension,
    queue_migration_directory,
)
from litestar_queues.backends.valkey.config import ValkeyBackendConfig
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
    sqlspec_backend = SQLSpecBackendConfig()
    assert sqlspec_backend.manage_schema is True
    assert sqlspec_backend.queue_table_name is None
    assert sqlspec_backend.event_history_table_name is None
    assert sqlspec_backend.maintenance_table_name is None
    assert sqlspec_backend.task_reservation_table_name is None
    assert isinstance(sqlspec_backend.worker_wakeups, SQLSpecWorkerWakeupConfig)
    assert callable(configure_queue_migration_extension)
    assert queue_migration_directory().is_dir()
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
    assert TaskExecutionContext is not None
    assert TaskExitCode is not None
    assert QueuedBackgroundTask is not None
    assert ScheduleConfig is not None
    assert RetryBackoff is not None
    assert QueuePlugin is not None
    assert QueueService is not None
