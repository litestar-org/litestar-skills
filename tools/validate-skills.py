"""Validate shipped skills / commands / agents manifest integrity.

Walks every shipped SKILL.md, command TOML, and agent Markdown file and
enforces:

* YAML frontmatter present, with ``name`` (matching parent dir / filename) and
  ``description`` (<= 1024 characters).
* SKILL.md body contains the four required sections (``workflow``,
  ``guardrails``, ``validation``, ``example``) — present either as
  ``<workflow>`` / ``<guardrails>`` / ``<validation>`` / ``<example>`` XML tags
  *or* as H2 Markdown headings (``## Workflow`` etc., case-insensitive).
* Every ``[text](./path)`` or ``[text](relative/path.md)`` link in a SKILL.md
  resolves relative to the file.
* ``commands/**/*.toml`` parses as TOML and has top-level ``description`` (str,
  <= 1024 chars) and ``prompt`` (non-empty str).
* ``agents/*.md`` frontmatter has ``name`` matching filename, ``description``
  (<= 1024 chars), ``mode`` in {subagent, primary}, and ``tools`` mapping with
  whitelisted keys and bool values.
* Shipped content (skills, commands, agents, and the root ``AGENTS.md`` /
  ``CONTRIBUTING.md`` / ``README.md`` / ``GEMINI.md``) contains no references
  to the framework authoring tree — except the user-install convention path
  (``skills/`` sub-path of the authoring directory), which is whitelisted.

Exit 0 on clean; exit 1 with a per-file violation list otherwise.
"""

import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any, NamedTuple, cast

if sys.version_info >= (3, 11):
    import tomllib as _tomllib
else:  # pragma: no cover - py310 fallback path
    import tomli as _tomllib  # type: ignore[import-not-found,unused-ignore]

import yaml

# The tomllib / tomli shim yields a dict whose keys are strings; the stdlib
# function returns ``dict[str, Any]`` but the py310 fallback lives in a third-
# party package without stubs, so we wrap the callables in ``Any``-typed
# aliases to keep pyright/mypy strict mode happy across both code paths.
_toml_loads_any: Any = _tomllib.loads  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]


def _toml_loads(text: str) -> dict[str, Any]:
    """Parse a TOML string into a dict, tolerant of py310 ``tomli`` fallback."""
    return cast("dict[str, Any]", _toml_loads_any(text))


