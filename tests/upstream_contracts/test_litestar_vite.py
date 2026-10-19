import inspect
from importlib.metadata import version
from pathlib import Path

import litestar_vite
import litestar_vite.codegen
import litestar_vite.fragments
import litestar_vite.inertia
import litestar_vite.ipc
import litestar_vite.plugin
from litestar import Litestar, get
from litestar.config.csrf import CSRFConfig
from litestar_vite import (
    ComponentResponse,
    DeployConfig,
    ExternalDevServer,
    FragmentEngine,
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
    render_fragment,
)
from litestar_vite.cli import vite_group
from litestar_vite.codegen import (
    export_asyncapi,
    find_asyncapi_plugin,
    generate_routes_json,
    generate_routes_ts,
    normalize_asyncapi_document,
    resolve_asyncapi_document,
)
from litestar_vite.config import InertiaTypeGenConfig, LoggingConfig, PaginationContainer, SPAConfig
from litestar_vite.fragments import vite_fragment
from litestar_vite.html_transform import inject_inertia_ssr_tags
from litestar_vite.inertia import (
    InertiaBack,
    InertiaExternalRedirect,
    InertiaRedirect,
    InertiaRequest,
    InertiaResponse,
    PrecognitionResponse,
    always,
    clear_history,
    defer,
    error,
    except_,
    flash,
    lazy,
    merge,
    once,
    only,
    optional,
    precognition,
    scroll_props,
    share,
)
from litestar_vite.ipc import (
    BaseIPCTransport,
    CircuitState,
    SSRCircuitBreaker,
    StdioIPCTransport,
    TCPStreamIPCTransport,
)
from litestar_vite.plugin import (
    ProxyHeadersMiddleware,
    SSRProxyMiddleware,
    StaticFilesConfig,
    ViteProxyMiddleware,
    create_vite_hmr_handler,
)
from litestar_vite.scaffolding import FrameworkTemplate, TemplateContext, generate_project, get_available_templates
from litestar_vite.scaffolding.templates import FrameworkType, get_template


def test_litestar_vite_032_config_contract() -> None:
    """Verify litestar-vite 0.32.0 version and config contracts."""
    assert version("litestar-vite") == "0.32.0"
    config = ViteConfig()
    assert config.mode == "template"
    assert config.enabled is None
    assert config.static_props == {}
    assert config.dev_mode is False
    assert config.exclude_static_from_auth is True
    assert config.include_root_spa_paths is False

    path_cfg = PathConfig()
    assert path_cfg.bundle_dir == Path("public")
    assert path_cfg.resource_dir == Path("src")
    assert path_cfg.static_dir == Path("src/public")
    assert path_cfg.manifest_name == "manifest.json"
    assert path_cfg.hot_file == "hot"
    assert path_cfg.asset_url == "/static/"
    assert path_cfg.ssr_output_dir is None

    runtime_cfg = RuntimeConfig()
    assert runtime_cfg.dev_mode is False
    assert runtime_cfg.proxy_mode is None
    assert runtime_cfg.external_dev_server is None
    assert runtime_cfg.host == "127.0.0.1"
    assert runtime_cfg.port == 5173
    assert runtime_cfg.protocol == "http"
    assert runtime_cfg.executor == "node"
    assert runtime_cfg.is_react is False
    assert runtime_cfg.health_check is False
    assert runtime_cfg.detect_nodeenv is False
    assert runtime_cfg.set_environment is True
    assert runtime_cfg.set_static_folders is True
    assert runtime_cfg.spa_handler is True
    assert runtime_cfg.http2 is True
    assert runtime_cfg.csp_nonce is None
    assert runtime_cfg.trusted_proxies is None
    assert runtime_cfg.extra_route_prefixes == ()

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
    assert typegen_cfg.generate_channels is True
    assert typegen_cfg.asyncapi_path == Path("src/generated/asyncapi.json")
    assert typegen_cfg.channels_ts_path == Path("src/generated/channels.ts")
    assert typegen_cfg.global_route is False
    assert typegen_cfg.fallback_type == "unknown"

    assert inspect.isclass(PaginationContainer)


def test_litestar_vite_032_exports_and_classes() -> None:
    """Verify all top-level and config exports are present."""
    expected_top_exports = {
        "ComponentResponse",
        "DeployConfig",
        "ExternalDevServer",
        "FragmentEngine",
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
        "render_fragment",
    }
    assert expected_top_exports.issubset(set(litestar_vite.__all__))


