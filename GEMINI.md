# `litestar-skills` — Gemini CLI Context

This extension bundles opinionated, first-party agent skills for the **Litestar** framework ecosystem.

> **Primary context:** [`AGENTS.md`](AGENTS.md). This file layers Gemini-CLI-specific guidance on top.

## Activation

Skills auto-activate on Litestar-relevant signals in the workspace:

- Imports: `litestar`, `litestar_granian`, `litestar_saq`, `litestar_vite`, `litestar_mcp`, `litestar_email`, `sqlspec`, `advanced_alchemy`, `msgspec`, `dishka`
- Files: `litestar.toml`, files using `from litestar import ...`

## Host Notes (Gemini CLI)

- Skills and MCP servers bundled in this extension install to `~/.gemini/extensions/litestar-skills/` on `gemini extensions install`.
- Update with `gemini extensions update litestar-skills`.
- Uninstall with `gemini extensions uninstall litestar-skills`.

## Conventions

See [`AGENTS.md`](AGENTS.md) for:

- Litestar-first-party bias (use `litestar-granian` / `litestar-saq` / `sqlspec` / `advanced-alchemy` / `msgspec` / `dishka` by default)
- Code style (PEP 604 unions, async all I/O; `from __future__ import annotations` is a library-author guardrail — application code MAY use it, only modules that define runtime-introspected types avoid it)
- Skill authoring conventions (XML-tagged sections, frontmatter rules)

## Flow Framework Compatibility

If the target project has an `.agents/` directory, skills in this extension will cooperate with the [Flow framework](https://github.com/cofin/flow) — spec-first planning + TDD + Beads task tracking.
