import ast
import dataclasses
import inspect
from importlib.metadata import version
from pathlib import Path
from typing import cast, get_args

import click
import litestar
from litestar import Litestar, static_files
from litestar.cli._utils import AUTODISCOVERY_FILE_NAMES, LitestarEnv
from litestar.cli.main import litestar_group
from litestar.config.app import AppConfig
from litestar.config.response_cache import (
    CACHE_FOREVER,
    ResponseCacheConfig,
    default_cache_key_builder,
)
from litestar.datastructures import ImmutableState, State
from litestar.di import Dependency as DIDependency
from litestar.di import NamedDependency
from litestar.enums import RequestEncodingType
from litestar.events import SimpleEventEmitter, listener
from litestar.logging import LoggingConfig, StructLoggingConfig
from litestar.params import (
    BodyKwarg,
    CookieParameter,
    FromCookie,
    FromHeader,
    FromPath,
    FromQuery,
    HeaderParameter,
    JSONBody,
    MsgPackBody,
    MultipartBody,
    PathParameter,
    QueryParameter,
    SkipValidation,
    SkipValidationMarker,
    URLEncodedBody,
)
from litestar.plugins import CLIPlugin, CLIPluginProtocol, InitPlugin, InitPluginProtocol
from litestar.plugins.structlog import StructlogConfig, StructlogPlugin
from litestar.stores.file import FileStore
from litestar.stores.memory import MemoryStore
from litestar.stores.registry import StoreRegistry


def _load_litestar_ast(relative_path: str) -> ast.Module:
    """Parse a Litestar module file into an AST without importing optional third-party extras."""
    package_root = Path(inspect.getfile(litestar)).parent
    source = (package_root / relative_path).read_text(encoding="utf-8")
    return ast.parse(source)


def test_litestar_224_explicit_parameter_and_dependency_contract() -> None:
    """Verify Litestar 2.22-2.24 explicit parameter, body, and dependency markers."""
    assert version("litestar") == "2.24.0"

    assert isinstance(get_args(FromPath[int])[1], PathParameter)
    assert isinstance(get_args(FromQuery[str])[1], QueryParameter)
    assert isinstance(get_args(FromHeader[str])[1], HeaderParameter)
    assert isinstance(get_args(FromCookie[str])[1], CookieParameter)

    json_body = get_args(JSONBody[dict[str, str]])[1]
    msgpack_body = get_args(MsgPackBody[dict[str, str]])[1]
    multipart_body = get_args(MultipartBody[dict[str, str]])[1]
    urlencoded_body = get_args(URLEncodedBody[dict[str, str]])[1]

    assert isinstance(json_body, BodyKwarg)
    assert json_body.media_type == RequestEncodingType.JSON
    assert isinstance(msgpack_body, BodyKwarg)
    assert msgpack_body.media_type == RequestEncodingType.MESSAGEPACK
    assert isinstance(multipart_body, BodyKwarg)
    assert multipart_body.media_type == RequestEncodingType.MULTI_PART
    assert isinstance(urlencoded_body, BodyKwarg)
    assert urlencoded_body.media_type == RequestEncodingType.URL_ENCODED

    assert get_args(NamedDependency[str])[0] is str
    assert isinstance(get_args(NamedDependency[str])[1], DIDependency)
    assert get_args(SkipValidation[str])[0] is str
    assert isinstance(get_args(SkipValidation[str])[1], SkipValidationMarker)


def test_litestar_app_and_app_config_contract() -> None:
    """Verify Litestar constructor parameters, AppConfig fields, and ApplicationCore composition."""
    expected_params = {
        "route_handlers",
        "path",
        "plugins",
        "middleware",
        "dependencies",
        "guards",
        "exception_handlers",
        "opt",
        "parameters",
        "state",
        "stores",
        "response_cache_config",
        "logging_config",
        "openapi_config",
        "template_config",
        "cors_config",
        "csrf_config",
        "allowed_hosts",
        "compression_config",
        "cache_control",
        "etag",
        "dto",
        "return_dto",
        "type_encoders",
        "type_decoders",
        "request_class",
        "response_class",
        "websocket_class",
        "request_max_body_size",
        "multipart_form_part_limit",
        "signature_namespace",
        "signature_types",
        "security",
        "tags",
        "include_in_schema",
        "event_emitter_backend",
        "listeners",
        "lifespan",
        "on_startup",
        "on_shutdown",
        "on_app_init",
        "before_request",
        "after_request",
        "after_response",
        "before_send",
        "after_exception",
        "debug",
        "pdb_on_exception",
        "debugger_module",
    }
    app_tree = _load_litestar_ast("app.py")
    init_params = {
        arg.arg
        for node in app_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Litestar"
        for item in node.body
        if isinstance(item, ast.FunctionDef) and item.name == "__init__"
        for arg in (*item.args.args, *item.args.kwonlyargs)
    }
    app_config_fields = {field.name for field in dataclasses.fields(AppConfig)}

    assert expected_params <= init_params
    assert (expected_params - {"on_app_init"}) <= app_config_fields
    assert hasattr(static_files, "create_static_files_router")
    assert callable(listener)
    assert SimpleEventEmitter is not None
    assert hasattr(CLIPlugin, "on_cli_init")
    assert hasattr(CLIPlugin, "server_lifespan")
    assert hasattr(InitPlugin, "on_app_init")

    class ApplicationCore(InitPluginProtocol, CLIPluginProtocol):
        """Test ApplicationCore plugin implementing InitPluginProtocol and CLIPluginProtocol."""

        def on_app_init(self, app_config: AppConfig) -> AppConfig:
            app_config.stores = StoreRegistry(stores={"response_cache": MemoryStore()})
            app_config.response_cache_config = ResponseCacheConfig(default_expiration=90)
            app_config.state = State({"service": "hub-contract"})
            return app_config

        def on_cli_init(self, cli: click.Group) -> None:
            _ = cli

    app = Litestar(plugins=[ApplicationCore()])
    assert app.state["service"] == "hub-contract"
    assert app.response_cache_config is not None
    assert app.response_cache_config.default_expiration == 90
    assert isinstance(app.stores.get("response_cache"), MemoryStore)


