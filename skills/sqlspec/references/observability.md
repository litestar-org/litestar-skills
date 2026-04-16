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

Pattern adapted from `dma/accelerator/src/py/dma/db/hooks.py:L20–189` (`ETLLogObserver`) + registration at `dma/accelerator/src/py/dma/config.py:L96–100`.

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
