from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

RETIRED_TOKENS = (
    "AdvancedAlchemyBackendConfig",
    "QueueEventConfig",
    "sqlspec database",
    "Meta(rename=",
    "from litestar.plugins.htmx",
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
    ]
    content = "\n".join(path.read_text(encoding="utf-8") for path in files)
    for token in RETIRED_TOKENS:
        assert token not in content


def test_retired_granian_flags_do_not_appear_as_exact_shell_tokens() -> None:
    content = (REPO_ROOT / "skills" / "litestar-granian" / "SKILL.md").read_text(encoding="utf-8")
    words = set(content.replace("`", " ").split())
    for flag in RETIRED_GRANIAN_FLAGS:
        assert flag not in words