_TOMLDecodeError: type[Exception] = cast(
    "type[Exception]",
    _tomllib.TOMLDecodeError,  # pyright: ignore[reportUnknownMemberType]
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"
COMMANDS_DIR = REPO_ROOT / "commands"
# `agents/` at repo root is Gemini CLI's extension subagents directory.
# `.opencode/agents/` is OpenCode's project-scoped subagents directory.
# `.claude-plugin/agents/` is Claude Code's plugin subagents directory.
# All three hosts use incompatible frontmatter schemas, so each location is
# validated by its own rules (see `validate_gemini_agent` /
# `validate_opencode_agent` / `validate_claude_agent`).
AGENTS_DIR = REPO_ROOT / "agents"
OPENCODE_AGENTS_DIR = REPO_ROOT / ".opencode" / "agents"
CLAUDE_AGENTS_DIR = REPO_ROOT / ".claude-plugin" / "agents"
SHIPPED_ROOT_FILES = ("AGENTS.md", "CONTRIBUTING.md", "README.md", "GEMINI.md")

MAX_DESCRIPTION_CHARS = 1024

REQUIRED_SECTIONS = ("workflow", "guardrails", "validation", "example")

# Match `<tag>` for each required section.
_XML_TAG_PATTERNS = {name: re.compile(rf"<{name}\b", re.IGNORECASE) for name in REQUIRED_SECTIONS}
# Match `## Heading` lines for each required section. Accepts any H2 that
# *mentions* the section name as a word ("## Example", "## End-to-End Example",
# "## Validation Checkpoint", "## Canonical Example", etc.) — singular or
# plural. This is intentionally lenient so existing skill docs with slightly
# different heading conventions are still considered structurally compliant.
_H2_HEADING_PATTERNS = {
    name: re.compile(
        rf"^##\s+.*\b{name}s?\b",
        re.IGNORECASE | re.MULTILINE,
    )
    for name in REQUIRED_SECTIONS
}

LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

# Match references to the framework authoring tree. A "leak" is a shipped-
# content file citing a path that only exists in the authoring workspace
# (``.agents/patterns.md``, ``.agents/knowledge/...``, ``.agents/specs/...``,
# ``.agents/archive/...``, ``.agents/plans/...``, ``.agents/research/...``,
# ``.agents/flows.md``, ``.agents/product.md``, ``.agents/product-guidelines.md``,
# ``.agents/workflow.md``, ``.agents/tech-stack.md``, ``.agents/index.md``,
# ``.agents/beads.json``, ``.agents/setup-state.json``, ``.agents/code-styleguides/``,
# ``.agents/backlog/``). These never exist on a user install.
#
# Benign mentions (prose about the Flow authoring convention, the user-install
# ``.agents/skills/`` or ``.agents/plugins/`` convention paths, or a bare
# ``.agents/`` directory reference) are allowed. The lookbehind rejects alnum/
# underscore prefixes so filesystem paths like ``foo_.agents/`` are not
# flagged.
_AUTHORING_TREE_SUBPATHS = (
    "patterns.md",
    "knowledge/",
    "specs/",
    "archive/",
    "plans/",
    "research/",
    "flows.md",
    "product.md",
    "product-guidelines.md",
    "workflow.md",
    "tech-stack.md",
    "index.md",
    "beads.json",
    "setup-state.json",
    "code-styleguides/",
    "backlog/",
)
_leak_targets = "|".join(re.escape(p) for p in _AUTHORING_TREE_SUBPATHS)
AGENTS_LEAK_PATTERN = re.compile(rf"(?<![A-Za-z0-9_])\.agents/(?:{_leak_targets})")

# Forbidden vocabulary in shipped content. These tokens leak internal Flow
# workflow taxonomy, codenames from non-public canonical apps, or machine-
# specific filesystem paths. Each tuple is ``(regex, human-readable label)``.
# Keep the list narrow and high-confidence; generic English meanings of these
# words rarely appear in this repo's prose, so default to forbidding the leak
# form. Add allowlist exceptions in ``_FORBIDDEN_VOCAB_ALLOWLIST`` below if a
# legitimate use is found.
FORBIDDEN_VOCAB_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # --- Internal Flow workflow vocabulary ----------------------------------
    (re.compile(r"\bSaga(?:s|-\d+)?\b"), "Flow workflow vocabulary 'Saga'"),
    (re.compile(r"\bEpics?\b"), "Flow workflow vocabulary 'Epic'"),
    (re.compile(r"\bCh\d+\b(?!\w)"), "internal PRD chapter ID 'ChN'"),
    (re.compile(r"TODO\(Ch\d+\)"), "internal PRD chapter TODO marker"),
    (re.compile(r"\b(?:parent\s+)?PRD\b"), "Flow vocabulary 'PRD' / 'parent PRD'"),
    (re.compile(r"\bls-[a-z]{3}\.\d+"), "Beads issue slug"),
    (re.compile(r"\bFlow\s+framework\b", re.IGNORECASE), "Flow framework name"),
    # --- Internal canonical-app codenames (non-public) ----------------------
    (re.compile(r"dma/accelerator"), "internal canonical-app path 'dma/accelerator'"),
    (re.compile(r"\bETLLogObserver\b"), "internal class name 'ETLLogObserver'"),
    (re.compile(r"~/\.dma/"), "internal app install path '~/.dma/'"),
    (re.compile(r"/opt/dma\b"), "internal app install path '/opt/dma'"),
    (re.compile(r"\bsrc/py/dma/"), "internal package path 'src/py/dma/'"),
    (re.compile(r"\bdma_(?:tasks|jobs|app|runtime)\b"), "internal app-derived identifier 'dma_*'"),
    # --- Machine-specific paths --------------------------------------------
    (re.compile(r"/home/cody/"), "machine-specific filesystem path '/home/cody/...'"),
)

