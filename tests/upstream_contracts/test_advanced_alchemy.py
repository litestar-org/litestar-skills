from importlib.metadata import version

from advanced_alchemy.extensions.litestar.cli import database_group
from advanced_alchemy.mixins import AuditColumns, SentinelMixin, SlugKey, UniqueMixin


def test_advanced_alchemy_111_mixins_and_cli_contract() -> None:
    assert version("advanced-alchemy") == "1.11.0"
    assert {"created_at", "updated_at"} <= AuditColumns.__annotations__.keys()
    assert all(mixin is not None for mixin in (SlugKey, UniqueMixin, SentinelMixin))
    assert "make-migrations" in database_group.commands
    assert "show-current-revision" in database_group.commands
    assert {"revision", "current", "create-database"}.isdisjoint(database_group.commands)
