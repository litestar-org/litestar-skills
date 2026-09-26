import inspect
from importlib.metadata import version
from pathlib import Path

import litestar_vite
import litestar_vite.inertia
from litestar import Litestar, get
from litestar.config.csrf import CSRFConfig
from litestar_vite import (
    DeployConfig,
    ExternalDevServer,
    HTMLEntryResolutionError,
    InertiaConfig,
    InertiaSSRConfig,
    PathConfig,
    RuntimeConfig,
    StaticPlacement,
    StaticServerConfig,
    StaticServerMount,
    TypeGenConfig,
    ViteAssetLoader,
    ViteConfig,
    VitePlugin,
)
from litestar_vite.cli import vite_group
from litestar_vite.codegen import generate_routes_json, generate_routes_ts
from litestar_vite.config import InertiaTypeGenConfig, LoggingConfig, PaginationContainer, SPAConfig
from litestar_vite.inertia import PrecognitionResponse


def test_litestar_vite_031_config_contract() -> None:
    """Verify litestar-vite 0.31.0 version and config contracts."""
    assert version("litestar-vite") == "0.31.0"
    config = ViteConfig()
    assert config.mode == "template"
    assert config.enabled is None
    assert config.exclude_static_from_auth is True
    assert config.include_root_spa_paths is False

    sig_params = set(inspect.signature(ViteConfig).parameters)
    expected_params = {
        "mode",
        "paths",
        "runtime",
        "types",
        "inertia",
        "spa",
        "logging",
        "deploy",
        "static_props",
        "dev_mode",
        "base_url",
        "enabled",
        "guards",
        "exclude_static_from_auth",
        "spa_path",
        "include_root_spa_paths",
    }
    assert expected_params.issubset(sig_params)

    spa_cfg = SPAConfig()
    assert spa_cfg.inject_csrf is True
    assert spa_cfg.csrf_var_name == "__LITESTAR_CSRF__"
    assert spa_cfg.app_selector == "#app"
    assert spa_cfg.cache_transformed_html is True
    assert spa_cfg.cache_duration == 0

    log_cfg = LoggingConfig()
    assert log_cfg.show_paths_absolute is False
    assert log_cfg.suppress_npm_output is False
    assert log_cfg.suppress_vite_banner is False
    assert log_cfg.timestamps is False

    deploy_cfg = DeployConfig()
    assert deploy_cfg.enabled is True
    assert isinstance(config.deploy, DeployConfig)
    assert config.deploy.enabled is False
    assert deploy_cfg.include_manifest is True
    assert deploy_cfg.delete_orphaned is True
    overridden = deploy_cfg.with_overrides(
        storage_backend="s3://bucket/assets",
        delete_orphaned=False,
        asset_url="https://cdn.example.com/",
    )
    assert overridden.enabled is True
    assert overridden.storage_backend == "s3://bucket/assets"
    assert overridden.delete_orphaned is False
    assert overridden.asset_url == "https://cdn.example.com/"

    typegen_cfg = TypeGenConfig()
    assert typegen_cfg.generate_sdk is True
    assert typegen_cfg.generate_zod is False
    assert typegen_cfg.generate_routes is True
    assert typegen_cfg.generate_schemas is True
    assert typegen_cfg.generate_page_props is True
    assert typegen_cfg.global_route is False
    assert typegen_cfg.fallback_type == "unknown"

    assert inspect.isclass(PaginationContainer)


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


def test_litestar_vite_031_static_server_and_html_entry_contract(tmp_path: Path) -> None:
    """Verify Granian static server config and secondary HTML entry resolution contracts."""
    bundle_dir = tmp_path / "public"
    bundle_dir.mkdir()
    manifest_file = bundle_dir / "manifest.json"
    manifest_file.write_text("{}", encoding="utf-8")
    entry_file = bundle_dir / "widget.html"
    entry_file.write_text("<html><body>widget</body></html>", encoding="utf-8")

    cfg = ViteConfig(
        mode="spa",
        dev_mode=False,
        paths=PathConfig(root=tmp_path, bundle_dir=bundle_dir, asset_url="/static/"),
        runtime=RuntimeConfig(set_static_folders=True),
        exclude_static_from_auth=True,
    )
    plugin = VitePlugin(config=cfg)
    static_cfg = plugin.get_static_server_config()
    assert isinstance(static_cfg, StaticServerConfig)
    assert static_cfg.placement == StaticPlacement.NATIVE
    assert len(static_cfg.mounts) >= 1
    assert isinstance(static_cfg.mounts[0], StaticServerMount)

    loader = ViteAssetLoader(config=cfg)
    resolved = loader.resolve_html_entry_sync("resources/widget.html", production_path=entry_file)
    assert "widget" in resolved

    missing_file = bundle_dir / "missing.html"
    try:
        loader.resolve_html_entry_sync("resources/missing.html", production_path=missing_file)
        raise AssertionError("Expected HTMLEntryResolutionError")
    except HTMLEntryResolutionError:
        pass


def test_litestar_vite_031_csrf_routes_ts_and_cli_contract() -> None:
    """Verify CSRF constant emission in routes.ts and CLI command registration."""

    @get("/items", name="items:list")
    async def list_items() -> dict[str, int]:
        return {"count": 1}

    csrf_token_key = "".join(("test", "-csrf-key"))
    app = Litestar(
        route_handlers=[list_items],
        csrf_config=CSRFConfig(secret=csrf_token_key, cookie_name="custom_csrf", header_name="x-custom-csrf"),
    )

    routes_ts = generate_routes_ts(app)
    assert "export const CSRF_COOKIE_NAME = 'custom_csrf';" in routes_ts
    assert "export const CSRF_HEADER_NAME = 'x-custom-csrf';" in routes_ts

    routes_json = generate_routes_json(app, only=["items:list"])
    assert "items:list" in routes_json["routes"]

    commands_dict: dict[str, object] = getattr(vite_group, "commands", {})
    expected_cli_commands = {
        "init",
        "install",
        "update",
        "serve",
        "build",
        "deploy",
        "generate-types",
        "export-routes",
        "doctor",
        "status",
    }
    assert expected_cli_commands.issubset(set(commands_dict.keys()))
