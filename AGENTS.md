# `litestar-skills` Agent Context

This file is loaded by AI coding agents that consume this repository: Google Antigravity, Claude Code, Codex CLI, Cursor, OpenCode, and VS Code / Copilot.

## Mission

`litestar-skills` is a curated, opinionated collection of agent skills, plugins, subagents, hooks, and rules for the **Litestar** framework and its first-party ecosystem. Agents working in this repo author and maintain content consumed by other agents to guide Litestar application development.

Style baseline for every skill here: [`skills/litestar-styleguide/`](skills/litestar-styleguide/SKILL.md).

## Agent Conduct

- **Terse, imperative, authoritative tone.** No hedging. State the preferred choice.
- **Litestar-first-party bias.** Prefer `litestar-granian`, `litestar-saq`, `litestar-queues`, `sqlspec`, `advanced-alchemy`, `msgspec` over generic alternatives in examples and recommendations.
- **Minimal targeted changes.** Do not make opportunistic cleanup edits without approval.
- **Canonical commands via Make.** Prefer `make <target>` over raw tool invocations. See [Development Commands](#development-commands).
- **Never silently descope.** If a task is larger than expected, refine the plan or ask how to prioritize.
- **No blame language.** Describe problems factually; offer the smallest useful next step.

## Skill Authoring Rules

Every `SKILL.md` MUST follow these conventions:

1. **YAML frontmatter** with `name` (kebab-case, matches directory) and trigger-only `description` (starts with `Use when`, ≤500 characters, includes concrete file/import/API signals, ends with `Not for X`, and contains no process summary such as `Produces ...`, `Auto-activate`, `Expert knowledge`, or `Comprehensive`).
2. **Byte budget**: Every `SKILL.md` MUST stay strictly under **24,000 bytes** (`< 24 KB`). Place deep architectural or multi-variant patterns in `skills/<skill-name>/references/*.md`.
3. **XML-tagged sections** in this order: Code Style Rules → Quick Reference → `<workflow>` → `<guardrails>` → `<validation>` → `<example>` → References Index → Official References → Shared Styleguide Baseline.
4. **Match-your-stack**: When multiple valid libraries, backends, or patterns exist for a concern (data access, DI, background tasks, Channels backend, documentation engine, settings, serialization, deployment target), present all supported options and match what is already in the user's project. Never force one path.
5. **Litestar code-sample conventions** (full detail in [`skills/litestar-styleguide/`](skills/litestar-styleguide/SKILL.md)):
   - PEP 604 unions (`T | None`), never `Optional[T]`
   - `from __future__ import annotations` is a library-author guardrail, not a consumer rule — application code MAY use it; library code that defines runtime-introspected types avoids it
   - Google-style docstrings, async all I/O
   - `msgspec` over Pydantic in Litestar contexts (unless the project already uses Pydantic)
   - `advanced-alchemy` / `sqlspec` over raw SQLAlchemy (match the project's chosen stack)

## Supported Hosts

| Host | Entry Point | Notes |
| --- | --- | --- |
| **Google Antigravity** | `plugin.json` + `hooks.json` + `rules/litestar-antigravity.md` + `agents/*.md` + `skills/` | Single-root plugin with H1 Markdown subagent templates, routing rules, and `SessionStart` hooks in root `hooks.json`. |
| **Claude Code** | `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` + `hooks/hooks-claude.json` + `agents/*.md` + `skills/` | Single-root plugin with auto-discovered `skills/` and `agents/` plus POSIX/Windows `SessionStart` hooks. |
| **Codex CLI** | `.codex-plugin/plugin.json` + `.agents/plugins/marketplace.json` + `.codex/agents/*.toml` + `skills/` | Single-root `"./"` marketplace source and pure TOML subagents. |
| **Cursor** | `.cursor-plugin/plugin.json` + `hooks/hooks-cursor.json` + `agents/*.md` + `skills/` | Single-root plugin with `sessionStart` hook and auto-discovered `skills/`. |
| **OpenCode** | `.opencode/plugins/litestar.js` + `skills/` | In-process Node (`node:fs` / `node:path`) plugin wrapper + native `.agents/skills/` discovery. |
| **VS Code / Copilot** | `skills/` via `chat.skillsLocations` | Raw `SKILL.md` tree. |

## File Resolution

| Resource | Location |
| --- | --- |
| Skills | `skills/<skill-name>/SKILL.md` |
| Subagents (Antigravity, Claude Code, Cursor) | `agents/<agent-name>.md` (`#` H1 sections, YAML list `tools`, `disallowedTools`, `skills`, `model: inherit`, `readonly: true`) |
| Subagents (Codex CLI) | `.codex/agents/<agent-name>.toml` (pure TOML; `developer_instructions` holds the prompt; no top-level `tools`) |
| Hooks | Root `hooks.json` (`SessionStart` for Antigravity), `hooks/hooks-claude.json` (Claude Code POSIX + `commandWindows`), `hooks/hooks-cursor.json` (Cursor); zero-dependency runtime in `hooks/session-start.sh` and `hooks/session-start.ps1` |
| Rules | `rules/litestar-antigravity.md` |
| Validator | `tools/validate.py` |

## Harness Names

| Harness | Skill Trigger | Reviewer Agent Trigger |
| --- | --- | --- |
| Google Antigravity | Uses skill names from the `litestar` plugin | `litestar-reviewer` from `agents/` |
| Claude Code | `/litestar:<skill-name>` (example: `/litestar:sqlspec`); policies use `Skill(litestar:<skill-name>)` | `litestar-reviewer` from `agents/` |
| Codex CLI | `$litestar:litestar` or `$litestar:<focused-skill>`; natural language also works | `$agent litestar-reviewer` from `.codex/agents/` |
| Cursor | Uses displayed skill names from the `litestar` plugin | `litestar-reviewer` from `agents/` |
| OpenCode | Uses displayed skill names from `.agents/skills/`; plugin reminders use `litestar:<skill-name>` | Uses `litestar` review skill |
| VS Code / Copilot | Uses displayed skill names from `chat.skillsLocations` | Uses `litestar` review skill |

## Hooks

The `SessionStart` hook (`hooks/session-start.sh` on POSIX and `hooks/session-start.ps1` on Windows) scans the project's working directory for Litestar-ecosystem signals (`pyproject.toml` dependencies, `zensical.toml`, `docs/conf.py`, `vite.config.*`, `alembic.ini`) using POSIX `sh` + `awk` (or PowerShell) with zero Python or Node runtime dependencies. It emits per-host JSON envelopes for Google Antigravity (`--harness agy`), Claude Code (`--harness claude`), and Cursor (`--harness cursor`). OpenCode uses the in-process `.opencode/plugins/litestar.js` plugin. Set `LITESTAR_SKILLS_HOOK_DISABLE=1` to disable hook output.

## Development Commands

Always run via `make`:

```bash
make install         # uv sync + bun install + prek install
make lint            # ruff + oxlint + markdownlint
make type-check      # mypy + pyright
make test            # pytest
make validate        # tools/validate.py + upstream import & kwarg checks
make check           # lint + type-check + test + validate (CI parity)
make release bump=patch   # atomic bump of all 8 manifests via bump-my-version
```

## External Integrations

- **Google Developer Knowledge MCP** — Firebase / Google Cloud / Android / Maps docs. See [`skills/litestar-styleguide/references/google-developer-knowledge-mcp.md`](skills/litestar-styleguide/references/google-developer-knowledge-mcp.md).

## Version Sync Rule

All 8 manifests (`pyproject.toml`, `package.json`, `plugin.json`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.codex-plugin/plugin.json`, `.cursor-plugin/plugin.json`, `.agents/plugins/marketplace.json`) are tracked under `[[tool.bumpversion.files]]` in `pyproject.toml` and verified by `tools/validate.py`.
