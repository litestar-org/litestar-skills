import inspect
from importlib.metadata import version

from google.adk.sessions.base_session_service import GetSessionConfig
from sqlspec import (
    LoggingConfig,
    ObservabilityConfig,
    RedactionConfig,
    SQLFileLoader,
    SQLSpec,
    StackResult,
    StatementStack,
    TelemetryConfig,
    create_statement_observer,
    default_statement_observer,
    sql,
)
from sqlspec.adapters.sqlite import SqliteConfig
from sqlspec.cli import add_migration_commands, get_sqlspec_group
from sqlspec.core import OffsetPagination
from sqlspec.core.filters import (
    LimitOffsetFilter,
    OrderByFilter,
    SearchFilter,
)
from sqlspec.core.result import SQLResult
from sqlspec.extensions.adk import (
    PruneReport,
    SQLSpecArtifactService,
    SQLSpecMemoryService,
    SQLSpecSessionService,
    SQLSpecSyncMemoryService,
    prune_artifacts,
    prune_events,
    prune_memory,
    prune_sessions,
    prune_user_state,
)
from sqlspec.extensions.litestar import SQLSpecPlugin
from sqlspec.service import SQLSpecAsyncService, SQLSpecSyncService
from sqlspec.storage import (
    AsyncStoragePipeline,
    StorageCapabilities,
    StorageRegistry,
    SyncStoragePipeline,
    storage_registry,
)


def test_sqlspec_062_contract() -> None:
    """Validate sqlspec 0.62.0 core contracts and exported API surface."""
    assert version("sqlspec") == "0.62.0"

    assert "sqlspec" in inspect.signature(SQLSpecPlugin).parameters
    spec = SQLSpec()
    plugin = SQLSpecPlugin(spec)
    assert plugin is not None

    assert callable(sql.select)
    assert callable(sql.insert)
    assert callable(sql.update)
    assert callable(sql.delete)
    assert callable(sql.merge)
    assert callable(sql.upsert)
    assert callable(sql.explain)
    assert callable(sql.create_table)
    assert callable(sql.alter_table)
    assert callable(sql.drop_table)
    assert callable(sql.copy)
    assert callable(sql.copy_from)
    assert callable(sql.copy_to)
    assert callable(sql.case)
    assert callable(sql.column)
    assert callable(sql.to_literal)

    assert hasattr(sql, "row_number_")
    assert hasattr(sql, "rank_")
    assert hasattr(sql, "dense_rank_")
    assert hasattr(sql, "count_over_")
    assert hasattr(sql, "sum_over_")
    assert hasattr(sql, "avg_over_")
    assert hasattr(sql, "min_over_")
    assert hasattr(sql, "max_over_")
    assert hasattr(sql, "lag_")
    assert hasattr(sql, "lead_")
    assert hasattr(sql, "inner_join_")
    assert hasattr(sql, "left_join_")
    assert hasattr(sql, "right_join_")
    assert hasattr(sql, "full_join_")
    assert hasattr(sql, "cross_join_")
    assert hasattr(sql, "lateral_join_")
    assert hasattr(sql, "left_lateral_join_")
    assert hasattr(sql, "cross_lateral_join_")

    loader = SQLFileLoader()
    loader.add_named_sql("test-query", "SELECT 1")
    assert loader.has_query("test-query")
    assert loader.get_sql("test-query").sql.strip() == "SELECT 1"

    commands = add_migration_commands(get_sqlspec_group()).commands
    assert "create-migration" in commands
    assert "upgrade" in commands
    assert "downgrade" in commands
    assert "show-current-revision" in commands
    assert "stamp" in commands
    assert "init" in commands
    assert "fix" in commands
    assert "squash" in commands
    assert "show-config" in commands
    assert "adk" in commands
    assert "database" not in commands

    obs = ObservabilityConfig(
        logging=LoggingConfig(include_sql_hash=True),
        telemetry=TelemetryConfig(enable_spans=False),
        redaction=RedactionConfig(mask_parameters=True),
    )
    assert obs.logging is not None
    assert obs.logging.include_sql_hash is True
    assert callable(create_statement_observer)
    assert callable(default_statement_observer)

    assert issubclass(SQLSpecSessionService, object)
    assert issubclass(SQLSpecMemoryService, object)
    assert issubclass(SQLSpecSyncMemoryService, object)
    assert issubclass(SQLSpecArtifactService, object)
    assert callable(prune_sessions)
    assert callable(prune_memory)
    assert callable(prune_events)
    assert callable(prune_artifacts)
    assert callable(prune_user_state)

    assert issubclass(SQLSpecAsyncService, object)
    assert issubclass(SQLSpecSyncService, object)
    assert issubclass(OffsetPagination, object)
    assert issubclass(LimitOffsetFilter, object)
    assert issubclass(OrderByFilter, object)
    assert issubclass(SearchFilter, object)

    assert isinstance(storage_registry, StorageRegistry)
    assert issubclass(AsyncStoragePipeline, object)
    assert issubclass(SyncStoragePipeline, object)
    assert issubclass(StorageCapabilities, object)