def test_litestar_vite_032_inertia_exports() -> None:
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

    deferred = defer("stats", lambda: {"count": 1}, group="analytics").once()
    assert deferred.key == "stats"
    assert deferred.group == "analytics"

    merged_append = merge("items", [1, 2], strategy="append", match_on="id")
    merged_deep = merge("config", {"a": 1}, strategy="deep")
    assert merged_append.strategy == "append"
    assert merged_deep.strategy == "deep"

    assert always("auth", {"ok": True}).key == "auth"
    assert once("settings", {"theme": "dark"}).key == "settings"
    assert optional("comments", lambda: []).key == "comments"
    assert lazy("export", lambda: "csv").key == "export"
    scroll = scroll_props(page_name="page", current_page=1, next_page=2)
    assert scroll.page_name == "page"
    assert scroll.current_page == 1
    assert scroll.next_page == 2
    assert only("a", "b") is not None
    assert except_("c") is not None
    assert callable(flash)
    assert callable(share)
    assert callable(error)
    assert callable(clear_history)
    assert callable(precognition)
    assert inspect.isclass(InertiaResponse)
    assert inspect.isclass(InertiaRedirect)
    assert inspect.isclass(InertiaBack)
    assert inspect.isclass(InertiaExternalRedirect)
    assert inspect.isclass(InertiaRequest)
    assert hasattr(InertiaRequest, "is_inertia")
    assert hasattr(InertiaRequest, "inertia_enabled")
    assert hasattr(InertiaRequest, "inertia_version")
    assert hasattr(InertiaRequest, "is_partial_render")
    assert hasattr(InertiaRequest, "partial_keys")
    assert hasattr(InertiaRequest, "partial_except_keys")
    assert hasattr(InertiaRequest, "except_once_props_keys")
    assert hasattr(InertiaRequest, "reset_keys")
    assert hasattr(InertiaRequest, "error_bag")
    assert hasattr(InertiaRequest, "merge_intent")
    assert hasattr(InertiaRequest, "is_precognition")
    assert hasattr(InertiaRequest, "precognition_validate_only")


def test_litestar_vite_032_inertia_config_ssr_and_precognition_contract() -> None:
    """Verify Inertia config, type-generation, IPC SSR, circuit breaker, and Precognition contracts."""
    config = InertiaConfig()
    assert config.root_template == "index.html"
    assert config.component_opt_keys == ("component", "page")
    assert config.encrypt_history is False
    assert config.precognition is False
    assert config.use_script_element is True

    assert InertiaTypeGenConfig().include_default_auth is True
    assert InertiaTypeGenConfig().include_default_flash is True

    ssr = InertiaSSRConfig()
    assert ssr.enabled is True
    assert ssr.timeout == 2.0
    assert ssr.target_selector == "#app"
    assert ssr.command is None
    assert ssr.cwd is None
    assert ssr.fallback_to_client is True
    assert ssr.circuit_breaker_enabled is True
    assert ssr.circuit_breaker_failure_threshold == 3
    assert ssr.circuit_breaker_reset_timeout == 30.0
    assert not hasattr(ssr, "url")
    assert not hasattr(ssr, "health_check")

    response = PrecognitionResponse()
    assert response.status_code == 204
    assert response.headers["Precognition-Success"] == "true"


def test_litestar_vite_032_fragments_ipc_and_proxy_contract() -> None:
    """Verify 0.32.0 component fragments, IPC transports, circuit breaker, and proxy exports."""
    assert set(litestar_vite.fragments.__all__) == {
        "ComponentResponse",
        "FragmentEngine",
        "render_fragment",
        "vite_fragment",
    }
    assert render_fragment is vite_fragment

    comp_resp = ComponentResponse("resources/components/Counter.tsx", props={"initial": 5}, mode="island")
    assert comp_resp.component == "resources/components/Counter.tsx"
    assert comp_resp.props == {"initial": 5}
    assert comp_resp.mode == "island"
    assert inspect.isclass(FragmentEngine)

    expected_ipc_exports = {
        "BaseIPCTransport",
        "CircuitBreakerOpenError",
        "CircuitState",
        "IPCError",
        "IPCRequest",
        "IPCResponse",
        "IPCTimeoutError",
        "IPCWorkerCrashError",
        "SSRCircuitBreaker",
        "StdioIPCTransport",
        "TCPStreamIPCTransport",
    }
    assert expected_ipc_exports.issubset(set(litestar_vite.ipc.__all__))

    stdio_transport = StdioIPCTransport(command=["node", "ssr.js"])
    tcp_transport = TCPStreamIPCTransport()
    assert isinstance(stdio_transport, BaseIPCTransport)
    assert isinstance(tcp_transport, BaseIPCTransport)
    assert tcp_transport.host == "127.0.0.1"
    assert tcp_transport.port == 5173
    assert tcp_transport.path == "/__litestar_ssr__"
    assert tcp_transport.scheme == "http"

    breaker = SSRCircuitBreaker(failure_threshold=2, reset_timeout=15.0)
    assert breaker.state is CircuitState.CLOSED
    assert breaker.failure_threshold == 2
    assert breaker.reset_timeout == 15.0
    breaker.record_failure()
    assert breaker.state is CircuitState.CLOSED
    breaker.record_failure()
    tripped_state: CircuitState = breaker.state
    assert tripped_state is CircuitState.OPEN
    breaker.record_success()
    recovered_state: CircuitState = breaker.state
    assert recovered_state is CircuitState.CLOSED

    assert inspect.isclass(ViteProxyMiddleware)
    assert inspect.isclass(SSRProxyMiddleware)
    assert inspect.isclass(ProxyHeadersMiddleware)
    assert callable(create_vite_hmr_handler)
    assert "ViteProxyMiddleware" in litestar_vite.plugin.__all__
    assert "export_asyncapi" in litestar_vite.codegen.__all__
    assert callable(export_asyncapi)
    assert callable(find_asyncapi_plugin)
    assert callable(normalize_asyncapi_document)
    assert callable(resolve_asyncapi_document)


