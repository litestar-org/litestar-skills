import ast
import importlib.util
import inspect
from dataclasses import fields
from importlib.metadata import entry_points, version
from pathlib import Path
from typing import get_args

import pytest_databases._service as core_service
import pytest_databases.docker as docker_pkg
from pytest_databases._service import DockerService
from pytest_databases.docker import (
    cockroachdb,
    dolt,
    mariadb,
    minio,
    mongodb,
    mssql,
    mysql,
    oracle,
    postgres,
    rustfs,
    yugabyte,
)
from pytest_databases.helpers import (
    get_xdist_worker_count,
    get_xdist_worker_id,
    get_xdist_worker_num,
)
from pytest_databases.types import ServiceContainer, XdistIsolationLevel


def _ast_module_tree(module_name: str) -> ast.Module:
    """Return the parsed AST for an installed module without importing it."""
    spec = importlib.util.find_spec(module_name)
    assert spec is not None and spec.origin is not None
    return ast.parse(Path(spec.origin).read_text(encoding="utf-8"))


def _ast_top_level_names(module_name: str) -> tuple[set[str], set[str]]:
    """Return top-level class names and function names defined in a module via AST."""
    tree = _ast_module_tree(module_name)
    classes = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
    funcs = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return classes, funcs


def _ast_class_contract(module_name: str, class_name: str) -> tuple[dict[str, str], set[str]]:
    """Return annotated field types and @property names for a class defined in a module via AST."""
    tree = _ast_module_tree(module_name)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            field_types = {
                item.target.id: ast.unparse(item.annotation)
                for item in node.body
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
            }
            properties = {
                item.name
                for item in node.body
                if isinstance(item, ast.FunctionDef)
                and any(ast.unparse(dec) == "property" for dec in item.decorator_list)
            }
            return field_types, properties
    msg = f"Class {class_name!r} not found in {module_name}"
    raise AssertionError(msg)


def _ast_function_params(module_name: str, func_name: str) -> list[str]:
    """Return positional parameter names for a top-level function in a module via AST."""
    tree = _ast_module_tree(module_name)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            return [arg.arg for arg in node.args.args]
    msg = f"Function {func_name!r} not found in {module_name}"
    raise AssertionError(msg)


def _ast_top_level_imports(module_name: str) -> set[str]:
    """Return top-level imported root module names for a module via AST."""
    tree = _ast_module_tree(module_name)
    imported: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module.split(".")[0])
    return imported


def test_pytest_databases_019_plugin_modules_and_core_hooks_contract() -> None:
    """Verify exact docker plugin module inventory and core entry-point hooks in 0.19.0."""
    docker_dir = Path(docker_pkg.__file__).parent
    actual_modules = {p.stem for p in docker_dir.glob("*.py") if p.stem != "__init__"}
    expected_modules = {
        "azure_blob",
        "bigquery",
        "cockroachdb",
        "dolt",
        "elastic_search",
        "gizmosql",
        "mariadb",
        "minio",
        "mongodb",
        "mssql",
        "mysql",
        "oracle",
        "postgres",
        "redis",
        "rustfs",
        "spanner",
        "valkey",
        "yugabyte",
    }
    assert actual_modules == expected_modules
    for mod in expected_modules:
        assert importlib.util.find_spec(f"pytest_databases.docker.{mod}") is not None

    non_existent_modules = (
        "alloydb",
        "ElasticSearch",
        "elasticsearch",
        "azurite",
        "cassandra",
        "clickhouse",
        "couchbase",
        "dynamodb",
        "meilisearch",
        "neo4j",
        "qdrant",
        "scylladb",
        "surrealdb",
        "timescaledb",
        "typesense",
        "vespa",
        "weaviate",
    )
    for mod in non_existent_modules:
        assert importlib.util.find_spec(f"pytest_databases.docker.{mod}") is None

    pytest11_eps = [ep for ep in entry_points(group="pytest11") if ep.name == "pytest_databases"]
    assert len(pytest11_eps) == 1
    assert pytest11_eps[0].value == "pytest_databases._service"
    assert hasattr(core_service, "docker_client")
    assert hasattr(core_service, "docker_service")
    assert hasattr(core_service, "pytest_sessionfinish")
    assert not hasattr(core_service, "pytest_addoption")


