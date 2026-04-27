# Contributing to `litestar-skills`

See [`docs/roadmap.md`](docs/roadmap.md) for v0.2 candidates and deferred items with graduation triggers. For what's already shipped, see [GitHub Releases](https://github.com/litestar-org/litestar-skills/releases).

## Adding a Skill

1. Copy `templates/skill-template/` to `skills/<your-skill-name>/`.
2. Fill in `SKILL.md` frontmatter:
   - `name` — kebab-case, must match directory name, ≤64 chars
   - `description` — trigger-only; starts with `Auto-activate for` or `Use when`, names concrete file/import/API signals, includes `Not for X — why`, and contains no process summary such as `Produces ...`
3. Author the body in this XML-tagged section order:
   - Code Style Rules → Quick Reference → `<workflow>` → `<guardrails>` → `<validation>` → `<example>` → References Index → Official References → Shared Styleguide Baseline (link to the relevant files in [`skills/litestar-styleguide/references/`](skills/litestar-styleguide/SKILL.md))
4. Apply the Litestar-first-party bias for all code samples.
5. Run `make validate-skills` — must pass `skills-ref validate` and schema checks.
6. Run `make check` — full CI parity locally.
7. Open a PR. Maintainer review verifies tone, first-party bias, and technical accuracy.

## Host Artifacts

When adding or changing host support, document the exact artifacts this repo ships for that host: manifests, generated subagents, hooks, install docs, and validator coverage.

Do not document a host capability unless the corresponding artifact exists in the same PR. If a host consumes only the raw `skills/` tree, say that directly and do not imply a native wrapper.

## Updating Host Manifests

When adding a skill, command, subagent, or MCP server, update the relevant per-host manifest so consumers auto-discover the new content:

| Addition | Manifests to update |
| --- | --- |
| New skill | None — all host manifests point at `./skills/` root. Skills auto-discovered. |
| New slash command | None — `./commands/` root is shared. |
| New subagent | Edit `tools/agent-sources/<name>.yaml` and run `make agents` — see [Multi-Projection Subagent Maintenance — Generator-driven](#multi-projection-subagent-maintenance--generator-driven) below. |
| New MCP server | `.codex-plugin/plugin.json` `dependencies.tools`, `gemini-extension.json` `mcpServers`, and `.codex/config.toml` |
| New host support | New `.<host>-plugin/plugin.json` + entry in `[[tool.bumpversion.files]]` |

### Multi-Projection Subagent Maintenance — Generator-driven

Every subagent ships in four host-specific dialects, each with its own frontmatter shape. **Do NOT hand-edit the generated files** — edit the canonical YAML source and regenerate.

**Workflow:**

1. Edit the canonical source: `tools/agent-sources/<name>.yaml` (frontmatter + body in one file; `tools` uses canonical names — `read`, `grep`, `glob`, `bash`).
2. Run `make agents` — regenerates the four host dialects.
3. Commit the source AND the regenerated dialect files.

CI runs `make agents-check` (`tools/generate-agents.py --check`); it fails on any drift between the source and the on-disk dialect files. If the test fails, run `make agents` and re-commit.

**Per-host dialects produced by the generator:**

| Host | Path | Dialect shape |
| --- | --- | --- |
| Claude Code | `.claude-plugin/agents/<name>.md` | `tools` as comma-string of PascalCase names (`Read, Grep, Glob, Bash`) |
| Codex CLI | `.codex/agents/<name>.toml` | Pure TOML; body in `developer_instructions = """..."""`; no `tools` field (inherited from session `config.toml`) |
| Gemini CLI | `agents/<name>.md` | `tools` as YAML list of snake_case (`- read_file`) |
| OpenCode | `.opencode/agents/<name>.md` | `tools` as dict (`read: true`) plus `mode: subagent` |

The tool-name mapping (`read` → `read_file` for Gemini, `Read` for Claude, `read` for OpenCode, etc.) lives in `tools/generate-agents.py` `TOOL_MAP`. Add new canonical tools there.

### Codex `.agents/plugins/` carve-out

The Codex CLI marketplace lives at `.agents/plugins/marketplace.json` per Codex's spec. The Codex plugin manifest lives at `.agents/plugins/plugins/<name>/.codex-plugin/plugin.json` (Codex 0.125+ rejects `source.path: "./"` so the plugin must be a subdirectory). These two paths are the ONLY exception to the rule that `.agents/` is Flow authoring (gitignored). The carve-out shape in `.gitignore` is:

```text
.agents/*
!.agents/plugins/
.agents/plugins/*
!.agents/plugins/marketplace.json
!.agents/plugins/plugins/
```

`tools/validate-codex-manifest.py` enforces the constraints (run via `make validate`):

- `source.path` must start with `./`, be non-empty, contain no `..`
- Claude `userConfig` keys must be camelCase; types must be one of `string|number|boolean|directory|file`; every entry must have a `title`

If you're working in a Flow stealth-mode clone (`bd init --stealth`), `.git/info/exclude` will contain a duplicate `.agents/` rule. Mirror the same `.agents/*` + `!.agents/plugins/...` pattern locally so the carve-out resolves.

The four `description` fields must match verbatim so agent-selection heuristics route to the same subagent regardless of host. Each dialect is enforced by a dedicated validator in `tools/validate-skills.py` (`validate_claude_agent`, `validate_codex_agent`, `validate_gemini_agent`, `validate_opencode_agent`) — mutual rejection catches drift (e.g., a Codex file with a top-level `tools = [...]` array fails CI).

### Skill Path Portability

Do not hard-code `.agents/` or `.agent/` inside a skill body. Hosts resolve Agent Skills through different directory names — Claude Code, OpenCode, VS Code/Copilot read `.agents/skills/`; Google Antigravity reads `.agent/skills/` (singular). Refer to skills by name, not path.

## Manifest Expansion Plans (v0.2+)

Several host-manifest fields are deferred from v0.1 to avoid shipping empty stubs that may trip strict validators:

- **`gemini-extension.json`**: `mcpServers` and `excludeTools` — added when the first Litestar MCP server ships (v0.2).
- **`.claude-plugin/plugin.json`**: `mcpServers` — same as above.
- **`.opencode/plugins/litestar.js`**: currently a minimal `export default {}` stub. Real `@opencode-ai/plugin` integration may land if programmatic registration proves necessary; OpenCode's native `.claude/skills/` + `.agents/skills/` discovery covers v0.1 needs.

When adding any of the above, update both the manifest and this section.

## Version Sync Rule

If a new file contains a `version` string, add it to `[[tool.bumpversion.files]]` in `pyproject.toml` **in the same commit**. This is enforced by `make check`.

## Releasing

```bash
make release bump=patch      # or minor, major
git push --tags
```

`bump-my-version` atomically updates every tracked manifest. The tag push triggers `.github/workflows/release.yml` → GitHub Release.

## Code Style

- **Python 3.10+**, PEP 604 unions (`T | None`). `from __future__ import annotations` is a library-author guardrail, not a consumer rule — application code MAY use it. Avoid it only in modules that define runtime-introspected types (msgspec.Struct, SQLAlchemy 2.0 `Mapped[...]`, Dishka `@provide`, SAQ `@task`, ADK tool registries).
- **Linting:** `ruff` + `oxlint` + `markdownlint-cli2`
- **Type-checking:** `mypy` + `pyright` (both strict)
- **Pre-commit:** `prek install` (runs on every commit)
- **No emojis** in skill content unless the user explicitly asks for them.

## Reporting Issues

Use GitHub Issues at <https://github.com/litestar-org/litestar-skills/issues>. For Litestar framework bugs (not skill-content bugs), file at <https://github.com/litestar-org/litestar/issues>.
