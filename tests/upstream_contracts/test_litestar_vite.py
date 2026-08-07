import inspect
from importlib.metadata import version

from litestar_vite import ViteConfig


def test_litestar_vite_029_config_contract() -> None:
    assert version("litestar-vite") == "0.29.1"
    config = ViteConfig()
    assert config.mode == "template"
    assert config.enabled is None
    assert "enabled" in inspect.signature(ViteConfig).parameters
    assert "logging" in inspect.signature(ViteConfig).parameters
