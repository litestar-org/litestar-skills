# SQLSpec Performance & Cloud Controls

## Overview

SQLSpec keeps performance controls explicit. Configure them through adapter `connection_config`, `driver_features`, `statement_config`, or the documented session providers. Do not invent new driver methods for cloud job/session control.

---

## Bounded Async Bridge

`sqlspec.utils.sync_tools.async_()` wraps blocking callables for async code. In `v0.51.0`, SQLSpec uses a process-local managed `ThreadPoolExecutor` capped by default.

Use an explicit executor when the call site owns the pool:

```python
from concurrent.futures import ThreadPoolExecutor

from sqlspec.utils.sync_tools import async_

executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="sqlspec")
run_query = async_(blocking_query, executor=executor)
result = await run_query()
```

Set the managed pool limit before the first bridge call:

```bash
export SQLSPEC_ASYNC_THREAD_LIMIT=8
```

Programmatic controls:

- `enable_default_async_thread_pool(max_workers=8)`
- `set_default_async_executor(executor)`
- `get_default_async_executor()`
- `shutdown_default_async_executor(wait=False)`

Precedence is explicit: `async_(fn, executor=...)` wins over `set_default_async_executor()`, which wins over SQLSpec's managed pool. Only `ThreadPoolExecutor` instances are accepted because SQLSpec preserves `contextvars` through bridge calls.

---

## Statement Cache And Fetch Tuning

| Adapter | Knob | Use when | Avoid when |
| --- | --- | --- | --- |
| All drivers | `driver_features={"sqlspec_statement_cache_size": N}` | Same raw SQL text runs repeatedly with simple parameters | SQL text is high-cardinality or DDL changes affect result shapes |
| `asyncpg` | `connection_config={"statement_cache_size": N}` | Long-lived PostgreSQL sessions repeat parameterized statements | PgBouncer transaction/statement pooling or frequent schema churn |
| `psycopg` | `connection_config={"prepare_threshold": N}` | Repeated queries amortize server-side planning | Rarely repeated queries or connection middleware changes sessions |
| `oracledb` | `connection_config={"stmtcachesize": N}` | Same Oracle statement text repeats frequently | Statement text has high cardinality or memory pressure dominates |
| `oracledb` | `driver_features={"arraysize": N, "prefetchrows": N}` | Large result sets spend time on network round trips | Single-row lookups or very wide rows dominate |
| `oracledb` | `driver_features={"fetch_lobs": False, "fetch_decimals": True}` | You need native LOB or NUMBER fetch representation | Application expects SQLSpec defaults |
| `bigquery` | `driver_features={"query_page_size": N, "query_max_results": N}` | Bound page size or total rows for SELECT result fetching | DML and scripts; these controls apply to result fetching |
| `arrow_odbc` | `driver_features={"chunk_size": N, "max_bytes_per_batch": N}` | Tune Arrow batch memory and round trips | Downstream requires a fixed batch shape |
| `arrow_odbc` | `driver_features={"max_text_size": N, "max_binary_size": N, "fetch_concurrently": bool}` | Bound text/binary columns or improve high-latency fetches | Truncation is unacceptable or the ODBC source is unstable under concurrent fetch |

Measure before changing defaults. Cache knobs help repeated statement text on stable sessions; fetch knobs tune network and memory after the query plan is already correct.

---

## BigQuery Job Controls

Configure BigQuery job behavior through `BigQueryConfig.driver_features`.

| Feature | Effect |
| --- | --- |
| `job_retry_deadline` | Total seconds for retry construction; `<= 0` disables the BigQuery job retry wrapper |
| `job_result_timeout` | Bounds waits on `QueryJob.result()` and load-job completion |
| `request_timeout` | Bounds the initial BigQuery API request; defaults from `job_result_timeout` when numeric |
| `use_query_and_wait` | Uses `Client.query_and_wait()` for simple query execution |
| `query_page_size` | Passed to `QueryJob.result()` for SELECT result fetching |
| `query_max_results` | Total row cap passed to `QueryJob.result()` for SELECT result fetching |
| `enable_storage_write_api` | Uses Storage Write API for `load_from_arrow(..., overwrite=False)` appends when available |

Use the normal SQLSpec calls: `execute()`, `select()`, `select_to_arrow()`, `select_to_storage()`, `load_from_arrow()`, and `load_from_storage()`. SQLSpec does not expose `execute_with_job()` or `export_table_to_storage()`.

Use `job_retry_deadline=0` for emulators or endpoints where retrying unsupported jobs extends failure time.

---

## Spanner Request And Session Controls

Configure defaults through `SpannerSyncConfig.driver_features`:

- `request_options` -- forwarded to `execute_sql()`, `execute_update()`, and `batch_update()`.
- `directed_read_options` -- forwarded only to read calls using `execute_sql()`.
- `retry` and `timeout` -- forwarded to statement execution calls.
- `enable_batch_write_api` -- routes `load_from_arrow()` through Spanner Batch Write API for high-throughput mutation groups when `overwrite=False`.

Per-call overrides use the existing driver methods:

```python
result = driver.execute(
    "SELECT id FROM users WHERE id = @id",
    {"id": "u-1"},
    request_options={"request_tag": "users.lookup"},
    directed_read_options=directed_read_options,
    timeout=10.0,
)
```

Session-scoped controls belong on `provide_session()`:

```python
with config.provide_session(
    request_options={"transaction_tag": "orders.write"},
    retry=retry,
    timeout=20.0,
) as driver:
    driver.execute("UPDATE orders SET status = @status WHERE id = @id", params)
```

Use `provide_read_session()` for single-use snapshot reads. Use `provide_session()` or `provide_write_session()` for DDL, DML, and write-capable transactions.

SQLSpec does not expose public `execute_with_options()`, `execute_partitioned_dml()`, `apply_mutations()`, or `provide_batch_snapshot()` methods.
