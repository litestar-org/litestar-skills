# `litestar-skills` Agent Context

This file is loaded by every AI agent CLI that consumes this repo: Claude Code, Gemini CLI, Codex CLI, Cursor, OpenCode, VS Code/Copilot, and others supporting the [agentskills.io](https://agentskills.io) standard.

## Mission

`litestar-skills` is a curated, opinionated collection of agent skills, plugins, subagents, slash commands, and MCP servers for the **Litestar** framework and its first-party ecosystem. Agents working in this repo are authoring or maintaining content that will be consumed by other agents to guide Litestar application development.

See [`.agents/product.md`](.agents/product.md) for the full product definition and [`.agents/product-guidelines.md`](.agents/product-guidelines.md) for tone, XML tagging, and authoring conventions.

## Agent Conduct

- **Terse, imperative, authoritative tone.** No hedging. State the preferred choice.
- **Litestar-first-party bias.** Prefer `litestar-granian`, `litestar-saq`, `sqlspec`, `advanced-alchemy`, `msgspec` over generic alternatives in examples and recommendations.
- **Minimal targeted changes.** Do not make opportunistic cleanup edits without approval.
- **Canonical commands via Make.** Always prefer `make <target>` over raw tool invocations. See [Development Commands](#development-commands).
- **Never silently descope.** If a task is larger than expected, refine the plan or ask how to prioritize.
- **No blame language.** Describe problems factually; offer the smallest useful next step.

## Skill Authoring Rules

Every `SKILL.md` MUST follow the conventions in `.agents/product-guidelines.md`:

1. **YAML frontmatter** with `name` (kebab-case, matches directory) and `description` (starts with auto-activation signal, ends with `Not for X — why`).
2. **XML-tagged sections** in this order: Code Style Rules → Quick Reference → `<workflow>` → `<guardrails>` → `<validation>` → `<example>` → References Index → Official References → Shared Styleguide Baseline.
3. **Litestar code-sample conventions**:
   - PEP 604 unions (`T | None`), never `Optional[T]`
   - **Never** `from __future__ import annotations` (breaks Litestar runtime introspection)
   - Google-style docstrings, async all I/O
   - `msgspec` over Pydantic in Litestar contexts
   - `advanced-alchemy` / `sqlspec` over raw SQLAlchemy

## Supported Hosts

| Host | Entry Point | Notes |
|---|---|---|
| **Claude Code** | `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` | Primary target. Full plugin with skills, commands, agents, hooks. |
| **Gemini CLI** | `gemini-extension.json`, context via `GEMINI.md` | Auto-indexed gallery (topic `gemini-cli-extension`). |
| **Codex CLI** | `.codex-plugin/plugin.json` | Includes `interface` metadata block. |
| **Cursor** | `.cursor-plugin/plugin.json` | Hooks via `hooks/hooks-cursor.json`. |
| **OpenCode** | `.opencode/plugins/litestar-skills.js` + native `.claude/skills/` + `.agents/skills/` reads | JS plugin wrapper. |
| **VS Code/Copilot** | User adds path to `chat.skillsLocations` | Raw SKILL.md tree (no wrapper extension in v0.1). |

## File Resolution

| Resource | Location |
|---|---|
| Skills | `skills/<skill-name>/SKILL.md` |
| Slash commands | `commands/<prefix>/<command>.toml` |
| Subagents | `agents/<agent-name>.md` |
| MCP servers | `mcp-servers/<server-name>/` |
| Hooks | `hooks/*.json` + `hooks/session-start` |
| Templates | `templates/skill-template/` |
| Flow context | `.agents/` (hidden; local-only) |

## Development Commands

Always run via `make` — never invoke underlying tools directly in documentation.

```bash
make install         # uv sync + bun install + prek install
make lint            # ruff + oxlint + markdownlint
make typecheck       # mypy + pyright
make test            # pytest + bun test
make validate-skills # frontmatter + link + skills-ref validation
make check           # lint + typecheck + test + validate-skills (CI parity)
make release bump=patch   # atomic bump of all 8 manifests via bump-my-version
```

## Version Sync Rule

Any file with a `version` string is listed under `[[tool.bumpversion.files]]` in `pyproject.toml`. Adding a new manifest requires adding it to bumpversion in the **same commit**. See [`.agents/patterns.md`](.agents/patterns.md) for the enforced pattern.

## Flow Framework

This repo is managed with the [Flow framework](https://github.com/cofin/flow) — spec-first planning + TDD + Beads task graph. Context files live in `.agents/`. If the `.agents/` directory exists on disk, Flow is active; agents should read `.agents/workflow.md` before starting substantive work.
