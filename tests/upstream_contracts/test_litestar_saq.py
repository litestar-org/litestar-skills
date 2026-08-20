from importlib.metadata import version

import pytest
from litestar.exceptions import ImproperlyConfiguredException
from litestar_saq import (
    Job,
    QueueConfig,
    SAQConfig,
    SAQPlugin,
    TaskQueues,
    Worker,
    monitored_job,
)
from litestar_saq import cli as saq_cli
from litestar_saq import controllers as saq_controllers


def test_litestar_saq_080_contract() -> None:
    """Verify litestar-saq 0.8.0 package metadata, configs, CLI, and decorators."""
    assert version("litestar-saq") == "0.8.0"

    with pytest.raises(ImproperlyConfiguredException, match="either `dsn` or `broker_instance`"):
        QueueConfig()
    with pytest.raises(ImproperlyConfiguredException, match="both `dsn` and `broker_instance`"):
        QueueConfig(dsn="redis://localhost", broker_instance=object())

    queue_config = QueueConfig(dsn="redis://localhost")
    assert queue_config.name == "default"
    assert queue_config.concurrency == 10
    assert queue_config.separate_process is True
    assert queue_config.multiprocessing_mode == "multiprocessing"
    assert queue_config.broker_options == {}

    saq_config = SAQConfig(queue_configs=[queue_config])
    assert saq_config.queues_dependency_key == "task_queues"
    assert saq_config.worker_processes == 1
    assert saq_config.web_enabled is False
    assert saq_config.web_path == "/saq"
    assert saq_config.web_include_in_schema is False
    assert saq_config.use_server_lifespan is False

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

    controller_cls = saq_controllers.build_controller(url_base="/saq", include_in_schema_=False)  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
    assert getattr(controller_cls, "tags") == ["SAQ"]  # noqa: B009
    assert getattr(controller_cls, "include_in_schema") is False  # noqa: B009

    assert callable(monitored_job)
    with pytest.raises(ValueError, match="Heartbeat interval must be positive"):
        monitored_job(interval=0)
    with pytest.raises(ValueError, match="Heartbeat interval must be positive"):
        monitored_job(interval=-1.0)
