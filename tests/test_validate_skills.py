"""Tests for tools/validate-skills.py.

Uses tmp_path fixtures to build isolated shipped-content trees per test; does
not depend on the real ``skills/`` tree at unit-test granularity. An integration
test at the bottom runs the validator against the real repo to confirm it
executes end-to-end.
"""

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "tools" / "validate-skills.py"


def _load_validator() -> Any:
    """Import tools/validate-skills.py as a module (hyphen in filename)."""
    spec = importlib.util.spec_from_file_location("validate_skills", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["validate_skills"] = mod
    spec.loader.exec_module(mod)
    return mod


VALID_SKILL_BODY = """
<workflow>
Steps here.
</workflow>

<guardrails>
Rules.
</guardrails>

<validation>
Checkpoints.
</validation>

<example>
Sample.
</example>
"""


def _write_skill(
    root: Path,
    name: str,
    description: str = "A valid skill description.",
    body: str = VALID_SKILL_BODY,
    frontmatter_name: str | None = None,
) -> Path:
    skill_dir = root / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    fm_name = frontmatter_name if frontmatter_name is not None else name
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(f'---\nname: {fm_name}\ndescription: "{description}"\n---\n{body}\n')
    return skill_path


def _patch_roots(mod: Any, tmp_root: Path) -> None:
    """Point the validator's module-level path constants at tmp_root."""
    mod.REPO_ROOT = tmp_root
    mod.SKILLS_DIR = tmp_root / "skills"
    mod.COMMANDS_DIR = tmp_root / "commands"
    mod.AGENTS_DIR = tmp_root / "agents"
    # Ensure dirs exist so glob returns empty rather than raising.
    for sub in ("skills", "commands", "agents"):
        (tmp_root / sub).mkdir(exist_ok=True)


class TestValidateSkill:
    def test_valid_skill_returns_no_violations(self, tmp_path: Path) -> None:
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        skill = _write_skill(tmp_path, "my-skill")
        violations = mod.validate_skill(skill)
        assert violations == []

    def test_missing_frontmatter_yields_violation(self, tmp_path: Path) -> None:
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        skill_dir = tmp_path / "skills" / "no-fm"
        skill_dir.mkdir(parents=True)
        skill = skill_dir / "SKILL.md"
        skill.write_text("# Just a heading\n")
        violations = mod.validate_skill(skill)
        assert len(violations) == 1
        assert "frontmatter" in violations[0].message.lower()

    def test_description_too_long_yields_violation(self, tmp_path: Path) -> None:
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        long_desc = "x" * 1025
        skill = _write_skill(tmp_path, "toolong", description=long_desc)
        violations = mod.validate_skill(skill)
        assert any("1025" in v.message for v in violations)

    def test_description_empty_yields_violation(self, tmp_path: Path) -> None:
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        skill = _write_skill(tmp_path, "emptydesc", description="")
        violations = mod.validate_skill(skill)
        assert any("description" in v.message.lower() for v in violations)

    def test_name_mismatch_yields_violation(self, tmp_path: Path) -> None:
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        skill = _write_skill(tmp_path, "dir-name", frontmatter_name="wrong-name")
        violations = mod.validate_skill(skill)
        assert any("name" in v.message.lower() for v in violations)

    def test_missing_workflow_tag_yields_violation(self, tmp_path: Path) -> None:
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        body = VALID_SKILL_BODY.replace("<workflow>", "").replace("</workflow>", "")
        skill = _write_skill(tmp_path, "no-workflow", body=body)
        violations = mod.validate_skill(skill)
        assert any("workflow" in v.message.lower() for v in violations)

    def test_h2_heading_counts_as_section(self, tmp_path: Path) -> None:
        """H2 markdown heading should satisfy the required-section check."""
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        body = "## Workflow\nsteps\n\n## Guardrails\nrules\n\n## Validation\ncheck\n\n## Example\nsample\n"
        skill = _write_skill(tmp_path, "h2-only", body=body)
        violations = mod.validate_skill(skill)
        assert violations == []

    def test_broken_link_yields_violation(self, tmp_path: Path) -> None:
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        body = VALID_SKILL_BODY + "\n[foo](./nonexistent.md)\n"
        skill = _write_skill(tmp_path, "broken-link", body=body)
        violations = mod.validate_skill(skill)
        assert any("broken link" in v.message.lower() for v in violations)

    def test_valid_relative_link_resolves(self, tmp_path: Path) -> None:
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        skill = _write_skill(tmp_path, "with-link")
        (skill.parent / "ref.md").write_text("# ref\n")
        skill.write_text(skill.read_text() + "\n[r](./ref.md)\n")
        violations = mod.validate_skill(skill)
        assert violations == []

    def test_http_links_skipped(self, tmp_path: Path) -> None:
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        body = VALID_SKILL_BODY + "\n[spec](https://example.com/spec)\n"
        skill = _write_skill(tmp_path, "with-http", body=body)
        violations = mod.validate_skill(skill)
        assert violations == []


class TestValidateCommand:
    def test_valid_command_returns_no_violations(self, tmp_path: Path) -> None:
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        cmd_dir = tmp_path / "commands" / "litestar"
        cmd_dir.mkdir(parents=True)
        cmd_path = cmd_dir / "do.toml"
        cmd_path.write_text('description = "A thing"\nprompt = "Do it"\n')
        violations = mod.validate_command(cmd_path)
        assert violations == []

    def test_missing_description_yields_violation(self, tmp_path: Path) -> None:
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        cmd_dir = tmp_path / "commands" / "litestar"
        cmd_dir.mkdir(parents=True)
        cmd_path = cmd_dir / "no-desc.toml"
        cmd_path.write_text('prompt = "Do it"\n')
        violations = mod.validate_command(cmd_path)
        assert any("description" in v.message.lower() for v in violations)

    def test_missing_prompt_yields_violation(self, tmp_path: Path) -> None:
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        cmd_dir = tmp_path / "commands" / "litestar"
        cmd_dir.mkdir(parents=True)
        cmd_path = cmd_dir / "no-prompt.toml"
        cmd_path.write_text('description = "x"\n')
        violations = mod.validate_command(cmd_path)
        assert any("prompt" in v.message.lower() for v in violations)

    def test_description_too_long_yields_violation(self, tmp_path: Path) -> None:
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        cmd_dir = tmp_path / "commands" / "litestar"
        cmd_dir.mkdir(parents=True)
        cmd_path = cmd_dir / "toolong.toml"
        long = "x" * 1025
        cmd_path.write_text(f'description = "{long}"\nprompt = "p"\n')
        violations = mod.validate_command(cmd_path)
        assert any("1025" in v.message for v in violations)

    def test_malformed_toml_yields_violation(self, tmp_path: Path) -> None:
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        cmd_dir = tmp_path / "commands" / "litestar"
        cmd_dir.mkdir(parents=True)
        cmd_path = cmd_dir / "bad.toml"
        cmd_path.write_text("this is [not valid = toml\n")
        violations = mod.validate_command(cmd_path)
        assert any("parse error" in v.message.lower() for v in violations)


class TestValidateAgent:
    def _write_agent(
        self,
        root: Path,
        name: str = "my-agent",
        description: str = "An agent.",
        mode: str = "subagent",
        tools: dict[str, bool] | None = None,
        frontmatter_name: str | None = None,
    ) -> Path:
        if tools is None:
            tools = {"read": True, "grep": True}
        agents_dir = root / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        fm_name = frontmatter_name if frontmatter_name is not None else name
        tools_yaml = "\n".join(f"  {k}: {str(v).lower()}" for k, v in tools.items())
        path = agents_dir / f"{name}.md"
        path.write_text(
            f'---\nname: {fm_name}\ndescription: "{description}"\nmode: {mode}\ntools:\n{tools_yaml}\n---\n\n# body\n'
        )
        return path

    def test_valid_agent_returns_no_violations(self, tmp_path: Path) -> None:
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        path = self._write_agent(tmp_path)
        violations = mod.validate_agent(path)
        assert violations == []

    def test_name_mismatch_yields_violation(self, tmp_path: Path) -> None:
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        path = self._write_agent(tmp_path, name="agent-a", frontmatter_name="other")
        violations = mod.validate_agent(path)
        assert any("name" in v.message.lower() for v in violations)

    def test_bad_mode_yields_violation(self, tmp_path: Path) -> None:
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        path = self._write_agent(tmp_path, mode="rogue")
        violations = mod.validate_agent(path)
        assert any("mode" in v.message.lower() for v in violations)

    def test_bad_tool_key_yields_violation(self, tmp_path: Path) -> None:
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        path = self._write_agent(tmp_path, tools={"bogusTool": True})
        violations = mod.validate_agent(path)
        assert any("tool" in v.message.lower() for v in violations)

    def test_non_bool_tool_value_yields_violation(self, tmp_path: Path) -> None:
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        path = agents_dir / "x.md"
        path.write_text('---\nname: x\ndescription: "x"\nmode: subagent\ntools:\n  read: "yes"\n---\n\nbody\n')
        violations = mod.validate_agent(path)
        assert any("bool" in v.message.lower() for v in violations)

    def test_description_too_long_yields_violation(self, tmp_path: Path) -> None:
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        path = self._write_agent(tmp_path, description="x" * 1025)
        violations = mod.validate_agent(path)
        assert any("1025" in v.message for v in violations)


class TestAgentsLeakGuard:
    def test_patterns_md_leak_yields_violation(self, tmp_path: Path) -> None:
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        skill_dir = tmp_path / "skills" / "leaky"
        skill_dir.mkdir(parents=True)
        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text("See .agents/patterns.md for more.\n")
        violations = mod.check_agents_leak([skill_path])
        assert len(violations) == 1
        assert violations[0].line == 1

    def test_knowledge_path_leak_yields_violation(self, tmp_path: Path) -> None:
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        skill_dir = tmp_path / "skills" / "leaky-knowledge"
        skill_dir.mkdir(parents=True)
        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text("Ref .agents/knowledge/authoring-conventions.md here.\n")
        violations = mod.check_agents_leak([skill_path])
        assert len(violations) == 1

    def test_specs_path_leak_yields_violation(self, tmp_path: Path) -> None:
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        skill_dir = tmp_path / "skills" / "leaky-specs"
        skill_dir.mkdir(parents=True)
        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text("cat .agents/specs/foo/spec.md\n")
        violations = mod.check_agents_leak([skill_path])
        assert len(violations) == 1

    def test_install_path_whitelist_no_violation(self, tmp_path: Path) -> None:
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        skill_dir = tmp_path / "skills" / "install-ok"
        skill_dir.mkdir(parents=True)
        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text("Install into `.agents/skills/foo/` on your machine.\n")
        violations = mod.check_agents_leak([skill_path])
        assert violations == []

    def test_bare_agents_dir_mention_not_flagged(self, tmp_path: Path) -> None:
        """Prose mentioning a user-project `.agents/` directory (no framework
        sub-path) is legitimate Flow-compatibility documentation."""
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        skill_dir = tmp_path / "skills" / "flow-aware"
        skill_dir.mkdir(parents=True)
        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text("If the target project has an `.agents/` directory, cooperate.\n")
        violations = mod.check_agents_leak([skill_path])
        assert violations == []

    def test_identifier_adjacent_not_flagged(self, tmp_path: Path) -> None:
        """Lookbehind prevents matching ``foo_.agents/`` as a leak."""
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        skill_dir = tmp_path / "skills" / "adjacent"
        skill_dir.mkdir(parents=True)
        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text("foo_.agents/patterns.md\n")
        violations = mod.check_agents_leak([skill_path])
        assert violations == []


class TestMain:
    def test_main_returns_zero_on_empty_tree(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        rc = mod.main()
        assert rc == 0
        captured = capsys.readouterr()
        assert "OK" in captured.out

    def test_main_returns_one_when_violation_present(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        skill_dir = tmp_path / "skills" / "bad"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("no frontmatter here\n")
        rc = mod.main()
        assert rc == 1
        captured = capsys.readouterr()
        assert "FAIL" in captured.out


class TestIterAllShippedFiles:
    def test_iter_all_shipped_files_covers_expected_paths(self, tmp_path: Path) -> None:
        mod = _load_validator()
        _patch_roots(mod, tmp_path)
        # Create representative files
        skill_dir = tmp_path / "skills" / "a"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("x")
        cmd_dir = tmp_path / "commands" / "b"
        cmd_dir.mkdir(parents=True)
        (cmd_dir / "c.toml").write_text("x")
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        (agents_dir / "r.md").write_text("x")
        (tmp_path / "AGENTS.md").write_text("x")
        (tmp_path / "README.md").write_text("x")
        found = list(mod.iter_all_shipped_files())
        names = {p.name for p in found}
        assert "SKILL.md" in names
        assert "c.toml" in names
        assert "r.md" in names
        assert "AGENTS.md" in names
        assert "README.md" in names


@pytest.mark.integration
def test_against_real_repo_content() -> None:
    """End-to-end: run main() against the real shipped tree; must exit 0."""
    mod = _load_validator()
    rc = mod.main()
    assert rc == 0, "real repo content produced validation failures"
