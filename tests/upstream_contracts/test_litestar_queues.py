from importlib.metadata import version

from litestar_queues import QueueConfig, QueueEventsConfig, QueueMaintenanceConfig, WorkerConfig
from litestar_queues._cli import queues_group
from litestar_queues.backends.advanced_alchemy.config import SQLAlchemyBackendConfig


def test_litestar_queues_080_nested_config_and_cli_contract() -> None:
    assert version("litestar-queues") == "0.8.0"
    config = QueueConfig()
    assert config.worker == WorkerConfig()
    assert config.worker.placement == "server"
    assert SQLAlchemyBackendConfig().worker_wakeups is False
    assert QueueEventsConfig is not None
    assert QueueMaintenanceConfig is not None
    assert set(queues_group.commands) == {
        "run",
        "run-consumer",
        "status",
        "scheduler-health",
        "run-task",
        "run-maintenance",
    }