def test_pytest_databases_019_provider_and_port_contract() -> None:
    """Verify pytest-databases 0.19.0 core DockerService, helpers, and PostgreSQL-family fixtures."""
    assert version("pytest-databases") == "0.19.0"
    assert "host_port" in inspect.signature(DockerService.run).parameters
    assert set(get_args(XdistIsolationLevel)) == {"database", "server"}
    assert callable(get_xdist_worker_id)
    assert callable(get_xdist_worker_num)
    assert callable(get_xdist_worker_count)

    for release in range(11, 19):
        assert hasattr(postgres, f"postgres_{release}_service")
        assert hasattr(postgres, f"postgres_{release}_connection")
        assert hasattr(postgres, f"postgres_{release}_port")
    for release in range(13, 19):
        assert hasattr(postgres, f"pgvector_{release}_service")
        assert hasattr(postgres, f"pgvector_{release}_connection")
        assert hasattr(postgres, f"pgvector_{release}_port")
    for release in range(15, 19):
        assert hasattr(postgres, f"paradedb_{release}_service")
        assert hasattr(postgres, f"paradedb_{release}_connection")
        assert hasattr(postgres, f"paradedb_{release}_port")
    for release in range(15, 18):
        assert hasattr(postgres, f"alloydb_omni_{release}_service")
        assert hasattr(postgres, f"alloydb_omni_{release}_connection")
        assert hasattr(postgres, f"alloydb_omni_{release}_port")
    assert hasattr(postgres, "xdist_postgres_isolation_level")
    assert inspect.unwrap(postgres.postgres_image)() == "postgres:18"
    assert inspect.unwrap(postgres.pgvector_image)() == "pgvector/pgvector:pg18"
    assert inspect.unwrap(postgres.paradedb_image)() == "paradedb/paradedb:latest-pg18"
    assert inspect.unwrap(postgres.alloydb_omni_image)() == "google/alloydbomni:17"
    assert list(inspect.signature(inspect.unwrap(postgres.postgres_port)).parameters) == []


