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
from litestar_saq.exceptions import ImproperConfigurationError
from saq.job import TERMINAL_STATUSES, UNSUCCESSFUL_TERMINAL_STATUSES, Status


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
    assert PostgresQueueOptions is not None
    assert RedisQueueOptions is not None
    assert HeartbeatManager is not None
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

    with pytest.raises(ImportError):
        QueueConfig(dsn="redis://localhost", startup="litestar_saq.hooks.startup_logger")

    queue_config = QueueConfig(
        dsn="redis://localhost",
        startup=["litestar_saq.hooks.startup_logger"],
        shutdown=shutdown_logger,
    )
    assert queue_config.name == "default"
    assert queue_config.concurrency == 10
    assert queue_config.separate_process is True
    assert queue_config.multiprocessing_mode == "multiprocessing"
    assert queue_config.broker_options == {}
    assert queue_config.broker_instance_options == {}
    assert queue_config.startup == [startup_logger]
    assert queue_config.shutdown == [shutdown_logger]

    cron_job = CronJob(
        function="litestar_saq.hooks.startup_logger",
        cron="*/15 * * * *",
        timeout=120,
    )
    assert cron_job.function is startup_logger
    assert cron_job.meta == {}

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

    build_controller_fn = vars(saq_controllers)["build_controller"]
    controller_cls = build_controller_fn(url_base="/saq", include_in_schema_=False)
    assert controller_cls.tags == ["SAQ"]
    assert controller_cls.include_in_schema is False

    assert callable(monitored_job)
    with pytest.raises(ValueError, match="Heartbeat interval must be positive"):
        monitored_job(interval=0)
    with pytest.raises(ValueError, match="Heartbeat interval must be positive"):
        monitored_job(interval=-1.0)

    assert {Status.COMPLETE, Status.FAILED, Status.ABORTED} == set(TERMINAL_STATUSES)
    assert {Status.FAILED, Status.ABORTED} == set(UNSUCCESSFUL_TERMINAL_STATUSES)
