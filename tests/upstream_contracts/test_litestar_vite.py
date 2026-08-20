import inspect
from importlib.metadata import version

import litestar_vite
import litestar_vite.inertia
from litestar_vite import (
    ExternalDevServer,
    InertiaConfig,
    InertiaSSRConfig,
    RuntimeConfig,
    ViteConfig,
)
from litestar_vite.config import InertiaTypeGenConfig
from litestar_vite.inertia import PrecognitionResponse


def test_litestar_vite_031_config_contract() -> None:
    """Verify litestar-vite 0.31.0 version and config contracts."""
    assert version("litestar-vite") == "0.31.0"
    config = ViteConfig()
    assert config.mode == "template"
    assert config.enabled is None
    assert "enabled" in inspect.signature(ViteConfig).parameters
    assert "logging" in inspect.signature(ViteConfig).parameters
    assert "spa" in inspect.signature(ViteConfig).parameters
    assert "deploy" in inspect.signature(ViteConfig).parameters


def test_litestar_vite_031_exports_and_classes() -> None:
    """Verify all top-level and config exports are present."""
    expected_top_exports = {
        "DeployConfig",
        "ExternalDevServer",
        "HTMLEntryResolutionError",
        "InertiaConfig",
        "InertiaSSRConfig",
        "PathConfig",
        "RuntimeConfig",
        "StaticPlacement",
        "StaticServerConfig",
        "StaticServerMount",
        "TypeGenConfig",
        "ViteAssetLoader",
        "ViteConfig",
        "VitePlugin",
        "inertia",
    }
    assert expected_top_exports.issubset(set(litestar_vite.__all__))


def test_litestar_vite_031_inertia_exports() -> None:
    """Verify inertia module exports and helper signatures."""
    expected_inertia_exports = {
        "AlwaysProp",
        "InertiaBack",
        "InertiaConfig",
        "InertiaDetails",
        "InertiaExternalRedirect",
        "InertiaHeaders",
        "InertiaMiddleware",
        "InertiaPlugin",
        "InertiaRedirect",
        "InertiaRequest",
        "InertiaResponse",
        "OnceProp",
        "OptionalProp",
        "PrecognitionResponse",
        "PropFilter",
        "always",
        "clear_history",
        "create_inertia_exception_response",
        "create_precognition_exception_handler",
        "defer",
        "error",
        "except_",
        "exception_to_http_response",
        "extract_deferred_props",
        "extract_merge_props",
        "extract_once_props",
        "flash",
        "get_shared_props",
        "helpers",
        "lazy",
        "merge",
        "normalize_validation_errors",
        "once",
        "only",
        "optional",
        "precognition",
        "scroll_props",
        "share",
    }
    assert expected_inertia_exports.issubset(set(litestar_vite.inertia.__all__))


def test_litestar_vite_031_inertia_config_and_precognition_contract() -> None:
    """Verify Inertia config, type-generation, SSR, and Precognition contracts."""
    config = InertiaConfig()
    assert config.root_template == "index.html"
    assert config.component_opt_keys == ("component", "page")
    assert config.encrypt_history is False
    assert config.precognition is False
    assert config.use_script_element is True

    assert InertiaTypeGenConfig().include_default_auth is True
    assert InertiaTypeGenConfig().include_default_flash is True

    ssr = InertiaSSRConfig()
    assert ssr.url == "http://127.0.0.1:13714/render"
    assert ssr.health_check is False
    assert ssr.health_check_timeout == 10.0

    response = PrecognitionResponse()
    assert response.status_code == 204
    assert response.headers["Precognition-Success"] == "true"


def test_litestar_vite_031_mode_normalization() -> None:
    """Verify mode alias normalization in ViteConfig."""
    assert ViteConfig(mode="htmx").mode == "template"
    assert ViteConfig(mode="inertia").mode == "hybrid"
    assert ViteConfig(mode="ssr").mode == "framework"
    assert ViteConfig(mode="ssg").mode == "framework"
    ext_server = ExternalDevServer(target="http://127.0.0.1:3000")
    cfg_ext = ViteConfig(mode="external", runtime=RuntimeConfig(external_dev_server=ext_server))
    assert cfg_ext.mode == "framework"