# Files exempt from FORBIDDEN_VOCAB_PATTERNS. Tests legitimately reference the
# literal patterns to verify the validator catches them; the validator itself
# documents the patterns in code. Use repo-relative POSIX paths.
_FORBIDDEN_VOCAB_ALLOWLIST: frozenset[str] = frozenset(
    {
        "tools/validate-skills.py",  # the validator defines the patterns
        "tests/test_validate_skills.py",  # tests assert against the patterns
    }
)

VALID_AGENT_MODES = frozenset({"subagent", "primary"})
VALID_AGENT_TOOLS = frozenset({"read", "grep", "glob", "bash", "edit", "write", "todoWrite", "webFetch", "webSearch"})

# Claude Code subagent tool registry (canonical Claude tool names exposed to
# subagents — see https://code.claude.com/docs/en/sub-agents).
VALID_CLAUDE_TOOLS = frozenset(
    {
        "Read",
        "Grep",
        "Glob",
        "Bash",
        "Edit",
        "Write",
        "WebFetch",
        "WebSearch",
        "TodoWrite",
        "NotebookEdit",
    }
)

# Gemini CLI subagent tool registry (see docs/core/subagents.md in google-gemini/gemini-cli).
# Wildcards `*`, `mcp_*`, and `mcp_<server>_*` are also accepted at runtime.
VALID_GEMINI_TOOLS = frozenset(
    {
        "read_file",
        "grep_search",
        "glob",
        "run_shell_command",
        "list_directory",
        "web_fetch",
        "google_web_search",
        "write_file",
        "edit",
        "save_memory",
    }
)
_GEMINI_WILDCARD_PATTERN = re.compile(r"^(?:\*|mcp_[A-Za-z0-9_-]*\*?)$")


class Violation(NamedTuple):
    path: Path
    line: int | None
    message: str


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def extract_frontmatter(text: str) -> tuple[dict[str, Any], int, str]:
    """Return ``(frontmatter_dict, body_start_line, body_text)``.

    Raises :class:`ValueError` on missing or unterminated frontmatter.
    """
    if not text.startswith("---\n"):
        msg = "missing YAML frontmatter"
        raise ValueError(msg)
    try:
        end = text.index("\n---\n", 4)
    except ValueError as exc:
        msg = "unterminated YAML frontmatter"
        raise ValueError(msg) from exc
    raw = text[4:end]
    loaded = yaml.safe_load(raw)
    fm: dict[str, Any] = {} if loaded is None else cast("dict[str, Any]", loaded)
    body_start_line = text[: end + 5].count("\n") + 1
    body = text[end + 5 :]
    return fm, body_start_line, body


def _check_description(desc: object, path: Path, line: int) -> list[Violation]:
    out: list[Violation] = []
    if not isinstance(desc, str) or not desc.strip():
        out.append(Violation(path, line, "description missing or empty"))
    elif len(desc) > MAX_DESCRIPTION_CHARS:
        out.append(
            Violation(
                path,
                line,
                f"description length {len(desc)} > {MAX_DESCRIPTION_CHARS}",
            )
        )
    return out


def _section_present(body: str, section: str) -> bool:
    if _XML_TAG_PATTERNS[section].search(body):
        return True
    return bool(_H2_HEADING_PATTERNS[section].search(body))


