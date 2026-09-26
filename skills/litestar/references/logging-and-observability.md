# Logging, Structlog, OpenTelemetry, and Prometheus

## Standard and Picologging (`LoggingConfig`)

`LoggingConfig` (`from litestar.logging import LoggingConfig`) configures standard library `logging` (or `picologging` automatically when installed) with a non-blocking `queue_listener` handler so log I/O does not block the asyncio event loop.

```python
from litestar import Litestar, Request, get
from litestar.datastructures import State
from litestar.exceptions import NotFoundException
from litestar.logging import LoggingConfig


logging_config = LoggingConfig(
    root={"level": "INFO", "handlers": ["queue_listener"]},
    formatters={
        "standard": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        },
    },
    log_exceptions="always",
    disable_stack_trace={404, NotFoundException, ValueError},
)


@get("/items/{item_id:int}")
async def get_item(
    request: Request[object, object, State],
) -> dict[str, str]:
    """Access the configured logger from the request instance."""
    request.logger.info("Fetching item")
    return {"status": "ok"}


app = Litestar(
    route_handlers=[get_item],
    logging_config=logging_config,
)
```

### Key `LoggingConfig` Options

| Parameter | Default | Notes |
| --- | --- | --- |
| `logging_module` | `"picologging"` if installed, else `"logging"` | Automatically selects `picologging` when present unless overridden. |
| `configure_root_logger` | `True` | Configures the root logger using `root={"level": "INFO", "handlers": ["queue_listener"]}`. |
| `log_exceptions` | `"debug"` | `"always"`, `"debug"`, or `"never"`. Controls automatic exception logging in the exception handler middleware. |
| `disable_stack_trace` | `set()` | Set of HTTP status codes (`int`) or exception types (`type[Exception]`, such as `{404, PermissionDeniedException}`) for which stack traces are suppressed when logging exceptions. |
| `exception_logging_handler` | `None` | Custom `Callable[[Logger, Scope, list[str]], None]` invoked to emit formatted exception tracebacks. |

Avoid deprecated `traceback_line_limit` and `propagate` arguments on `LoggingConfig`.

## Structured Logging (`StructlogPlugin` and `StructLoggingConfig`)

When `structlog` is in the project stack, prefer `StructlogPlugin` (`from litestar.plugins.structlog import StructlogConfig, StructlogPlugin`), which configures both structured application logging (`StructLoggingConfig`) and request/response middleware logging (`LoggingMiddlewareConfig`):

```python
from litestar import Litestar
from litestar.logging import LoggingConfig, StructLoggingConfig
from litestar.middleware.logging import LoggingMiddlewareConfig
from litestar.plugins.structlog import StructlogConfig, StructlogPlugin


structlog_plugin = StructlogPlugin(
    config=StructlogConfig(
        structlog_logging_config=StructLoggingConfig(
            log_exceptions="always",
            disable_stack_trace={404},
            pretty_print_tty=True,
            standard_lib_logging_config=LoggingConfig(
                root={"level": "INFO", "handlers": ["queue_listener"]},
            ),
        ),
        middleware_logging_config=LoggingMiddlewareConfig(
            request_log_fields=("method", "path", "query"),
            response_log_fields=("status_code",),
        ),
        enable_middleware_logging=True,
    ),
)

app = Litestar(
    route_handlers=[],
    plugins=[structlog_plugin],
)
```

## OpenTelemetry (`OpenTelemetryPlugin` and `OpenTelemetryConfig`)

Install `litestar[opentelemetry]` and import from `litestar.plugins.opentelemetry` (`litestar.contrib.opentelemetry` was deprecated in Litestar 2.22.0):

```python
from litestar import Litestar
from litestar.plugins.opentelemetry import OpenTelemetryConfig, OpenTelemetryPlugin


otel_config = OpenTelemetryConfig(
    exclude=["/health", "/metrics"],
    exclude_opt_key="skip_otel",
    http_capture_headers_server_request=["x-request-id", "x-tenant-id"],
    http_capture_headers_server_response=["x-request-id"],
    http_capture_headers_sanitize_fields=["authorization", "cookie", "set-cookie"],
)

app = Litestar(
    route_handlers=[],
    plugins=[OpenTelemetryPlugin(config=otel_config)],
)
```

- Pass custom `tracer_provider` and `meter_provider` instances to `OpenTelemetryConfig` when initializing the OpenTelemetry SDK in a lifespan manager or startup hook.
- Mark individual routes with `@get("/ping", opt={"skip_otel": True})` when `exclude_opt_key="skip_otel"` is set.

## Prometheus Metrics (`PrometheusConfig` and `PrometheusController`)

Install `litestar[prometheus]` and import from `litestar.plugins.prometheus` (`litestar.contrib.prometheus` is deprecated):

```python
from litestar import Litestar
from litestar.plugins.prometheus import PrometheusConfig, PrometheusController


class MetricsController(PrometheusController):
    """Expose Prometheus metrics in OpenMetrics format at /metrics."""

    path = "/metrics"
    openmetrics_format = True


prometheus_config = PrometheusConfig(
    app_name="billing-api",
    prefix="litestar",
    group_path=True,
    exclude=["/health", "/metrics"],
    exclude_unhandled_paths=True,
)

app = Litestar(
    route_handlers=[MetricsController],
    middleware=[prometheus_config.middleware],
)
```

### Key `PrometheusConfig` Settings

| Parameter | Default | Notes |
| --- | --- | --- |
| `app_name` | `"litestar"` | Value emitted in the `app_name` metric label. |
| `prefix` | `"litestar"` | Metric name prefix (`<prefix>_requests_total`, `<prefix>_request_duration_seconds`, `<prefix>_requests_in_progress`). |
| `group_path` | `False` | Set `group_path=True` in production to group metrics by route template (`/users/{user_id:int}`) instead of raw URL path (`/users/42`) and avoid label cardinality explosions. |
| `exclude_unhandled_paths` | `False` | Set `True` to drop unmatched 404 paths from metric labels and prevent scanner traffic from inflating time-series cardinality. |
| `labels` | `None` | Mapping of extra label names to static strings or `Callable[[Request], str]` extractors. |
| `buckets` | `None` | Custom histogram latency buckets (seconds). |