def test_sqlspec_062_statement_stack_execution_contract() -> None:
    """Verify immutable stack construction and ordered SQLite execution."""
    config = SQLSpec().add_config(SqliteConfig(connection_config={"database": ":memory:"}))
    initial_stack = StatementStack()
    stack = (
        initial_stack.push_execute("CREATE TABLE users (name TEXT)")
        .push_execute_many("INSERT INTO users (name) VALUES (?)", [("Ada",), ("Lin",)])
        .push_execute("SELECT name FROM users ORDER BY name")
    )

    assert len(initial_stack) == 0
    assert len(stack.operations) == 3

    with config.provide_session() as session:
        results = session.execute_stack(stack)

    assert isinstance(results, tuple)
    assert len(results) == 3
    assert all(isinstance(result, StackResult) for result in results)
    query_result = results[-1].result
    assert isinstance(query_result, SQLResult)
    assert query_result.all() == [{"name": "Ada"}, {"name": "Lin"}]


def test_sqlspec_062_vector_expression_contract() -> None:
    """Verify vector distance is a column expression that can order a query."""
    distance = sql.column("embedding").vector_distance([0.1, 0.2, 0.3], metric="cosine")
    query = sql.select("id").from_("documents").where(distance < 0.3).order_by(distance.asc()).limit(10)

    assert "<=>" in query.build(dialect="postgres").sql


def test_sqlspec_062_adk_retention_contract() -> None:
    """Verify the public retention helpers and their distinct day parameters."""
    assert set(PruneReport.__annotations__) == {"deleted_count", "elapsed_ms", "table"}
    assert {"target", "idle_days", "app_name"}.issubset(inspect.signature(prune_sessions).parameters)
    assert {"target", "older_than_days", "app_name"}.issubset(inspect.signature(prune_events).parameters)
    assert {"target", "older_than_days", "app_name", "scope"}.issubset(inspect.signature(prune_memory).parameters)
    assert {"target", "older_than_days", "app_name"}.issubset(inspect.signature(prune_artifacts).parameters)
    assert {"target", "idle_days", "app_name"}.issubset(inspect.signature(prune_user_state).parameters)


def test_sqlspec_062_adk_bounded_session_contract() -> None:
    """Verify bounded event reads and ordered session-list parameters."""
    config = GetSessionConfig(num_recent_events=200, after_timestamp=1_725_000_000.0)
    get_session_params = inspect.signature(SQLSpecSessionService.get_session).parameters
    list_sessions_params = inspect.signature(SQLSpecSessionService.list_sessions).parameters

    assert config.num_recent_events == 200
    assert config.after_timestamp == 1_725_000_000.0
    assert {"app_name", "user_id", "session_id", "config"}.issubset(get_session_params)
    assert {"app_name", "user_id", "order_by", "descending", "limit", "offset"}.issubset(list_sessions_params)