def validate_skill(path: Path) -> list[Violation]:
    violations: list[Violation] = []
    text = path.read_text(encoding="utf-8")
    try:
        fm, body_start, body = extract_frontmatter(text)
    except ValueError as exc:
        return [Violation(path, 1, str(exc))]
    expected_name = path.parent.name
    fm_name = fm.get("name")
    if fm_name != expected_name:
        violations.append(Violation(path, 1, f"name {fm_name!r} != parent dir {expected_name!r}"))
    violations.extend(_check_description(fm.get("description"), path, 1))
    for section in REQUIRED_SECTIONS:
        if not _section_present(body, section):
            violations.append(
                Violation(
                    path,
                    body_start,
                    f"missing required section <{section}> (XML tag or '## {section.title()}' heading)",
                )
            )
    for match in LINK_PATTERN.finditer(body):
        target = match.group(2).split("#")[0].strip()
        if not target:
            continue
        if target.startswith(("http://", "https://", "mailto:", "tel:")):
            continue
        resolved = (path.parent / target).resolve()
        if not resolved.exists():
            violations.append(Violation(path, body_start, f"broken link target: {target}"))
    return violations


def validate_command(path: Path) -> list[Violation]:
    violations: list[Violation] = []
    try:
        data = _toml_loads(path.read_text(encoding="utf-8"))
    except _TOMLDecodeError as exc:
        return [Violation(path, 1, f"TOML parse error: {exc}")]
    violations.extend(_check_description(data.get("description"), path, 1))
    prompt = data.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        violations.append(Violation(path, 1, "prompt missing or empty"))
    return violations


def validate_opencode_agent(path: Path) -> list[Violation]:
    """Validate an OpenCode subagent file under ``.opencode/agents/``.

    OpenCode schema: ``mode`` in {primary, subagent}, ``tools`` as a dict
    mapping whitelisted tool keys to bool values.
    """
    violations: list[Violation] = []
    text = path.read_text(encoding="utf-8")
    try:
        fm, _body_start, _body = extract_frontmatter(text)
    except ValueError as exc:
        return [Violation(path, 1, str(exc))]
    expected_name = path.stem
    if fm.get("name") != expected_name:
        violations.append(Violation(path, 1, f"name {fm.get('name')!r} != filename stem {expected_name!r}"))
    violations.extend(_check_description(fm.get("description"), path, 1))
    mode = fm.get("mode")
    if mode not in VALID_AGENT_MODES:
        violations.append(Violation(path, 1, f"mode {mode!r} not in {sorted(VALID_AGENT_MODES)}"))
    tools = fm.get("tools")
    if not isinstance(tools, dict):
        violations.append(Violation(path, 1, "tools missing or not a mapping"))
    else:
        tools_typed = cast("dict[str, Any]", tools)
        for key, value in tools_typed.items():
            key_s = str(key)
            if key_s not in VALID_AGENT_TOOLS:
                violations.append(Violation(path, 1, f"tool key {key_s!r} not in whitelist"))
            if not isinstance(value, bool):
                type_name = type(value).__name__
                violations.append(
                    Violation(
                        path,
                        1,
                        f"tool {key_s!r} value must be bool, got {type_name}",
                    )
                )
    return violations