def test_litestar_state_and_immutable_state_contract() -> None:
    """Verify State and ImmutableState methods and conversions."""
    state = State({"region": "us-central1"}, deep_copy=False)
    assert state.region == "us-central1"
    assert state["region"] == "us-central1"
    assert state.dict() == {"region": "us-central1"}

    copied = state.copy()
    assert copied.dict() == {"region": "us-central1"}

    immutable = state.immutable_copy()
    assert isinstance(immutable, ImmutableState)
    assert immutable["region"] == "us-central1"

    mutable_again = immutable.mutable_copy()
    assert isinstance(mutable_again, State)
    assert mutable_again.region == "us-central1"


def test_litestar_stores_and_response_cache_contract(tmp_path: Path) -> None:
    """Verify StoreRegistry, MemoryStore, FileStore, ResponseCacheConfig, and Redis/Valkey store contracts."""
    memory_store = MemoryStore()
    file_store = FileStore(path=tmp_path / "stores", create_directories=True)
    registry = StoreRegistry(stores={"memory": memory_store, "files": file_store})

    assert registry.get("memory") is memory_store
    assert registry.get("files") is file_store

    cache_config = ResponseCacheConfig(
        default_expiration=120,
        key_builder=default_cache_key_builder,
        store="response_cache",
    )
    assert cache_config.default_expiration == 120
    assert cache_config.store == "response_cache"
    assert CACHE_FOREVER is not None

    for relative_path, class_name in (
        ("stores/redis.py", "RedisStore"),
        ("stores/valkey.py", "ValkeyStore"),
    ):
        tree = _load_litestar_ast(relative_path)
        class_defs = {
            node.name: {item.name for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))}
            for node in tree.body
            if isinstance(node, ast.ClassDef)
        }
        assert class_name in class_defs
        assert {"with_client", "with_namespace", "set", "get", "delete", "delete_all"} <= class_defs[class_name]


def test_litestar_logging_and_observability_contract() -> None:
    """Verify LoggingConfig, StructLoggingConfig, StructlogPlugin, OpenTelemetryConfig, and PrometheusConfig."""
    logging_config = LoggingConfig(
        log_exceptions="always",
        disable_stack_trace={404, ValueError},
    )
    assert logging_config.log_exceptions == "always"
    assert logging_config.disable_stack_trace == {404, ValueError}
    assert logging_config.configure_root_logger is True

    struct_logging_config = StructLoggingConfig(
        log_exceptions="always",
        disable_stack_trace={404},
        pretty_print_tty=True,
    )
    struct_config = StructlogConfig(
        structlog_logging_config=struct_logging_config,
        enable_middleware_logging=True,
    )
    structlog_plugin = StructlogPlugin(config=struct_config)
    assert struct_config.enable_middleware_logging is True
    assert isinstance(structlog_plugin, StructlogPlugin)

    otel_tree = _load_litestar_ast("plugins/opentelemetry/config.py")
    otel_fields = {
        stmt.target.id
        for node in otel_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "OpenTelemetryConfig"
        for stmt in node.body
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
    }
    assert {
        "tracer_provider",
        "meter_provider",
        "exclude",
        "exclude_opt_key",
        "http_capture_headers_server_request",
        "http_capture_headers_server_response",
        "http_capture_headers_sanitize_fields",
    } <= otel_fields

    prom_tree = _load_litestar_ast("plugins/prometheus/config.py")
    prom_fields = {
        stmt.target.id
        for node in prom_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "PrometheusConfig"
        for stmt in node.body
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
    }
    assert {
        "app_name",
        "prefix",
        "labels",
        "buckets",
        "group_path",
        "exclude",
        "exclude_unhandled_paths",
    } <= prom_fields


def test_litestar_cli_contract() -> None:
    """Verify built-in Litestar CLI subcommands, autodiscovery names, and LitestarEnv."""
    cli_group = cast("click.Group", litestar_group)
    assert {
        "info",
        "run",
        "routes",
        "version",
        "schema",
        "sessions",
    } <= set(cli_group.commands)
    assert "app" in AUTODISCOVERY_FILE_NAMES
    assert "application" in AUTODISCOVERY_FILE_NAMES
    assert callable(LitestarEnv.from_env)
