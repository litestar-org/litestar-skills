import ast
import dataclasses
import inspect
from collections.abc import AsyncGenerator
from importlib.metadata import version
from pathlib import Path
from typing import Any, cast, get_args

import click
import dishka
import litestar
import litestar.dto as litestar_dto
import litestar.exceptions.responses as litestar_exc_responses
import litestar.handlers as litestar_handlers
import msgspec
from advanced_alchemy.extensions.litestar import SQLAlchemyDTO, SQLAlchemyDTOConfig
from dishka import Provider, Scope, make_async_container
from dishka.integrations.litestar import (
    DishkaRouter,
    FromDishka,
    LitestarProvider,
    inject,
    inject_websocket,
    setup_dishka,
)
from litestar import (
    Controller,
    Litestar,
    MediaType,
    Request,
    Response,
    Router,
    WebSocket,
    delete,
    get,
    patch,
    post,
    put,
    route,
    static_files,
    websocket,
    websocket_listener,
)
from litestar.channels import ChannelsPlugin
from litestar.channels.backends.memory import MemoryChannelsBackend
from litestar.cli._utils import AUTODISCOVERY_FILE_NAMES, LitestarEnv
from litestar.cli.main import litestar_group
from litestar.config.allowed_hosts import AllowedHostsConfig
from litestar.config.app import AppConfig
from litestar.config.compression import CompressionConfig
from litestar.config.cors import CORSConfig
from litestar.config.csrf import CSRFConfig
from litestar.config.response_cache import (
    CACHE_FOREVER,
    ResponseCacheConfig,
    default_cache_key_builder,
)
from litestar.connection import ASGIConnection
from litestar.datastructures import CacheControlHeader, Cookie, ETag, ImmutableState, State, UploadFile
from litestar.di import Dependency as DIDependency
from litestar.di import NamedDependency, Provide
from litestar.dto import (
    AbstractDTO,
    DataclassDTO,
    DTOConfig,
    DTOData,
    DTOField,
    Mark,
    MsgspecDTO,
    dto_field,
)
from litestar.enums import OpenAPIMediaType, RequestEncodingType, ScopeType
from litestar.events import SimpleEventEmitter, listener
from litestar.exceptions import (
    ClientException,
    HTTPException,
    ImproperlyConfiguredException,
    InternalServerException,
    MethodNotAllowedException,
    MissingDependencyException,
    NoRouteMatchFoundException,
    NotAuthorizedException,
    NotFoundException,
    PermissionDeniedException,
    SerializationException,
    ServiceUnavailableException,
    TemplateNotFoundException,
    TooManyRequestsException,
    ValidationException,
    WebSocketDisconnect,
    WebSocketException,
)
from litestar.exceptions.responses import ExceptionResponseContent
from litestar.handlers import BaseRouteHandler, WebsocketListener, WebsocketRouteHandler
from litestar.logging import LoggingConfig, StructLoggingConfig
from litestar.middleware import (
    AbstractAuthenticationMiddleware,
    ASGIMiddleware,
    AuthenticationResult,
    DefineMiddleware,
)
from litestar.middleware.logging import LoggingMiddlewareConfig
from litestar.middleware.rate_limit import RateLimitConfig
from litestar.middleware.session.client_side import CookieBackendConfig
from litestar.middleware.session.server_side import ServerSideSessionConfig
from litestar.openapi import OpenAPIConfig, ResponseSpec
from litestar.openapi.plugins import (
    JsonRenderPlugin,
    RapidocRenderPlugin,
    RedocRenderPlugin,
    ScalarRenderPlugin,
    StoplightRenderPlugin,
    SwaggerRenderPlugin,
    YamlRenderPlugin,
)
from litestar.pagination import (
    AbstractAsyncClassicPaginator,
    AbstractAsyncCursorPaginator,
    AbstractAsyncOffsetPaginator,
    ClassicPagination,
    CursorPagination,
    OffsetPagination,
)
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
from litestar.plugins import (
    CLIPlugin,
    CLIPluginProtocol,
    DIPlugin,
    InitPlugin,
    InitPluginProtocol,
    OpenAPISchemaPlugin,
    OpenAPISchemaPluginProtocol,
    PluginProtocol,
    PluginRegistry,
    ReceiveRoutePlugin,
    SerializationPlugin,
    SerializationPluginProtocol,
)
from litestar.plugins.flash import FlashConfig, FlashPlugin, flash, get_flashes
from litestar.plugins.jinja import JinjaTemplateEngine
from litestar.plugins.problem_details import (
    ProblemDetailsConfig,
    ProblemDetailsException,
    ProblemDetailsPlugin,
)
from litestar.plugins.pydantic import (
    PydanticDIPlugin,
    PydanticDTO,
    PydanticInitPlugin,
    PydanticPlugin,
    PydanticSchemaPlugin,
)
from litestar.plugins.structlog import StructlogConfig, StructlogPlugin
from litestar.response import File, Redirect, ServerSentEvent, ServerSentEventMessage, Stream, Template
from litestar.security.jwt import JWTAuth, JWTCookieAuth, OAuth2PasswordBearerAuth, Token
from litestar.security.session_auth import SessionAuth
from litestar.stores.file import FileStore
from litestar.stores.memory import MemoryStore
from litestar.stores.registry import StoreRegistry
from litestar.testing import TestClient
from litestar.types import ASGIApp, Receive, Send
from litestar.types import Scope as ASGIScope


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