def validate_gemini_agent(path: Path) -> list[Violation]:
    """Validate a Gemini CLI subagent file under ``agents/``.

    Gemini schema: no ``mode`` key (rejected by Gemini's loader), ``tools`` as
    a list of tool-name strings. Each string must be a known Gemini tool or a
    wildcard pattern (``*``, ``mcp_*``, ``mcp_<server>_*``).
    """
    violations: list[Violation] = []
    text = path.read_text(encoding="utf-8")
    try:
        fm, _body_start, _body = extract_frontmatter(text)
    except ValueError as exc:
        return [Violation(path, 1, str(exc))]
    expected_name = path.stem
    if fm.get("name") != expected_name:
        violations.append(Violation(path, 1, f"name {fm.get('name')!r} != filename stem {expected_name!r}"))
    violations.extend(_check_description(fm.get("description"), path, 1))
    if "mode" in fm:
        violations.append(Violation(path, 1, "mode key not allowed (Gemini subagents reject it)"))
    tools = fm.get("tools")
    if tools is None:
        return violations
    if not isinstance(tools, list):
        violations.append(Violation(path, 1, "tools must be a list of strings"))
        return violations
    # pyright strict requires an explicit cast here even though mypy's
    # narrowing already gives us list[Any]; silence the redundant-cast warning.
    tools_list = cast("list[Any]", tools)  # type: ignore[redundant-cast]
    for entry in tools_list:
        if not isinstance(entry, str):
            type_name = type(entry).__name__
            violations.append(Violation(path, 1, f"tools entry must be a string, got {type_name}"))
            continue
        if entry in VALID_GEMINI_TOOLS:
            continue
        if _GEMINI_WILDCARD_PATTERN.match(entry):
            continue
        violations.append(Violation(path, 1, f"tool {entry!r} not in Gemini tool registry"))
    return violations


def validate_claude_agent(path: Path) -> list[Violation]:
    """Validate a Claude Code subagent file under ``.claude-plugin/agents/``.

    Claude schema: ``tools`` as a comma-separated string of canonical Claude
    tool names (e.g. ``Read, Grep, Glob, Bash``). YAML lists and dict mappings
    are rejected by Claude's plugin manifest validator. ``mode`` is not part
    of Claude's subagent schema.
    """
    violations: list[Violation] = []
    text = path.read_text(encoding="utf-8")
    try:
        fm, _body_start, _body = extract_frontmatter(text)
    except ValueError as exc:
        return [Violation(path, 1, str(exc))]
    expected_name = path.stem
    if fm.get("name") != expected_name:
        violations.append(Violation(path, 1, f"name {fm.get('name')!r} != filename stem {expected_name!r}"))
    violations.extend(_check_description(fm.get("description"), path, 1))
    if "mode" in fm:
        violations.append(Violation(path, 1, "mode key not allowed (Claude subagents reject it)"))
    tools = fm.get("tools")
    if tools is None:
        return violations
    if not isinstance(tools, str):
        violations.append(
            Violation(path, 1, "tools must be a comma-separated string (Claude rejects YAML lists/dicts)")
        )
        return violations
    for entry in (t.strip() for t in tools.split(",")):
        if not entry:
            continue
        if entry not in VALID_CLAUDE_TOOLS:
            violations.append(Violation(path, 1, f"tool {entry!r} not in Claude tool registry"))
    return violations


def check_agents_leak(files: Iterable[Path]) -> list[Violation]:
    violations: list[Violation] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if AGENTS_LEAK_PATTERN.search(line):
                snippet = line.strip()
                if len(snippet) > 80:
                    snippet = snippet[:77] + "..."
                violations.append(
                    Violation(
                        path,
                        lineno,
                        f"shipped content references framework path: {snippet}",
                    )
                )
    return violations


def check_forbidden_vocab(files: Iterable[Path]) -> list[Violation]:
    """Flag forbidden internal vocabulary or machine-specific paths in shipped
    content.

    Walks every file, line by line, and flags any match of
    :data:`FORBIDDEN_VOCAB_PATTERNS`. Files in
    :data:`_FORBIDDEN_VOCAB_ALLOWLIST` are skipped (the validator + its tests
    legitimately reference the literal patterns).
    """
    violations: list[Violation] = []
    for path in files:
        rel = _rel(path)
        if rel in _FORBIDDEN_VOCAB_ALLOWLIST:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pattern, label in FORBIDDEN_VOCAB_PATTERNS:
                if pattern.search(line):
                    snippet = line.strip()
                    if len(snippet) > 80:
                        snippet = snippet[:77] + "..."
                    violations.append(
                        Violation(
                            path,
                            lineno,
                            f"forbidden vocabulary ({label}): {snippet}",
                        )
                    )
                    break  # one violation per line is enough
    return violations


