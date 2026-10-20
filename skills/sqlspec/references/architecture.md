# SQLSpec Architecture & Caching

## Core Data Flow

```text
Raw SQL / Builder API / SQL File
        |
        v
    SQL Object (immutable statement + params)
        |
        v
    sqlglot AST (parse, validate, transpile)
        |
        v
    Parameter Binding (style conversion)
        |
        v
    Driver Adapter (execute against database)
        |
        v
    Result (rows, Arrow, scalar, rows_affected)
```

The `SQL` object is the single source of truth. All operations produce new `SQL` instances (immutability). The pipeline is single-pass: parse once, transform once, validate once.

---

## NamespacedCache System

SQLSpec uses a structured caching system to eliminate redundant parsing, transpilation, and file I/O. All caches are keyed by namespace and managed through the `NamespacedCache` coordinator.

### Cache Namespaces

Names used by `NamespacedCache`:

- `statement`: compiled SQL and safe rebinding state
- `builder`: value-independent builder templates
- `expression`: parsed sqlglot expressions and fragments
- `file`: loaded SQL files
- `optimized`: optimizer-processed expressions

### Cache Configuration

`CacheConfig` groups namespaces by workload. It does not accept per-namespace objects or TTL values:

```python
from sqlspec import CacheConfig, SQLSpec

cache_config = CacheConfig(
    compiled_cache_enabled=True,
    sql_cache_enabled=True,
    fragment_cache_enabled=True,
    optimized_cache_enabled=True,
    sql_cache_size=2_000,
    fragment_cache_size=5_000,
    optimized_cache_size=2_000,
)

db_manager = SQLSpec()
db_manager.update_cache_config(cache_config)
```

### Cache Behavior

- **Global configuration**: `update_cache_config()` replaces the process-global configuration and clears existing caches.
- **LRU + TTL**: the built-in namespaces use bounded, locked LRU caches with a one-hour default TTL.
- **Template isolation & zero-copy AST sharing**: builder and optimized-expression cache hits return isolated expressions; current values and statement configuration are rebound on each call. Compiled `ProcessedState` instances share cached SQLGlot ASTs (`expression_is_shared=True`) across executions without eager deep copies; public `SQL.expression` and `SQL.statement_expression` properties copy lazily on first access via `ProcessedState.ensure_owned_expression()`, while internal read-only paths inspect `SQL._peek_expression()`.
- **File validation**: `SQLFileLoader` compares an MD5 content checksum before reusing a tracked file.
- **Shared per-config `StatementCacheHolder` & fast path**: every database config creates a single `StatementCacheHolder` (`sqlspec.driver._query_cache.StatementCacheHolder`) shared across all sessions spawned from that config. It holds the raw-statement `QueryCache` (controlled by `driver_features={"sqlspec_statement_cache_size": N}`; set `N=0` to disable), the compiled `_statement_cache`, a shared `rebind_processor` (`ParameterProcessor`), `_row_count_hints`, and `_bulk_insert_sql`. The driver fast path (`_cached_execution` -> `_execute_cache_hit`) executes parameterless (`()`) and scalar-positional (`(v1, v2, ...)`) cache hits directly and remains active when observability spans, observers, or lifecycle hooks are enabled.

### Cache Hit/Miss Monitoring

```python
from sqlspec import SQLSpec

db_manager = SQLSpec()
metrics = db_manager.get_cache_stats()
```

The result maps cache namespace names to `CacheStats` objects with `hits`, `misses`, `evictions`, `total_operations`, `memory_usage`, and `hit_rate`. Use `db_manager.log_cache_stats()` for structured debug logging and `db_manager.reset_stats_only()` to reset counters without clearing entries.

---

## Performance Guidelines

### Mypyc Compilation

Gate compilation via `HATCH_BUILD_HOOKS_ENABLE=1` and verify with `.so` imports:

```bash
HATCH_BUILD_HOOKS_ENABLE=1 uv build --wheel
```

### Optimization Rules

- Favor primitive types to minimize boxed operations under mypyc.
- Cache constant SQL fragments at module scope.
- Use `copy=False` on all sqlglot builder mutations (mandatory project default).
- Prefer `select_to_arrow()` over row-based methods for large result sets.
- Use `execute_many()` with tuple parameters for batch DML operations.
- Gate CPU-bound crawlers under `@profile` for debugging logic gaps.
