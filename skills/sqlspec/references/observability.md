# SQLSpec Observability & Tracing

## Logging Framework

SQLSpec emits structured log records following OpenTelemetry semantic conventions to aid distributed systems diagnosis.

### Common Event Fields

- `timestamp`, `level`, `logger`, `message` (static name)
- `db.system`, `db.operation`, `db.statement` (truncated if needed)
- `duration_ms`, `rows_affected`

### Configuration

```python
from sqlspec.observability import ObservabilityConfig, LoggingConfig

ObservabilityConfig(
    logging=LoggingConfig(
        include_sql_hash=True,
        sql_truncation_length=2000,
        include_trace_context=True,
    )
)
```

---

## Correlation Middleware

Extracts trace headers across HTTP environments (Starlette, FastAPI, Flask).

### Supported Headers (Priority order)

1. `CorrelationExtractor` configured `correlation_header`
2. `traceparent` (W3C Trace Context)
3. `x-cloud-trace-context` (GCP)
4. `x-request-id`

### Generic Extraction Pattern

```python
from sqlspec.core import CorrelationExtractor

extractor = CorrelationExtractor(primary_header="x-request-id")
correlation_id = extractor.extract(lambda h: request.headers.get(h))
```

---

## Sampling Diagnostics

Control volume rates using bounded rates and clamps.

```python
from sqlspec.observability import SamplingConfig

config = SamplingConfig(
    sample_rate=0.1,                 # Sample 10% of requests
    force_sample_on_error=True,     # Always sample errors
    deterministic=True,              # Stable across replicas
)

---

## SQL-level Event Broadcasting (StatementObserver → Channels)

`SQLSpec.ObservabilityConfig` accepts a `statement_observers` tuple — callables invoked synchronously with a `StatementEvent` for every executed statement. This is the primary extension point for SQL-level side effects: audit logs, Prometheus counters, and **real-time broadcasts of DB changes** without modifying service code.

The canonical use case: broadcasting INSERT/UPDATE events on a target table to WebSocket clients subscribed to a Channels backend, without adding any publish calls to the service layer. Because the observer fires inside SQLSpec's statement lifecycle, it has access to the raw SQL string and parameters before the result is returned to the caller. The async bridge (`asyncio.get_running_loop().create_task(...)`) keeps the observer non-blocking.

### Implementation

```python
import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from msgspec.json import encode as to_json

if TYPE_CHECKING:
    from litestar_channels.backends.base import ChannelsBackend
    from sqlspec.observability import StatementEvent

logger = logging.getLogger(__name__)


class ChangeBroadcaster:
    """Broadcast INSERT/UPDATE events on a specific table to a Channels backend."""

    def __init__(
        self,
        backend: "ChannelsBackend",
        table: str,
        channel_resolver: Callable[..., str],
    ) -> None:
        self.backend = backend
        self.table = table
        self.channel_resolver = channel_resolver

    def __call__(self, event: "StatementEvent") -> None:
        sql_upper = event.sql.upper()
        if self.table.upper() not in sql_upper or (
            "INSERT" not in sql_upper and "UPDATE" not in sql_upper
        ):
            return  # quick-match filter — avoids create_task overhead for unrelated queries
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # sync script / test — no event loop; graceful no-op
        loop.create_task(self._publish(event))

    async def _publish(self, event: "StatementEvent") -> None:
        try:
            payload = {"sql": event.sql, "parameters": event.parameters}
            channel = self.channel_resolver(event.parameters)
            await self.backend.publish(to_json(payload, as_bytes=True), channels=[channel])
        except (OSError, RuntimeError, ValueError, TypeError):
            logger.exception("SQL change broadcast failed")
```

### Registration

Wire the observer into `ObservabilityConfig` when building `SQLSpec`:

```python
from sqlspec import SQLSpec
from sqlspec.observability import ObservabilityConfig