def iter_skills() -> Iterator[Path]:
    if SKILLS_DIR.is_dir():
        yield from sorted(SKILLS_DIR.glob("*/SKILL.md"))


def iter_commands() -> Iterator[Path]:
    if COMMANDS_DIR.is_dir():
        yield from sorted(COMMANDS_DIR.rglob("*.toml"))


def iter_gemini_agents() -> Iterator[Path]:
    if AGENTS_DIR.is_dir():
        yield from sorted(AGENTS_DIR.glob("*.md"))


def iter_opencode_agents() -> Iterator[Path]:
    if OPENCODE_AGENTS_DIR.is_dir():
        yield from sorted(OPENCODE_AGENTS_DIR.glob("*.md"))


def iter_claude_agents() -> Iterator[Path]:
    if CLAUDE_AGENTS_DIR.is_dir():
        yield from sorted(CLAUDE_AGENTS_DIR.glob("*.md"))


def iter_all_shipped_files() -> Iterator[Path]:
    if SKILLS_DIR.is_dir():
        yield from sorted(SKILLS_DIR.rglob("*.md"))
    if COMMANDS_DIR.is_dir():
        yield from sorted(COMMANDS_DIR.rglob("*.toml"))
    if AGENTS_DIR.is_dir():
        yield from sorted(AGENTS_DIR.rglob("*.md"))
    if OPENCODE_AGENTS_DIR.is_dir():
        yield from sorted(OPENCODE_AGENTS_DIR.rglob("*.md"))
    if CLAUDE_AGENTS_DIR.is_dir():
        yield from sorted(CLAUDE_AGENTS_DIR.rglob("*.md"))
    for name in SHIPPED_ROOT_FILES:
        candidate = REPO_ROOT / name
        if candidate.is_file():
            yield candidate
    # Public docs/ tree — user-facing release notes, roadmap, launch playbook.
    docs_dir = REPO_ROOT / "docs"
    if docs_dir.is_dir():
        yield from sorted(docs_dir.rglob("*.md"))
    # Host-specific install / config files that ship with the plugin.
    for rel in (
        ".opencode/INSTALL.md",
        ".opencode/plugins/litestar-skills.js",
        ".codex/INSTALL.md",
        ".codex/config.toml",
    ):
        candidate = REPO_ROOT / rel
        if candidate.is_file():
            yield candidate


def _print_violations(violations: list[Violation]) -> None:
    for v in violations:
        loc = f":{v.line}" if v.line is not None else ""
        print(f"[FAIL] {_rel(v.path)}{loc}: {v.message}")


def main() -> int:
    all_violations: list[Violation] = []
    skills = list(iter_skills())
    commands = list(iter_commands())
    gemini_agents = list(iter_gemini_agents())
    opencode_agents = list(iter_opencode_agents())
    claude_agents = list(iter_claude_agents())
    for skill_path in skills:
        all_violations.extend(validate_skill(skill_path))
    for cmd_path in commands:
        all_violations.extend(validate_command(cmd_path))
    for agent_path in gemini_agents:
        all_violations.extend(validate_gemini_agent(agent_path))
    for agent_path in opencode_agents:
        all_violations.extend(validate_opencode_agent(agent_path))
    for agent_path in claude_agents:
        all_violations.extend(validate_claude_agent(agent_path))
    shipped = list(iter_all_shipped_files())
    all_violations.extend(check_agents_leak(shipped))
    all_violations.extend(check_forbidden_vocab(shipped))
    if all_violations:
        _print_violations(all_violations)
        print(f"\n{len(all_violations)} violation(s)", file=sys.stderr)
        return 1
    agent_total = len(gemini_agents) + len(opencode_agents) + len(claude_agents)
    print(f"[ OK ] validated {len(skills)} skills, {len(commands)} commands, {agent_total} agents — no violations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
