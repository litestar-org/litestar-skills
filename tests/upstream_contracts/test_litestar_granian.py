import logging
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from importlib.metadata import version
from pathlib import Path
from typing import Any, cast, get_args

import pytest
from granian import Granian
from granian.cli import cli as granian_cli
from granian.constants import HTTPModes, Interfaces, Loops, RuntimeModes, SSLProtocols, TaskImpl
from granian.http import HTTP1Settings, HTTP2Settings
from granian.log import LogLevels
from granian.server.embed import Server as EmbeddedServer
from granian.utils import proxies
from litestar import Litestar, Request, get
from litestar.logging import LoggingConfig
from litestar.plugins import CLIPluginProtocol, InitPlugin
from litestar.testing import TestClient
from litestar_granian import GranianPlugin, __project__, __version__
from litestar_granian import static as granian_static
from litestar_granian._runner import main as runner_main
from litestar_granian.cli import run_command
from litestar_granian.logging import build_logging_config, load_serialized_formatter
from litestar_granian.plugin import StaticMode


@dataclass
class _DummyStaticMount:
    """Stub static mount definition for provider contract testing."""

    route: str
    directory: Path
    directory_index: str | None = None


@dataclass
class _DummyStaticConfig:
    """Stub static server configuration returned by a static provider plugin."""

    mounts: tuple[_DummyStaticMount, ...]
    placement: str | None = "native"
    reason: str | None = None
    fallback_reason: str | None = None


class _DummyStaticProvider(InitPlugin):
    """Stub Litestar plugin implementing get_static_server_config()."""

    def __init__(self, config: _DummyStaticConfig) -> None:
        self._config = config

    def get_static_server_config(self) -> _DummyStaticConfig:
        """Return configured static mount metadata."""
        return self._config


def test_litestar_granian_and_granian_versions() -> None:
    """Verify exact audited upstream versions for litestar-granian and granian."""
    assert version("litestar-granian") == "0.16.0"
    assert __version__ == "0.16.0"
    assert __project__ == "litestar-granian"
    assert version("granian") == "2.8.4"


def test_granian_plugin_contract() -> None:
    """Verify GranianPlugin initialization, protocols, and static option validation."""
    assert set(get_args(StaticMode)) == {"off", "auto"}
    assert callable(runner_main)

    plugin_default = GranianPlugin()
    assert plugin_default.static == "off"
    assert isinstance(plugin_default, (InitPlugin, CLIPluginProtocol))

    plugin_auto = GranianPlugin(static="auto")
    assert plugin_auto.static == "auto"

    with pytest.raises(ValueError, match="static must be 'off' or 'auto'"):
        GranianPlugin(static=cast("Any", "invalid"))