observer = ChangeBroadcaster(
    backend=channels._backend,
    table="orders",
    channel_resolver=lambda params: f"orders:{params['id']}:events",
)
observability = ObservabilityConfig(statement_observers=(observer,))
dbm = SQLSpec(observability_config=observability)
```

### Why it's safe

- **Sync→async bridge** — `asyncio.get_running_loop().create_task(...)` hands the async work off to the running loop without blocking the observer. `RuntimeError` is caught for non-loop contexts (sync scripts, test collection, Alembic migrations run from the shell).
- **Broadcast errors are swallowed** — the `except (OSError, RuntimeError, ValueError, TypeError)` block ensures a publish failure never disrupts the caller's SQL execution path.
- **Quick-match filter on `event.sql`** — checking `table.upper() in sql_upper` before spawning a task avoids `create_task` overhead for the vast majority of queries that don't match.

### Anti-patterns

- **Don't `await` anything in `__call__`** — the observer is a sync callback. All async work must go through `create_task`; an `await` here would require the caller to be a coroutine, which SQLSpec does not guarantee.
- **Don't raise from the observer** — SQLSpec does not trap observer exceptions in this contract; an unhandled exception will propagate into the statement lifecycle and corrupt the caller's stack trace.
- **Don't open DB connections from inside the observer** — you're already inside a statement lifecycle on that connection. If you need a second query (e.g. to resolve a tenant ID from a cache), use a separate connection pool acquired inside `_publish`, and reason carefully about re-entrancy.

---

## OpenTelemetry Extension

`sqlspec.extensions.otel` attaches a `CLIENT`-kind span to every statement execution, annotated with [OpenTelemetry database semantic conventions](https://opentelemetry.io/docs/specs/semconv/database/). Enable it by passing the returned `ObservabilityConfig` to `SQLSpec`.

### Wiring

`enable_tracing` returns an `ObservabilityConfig` with `telemetry` populated. Call `ensure_opentelemetry()` is invoked for you — if the OTel SDK is missing, you get a `MissingDependencyError` at config time rather than a silent no-op at runtime.

```python
from sqlspec import SQLSpec
from sqlspec.extensions.otel import enable_tracing

# Auto-discovery — uses the globally configured TracerProvider (the common case
# when you've already called `opentelemetry.trace.set_tracer_provider(...)` at
# app startup).
observability = enable_tracing(resource_attributes={"service.name": "orders-api"})
dbm = SQLSpec(observability_config=observability)
```

To override the ambient provider (e.g., for tests or multi-tenant isolation):

```python
from opentelemetry.sdk.trace import TracerProvider

provider = TracerProvider()
observability = enable_tracing(tracer_provider=provider)
```

Pass `tracer_provider_factory=...` when the provider is only safe to construct lazily (late-binding service names, post-fork init).

### Span Attributes

Every query span emits `sqlspec.query` with these attributes (see `sqlspec/observability/_spans.py::SpanManager.start_query_span`):

- `db.system` — OTel-canonical backend name (`postgresql`, `oracle`, `duckdb`, `sqlite`, …)
- `db.operation` — `SELECT` / `INSERT` / `UPDATE` / `DELETE` / `EXECUTE`
- `db.statement` — the compiled SQL (after redaction)
- `sqlspec.driver` — adapter class name
- `sqlspec.bind_key` — bind key if multiple adapters are registered
- `sqlspec.storage_backend` — Arrow storage backend when applicable
- `sqlspec.correlation_id` — request correlation ID when `CorrelationContext` is populated

Exceptions during execution call `span.record_exception(error)` and set `Status(StatusCode.ERROR)`.

### Common Pitfalls

- **Cardinality** — span names are a static string (`sqlspec.query`); `db.statement` goes into attributes. Do not templatize the span name with user input — attribute-based search is the right escape hatch.
- **Sampling interaction** — sqlspec's `SamplingConfig` controls whether log records and statement observers fire; it does not short-circuit OTel spans. The OTel `TracerProvider`'s sampler is authoritative for span drop decisions. Configure both layers consistently to avoid half-sampled telemetry.
- **Tracer provider factory failures are silent** — if `provider_factory()` raises, `SpanManager` falls back to `trace.get_tracer_provider()` and logs at DEBUG. Wire a provider-init smoke test if you depend on custom resource attributes flowing through.

---

## Prometheus Extension

`sqlspec.extensions.prometheus` registers a `PrometheusStatementObserver` that emits a counter plus two histograms keyed by low-cardinality labels.

### Metrics Surface

Built on `prometheus_client.Counter` and `prometheus_client.Histogram` with namespace `sqlspec` and subsystem `driver` by default:

- `sqlspec_driver_query_total{db_system,operation}` — counter of executed statements
- `sqlspec_driver_query_duration_seconds{db_system,operation}` — execution-time histogram (default buckets; override with `duration_buckets=(...)`)
- `sqlspec_driver_query_rows{db_system,operation}` — `rows_affected` histogram (observations skipped when the driver does not report a row count)

### Wiring

`enable_metrics` attaches the observer to an existing `ObservabilityConfig` (or creates one). Pair it with a `/metrics` Litestar route that scrapes `prometheus_client.generate_latest()`:

```python
from litestar import Litestar, get
from litestar.response import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from sqlspec import SQLSpec
from sqlspec.extensions.prometheus import enable_metrics


