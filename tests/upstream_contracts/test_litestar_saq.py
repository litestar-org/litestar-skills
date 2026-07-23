from importlib.metadata import version

import pytest
from litestar.exceptions import ImproperlyConfiguredException
from litestar_saq import QueueConfig


def test_litestar_saq_080_requires_exactly_one_connection_source() -> None:
    assert version("litestar-saq") == "0.8.0"
    with pytest.raises(ImproperlyConfiguredException, match="either `dsn` or `broker_instance`"):
        QueueConfig()
    with pytest.raises(ImproperlyConfiguredException, match="both `dsn` and `broker_instance`"):
        QueueConfig(dsn="redis://localhost", broker_instance=object())
    assert QueueConfig(dsn="redis://localhost").name == "default"