def test_litestar_granian_016_cli_contract() -> None:
    """Verify presence of supported options, secondary flags, envvars, and absence of retired flags."""
    options = {option for parameter in run_command.params for option in (*parameter.opts, *parameter.secondary_opts)}
    params_by_name = {parameter.name: parameter for parameter in run_command.params}

    expected_options = {
        "--host",
        "-H",
        "--port",
        "-p",
        "--uds",
        "-U",
        "--unix-domain-socket",
        "--uds-permissions",
        "--fd",
        "-F",
        "--file-descriptor",
        "--url-path-prefix",
        "--http",
        "--ws",
        "--no-ws",
        "--debug",
        "-d",
        "--pdb",
        "-P",
        "--use-pdb",
        "--workers",
        "-W",
        "--wc",
        "--web-concurrency",
        "--runtime-mode",
        "--runtime-threads",
        "--runtime-blocking-threads",
        "--blocking-threads",
        "--blocking-threads-idle-timeout",
        "--loop",
        "--task-impl",
        "--backlog",
        "--backpressure",
        "--http1-buffer-size",
        "--http1-header-read-timeout",
        "--http1-keep-alive",
        "--no-http1-keep-alive",
        "--http1-pipeline-flush",
        "--no-http1-pipeline-flush",
        "--http2-adaptive-window",
        "--no-http2-adaptive-window",
        "--http2-initial-connection-window-size",
        "--http2-initial-stream-window-size",
        "--http2-keep-alive-interval",
        "--http2-keep-alive-timeout",
        "--http2-max-concurrent-streams",
        "--http2-max-frame-size",
        "--http2-max-headers-size",
        "--http2-max-send-buffer-size",
        "--ssl-certificate",
        "--ssl-certfile",
        "--ssl-keyfile",
        "--ssl-keyfile-password",
        "--ssl-protocol-min",
        "--ssl-ca",
        "--ssl-crl",
        "--ssl-client-verify",
        "--no-ssl-client-verify",
        "--create-self-signed-cert",
        "--granian-log",
        "--granian-no-log",
        "--granian-log-level",
        "--granian-access-log",
        "--granian-no-access-log",
        "--granian-access-log-fmt",
        "--log-config",
        "--respawn-failed-workers",
        "--no-respawn-failed-workers",
        "--respawn-interval",
        "--workers-lifetime",
        "--workers-kill-timeout",
        "--workers-max-rss",
        "--rss-sample-interval",
        "--rss-samples",
        "--reload",
        "--no-reload",
        "-r",
        "--reload-paths",
        "-R",
        "--reload-dir",
        "--reload-include",
        "-I",
        "--reload-exclude",
        "-E",
        "--reload-ignore-dirs",
        "--reload-ignore-patterns",
        "--reload-ignore-paths",
        "--reload-tick",
        "--reload-ignore-worker-failure",
        "--no-reload-ignore-worker-failure",
        "--static-path-route",
        "--static-path-mount",
        "--static-path-dir-to-file",
        "--static-path-expires",
        "--metrics",
        "--no-metrics",
        "--metrics-scrape-interval",
        "--metrics-address",
        "--metrics-port",
        "--process-name",
        "--pid-file",
        "--working-dir",
        "--env-files",
        "--in-subprocess",
        "--no-subprocess",
        "--use-litestar-logger",
        "--no-litestar-logger",
    }
    assert expected_options <= options

    assert params_by_name["host"].envvar == ["LITESTAR_HOST", "GRANIAN_HOST"]
    assert params_by_name["port"].envvar == ["LITESTAR_PORT", "GRANIAN_PORT"]
    assert params_by_name["wc"].envvar == ["LITESTAR_WEB_CONCURRENCY", "WEB_CONCURRENCY", "GRANIAN_WORKERS"]
    assert params_by_name["uds"].envvar == ["LITESTAR_UNIX_DOMAIN_SOCKET", "GRANIAN_UDS"]
    assert params_by_name["fd"].envvar == ["LITESTAR_FILE_DESCRIPTOR", "GRANIAN_FILE_DESCRIPTOR"]
    assert params_by_name["reload"].envvar == ["LITESTAR_RELOAD", "GRANIAN_RELOAD"]
    assert params_by_name["reload_paths"].envvar == ["LITESTAR_RELOAD_DIRS", "GRANIAN_RELOAD_PATHS"]
    assert params_by_name["reload_include"].envvar == ["LITESTAR_RELOAD_INCLUDES", "GRANIAN_RELOAD_INCLUDE"]
    assert params_by_name["reload_exclude"].envvar == ["LITESTAR_RELOAD_EXCLUDES", "GRANIAN_RELOAD_EXCLUDE"]
    assert params_by_name["ssl_certificate"].envvar == ["LITESTAR_SSL_CERT_PATH", "GRANIAN_SSL_CERTIFICATE"]
    assert params_by_name["ssl_keyfile"].envvar == ["LITESTAR_SSL_KEY_PATH", "GRANIAN_SSL_KEYFILE"]
    assert params_by_name["ssl_client_verify"].envvar == ["LITESTAR_SSL_CLIENT_VERIFY", "GRANIAN_SSL_CLIENT_VERIFY"]
    assert params_by_name["create_self_signed_cert"].envvar == "LITESTAR_CREATE_SELF_SIGNED_CERT"

    retired_flags = {
        "--threads",
        "--threading-mode",
        "--log-access",
        "--log-access-format",
        "--log-access-fmt",
        "--proxy-headers",
        "--forwarded-allow-ips",
    }
    assert retired_flags.isdisjoint(options)


