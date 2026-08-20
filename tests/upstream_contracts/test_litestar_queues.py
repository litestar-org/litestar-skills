import dataclasses
from importlib.metadata import version

from litestar_queues import (
    CloudRunExecutionConfig,
    CloudTasksExecutionConfig,
    EventBufferConfig,
    EventDeliveryConfig,
    EventHistoryConfig,
    EventStreamConfig,
    JobCancelledError,
    KafkaExecutionConfig,
    NonRetryableError,
    PubSubExecutionConfig,
    QueueConfig,
    QueueEventsConfig,
    QueueMaintenanceConfig,
    QueuePlugin,
    QueueService,
    RabbitMQExecutionConfig,
    RetryBackoff,
    ScheduleConfig,
    SqsExecutionConfig,
    WorkerConfig,
    job_cancelled,
    list_execution_backends,
    list_queue_backends,
    non_retryable,
    task,
)
from litestar_queues._cli import queues_group
from litestar_queues.backends.advanced_alchemy.config import SQLAlchemyBackendConfig
from litestar_queues.backends.redis.config import RedisBackendConfig
from litestar_queues.backends.sqlspec.config import SQLSpecBackendConfig, SQLSpecWorkerWakeupConfig
from litestar_queues.backends.valkey.config import ValkeyBackendConfig
from litestar_queues.observability import ObservabilityConfig


def test_litestar_queues_090_contract() -> None:
    """Verify litestar-queues 0.9.0 package metadata, configs, and CLI contract."""
    assert version("litestar-queues") == "0.9.0"

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
    sqlspec_backend = SQLSpecBackendConfig()
    assert sqlspec_backend.manage_schema is True
    assert isinstance(sqlspec_backend.worker_wakeups, SQLSpecWorkerWakeupConfig)
    assert RedisBackendConfig().worker_wakeups is True
    assert ValkeyBackendConfig().worker_wakeups is True

    assert QueueEventsConfig is not None
    assert QueueMaintenanceConfig is not None
    assert ObservabilityConfig is not None
    assert {"enable_otel", "enable_prometheus", "enable_sqlcommenter"} <= {
        field.name for field in dataclasses.fields(ObservabilityConfig)
    }
    assert EventBufferConfig is not None
    assert EventDeliveryConfig is not None
    assert EventStreamConfig is not None
    assert EventHistoryConfig is not None

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

    assert issubclass(NonRetryableError, Exception)
    assert issubclass(JobCancelledError, Exception)
    assert callable(non_retryable)
    assert callable(job_cancelled)
    assert callable(task)
    assert ScheduleConfig is not None
    assert RetryBackoff is not None
    assert QueuePlugin is not None
    assert QueueService is not None
