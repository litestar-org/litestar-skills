# Contributing to `litestar-skills`

See [`docs/roadmap.md`](docs/roadmap.md) for deferred candidates and graduation triggers.

## Adding or Updating a Skill

1. Create `skills/<your-skill-name>/SKILL.md` (and optional `skills/<your-skill-name>/references/*.md`).
2. Populate `SKILL.md` YAML frontmatter:
   - `name` — kebab-case, must match directory name, ≤64 characters.
   - `description` — trigger-only; starts with `Use when`, ≤500 characters, names concrete file/import/API signals, ends with `Not for X`, and avoids forbidden terms (`Auto-activate`, `Produces`, `Expert knowledge`, `Comprehensive`).
3. Keep `SKILL.md` strictly under **24,000 bytes** (`< 24 KB`). Extract deep-dive reference material into `references/*.md`.
4. Author the body in this XML-tagged section order:
   - Code Style Rules → Quick Reference → `<workflow>` → `<guardrails>` → `<validation>` → `<example>` → References Index → Official References → Shared Styleguide Baseline (linking to [`skills/litestar-styleguide/`](skills/litestar-styleguide/SKILL.md)).
5. Apply the Litestar-first-party bias and match-your-stack neutrality where multiple first-party or supported tools exist.
6. Run `make validate` and `make check` before opening a PR.

## Single-Root Multi-Harness Architecture

`litestar-skills` uses a single-root layout with 8 synchronized manifests and zero duplicate plugin trees:

| Manifest | Purpose |
| --- | --- |
| `pyproject.toml` | Canonical Python package & `bump-my-version` configuration |
| `package.json` | JavaScript/Bun tooling metadata |
| `plugin.json` | Google Antigravity plugin manifest |
| `.claude-plugin/plugin.json` | Claude Code plugin manifest (`hooks: "./hooks/hooks-claude.json"`) |
| `.claude-plugin/marketplace.json` | Claude Code marketplace (`source: "./"`) |
| `.codex-plugin/plugin.json` | Codex CLI plugin manifest (`skills: "./skills"`) |
| `.cursor-plugin/plugin.json` | Cursor plugin manifest (`hooks: "hooks/hooks-cursor.json"`) |
| `.agents/plugins/marketplace.json` | Codex / Universal Agent marketplace (`path: "./"`) |

## Subagent Maintenance

Subagents live in two synchronized files:

1. `agents/<name>.md` — shared Markdown subagent consumed by Google Antigravity, Claude Code, and Cursor. Must declare `name`, `description`, `model: inherit`, `mainAgent: false`, `subagent: true`, `readonly: true`, YAML lists for `tools`, `disallowedTools`, and `skills`, and `#` H1 section headings in the Markdown body (never `##` H2+).
2. `.codex/agents/<name>.toml` — Codex CLI TOML subagent declaring `name`, `description`, `model_reasoning_effort`, `sandbox_mode`, and `developer_instructions` (never a top-level `tools` array).

Both files are validated by `tools/validate.py`.

## Hooks Maintenance

- `hooks/session-start.sh` — pure POSIX `sh` + `awk` detector and JSON envelope emitter (`--harness agy|claude|cursor`, `--json`).
- `hooks/session-start.ps1` — native Windows PowerShell equivalent (`-Harness agy|claude|cursor`, `-Json`) wired via `commandWindows` in `hooks/hooks-claude.json`.
- `.opencode/plugins/litestar.js` — in-process Node (`node:fs` / `node:path`) OpenCode V2 plugin.

## Version Sync Rule

All 8 manifests are tracked in `[[tool.bumpversion.files]]` in `pyproject.toml`. `uv run python tools/validate.py` verifies version parity across all 8 files on every run.

## Releasing

```bash
make release bump=patch      # or minor, major
git push origin HEAD --tags
```

## Code Style

- **Python 3.10+**, PEP 604 unions (`T | None`), Google-style docstrings, zero inline `#` comments in repository Python code.
- **Linting:** `ruff` + `oxlint` + `markdownlint-cli2` (`make lint`).
- **Type-checking:** `mypy` + `pyright` (`make type-check`).
- **Validation:** `tools/validate.py` + `tools/check-upstream-imports.py` + `tools/check-sample-kwargs.py` (`make validate`).
