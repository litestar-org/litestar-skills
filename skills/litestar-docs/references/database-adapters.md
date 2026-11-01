# Database Adapter Documentation

Standard pattern for documenting multi-driver database libraries (`sqlspec`, `advanced-alchemy`, `pytest-databases`) across both **Zensical** and **Sphinx** without duplicating core concepts across driver pages.

## Adapter Documentation Structure

1. **Central Capability Matrix (`docs/databases/index.{md,rst}`)**:
   - Opens the `Databases` section with a comparison table across all supported adapters (`Adapter`, `Driver Package`, `Sync / Async`, `Parameter Style`, `Native Pool`, `Arrow / Bulk Ingest`, `Extension Stores`).
   - Lists peer engine sections flat in the left sidebar (`PostgreSQL`, `CockroachDB`, `SQLite`, `DuckDB`, `MySQL & MariaDB`, `Oracle Database`, `SQL Server`, `IBM Db2`, `BigQuery`, `Cloud Spanner`, `ADBC`, `Arrow ODBC`).
2. **Concise Per-Driver Setup Guide (`docs/databases/<engine>/<adapter>.{md,rst}`)**:
   - Strictly `<= 10` viewports (`~80–140` lines).
   - Covers **only** driver-specific concerns; do not re-teach core query builders or general middleware on adapter pages.
3. **Own-Symbols-Only Adapter API Reference (`docs/reference/adapters/<adapter>.{md,rst}`)**:
   - Documents only the adapter's own `*Config`, `*ConnectionParams`, `*PoolParams`, `*DriverFeatures`, `*Driver`, and `*ExceptionHandler`.
   - Links to `SyncDriverAdapterBase` or `AsyncDriverAdapterBase` for inherited execution methods (`select`, `select_one`, `execute`, `execute_many`).

## Per-Driver Guide Sections

Every `docs/databases/<engine>/<adapter>` page follows five sections:

1. **Installation & Summary Table**:
   - Synchronized package manager tabs (`uv`, `pip`, `pdm`, `poetry`).
   - Compact metadata table (`Driver`, `Config Class`, `Driver Class`, `Execution Mode`, `Param Style`, `API Reference` link).
2. **Quickstart Snippet**:
   - Standalone runnable example from `docs/examples/databases/<adapter>/connect.py`.
3. **Connection & Pool Configuration**:
   - Concise table or example of primary `connection_config` / `pool_config` keys linking to the full `TypedDict` table in the API Reference.
4. **Type Mapping & Dialect Notes**:
   - Engine-specific behaviors (`JSONB` codecs, `VECTOR` embeddings, prepared-statement pooling, `MERGE` / `RETURNING` support, TLS/wallet setup).
5. **See Also**:
   - Links to the Central Capability Matrix, Core Configuration guide, and the adapter's API Reference page.

## Curated Adapter API Reference Templates

### Zensical (`docs/reference/adapters/asyncpg.md`)

````markdown
# AsyncPG API Reference

```python
from sqlspec.adapters.asyncpg import AsyncpgConfig, AsyncpgDriver
```

API reference for `sqlspec.adapters.asyncpg`. Inherited execution methods are documented on [`AsyncDriverAdapterBase`](../driver/async.md).

## Configuration & Parameter Types

::: sqlspec.adapters.asyncpg.AsyncpgConfig
    options:
      members:
        - provide_connection
        - provide_session
        - provide_pool
        - create_pool
        - close_pool

::: sqlspec.adapters.asyncpg.config.AsyncpgPoolConfig

::: sqlspec.adapters.asyncpg.config.AsyncpgConnectionConfig

## Driver & Exception Handling

::: sqlspec.adapters.asyncpg.AsyncpgDriver
    options:
      inherited_members: false
      show_bases: true
      members:
        - dialect
        - data_dictionary

::: sqlspec.adapters.asyncpg.driver.AsyncpgExceptionHandler
````

### Sphinx (`docs/reference/adapters/asyncpg.rst`)

```rst
AsyncPG API Reference
=====================

.. code-block:: python

    from sqlspec.adapters.asyncpg import AsyncpgConfig, AsyncpgDriver

API reference for ``sqlspec.adapters.asyncpg``. Inherited execution methods are documented on :class:`~sqlspec.driver.AsyncDriverAdapterBase`.

Configuration & Parameter Types
-------------------------------

.. autoclass:: sqlspec.adapters.asyncpg.AsyncpgConfig
    :members: provide_connection, provide_session, provide_pool, create_pool, close_pool
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: sqlspec.adapters.asyncpg.config.AsyncpgPoolConfig
    :members:
    :no-inherited-members:

.. autoclass:: sqlspec.adapters.asyncpg.config.AsyncpgConnectionConfig
    :members:
    :no-inherited-members:

Driver & Exception Handling
---------------------------

.. autoclass:: sqlspec.adapters.asyncpg.AsyncpgDriver
    :members: dialect, data_dictionary
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: sqlspec.adapters.asyncpg.driver.AsyncpgExceptionHandler
    :members:
    :no-inherited-members:
```
