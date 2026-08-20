import logging
from importlib.metadata import version

import pytest
from granian import Granian
from granian.constants import HTTPModes, Interfaces, Loops, RuntimeModes, SSLProtocols, TaskImpl
from litestar.logging import LoggingConfig
from litestar.plugins import CLIPluginProtocol, InitPlugin
from litestar_granian import GranianPlugin
from litestar_granian.cli import run_command
from litestar_granian.logging import build_logging_config


def test_litestar_granian_and_granian_versions() -> None:
    """Verify exact audited upstream versions for litestar-granian and granian."""
    assert version("litestar-granian") == "0.16.0"
    assert version("granian") == "2.8.1"


def test_granian_plugin_contract() -> None:
    """Verify GranianPlugin initialization, protocols, and static option validation."""
    plugin_default = GranianPlugin()
    assert plugin_default.static == "off"
    assert isinstance(plugin_default, (InitPlugin, CLIPluginProtocol))

    plugin_auto = GranianPlugin(static="auto")
    assert plugin_auto.static == "auto"

    with pytest.raises(ValueError, match="static must be 'off' or 'auto'"):
        GranianPlugin(static="invalid")  # type: ignore[arg-type]


def test_litestar_granian_016_cli_contract() -> None:
    """Verify presence of supported options and absence of retired flags in run_command."""
    options = {option for parameter in run_command.params for option in parameter.opts}

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
        "--http1-pipeline-flush",
        "--http2-adaptive-window",
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
        "--create-self-signed-cert",
        "--granian-log",
        "--granian-log-level",
        "--granian-access-log",
        "--granian-access-log-fmt",
        "--log-config",
        "--respawn-failed-workers",
        "--respawn-interval",
        "--workers-lifetime",
        "--workers-kill-timeout",
        "--workers-max-rss",
        "--rss-sample-interval",
        "--rss-samples",
        "--reload",
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
        "--static-path-route",
        "--static-path-mount",
        "--static-path-dir-to-file",
        "--static-path-expires",
        "--metrics",
        "--metrics-scrape-interval",
        "--metrics-address",
        "--metrics-port",
        "--process-name",
        "--pid-file",
        "--working-dir",
        "--env-files",
    }
    assert expected_options <= options

    retired_flags = {
        "--threads",
        "--threading-mode",
        "--log-access",
        "--log-access-format",
        "--log-access-fmt",
    }
    assert retired_flags.isdisjoint(options)


def test_granian_embedded_server_contract() -> None:
    """Verify programmatic Granian instantiation and constants."""
    assert HTTPModes.auto.value == "auto"
    assert HTTPModes.http1.value == "1"
    assert HTTPModes.http2.value == "2"
    assert Interfaces.ASGI.value == "asgi"
    assert Interfaces.RSGI.value == "rsgi"
    assert Interfaces.WSGI.value == "wsgi"
    assert Loops.auto.value == "auto"
    assert RuntimeModes.auto.value == "auto"
    assert TaskImpl.asyncio.value == "asyncio"
    assert SSLProtocols.tls13.value == "tls1.3"

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


def test_logging_bridge_builds_config() -> None:
    """Verify logging configuration serialization helper produces a config dict."""
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
    finally:
        app_logger.removeHandler(handler)