@get("/metrics", sync_to_thread=False)
def metrics() -> Response[bytes]:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


observability = enable_metrics(label_names=("db_system", "operation"))
dbm = SQLSpec(observability_config=observability)
app = Litestar(route_handlers=[metrics])
```

### Label Cardinality

`label_names` defaults to `("db_system", "operation")` — both bounded. The observer also accepts `"driver"`, `"adapter"`, and `"bind_key"` as known keys. **Never** add per-query or user-supplied values as labels: Prometheus allocates a time series per unique label tuple, and `sql_hash` alone blows past a million series on any non-trivial workload. Use OTel spans (previous section) for per-statement drill-downs.

---

## Cloud Log Formatters

`sqlspec.observability` ships three `CloudLogFormatter` implementations (`CloudLogFormatter` being the `typing.Protocol` they satisfy). Attach one to `ObservabilityConfig(cloud_formatter=...)` and the runtime uses it to shape structured log records.

### Selection

```python
from sqlspec import SQLSpec
from sqlspec.observability import (
    AWSLogFormatter,
    AzureLogFormatter,
    GCPLogFormatter,
    ObservabilityConfig,
)

gcp = ObservabilityConfig(cloud_formatter=GCPLogFormatter(project_id="acme-prod"))
aws = ObservabilityConfig(cloud_formatter=AWSLogFormatter())
azure = ObservabilityConfig(cloud_formatter=AzureLogFormatter())
```

### GCP (`GCPLogFormatter`)

- Field shape follows [Google's structured logging contract](https://cloud.google.com/logging/docs/structured-logging).
- Emits `severity` (string enum), `message`, `logging.googleapis.com/trace` (requires `project_id`), `logging.googleapis.com/spanId`, and `logging.googleapis.com/labels` (includes `correlation_id` when present).
- Severity map — Python → GCP: `DEBUG→DEBUG`, `INFO→INFO`, `WARNING→WARNING`, `ERROR→ERROR`, `CRITICAL→CRITICAL`. Unknown levels fall back to `DEFAULT`.
- `project_id` defaults to the `GOOGLE_CLOUD_PROJECT` environment variable.

Sample output:

```json
{"severity": "INFO", "message": "SELECT", "logging.googleapis.com/trace": "projects/acme-prod/traces/4bf92f3577b34da6a3ce929d0e0e4736", "logging.googleapis.com/spanId": "00f067aa0ba902b7", "logging.googleapis.com/labels": {"correlation_id": "req-abc123"}, "duration_ms": 15.5}
```

### AWS (`AWSLogFormatter`)

- Adds ISO 8601 UTC `timestamp`, `level`, `message`, `requestId` (from `correlation_id`), `xray_trace_id`, `xray_segment_id`.
- Level map collapses `WARNING→WARN` and `CRITICAL→FATAL` to match CloudWatch Logs Insights conventions.

Sample output:

```json
{"level": "INFO", "message": "SELECT", "timestamp": "2026-04-17T12:00:00+00:00", "requestId": "req-abc123", "xray_trace_id": "1-5f84c7a1-abcd", "duration_ms": 15.5}
```

### Azure (`AzureLogFormatter`)

- Shapes output for Azure Monitor / Application Insights: `message`, numeric `severityLevel` (0–4), `operation_Id` (trace), `operation_ParentId` (span), and a `properties` sub-dict for correlation + duration + extras.
- Severity map — Python → Azure numeric: `DEBUG→0`, `INFO→1`, `WARNING→2`, `ERROR→3`, `CRITICAL→4`.

Sample output:

```json
{"message": "SELECT", "severityLevel": 1, "operation_Id": "4bf92f3577b34da6a3ce929d0e0e4736", "operation_ParentId": "00f067aa0ba902b7", "properties": {"correlationId": "req-abc123", "durationMs": 15.5}}
```

### Correlation Propagation

All three formatters accept `correlation_id`, `trace_id`, and `span_id` directly — the runtime pulls `trace_id` / `span_id` from `get_trace_context()` (the ambient OTel span) and `correlation_id` from `CorrelationContext` before calling `formatter.format(...)`. No extra wiring is required beyond attaching the formatter and a correlation middleware.

### Custom Formatters

Implement the `CloudLogFormatter` protocol (`sqlspec/observability/_formatters/_base.py`) — a single `format(level, message, *, correlation_id, trace_id, span_id, duration_ms, extra)` method returning a `dict[str, Any]`. The protocol is structural; no base class inheritance is required.

---

## SQLCommenter

`sqlspec.core.sqlcommenter` implements the [Google SQLCommenter spec](https://google.github.io/sqlcommenter/) — URL-encoded key/value pairs appended to each statement as an SQL comment, using sqlglot AST manipulation so comments coexist with optimizer hints. DB-side tools (`pg_stat_statements`, Cloud SQL Query Insights, Oracle ASH) then correlate each query with the originating request.

### Enabling

Register the transformer on a `StatementConfig`. The three toggles compose:

- `attributes={...}` — static key/value pairs added to every statement (e.g., `framework`, `db_driver`).
- `enable_traceparent=True` — auto-populate `traceparent` from the current OTel span context via `get_trace_context()`.
- `enable_context=True` — merge per-request attributes from `SQLCommenterContext` (set by framework middleware) plus `correlation_id` from `CorrelationContext`.

```python
from sqlspec.core import StatementConfig
from sqlspec.core.sqlcommenter import create_sqlcommenter_statement_transformer