def test_litestar_vite_032_mode_normalization() -> None:
    """Verify mode alias normalization in ViteConfig."""
    assert ViteConfig(mode="htmx").mode == "template"
    assert ViteConfig(mode="inertia").mode == "hybrid"
    assert ViteConfig(mode="ssr").mode == "framework"
    assert ViteConfig(mode="ssg").mode == "framework"
    ext_server = ExternalDevServer(target="http://127.0.0.1:3000")
    cfg_ext = ViteConfig(mode="external", runtime=RuntimeConfig(external_dev_server=ext_server))
    assert cfg_ext.mode == "framework"


def test_litestar_vite_032_static_server_and_html_entry_contract(tmp_path: Path) -> None:
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


def test_litestar_vite_032_csrf_routes_ts_and_cli_contract() -> None:
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


def test_litestar_vite_032_ssr_slots_island_and_scaffolding_contract(tmp_path: Path) -> None:
    """Verify Inertia SSR slot injection, <litestar-island> wrapper, StaticFilesConfig, and scaffolding templates."""
    shell_comments = "<html><head><!--inertia-head--></head><body><!--inertia-body--></body></html>"
    injected_comments = inject_inertia_ssr_tags(
        shell_comments,
        head=["<title>Dashboard</title>"],
        body="<div id='app' data-page='{}'>SSR</div>",
    )
    assert "<title>Dashboard</title>" in injected_comments
    assert "<div id='app' data-page='{}'>SSR</div>" in injected_comments

    shell_directives = "<html><head>@inertiaHead</head><body>@inertia</body></html>"
    injected_directives = inject_inertia_ssr_tags(
        shell_directives,
        head=["<meta name='ssr' content='1'>"],
        body="<div id='app'>Body</div>",
    )
    assert "<meta name='ssr' content='1'>" in injected_directives
    assert "<div id='app'>Body</div>" in injected_directives

    cfg = ViteConfig(
        mode="template",
        dev_mode=False,
        paths=PathConfig(root=tmp_path, bundle_dir=tmp_path / "public"),
    )
    loader = ViteAssetLoader(config=cfg)
    engine = FragmentEngine(config=cfg, asset_loader=loader)
    assert engine.get_component_css_urls("resources/components/Counter.tsx") == []
    assert engine.generate_component_css_tags("resources/components/Counter.tsx") == ""

    static_files_cfg = StaticFilesConfig(opt={"exclude_from_auth": True}, tags=["static"])
    assert static_files_cfg.has_asgi_overrides() is False
    plugin = VitePlugin(config=cfg, static_files_config=static_files_cfg)
    assert plugin.config is cfg

    template_names = {t.value for t in FrameworkType}
    expected_templates = {
        "react",
        "react-router",
        "react-tanstack",
        "react-inertia",
        "react-inertia-jinja",
        "vue",
        "vue-inertia",
        "vue-inertia-ssr",
        "vue-inertia-jinja",
        "vue-inertia-jinja-ssr",
        "svelte",
        "svelte-inertia",
        "svelte-inertia-jinja",
        "sveltekit",
        "nuxt",
        "astro",
        "htmx",
        "jinja-htmx",
        "htmx-no-jinja",
        "angular",
        "angular-cli",
    }
    assert expected_templates == template_names
    assert len(get_available_templates()) == 21
    react_inertia_tpl = get_template("react-inertia")
    assert isinstance(react_inertia_tpl, FrameworkTemplate)
    assert inspect.isclass(TemplateContext)
    assert callable(generate_project)