def test_litestar_routing_and_datastructures_contract() -> None:
    """Verify routing decorators, Controller, Router, pagination types, and response/datastructure exports."""
    for handler_decorator in (get, post, put, patch, delete, route):
        assert callable(handler_decorator)

    assert issubclass(Controller, object)
    assert issubclass(Router, object)
    assert all(
        cls is not None
        for cls in (
            Request,
            Response,
            File,
            Redirect,
            Template,
            Cookie,
            ETag,
            CacheControlHeader,
            UploadFile,
            MediaType,
            ClassicPagination,
            OffsetPagination,
            CursorPagination,
            AbstractAsyncClassicPaginator,
            AbstractAsyncOffsetPaginator,
            AbstractAsyncCursorPaginator,
        )
    )


def test_litestar_dtos_contract() -> None:
    """Verify DTO classes, DTOConfig fields, DTOData methods, and DTOField/Mark exports."""
    assert issubclass(MsgspecDTO, AbstractDTO)
    assert issubclass(DataclassDTO, AbstractDTO)
    assert issubclass(PydanticDTO, AbstractDTO)
    assert issubclass(SQLAlchemyDTO, AbstractDTO)
    assert issubclass(SQLAlchemyDTOConfig, DTOConfig)
    assert not hasattr(litestar_dto, "PatchDTO")
    assert not hasattr(litestar_dto, "SimpleDTO")

    dto_config_fields = {field.name for field in dataclasses.fields(DTOConfig)}
    assert {
        "exclude",
        "include",
        "rename_fields",
        "rename_strategy",
        "max_nested_depth",
        "partial",
        "underscore_fields_private",
        "experimental_codegen_backend",
        "forbid_unknown_fields",
    } <= dto_config_fields

    assert {"READ_ONLY", "WRITE_ONLY", "PRIVATE"} <= {member.name for member in Mark}
    assert isinstance(dto_field(mark="read-only"), dict)
    assert DTOField(mark=Mark.READ_ONLY).mark == Mark.READ_ONLY
    assert {"create_instance", "update_instance", "as_builtins"} <= {
        name for name, _ in inspect.getmembers(DTOData, predicate=inspect.isfunction)
    }

    class ItemStruct(msgspec.Struct):
        name: str
        internal_note: str = "hidden"

    class ItemReadDTO(MsgspecDTO[ItemStruct]):
        config = DTOConfig(exclude={"internal_note"}, rename_strategy="camel")

    assert ItemReadDTO.config.partial is False
    assert ItemReadDTO.config.rename_strategy == "camel"


def test_litestar_openapi_contract() -> None:
    """Verify OpenAPIConfig, ResponseSpec, OpenAPIMediaType, and all 7 OpenAPI render plugins."""
    render_plugins = [
        ScalarRenderPlugin(),
        SwaggerRenderPlugin(),
        RedocRenderPlugin(),
        RapidocRenderPlugin(),
        StoplightRenderPlugin(),
        JsonRenderPlugin(),
        YamlRenderPlugin(),
    ]
    openapi_config = OpenAPIConfig(
        title="Contract Service",
        version="2.24.0",
        path="/schema",
        render_plugins=render_plugins,
        use_handler_docstrings=True,
    )
    assert openapi_config.title == "Contract Service"
    assert openapi_config.path == "/schema"
    assert len(openapi_config.render_plugins) == 7
    assert OpenAPIMediaType.OPENAPI_JSON is not None
    assert OpenAPIMediaType.OPENAPI_YAML is not None

    spec = ResponseSpec(data_container=dict[str, str], description="Contract response")
    assert spec.description == "Contract response"