def test_pytest_databases_019_imported_plugin_modules_contract() -> None:
    """Verify service classes, attributes, and fixtures across directly importable docker modules."""
    assert issubclass(postgres.PostgresService, ServiceContainer)
    assert {f.name for f in fields(postgres.PostgresService)} >= {
        "host",
        "port",
        "container",
        "database",
        "user",
        "password",
    }

    assert issubclass(cockroachdb.CockroachDBService, ServiceContainer)
    assert {(f.name, f.type) for f in fields(cockroachdb.CockroachDBService)} >= {
        ("database", "str"),
        ("driver_opts", "dict[str, str]"),
    }
    assert hasattr(cockroachdb, "cockroachdb_service")
    assert hasattr(cockroachdb, "cockroachdb_connection")
    assert hasattr(cockroachdb, "xdist_cockroachdb_isolation_level")

    assert issubclass(mysql.MySQLService, ServiceContainer)
    assert {f.name for f in fields(mysql.MySQLService)} >= {"host", "port", "container", "db", "user", "password"}
    for suffix in ("56", "57", "8", "84", "96"):
        assert hasattr(mysql, f"mysql_{suffix}_service")
    assert hasattr(mysql, "mysql_service")
    assert hasattr(mysql, "xdist_mysql_isolation_level")

    assert issubclass(mariadb.MariaDBService, ServiceContainer)
    for suffix in ("113", "114", "122"):
        assert hasattr(mariadb, f"mariadb_{suffix}_service")
    assert hasattr(mariadb, "mariadb_service")
    assert hasattr(mariadb, "xdist_mariadb_isolation_level")

    assert issubclass(dolt.DoltService, ServiceContainer)
    assert hasattr(dolt, "dolt_service")
    assert hasattr(dolt, "xdist_dolt_isolation_level")

    assert issubclass(oracle.OracleService, ServiceContainer)
    assert {f.name for f in fields(oracle.OracleService)} >= {
        "host",
        "port",
        "container",
        "user",
        "password",
        "system_password",
        "service_name",
    }
    assert hasattr(oracle, "oracle_service")
    assert hasattr(oracle, "oracle_18c_service")
    assert hasattr(oracle, "oracle_23ai_service")
    assert hasattr(oracle, "oracle_18c_connection")
    assert hasattr(oracle, "oracle_23ai_connection")
    assert list(inspect.signature(inspect.unwrap(oracle.oracle_startup_connection)).parameters) == [
        "oracle_23ai_startup_connection"
    ]
    assert not hasattr(oracle, "oracle_23ai_startup_connection")

    assert issubclass(mssql.MSSQLService, ServiceContainer)
    assert hasattr(mssql.MSSQLService, "connection_string")
    assert hasattr(mssql, "mssql_service")
    assert hasattr(mssql, "xdist_mssql_isolation_level")

    assert issubclass(yugabyte.YugabyteService, ServiceContainer)
    assert hasattr(yugabyte, "yugabyte_service")
    assert hasattr(yugabyte, "xdist_yugabyte_isolation_level")

    assert issubclass(mongodb.MongoDBService, ServiceContainer)
    assert {f.name for f in fields(mongodb.MongoDBService)} >= {
        "host",
        "port",
        "container",
        "username",
        "password",
        "database",
    }
    assert hasattr(mongodb, "mongodb_service")
    assert hasattr(mongodb, "mongodb_connection")
    assert hasattr(mongodb, "mongodb_database")
    assert hasattr(mongodb, "xdist_mongodb_isolation_level")

    assert issubclass(minio.MinioService, ServiceContainer)
    assert {f.name for f in fields(minio.MinioService)} >= {
        "host",
        "port",
        "container",
        "endpoint",
        "access_key",
        "secret_key",
        "secure",
    }
    assert hasattr(minio, "minio_service")
    assert hasattr(minio, "minio_default_bucket_name")
    assert hasattr(minio, "xdist_minio_isolation_level")

    assert issubclass(rustfs.RustfsService, ServiceContainer)
    assert {f.name for f in fields(rustfs.RustfsService)} >= {
        "host",
        "port",
        "container",
        "endpoint",
        "access_key",
        "secret_key",
        "secure",
    }
    assert hasattr(rustfs, "rustfs_service")
    assert hasattr(rustfs, "rustfs_default_bucket_name")
    assert hasattr(rustfs, "xdist_rustfs_isolation_level")


