import dataclasses
import inspect
from importlib.metadata import version

import litestar_saq
import pytest
from litestar.exceptions import ImproperlyConfiguredException
from litestar_saq import (
    OPENTELEMETRY_INSTALLED,
    CronJob,
    HeartbeatManager,
    Job,
    PostgresQueueOptions,
    QueueConfig,
    RedisQueueOptions,
    SAQConfig,
    SAQPlugin,
    TaskQueues,
    Worker,
    after_process_logger,
    before_process_logger,
    monitored_job,
    shutdown_logger,
    startup_logger,
    timing_after_process,
    timing_before_process,
)
from litestar_saq import cli as saq_cli
from litestar_saq import controllers as saq_controllers
from litestar_saq import decorators as saq_decorators
from litestar_saq import instrumentation as saq_instrumentation
from litestar_saq import typing as saq_typing
from litestar_saq.exceptions import ImproperConfigurationError
from saq.job import ACTIVE_STATUSES, TERMINAL_STATUSES, UNSUCCESSFUL_TERMINAL_STATUSES, Status
from saq.queue.postgres import PostgresQueue
from saq.types import Context, PartialTimersDict, TimersDict


def test_litestar_saq_080_contract() -> None:
    """Verify litestar-saq 0.8.0 and saq 0.26.4 metadata, exports, configs, CLI, and decorators."""
    assert version("litestar-saq") == "0.8.0"
    assert version("saq") == "0.26.4"

    expected_exports = {
        "OPENTELEMETRY_INSTALLED",
        "CronJob",
        "HeartbeatManager",
        "Job",
        "PostgresQueueOptions",
        "QueueConfig",
        "RedisQueueOptions",
        "SAQConfig",
        "SAQPlugin",
        "TaskQueues",
        "Worker",
        "after_process_logger",
        "before_process_logger",
        "monitored_job",
        "shutdown_logger",
        "startup_logger",
        "timing_after_process",
        "timing_before_process",
    }
    assert set(litestar_saq.__all__) == expected_exports
    assert isinstance(OPENTELEMETRY_INSTALLED, bool)
    assert set(PostgresQueueOptions.__annotations__) == {
        "versions_table",
        "jobs_table",
        "stats_table",
        "min_size",
        "max_size",
        "saq_lock_keyspace",
        "priorities",
        "swept_error_message",
        "manage_pool_lifecycle",
    }
    assert set(RedisQueueOptions.__annotations__) == {
        "max_concurrent_ops",
        "swept_error_message",
    }
    pg_init_params = set(inspect.signature(PostgresQueue.__init__).parameters)
    assert {
        "pool",
        "url",
        "name",
        "versions_table",
        "jobs_table",
        "stats_table",
        "min_size",
        "max_size",
        "saq_lock_keyspace",
        "priorities",
        "swept_error_message",
        "manage_pool_lifecycle",
    } <= pg_init_params
    assert HeartbeatManager is not None
    assert callable(saq_instrumentation.InstrumentedQueue)
    assert callable(saq_instrumentation.inject_trace_context)
    assert saq_typing.Context is not Context
    assert set(Context.__annotations__) == {"worker", "job", "queue", "exception"}
    assert set(TimersDict.__annotations__) == {"schedule", "worker_info", "sweep", "abort"}
    assert issubclass(PartialTimersDict, dict)
    assert all(
        callable(hook)
        for hook in (
            startup_logger,
            shutdown_logger,
            before_process_logger,
            after_process_logger,
            timing_before_process,
            timing_after_process,
        )
    )

    with pytest.raises(ImproperlyConfiguredException, match="either `dsn` or `broker_instance`"):
        QueueConfig()
    with pytest.raises(ImproperlyConfiguredException, match="both `dsn` and `broker_instance`"):
        QueueConfig(dsn="redis://localhost", broker_instance=object())

    invalid_pg_config = QueueConfig(dsn="postgres://localhost/db")
    with pytest.raises(ImproperlyConfiguredException, match="Invalid broker type"):
        invalid_pg_config.get_broker()

    valid_pg_config = QueueConfig(
        dsn="postgresql://localhost/db",
        broker_options=PostgresQueueOptions(
            jobs_table="custom_jobs",
            stats_table="custom_stats",
            versions_table="custom_versions",
        ),
    )
    pg_broker = valid_pg_config.get_broker()
    pg_queue = SAQConfig(queue_configs=[valid_pg_config]).get_queues().get("default")
    assert valid_pg_config.broker_type == "postgres"
    assert valid_pg_config.queue_class is PostgresQueue
    assert isinstance(pg_queue, PostgresQueue)
    assert pg_broker.kwargs.get("autocommit") is True
    assert valid_pg_config.broker_options.get("manage_pool_lifecycle") is True
    assert valid_pg_config.broker_options.get("jobs_table") == "custom_jobs"

    with pytest.raises(ImportError):
        QueueConfig(dsn="redis://localhost", startup="litestar_saq.hooks.startup_logger")
    with pytest.raises(ImportError):
        QueueConfig(dsn="redis://localhost", shutdown="litestar_saq.hooks.shutdown_logger")
    with pytest.raises(ImportError):
        QueueConfig(dsn="redis://localhost", before_process="litestar_saq.hooks.before_process_logger")
    with pytest.raises(ImportError):
        QueueConfig(dsn="redis://localhost", after_process="litestar_saq.hooks.after_process_logger")

    queue_config = QueueConfig(
        dsn="redis://localhost",
        startup=["litestar_saq.hooks.startup_logger"],
        shutdown=shutdown_logger,
        before_process=["litestar_saq.hooks.before_process_logger"],
        after_process=["litestar_saq.hooks.after_process_logger"],
    )
    assert queue_config.name == "default"
    assert queue_config.concurrency == 10
    assert queue_config.separate_process is True
    assert queue_config.multiprocessing_mode == "multiprocessing"
    assert queue_config.broker_options == {}
    assert queue_config.broker_instance_options == {}
    assert queue_config.startup == [startup_logger]
    assert queue_config.shutdown == [shutdown_logger]
    assert queue_config.before_process == [before_process_logger]
    assert queue_config.after_process == [after_process_logger]

    cron_job = CronJob(
        function="litestar_saq.hooks.startup_logger",
        cron="*/15 * * * *",
        timeout=120,
    )
    assert cron_job.function is startup_logger
    assert cron_job.meta == {}

    job_fields = {f.name: f.default for f in dataclasses.fields(Job)}
    assert job_fields["timeout"] == 10
    assert job_fields["heartbeat"] == 0
    assert job_fields["retries"] == 1
    assert job_fields["ttl"] == 600
    assert job_fields["retry_delay"] == 0.0
    assert job_fields["retry_backoff"] is False
    assert job_fields["scheduled"] == 0
    assert job_fields["priority"] == 0
    assert job_fields["group_key"] is None

    saq_config = SAQConfig(queue_configs=[queue_config])
    assert saq_config.queues_dependency_key == "task_queues"
    assert saq_config.worker_processes == 1
    assert saq_config.web_enabled is False
    assert saq_config.web_path == "/saq"
    assert saq_config.web_include_in_schema is False
    assert saq_config.use_server_lifespan is False
    assert saq_config.enable_otel is None
    assert saq_config.otel_tracer_name == "litestar_saq"
    assert saq_config.should_enable_otel() is False

    queue_config.broker_instance = object()
    spawn_copy = saq_cli.prepare_config_for_spawn(saq_config)
    spawn_queue_config = next(iter(spawn_copy.queue_configs))
    assert spawn_queue_config.broker_instance is None
    assert queue_config.broker_instance is not None

    custom_broker_qc = QueueConfig(name="custom", broker_instance=object())
    with pytest.raises(ImproperlyConfiguredException, match="Invalid broker type"):
        _ = custom_broker_qc.broker_type

    broker_only_config = SAQConfig(queue_configs=[custom_broker_qc])
    with pytest.raises(ImproperConfigurationError, match="Multi-process worker spawning requires a `dsn`"):
        saq_cli.prepare_config_for_spawn(broker_only_config)

    plugin = SAQPlugin(config=saq_config)
    assert plugin.config is saq_config

    otel_queue_config = QueueConfig(dsn="postgresql://localhost/db", metadata={"region": "us-east-1"})
    default_otel_plugin = SAQPlugin(config=SAQConfig(queue_configs=[otel_queue_config], enable_otel=None))
    default_worker = default_otel_plugin.get_workers()["default"]
    assert vars(default_worker)["_enable_otel"] is False
    assert default_worker.get_structlog_context() == {
        "worker_id": default_worker.id,
        "queue_name": "default",
        "concurrency": 10,
        "separate_process": True,
        "worker_meta_region": "us-east-1",
    }

    if OPENTELEMETRY_INSTALLED:
        enabled_otel_plugin = SAQPlugin(
            config=SAQConfig(
                queue_configs=[QueueConfig(dsn="postgresql://localhost/db")],
                enable_otel=True,
                otel_tracer_name="custom_tracer",
            )
        )
        assert vars(enabled_otel_plugin.get_workers()["default"])["_enable_otel"] is True
    else:
        with pytest.raises(ImproperlyConfiguredException, match="enable_otel=True"):
            SAQConfig(enable_otel=True).should_enable_otel()

    hb_init_params = inspect.signature(HeartbeatManager.__init__).parameters
    assert hb_init_params["flush_interval"].default == 30.0
    worker_init_fn = vars(Worker)["__init__"]
    worker_init_params = inspect.signature(worker_init_fn).parameters
    assert worker_init_params["enable_heartbeat_manager"].default is True
    assert worker_init_params["heartbeat_flush_interval"].default == 30.0
    assert worker_init_params["enable_otel"].default is False
    assert worker_init_params["shutdown_grace_period_s"].default is None
    assert worker_init_params["cancellation_hard_deadline_s"].default is None
    assert worker_init_params["poll_interval"].default is None

    assert set(saq_instrumentation.__all__) == {
        "InstrumentedQueue",
        "create_process_span",
        "end_process_span",
        "extract_trace_context",
        "get_tracer",
        "inject_trace_context",
    }

    namespace = saq_config.signature_namespace
    assert namespace["TaskQueues"] is TaskQueues
    assert namespace["Job"] is Job
    assert namespace["Worker"] is Worker

    task_queues = TaskQueues(queues={})
    with pytest.raises(ImproperlyConfiguredException, match="Could not find the specified queue"):
        task_queues.get("nonexistent")

    cli_app = saq_cli.build_cli_app()
    assert cli_app.name == "workers"
    assert set(cli_app.commands.keys()) == {"run", "status"}
    run_opts = {opt for param in cli_app.commands["run"].params for opt in param.opts}
    assert {"--workers", "--queues", "-v", "--verbose", "-d", "--debug"} <= run_opts
    assert "--process" not in run_opts

    build_controller_fn = vars(saq_controllers)["build_controller"]
    controller_cls = build_controller_fn(url_base="/saq", include_in_schema_=False)
    assert controller_cls.tags == ["SAQ"]
    assert controller_cls.include_in_schema is False
    for handler_name in ("queue_list", "queue_detail", "job_detail", "job_retry", "job_abort", "health", "index"):
        assert hasattr(controller_cls, handler_name)

    assert callable(monitored_job)
    assert saq_decorators.MIN_HEARTBEAT_INTERVAL == 1.0
    assert saq_decorators.DEFAULT_HEARTBEAT_INTERVAL == 5.0
    calculate_interval_fn = vars(saq_decorators)["_calculate_interval"]
    assert calculate_interval_fn(Job(function="task", heartbeat=120), None) == 60.0
    assert calculate_interval_fn(Job(function="task", heartbeat=0), None) == 5.0
    assert calculate_interval_fn(Job(function="task", heartbeat=1), None) == 1.0
    assert calculate_interval_fn(Job(function="task", heartbeat=120), 15.0) == 15.0
    with pytest.raises(ValueError, match="Heartbeat interval must be positive"):
        monitored_job(interval=0)
    with pytest.raises(ValueError, match="Heartbeat interval must be positive"):
        monitored_job(interval=-1.0)

    assert {Status.NEW, Status.QUEUED, Status.ACTIVE} == set(ACTIVE_STATUSES)
    assert {Status.COMPLETE, Status.FAILED, Status.ABORTED} == set(TERMINAL_STATUSES)
    assert {Status.FAILED, Status.ABORTED} == set(UNSUCCESSFUL_TERMINAL_STATUSES)