def test_granian_embedded_server_contract() -> None:
    """Verify programmatic Granian and EmbeddedServer instantiation and constants."""
    assert HTTPModes.auto.value == "auto"
    assert HTTPModes.http1.value == "1"
    assert HTTPModes.http2.value == "2"
    assert Interfaces.ASGI.value == "asgi"
    assert Interfaces.ASGINL.value == "asginl"
    assert Interfaces.RSGI.value == "rsgi"
    assert Interfaces.WSGI.value == "wsgi"
    assert Loops.auto.value == "auto"
    assert Loops.asyncio.value == "asyncio"
    assert Loops.rloop.value == "rloop"
    assert Loops.uvloop.value == "uvloop"
    assert Loops.winloop.value == "winloop"
    assert RuntimeModes.auto.value == "auto"
    assert RuntimeModes.mt.value == "mt"
    assert RuntimeModes.st.value == "st"
    assert TaskImpl.asyncio.value == "asyncio"
    assert TaskImpl.rust.value == "rust"
    assert SSLProtocols.tls12.value == "tls1.2"
    assert SSLProtocols.tls13.value == "tls1.3"
    assert LogLevels.critical.value == "critical"
    assert LogLevels.error.value == "error"
    assert LogLevels.warning.value == "warning"
    assert LogLevels.warn.value == "warn"
    assert LogLevels.info.value == "info"
    assert LogLevels.debug.value == "debug"
    assert LogLevels.notset.value == "notset"
    assert HTTP1Settings.max_buffer_size == 417792
    assert HTTP1Settings.header_read_timeout == 30000
    assert HTTP1Settings.keep_alive is True
    assert HTTP1Settings.pipeline_flush is False
    assert HTTP2Settings.adaptive_window is False
    assert HTTP2Settings.initial_connection_window_size == 1048576
    assert HTTP2Settings.initial_stream_window_size == 1048576
    assert HTTP2Settings.keep_alive_interval is None
    assert HTTP2Settings.keep_alive_timeout == 20
    assert HTTP2Settings.max_concurrent_streams == 200
    assert HTTP2Settings.max_frame_size == 16384
    assert HTTP2Settings.max_headers_size == 16777216
    assert HTTP2Settings.max_send_buffer_size == 409600

    server = Granian(
        target="dummy.app:app",
        address="127.0.0.1",
        port=8000,
        interface=Interfaces.ASGI,
        workers=1,
        runtime_mode=RuntimeModes.auto,
        runtime_threads=1,
        http=HTTPModes.auto,
        websockets=True,
        metrics_enabled=False,
    )
    assert server.bind_addr == "127.0.0.1"
    assert server.bind_port == 8000
    assert server.workers == 1
    assert server.interface == Interfaces.ASGI

    app = Litestar(route_handlers=[])
    embedded = EmbeddedServer(
        target=app,
        address="127.0.0.1",
        port=8000,
        interface=Interfaces.ASGI,
        runtime_threads=1,
        http=HTTPModes.auto,
        websockets=True,
    )
    assert embedded.bind_addr == "127.0.0.1"
    assert embedded.bind_port == 8000
    assert embedded.interface == Interfaces.ASGI


