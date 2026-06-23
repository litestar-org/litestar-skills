# `litestar-skills` Agent Context

This file is loaded by every AI agent CLI that consumes this repo: Claude Code, Antigravity CLI, Codex CLI, Cursor, OpenCode, VS Code/Copilot, and others supporting the [agentskills.io](https://agentskills.io) standard.

## Mission

`litestar-skills` is a curated, opinionated collection of agent skills, plugins, subagents, slash commands, and MCP servers for the **Litestar** framework and its first-party ecosystem. Agents working in this repo are authoring or maintaining content that will be consumed by other agents to guide Litestar application development.

Style baseline for every skill here: [`skills/litestar-styleguide/`](skills/litestar-styleguide/SKILL.md).

## Agent Conduct

- **Terse, imperative, authoritative tone.** No hedging. State the preferred choice.
- **Litestar-first-party bias.** Prefer `litestar-granian`, `litestar-saq`, `sqlspec`, `advanced-alchemy`, `msgspec` over generic alternatives in examples and recommendations.
- **Minimal targeted changes.** Do not make opportunistic cleanup edits without approval.
- **Canonical commands via Make.** Always prefer `make <target>` over raw tool invocations. See [Development Commands](#development-commands).
- **Never silently descope.** If a task is larger than expected, refine the plan or ask how to prioritize.
- **No blame language.** Describe problems factually; offer the smallest useful next step.

## Skill Authoring Rules

Every `SKILL.md` MUST follow these conventions:

1. **YAML frontmatter** with `name` (kebab-case, matches directory) and trigger-only `description` (starts with `Auto-activate for` or `Use when`, includes concrete file/import/API signals, ends with `Not for X — why`, and contains no process summary such as "Produces ...").
2. **XML-tagged sections** in this order: Code Style Rules → Quick Reference → `<workflow>` → `<guardrails>` → `<validation>` → `<example>` → References Index → Official References → Shared Styleguide Baseline.
3. **Match-your-stack**: when multiple valid libraries / backends / patterns exist for a concern (data access, DI, background tasks, Channels backend, settings, serialization, deployment target), present all options and help the user pick based on what's already in their project. Never force one path.
4. **Litestar code-sample conventions** (full detail in [`skills/litestar-styleguide/`](skills/litestar-styleguide/SKILL.md)):
   - PEP 604 unions (`T | None`), never `Optional[T]`
   - `from __future__ import annotations` is a library-author guardrail, not a consumer rule — application code MAY use it; library code that defines runtime-introspected types avoids it
   - Google-style docstrings, async all I/O
   - `msgspec` over Pydantic in Litestar contexts (unless the project already uses Pydantic)
   - `advanced-alchemy` / `sqlspec` over raw SQLAlchemy (match the project's chosen stack)

## Supported Hosts

Document hosts by the artifacts this repo ships. Do not describe hosts as compatibility tiers.

| Host | Entry Point | Notes |
| --- | --- | --- |
| **Claude Code** | `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` + `.claude-plugin/agents/*.md` | Full plugin with skills, commands, agents, hooks. |
| **Antigravity CLI** | `plugin.json` + `hooks.json` + `agents/*.md` + `skills/` + `hooks/` | Google CLI plugin with Markdown subagent templates and SessionStart hooks. |
| **Codex CLI** | `.codex-plugin/plugin.json` + `.codex/agents/*.toml` + `.codex/config.toml` | Custom agents ship as pure TOML (tools inherited from session). |
| **OpenCode** | `.opencode/plugins/litestar.js` + `.opencode/agents/*.md` + native `.claude/skills/` / `.agents/skills/` reads | JS plugin wrapper + dict-schema agents. |
| **Cursor** | `.cursor-plugin/plugin.json` | Hooks via `hooks/hooks-cursor.json`. |
| **VS Code / Copilot** | User adds path to `chat.skillsLocations` | Raw SKILL.md tree; no wrapper extension in v0.1. |
| **OpenClaw** | `.agents/skills/` + `AGENTS.md` | Consumes generic Agent Skills tree without extra config. |

## File Resolution

| Resource | Location |
| --- | --- |
| Skills | `skills/<skill-name>/SKILL.md` |
| Slash commands | `commands/<prefix>/<command>.toml` |
| Subagents (Antigravity CLI) | `agents/<agent-name>.md` (`tools` as YAML list of Antigravity tool names) |
| Subagents (Claude Code) | `.claude-plugin/agents/<agent-name>.md` (`tools` as comma-separated string of Claude tool names) |
| Subagents (Codex CLI) | `.codex/agents/<agent-name>.toml` (pure TOML; `developer_instructions` holds the prompt; no top-level `tools` — inherited from session `config.toml`) |
| Subagents (OpenCode) | `.opencode/agents/<agent-name>.md` (`tools` as dict mapping + `mode: subagent`) |
| MCP servers | `mcp-servers/<server-name>/` |
| Hooks | Root `hooks.json` for Antigravity CLI; `hooks/hooks-<host>.json` for Claude/Cursor/Codex; shared runtime in `hooks/session-start.{sh,ps1,js}` + `hooks/lib/{detect-env.{sh,ps1,js},_detector.py,skill-map.json}` |
| Templates | `templates/skill-template/` |

## Harness Names

Keep package identity, skill namespace, command syntax, and agent syntax separate:

| Harness | Skill Manual Trigger | Command Trigger | Reviewer Agent Trigger |
| --- | --- | --- | --- |
| Claude Code | `/litestar:<skill-name>` (example: `/litestar:litestar-routing`); policies use `Skill(litestar:<skill-name>)` | `/litestar:configure`, `/litestar:new-app`, `/litestar:new-domain`, `/litestar:review` | `litestar-reviewer` from `.claude-plugin/agents/` |
| Antigravity CLI | Uses displayed skill/template names from the `litestar` plugin | No TOML slash-command surface in the Antigravity plugin schema | `litestar-reviewer` from top-level `agents/` |
| Codex CLI | `$litestar:litestar` or `$litestar:<focused-skill>` where the Codex surface supports `$` skill triggers; natural language also works | Codex plugins do not currently expose plugin-defined `/litestar:*` slash commands | `$agent litestar-reviewer` from `.codex/agents/` |
| OpenCode | Uses displayed skill names from copied `.agents/skills/`; plugin reminders use `litestar:<skill-name>` | No TOML command loader in the OpenCode plugin | `litestar-reviewer` from `.opencode/agents/` |

Canonical command files live in `commands/litestar/*.toml`. Generated subagents all come from `tools/agent-sources/litestar-reviewer.yaml`; run `make agents` after editing the source, then `make sync-codex-package` before `make lint`.

## Hooks

The SessionStart hook scans the project's cwd for known Litestar-ecosystem signals (pyproject deps, `[tool.<lib>]` sections, Python imports, file globs in `hooks/lib/skill-map.json`) and injects per-host context naming the relevant `litestar:<skill>` skills. Detection logic lives in `hooks/lib/_detector.py` (the canonical Python implementation reused by `detect-env.sh` and `detect-env.ps1`) and a parallel ESM port in `hooks/lib/detect-env.js` (used by the OpenCode plugin). Per-host shims: root `hooks.json` (Antigravity CLI plugin hook file), `hooks/hooks.json` (Claude Code default plugin hook file), `hooks/hooks-cursor.json` (Cursor), and `hooks/hooks-codex.json` (Codex). Override via `LITESTAR_SKILLS_HOOK_DISABLE=1`. Run `make test-hooks` to exercise the suite.

## Development Commands

Always run via `make` — never invoke underlying tools directly in documentation.

```bash
make install         # uv sync + bun install + prek install
make lint            # ruff + oxlint + markdownlint
make typecheck       # mypy + pyright
make test            # pytest + bun test
make validate-skills # frontmatter + link + skills-ref validation
make check           # lint + typecheck + test + validate-skills (CI parity)
make release bump=patch   # atomic bump of all versioned manifests via bump-my-version
```

## External Integrations

Optional, opt-in only. No manifests shipped — users add them per host.

- **Google Developer Knowledge MCP** — fresh Firebase / Google Cloud / Android / Maps docs. See [`skills/litestar-styleguide/references/google-developer-knowledge-mcp.md`](skills/litestar-styleguide/references/google-developer-knowledge-mcp.md) for auth, install one-liners, and the Codex/OpenCode gap note.

## Version Sync Rule

Any file with a `version` string is listed under `[[tool.bumpversion.files]]` in `pyproject.toml`. Adding a new manifest requires adding it to bumpversion in the **same commit**.