def test_litestar_di_and_dishka_contract() -> None:
    """Verify Provide, NamedDependency, SkipValidation, and Dishka Litestar integration."""
    assert version("dishka") == "1.10.1"
    assert hasattr(dishka, "provide")

    provider_def = Provide(lambda: "ok", sync_to_thread=False, use_cache=True)
    assert provider_def.use_cache is True
    assert provider_def.sync_to_thread is False

    class GreeterService:
        def greet(self) -> str:
            return "hello-dishka"

    async def build_greeter() -> AsyncGenerator[GreeterService, None]:
        yield GreeterService()

    service_provider = Provider(scope=Scope.REQUEST)
    service_provider.provide(build_greeter, provides=GreeterService)

    @get("/greet")
    async def greet_endpoint(service: FromDishka[GreeterService]) -> dict[str, str]:
        return {"greeting": service.greet()}

    router = DishkaRouter(path="/v1", route_handlers=[greet_endpoint])
    container = make_async_container(LitestarProvider(), service_provider)
    app = Litestar(route_handlers=[router])
    setup_dishka(container, app)

    assert app.state.dishka_container is container
    assert callable(inject)
    assert callable(inject_websocket)

    with TestClient(app=app) as client:
        response = client.get("/v1/greet")
        assert response.status_code == 200
        assert response.json() == {"greeting": "hello-dishka"}


def test_litestar_guards_auth_and_middleware_contract() -> None:
    """Verify ASGIMiddleware, authentication middleware, security backends, and guard execution on exclude_from_auth."""
    middleware_fields = {name for name, _ in inspect.getmembers(ASGIMiddleware)}
    assert {
        "scopes",
        "exclude_path_pattern",
        "exclude_opt_key",
        "should_bypass_for_scope",
        "handle",
    } <= middleware_fields
    assert DefineMiddleware is not None
    assert all(
        cls is not None
        for cls in (
            JWTAuth,
            JWTCookieAuth,
            OAuth2PasswordBearerAuth,
            Token,
            SessionAuth,
            CORSConfig,
            CSRFConfig,
            AllowedHostsConfig,
            CompressionConfig,
            RateLimitConfig,
            LoggingMiddlewareConfig,
            ServerSideSessionConfig,
            CookieBackendConfig,
        )
    )

    class HeaderTraceMiddleware(ASGIMiddleware):
        scopes = (ScopeType.HTTP,)
        exclude_path_pattern = r"^/health$"
        exclude_opt_key = "skip_trace"

        async def handle(self, scope: ASGIScope, receive: Receive, send: Send, next_app: ASGIApp) -> None:
            await next_app(scope, receive, send)

    class DummyAuthMiddleware(AbstractAuthenticationMiddleware):
        async def authenticate_request(
            self,
            connection: ASGIConnection[Any, Any, Any, Any],
        ) -> AuthenticationResult:
            _ = connection
            raise NotAuthorizedException("Missing auth")

    def require_admin_guard(
        connection: ASGIConnection[Any, Any, Any, Any],
        _: BaseRouteHandler,
    ) -> None:
        if connection.headers.get("x-admin") != "1":
            raise PermissionDeniedException("Admin guard rejected")

    @get("/protected-by-guard", exclude_from_auth=True, guards=[require_admin_guard])
    async def guarded_route() -> dict[str, bool]:
        return {"ok": True}

    app = Litestar(
        route_handlers=[guarded_route],
        middleware=[HeaderTraceMiddleware(), DefineMiddleware(DummyAuthMiddleware)],
    )

    with TestClient(app=app) as client:
        denied = client.get("/protected-by-guard")
        assert denied.status_code == 403

        allowed = client.get("/protected-by-guard", headers={"x-admin": "1"})
        assert allowed.status_code == 200
        assert allowed.json() == {"ok": True}


