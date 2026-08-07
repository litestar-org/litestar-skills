import inspect
from importlib.metadata import version

from sqlspec import SQLSpec, sql
from sqlspec.cli import add_migration_commands, get_sqlspec_group
from sqlspec.extensions.litestar import SQLSpecPlugin


def test_sqlspec_058_plugin_builder_and_cli_contract() -> None:
    assert version("sqlspec") == "0.58.3"
    assert "sqlspec" in inspect.signature(SQLSpecPlugin).parameters
    SQLSpecPlugin(SQLSpec())
    assert callable(sql.merge)
    commands = add_migration_commands(get_sqlspec_group()).commands
    assert "create-migration" in commands
    assert "database" not in commands
