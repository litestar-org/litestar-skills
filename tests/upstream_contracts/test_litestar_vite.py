import inspect
from importlib.metadata import version

from litestar_vite import ViteConfig


def test_litestar_vite_027_config_contract() -> None:
    assert version("litestar-vite") == "0.27.0"
    config = ViteConfig()
    assert config.mode == "template"
    assert config.enabled is None
    assert "enabled" in inspect.signature(ViteConfig).parameters
    assert "logging" in inspect.signature(ViteConfig).parameters