def test_litestar_channels_sse_and_websockets_contract() -> None:
    """Verify ChannelsPlugin backends, SSE responses, Stream, and WebSocket handlers."""
    channels_plugin = ChannelsPlugin(
        backend=MemoryChannelsBackend(history=10),
        channels=["alerts"],
        arbitrary_channels_allowed=True,
        create_ws_route_handlers=True,
        ws_handler_send_history=5,
    )
    assert isinstance(channels_plugin, ChannelsPlugin)

    for relative_path, class_name in (
        ("channels/backends/redis.py", "RedisChannelsPubSubBackend"),
        ("channels/backends/redis.py", "RedisChannelsStreamBackend"),
        ("channels/backends/asyncpg.py", "AsyncPgChannelsBackend"),
        ("channels/backends/psycopg.py", "PsycoPgChannelsBackend"),
    ):
        tree = _load_litestar_ast(relative_path)
        class_names = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
        assert class_name in class_names

    sse_msg = ServerSentEventMessage(data="ping", event="heartbeat", id="1", retry=1000)
    sse_response = ServerSentEvent(iter([sse_msg]), event_type="heartbeat")
    stream_response = Stream(iter([b"{}\n"]), media_type="application/x-ndjson")
    assert sse_response is not None
    assert stream_response.media_type == "application/x-ndjson"

    assert WebSocket is not None
    assert issubclass(WebsocketListener, object)
    assert issubclass(WebsocketRouteHandler, BaseRouteHandler)
    assert callable(websocket)
    assert callable(websocket_listener)
    assert hasattr(litestar_handlers, "websocket_stream")
    assert hasattr(litestar_handlers, "send_websocket_stream")


def test_litestar_exceptions_and_problem_details_contract() -> None:
    """Verify HTTPException hierarchy, ExceptionResponseContent, and ProblemDetailsPlugin."""
    for exc_cls in (
        ClientException,
        ValidationException,
        ImproperlyConfiguredException,
        NotAuthorizedException,
        PermissionDeniedException,
        NotFoundException,
        MethodNotAllowedException,
        TooManyRequestsException,
        InternalServerException,
        ServiceUnavailableException,
        NoRouteMatchFoundException,
        TemplateNotFoundException,
    ):
        assert issubclass(exc_cls, HTTPException)

    assert issubclass(MissingDependencyException, Exception)
    assert issubclass(SerializationException, Exception)
    assert issubclass(WebSocketDisconnect, WebSocketException)
    assert hasattr(litestar_exc_responses, "create_exception_response")
    assert ExceptionResponseContent is not None
    assert getattr(ProblemDetailsException, "_PROBLEM_DETAILS_MEDIA_TYPE", None) == "application/problem+json"

    def value_error_to_problem(exc: ValueError) -> ProblemDetailsException:
        return ProblemDetailsException(
            status_code=422,
            title="Invalid domain value",
            detail=str(exc),
        )

    problem_config = ProblemDetailsConfig(
        enable_for_all_http_exceptions=True,
        exception_to_problem_detail_map={ValueError: value_error_to_problem},
    )
    problem_plugin = ProblemDetailsPlugin(config=problem_config)

    @get("/fail")
    async def fail_route() -> None:
        raise ValueError("bad input")

    app = Litestar(route_handlers=[fail_route], plugins=[problem_plugin])
    with TestClient(app=app) as client:
        response = client.get("/fail")
        assert response.status_code == 422
        assert response.headers["content-type"].startswith("application/problem+json")
        assert response.json()["title"] == "Invalid domain value"


def test_litestar_plugins_contract() -> None:
    """Verify plugin protocols, FlashPlugin, PydanticPlugin, and JinjaTemplateEngine."""
    assert all(
        proto is not None
        for proto in (
            InitPlugin,
            InitPluginProtocol,
            CLIPlugin,
            CLIPluginProtocol,
            SerializationPlugin,
            SerializationPluginProtocol,
            OpenAPISchemaPlugin,
            OpenAPISchemaPluginProtocol,
            PluginProtocol,
            PluginRegistry,
            ReceiveRoutePlugin,
            DIPlugin,
        )
    )
    assert all(
        item is not None
        for item in (
            FlashPlugin,
            FlashConfig,
            flash,
            get_flashes,
            PydanticPlugin,
            PydanticInitPlugin,
            PydanticSchemaPlugin,
            PydanticDIPlugin,
            JinjaTemplateEngine,
        )
    )
    pydantic_plugin = PydanticPlugin(prefer_alias=True, validate_strict=False)
    assert pydantic_plugin.prefer_alias is True
    assert pydantic_plugin.validate_strict is False