def test_granian_proxy_headers_contract() -> None:
    """Verify granian.utils.proxies wrappers rewrite client host and scheme for trusted proxies."""
    proxies_mod: Any = proxies
    asgi_wrapper = cast("Callable[..., Any]", proxies_mod.wrap_asgi_with_proxy_headers)
    wsgi_wrapper = cast("Callable[..., Any]", proxies_mod.wrap_wsgi_with_proxy_headers)
    assert callable(asgi_wrapper)
    assert callable(wsgi_wrapper)

    @get("/proxy-info")
    async def proxy_info(request: Request[Any, Any, Any]) -> dict[str, str | None]:
        return {
            "client": request.client.host if request.client else None,
            "scheme": request.scope["scheme"],
        }

    app = Litestar(
        route_handlers=[proxy_info],
        middleware=[partial(asgi_wrapper, trusted_hosts=["*"])],
    )
    with TestClient(app=app) as client:
        response = client.get(
            "/proxy-info",
            headers={
                "x-forwarded-for": "198.51.100.7",
                "x-forwarded-proto": "https",
            },
        )
        assert response.status_code == 200
        assert response.json() == {"client": "198.51.100.7", "scheme": "https"}


def test_logging_bridge_builds_config() -> None:
    """Verify logging configuration serialization helper produces a reconstructible formatter."""
    app_logger = logging.getLogger("test_litestar_granian_logging")
    app_logger.propagate = False
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    app_logger.addHandler(handler)
    try:
        config = build_logging_config(LoggingConfig(), logger=app_logger)
        assert isinstance(config, dict)
        assert config.get("version") == 1
        assert "formatters" in config
        assert "generic" in config["formatters"]
        assert "access" in config["formatters"]
        payload = config["formatters"]["generic"]["payload"]
        reconstructed = load_serialized_formatter(payload)
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "hello", (), None)
        assert reconstructed.format(record) == "INFO: hello"
    finally:
        app_logger.removeHandler(handler)


def test_standalone_granian_cli_contract() -> None:
    """Verify standalone granian CLI option names that differ from litestar run."""
    options = {option for parameter in granian_cli.params for option in (*parameter.opts, *parameter.secondary_opts)}
    expected_standalone_options = {
        "--interface",
        "--factory",
        "--no-factory",
        "--log",
        "--no-log",
        "--log-level",
        "--access-log",
        "--no-access-log",
        "--access-log-fmt",
        "--blocking-threads",
        "--runtime-threads",
        "--runtime-blocking-threads",
        "--runtime-mode",
        "--ssl-certificate",
        "--ssl-keyfile",
    }
    assert expected_standalone_options <= options


def test_static_provider_discovery_contract(tmp_path: Path) -> None:
    """Verify static provider placement resolution and explicit CLI mount precedence."""
    static_mod: Any = granian_static
    resolve_static_mounts = cast("Callable[..., Any]", static_mod._resolve_static_mounts)
    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    (static_dir / "app.js").write_text("console.log('ok');", encoding="utf-8")

    native_provider = _DummyStaticProvider(
        _DummyStaticConfig(
            mounts=(_DummyStaticMount(route="/static", directory=static_dir, directory_index="index.html"),),
            placement="native",
        )
    )
    app_native = Litestar(route_handlers=[], plugins=[GranianPlugin(static="auto"), native_provider])

    assert resolve_static_mounts(app_native, static_mode="off") is None

    resolved_native = resolve_static_mounts(app_native, static_mode="auto")
    assert resolved_native is not None
    assert resolved_native.routes == ("/static",)
    assert resolved_native.mounts == (static_dir.resolve(),)
    assert resolved_native.directory_index == "index.html"

    explicit = resolve_static_mounts(
        app_native,
        static_mode="off",
        explicit_routes=("/assets",),
        explicit_mounts=(static_dir,),
        explicit_directory_index=None,
    )
    assert explicit is not None
    assert explicit.routes == ("/assets",)
    assert explicit.mounts == (static_dir.resolve(),)
    assert explicit.directory_index is None

    asgi_provider = _DummyStaticProvider(
        _DummyStaticConfig(
            mounts=(_DummyStaticMount(route="/static", directory=static_dir),),
            placement="asgi",
            reason="dev server active",
        )
    )
    app_asgi = Litestar(route_handlers=[], plugins=[GranianPlugin(static="auto"), asgi_provider])
    assert resolve_static_mounts(app_asgi, static_mode="auto") is None
