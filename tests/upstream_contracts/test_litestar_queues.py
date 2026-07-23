from importlib.metadata import version

from litestar_queues import QueueConfig, QueueEventsConfig, QueueMaintenanceConfig, WorkerConfig
from litestar_queues._cli import queues_group
from litestar_queues.backends.advanced_alchemy.config import SQLAlchemyBackendConfig


def test_litestar_queues_050_nested_config_and_cli_contract() -> None:
    assert version("litestar-queues") == "0.5.0"
    config = QueueConfig()
    assert config.worker == WorkerConfig()
    assert config.worker.run_in_app is True
    assert SQLAlchemyBackendConfig().worker_wakeups is False
    assert QueueEventsConfig is not None
    assert QueueMaintenanceConfig is not None
    assert set(queues_group.commands) == {
        "run",
        "status",
        "scheduler-health",
        "run-task",
        "run-maintenance",
    }
