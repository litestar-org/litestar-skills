from importlib.metadata import version

import pytest
from litestar_autowire import (
    AutowireConfig,
    AutowireIntegration,
    AutowireLoader,
    clear_autowire_cache,
)


def test_litestar_autowire_020_config_and_error_contract() -> None:
    assert version("litestar-autowire") == "0.2.0"
    config = AutowireConfig(domain_packages="app.domain")
    assert config.domain_packages == ("app.domain",)
    assert config.controller_modules == ("controllers", "routes", "controller", "route")
    with pytest.raises(TypeError, match="renamed to integrations"):
        AutowireConfig(extensions=["dishka"])
    with pytest.raises(ValueError, match="Unsupported Autowire integration"):
        AutowireConfig(integrations=["unknown"])
    assert all(symbol is not None for symbol in (AutowireIntegration, AutowireLoader, clear_autowire_cache))
