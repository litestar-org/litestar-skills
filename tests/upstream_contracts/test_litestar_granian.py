import logging
from importlib.metadata import version
from typing import Any, cast, get_args

import pytest
from granian import Granian
from granian.constants import HTTPModes, Interfaces, Loops, RuntimeModes, SSLProtocols, TaskImpl
from granian.http import HTTP1Settings, HTTP2Settings
from granian.log import LogLevels
from granian.server.embed import Server as EmbeddedServer
from litestar import Litestar
from litestar.logging import LoggingConfig
from litestar.plugins import CLIPluginProtocol, InitPlugin
from litestar_granian import GranianPlugin, __project__, __version__
from litestar_granian._runner import main as runner_main
from litestar_granian.cli import run_command
from litestar_granian.logging import build_logging_config, load_serialized_formatter
from litestar_granian.plugin import StaticMode


def test_litestar_granian_and_granian_versions() -> None:
    """Verify exact audited upstream versions for litestar-granian and granian."""
    assert version("litestar-granian") == "0.16.0"
    assert __version__ == "0.16.0"
    assert __project__ == "litestar-granian"
    assert version("granian") == "2.8.3"


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
    assert RuntimeModes.auto.value == "auto"
    assert TaskImpl.asyncio.value == "asyncio"
    assert TaskImpl.rust.value == "rust"
    assert SSLProtocols.tls12.value == "tls1.2"
    assert SSLProtocols.tls13.value == "tls1.3"
    assert LogLevels.info.value == "info"
    assert LogLevels.warn.value == "warn"
    assert HTTP1Settings.max_buffer_size == 417792
    assert HTTP2Settings.max_concurrent_streams == 200

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
