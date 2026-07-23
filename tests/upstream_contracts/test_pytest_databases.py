import inspect
from importlib.metadata import version

from pytest_databases._service import DockerService
from pytest_databases.docker import postgres


def test_pytest_databases_019_provider_and_port_contract() -> None:
    assert version("pytest-databases") == "0.19.0"
    assert "host_port" in inspect.signature(DockerService.run).parameters
    for release in range(11, 19):
        assert hasattr(postgres, f"postgres_{release}_service")
    for release in range(13, 19):
        assert hasattr(postgres, f"pgvector_{release}_service")
    assert inspect.unwrap(postgres.postgres_image)() == "postgres:18"