transformer = create_sqlcommenter_statement_transformer(
    attributes={"framework": "litestar", "db_driver": "asyncpg"},
    enable_traceparent=True,
    enable_context=True,
)
statement_config = StatementConfig(statement_transformers=(transformer,))
```

Per-request attributes flow through a context manager inside middleware:

```python
from sqlspec.core.sqlcommenter import SQLCommenterContext

with SQLCommenterContext.scope({"route": "/orders/{id}", "controller": "OrderController"}):
    ...  # run handler; every SQL statement inside carries these attributes
```

### Emitted Comment

A `SELECT` inside the scope above compiles to (keys sorted lexicographically, single-quote values URL-encoded):

```sql
SELECT * FROM orders WHERE id = $1 /* controller='OrderController',db_driver='asyncpg',framework='litestar',route='%2Forders%2F%7Bid%7D',traceparent='00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01' */
```

### Common Pitfalls

- **Plan cache churn** — Postgres hashes the full statement including comments for `pg_stat_statements`. Without `pg_stat_statements.track=top` plus `compute_query_id=on` and a normalization step, per-request `traceparent` values create a new row per execution. Enable `pg_stat_statements.track_utility=off` and rely on `queryid` (not the raw text) for aggregation. Oracle's cursor cache behaves similarly — confirm `CURSOR_SHARING=FORCE` or use bind-variable-only queries.
- **Comment leakage into logs** — if you ship raw SQL to your log sink, `traceparent` and `correlation_id` are now in cleartext log bodies. The `RedactionConfig` redacts parameters, not comments; strip comments in the log pipeline if that's a concern.
- **Static-only mode is cheap** — when neither `enable_traceparent` nor `enable_context` is set, the comment body is pre-generated once at transformer-creation time. The dynamic path re-serializes per statement; profile before enabling on extremely hot write paths.
