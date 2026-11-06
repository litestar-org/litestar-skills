from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

RETIRED_TOKENS = (
    "AdvancedAlchemyBackendConfig",
    "QueueEventConfig",
    "run_in_app",
    "sqlspec database",
    "litestar database revision",
    "litestar database current",
    "litestar database create-database",
    "Meta(rename=",
    "from litestar.plugins.htmx",
    "AutowireConfig(extensions=",
    "guard_any_of",
    "guard_all_of",
    "guard_at_least",
    "guard_one_of",
    "requires_team_role",
    "team_parameter=",
    "TemplatesPlugin",
    "InertiaPlugin(",
    "MCPAuthConfig",
    "MCPAuthBackend",
    "OIDCProviderConfig",
    "DefaultJWKSCache",
    "from litestar_mcp.auth",
    "SKILL_FILE_NAME",
    "AgentTeam",
    "use_query_and_wait",
    "pgbouncer_mode",
    "SQLiteStore",
    "ADBCStore",
    "DuckdbStore",
    "DuckdbADKStore",
    "DuckdbADKMemoryStore",
)
RETIRED_GRANIAN_FLAGS = (
    "--threads",
    "--threading-mode",
    "--log-access",
    "--log-access-format",
    "--log-access-fmt",
)


def test_retired_upstream_tokens_do_not_appear_in_canonical_content() -> None:
    files = [
        *sorted((REPO_ROOT / "skills").rglob("*.md")),
        *sorted((REPO_ROOT / "agents").rglob("*.md")),
        *sorted((REPO_ROOT / ".codex" / "agents").rglob("*.toml")),
    ]
    content = "\n".join(path.read_text(encoding="utf-8") for path in files)
    for token in RETIRED_TOKENS:
        assert token not in content


def test_retired_granian_flags_do_not_appear_as_exact_shell_tokens() -> None:
    content = (REPO_ROOT / "skills" / "litestar-granian" / "SKILL.md").read_text(encoding="utf-8")
    words = set(content.replace("`", " ").split())
    for flag in RETIRED_GRANIAN_FLAGS:
        assert flag not in words


def test_rule_covers_all_shipped_skills() -> None:
    skill_dirs = {path.parent.name for path in (REPO_ROOT / "skills").glob("*/SKILL.md")}
    rule_text = (REPO_ROOT / "rules" / "litestar-antigravity.md").read_text(encoding="utf-8")

    assert len(skill_dirs) == 20
    for skill in sorted(skill_dirs):
        assert f"`{skill}`" in rule_text