def test_pytest_databases_019_optional_client_plugin_modules_contract() -> None:
    """Verify AST contracts for docker plugin modules whose optional client extras are not installed."""
    redis_classes, redis_funcs = _ast_top_level_names("pytest_databases.docker.redis")
    assert "RedisService" in redis_classes
    assert _ast_class_contract("pytest_databases.docker.redis", "RedisService") == ({"db": "int"}, set())
    assert "redis" in _ast_top_level_imports("pytest_databases.docker.redis")
    assert _ast_function_params("pytest_databases.docker.redis", "redis_port") == ["redis_service"]
    assert _ast_function_params("pytest_databases.docker.redis", "dragonfly_port") == ["dragonfly_service"]
    assert _ast_function_params("pytest_databases.docker.redis", "keydb_port") == ["keydb_service"]
    assert {
        "redis_service",
        "redis_host",
        "redis_port",
        "redis_image",
        "dragonfly_service",
        "dragonfly_host",
        "dragonfly_port",
        "dragonfly_image",
        "keydb_service",
        "keydb_host",
        "keydb_port",
        "keydb_image",
        "xdist_redis_isolation_level",
    } <= redis_funcs

    valkey_classes, valkey_funcs = _ast_top_level_names("pytest_databases.docker.valkey")
    assert "ValkeyService" in valkey_classes
    assert _ast_class_contract("pytest_databases.docker.valkey", "ValkeyService") == ({"db": "int"}, set())
    assert "valkey" in _ast_top_level_imports("pytest_databases.docker.valkey")
    assert _ast_function_params("pytest_databases.docker.valkey", "valkey_port") == ["valkey_service"]
    assert {
        "valkey_service",
        "valkey_host",
        "valkey_port",
        "valkey_image",
        "xdist_valkey_isolation_level",
    } <= valkey_funcs

    es_classes, es_funcs = _ast_top_level_names("pytest_databases.docker.elastic_search")
    assert "ElasticsearchService" in es_classes
    assert _ast_class_contract("pytest_databases.docker.elastic_search", "ElasticsearchService") == (
        {"scheme": "str", "user": "str", "password": "str", "database": "str"},
        set(),
    )
    assert "elasticsearch7" in _ast_top_level_imports("pytest_databases.docker.elastic_search")
    assert {
        "elasticsearch_7_service",
        "elasticsearch_8_service",
        "elasticsearch_service",
        "elasticsearch_service_memory_limit",
    } <= es_funcs
    assert _ast_function_params("pytest_databases.docker.elastic_search", "elasticsearch_service") == [
        "elasticsearch8_service"
    ]
    assert "elasticsearch8_service" not in es_funcs

    bq_classes, bq_funcs = _ast_top_level_names("pytest_databases.docker.bigquery")
    assert "BigQueryService" in bq_classes
    assert _ast_class_contract("pytest_databases.docker.bigquery", "BigQueryService") == (
        {"project": "str", "dataset": "str", "credentials": "Credentials"},
        {"endpoint", "client_options"},
    )
    assert {
        "bigquery_service",
        "bigquery_client",
        "bigquery_image",
        "platform",
        "xdist_bigquery_isolation_level",
    } <= bq_funcs

    spanner_classes, spanner_funcs = _ast_top_level_names("pytest_databases.docker.spanner")
    assert "SpannerService" in spanner_classes
    assert _ast_class_contract("pytest_databases.docker.spanner", "SpannerService") == (
        {"credentials": "Credentials", "project": "str", "database_name": "str", "instance_name": "str"},
        {"endpoint", "client_options"},
    )
    assert {"spanner_service", "spanner_connection", "spanner_image"} <= spanner_funcs

    gizmo_classes, gizmo_funcs = _ast_top_level_names("pytest_databases.docker.gizmosql")
    assert "GizmoSQLService" in gizmo_classes
    assert _ast_class_contract("pytest_databases.docker.gizmosql", "GizmoSQLService") == (
        {"username": "str", "password": "str"},
        {"uri"},
    )
    assert {
        "gizmosql_service",
        "gizmosql_connection",
        "gizmosql_image",
        "gizmosql_username",
        "gizmosql_password",
        "xdist_gizmosql_isolation_level",
    } <= gizmo_funcs

    azure_classes, azure_funcs = _ast_top_level_names("pytest_databases.docker.azure_blob")
    assert "AzureBlobService" in azure_classes
    assert _ast_class_contract("pytest_databases.docker.azure_blob", "AzureBlobService") == (
        {
            "connection_string": "str",
            "account_url": "str",
            "account_key": "str",
            "account_name": "str",
        },
        set(),
    )
    assert {
        "azure_blob_service",
        "azure_blob_container_client",
        "azure_blob_async_container_client",
        "azure_blob_default_container_name",
        "azurite_in_memory",
        "azure_blob_xdist_isolation_level",
    } <= azure_funcs
