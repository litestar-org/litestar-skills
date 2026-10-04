import json
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
        *sorted((REPO_ROOT / "commands").rglob("*.toml")),
        REPO_ROOT / "tools" / "agent-sources" / "litestar-reviewer.yaml",
        REPO_ROOT / "hooks" / "lib" / "skill-map.json",
    ]
    content = "\n".join(path.read_text(encoding="utf-8") for path in files)
    for token in RETIRED_TOKENS:
        assert token not in content


def test_retired_granian_flags_do_not_appear_as_exact_shell_tokens() -> None:
    content = (REPO_ROOT / "skills" / "litestar-granian" / "SKILL.md").read_text(encoding="utf-8")
    words = set(content.replace("`", " ").split())
    for flag in RETIRED_GRANIAN_FLAGS:
        assert flag not in words


def test_skill_map_covers_all_shipped_skills() -> None:
    skill_dirs = {path.parent.name for path in (REPO_ROOT / "skills").glob("*/SKILL.md")}
    skill_map = json.loads((REPO_ROOT / "hooks" / "lib" / "skill-map.json").read_text(encoding="utf-8"))
    matcher_skills = {entry["skill"] for entry in skill_map["matchers"]}
    rule_text = (REPO_ROOT / "rules" / "litestar-antigravity.md").read_text(encoding="utf-8")

    assert len(skill_dirs) == 20
    assert matcher_skills == skill_dirs
    for skill in sorted(skill_dirs):
        assert f"`{skill}`" in rule_text
