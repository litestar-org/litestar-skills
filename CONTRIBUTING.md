# Contributing to `litestar-skills`

See [`docs/roadmap.md`](docs/roadmap.md) for shipped features, v0.2 candidates, and deferred items with graduation triggers.

## Adding a Skill

1. Copy `templates/skill-template/` to `skills/<your-skill-name>/`.
2. Fill in `SKILL.md` frontmatter:
   - `name` — kebab-case, must match directory name, ≤64 chars
   - `description` — starts with auto-activation signal (file globs, imports), ends with `Not for X — why`
3. Author the body in this XML-tagged section order:
   - Code Style Rules → Quick Reference → `<workflow>` → `<guardrails>` → `<validation>` → `<example>` → References Index → Official References → Shared Styleguide Baseline (link to the relevant files in [`skills/litestar-styleguide/references/`](skills/litestar-styleguide/SKILL.md))
4. Apply the Litestar-first-party bias for all code samples.
5. Run `make validate-skills` — must pass `skills-ref validate` and schema checks.
6. Run `make check` — full CI parity locally.
7. Open a PR. Maintainer review verifies tone, first-party bias, and technical accuracy.

## Support Tiers

When adding or changing host support, classify the host into one of three tiers:

- **First-class** — the repo ships maintained host-specific artifacts (manifest, subagents, hooks) and install guidance. Adding a new first-class host requires per-host validator coverage in `tools/validate-skills.py`.
- **Compatible bundle** — the host consumes standard manifests or generic skill-discovery paths. No native wrapper is promised; no per-host validator is required.
- **Free ride** — the host discovers generic Agent Skills / `AGENTS.md` content. The repo ships no dedicated integration; docs only.

Do not promote a host to a higher tier without shipping the corresponding artifacts and validator coverage in the same PR.

## Updating Host Manifests

When adding a skill, command, subagent, or MCP server, update the relevant per-host manifest so consumers auto-discover the new content:

| Addition | Manifests to update |
| --- | --- |
| New skill | None — all host manifests point at `./skills/` root. Skills auto-discovered. |
| New slash command | None — `./commands/` root is shared. |
| New subagent | Four host-specific projections — see [Multi-Projection Subagent Maintenance](#multi-projection-subagent-maintenance) below. |
| New MCP server | `.codex-plugin/plugin.json` `dependencies.tools`, `gemini-extension.json` `mcpServers`, and `.codex/config.toml` |
| New host support | New `.<host>-plugin/plugin.json` + entry in `[[tool.bumpversion.files]]` |

### Multi-Projection Subagent Maintenance

Every subagent ships in four host-specific dialects. When changing a reviewer prompt or adding a new subagent, update **all four** projections in the same PR — otherwise hosts drift:

| Host | Path | Dialect |
| --- | --- | --- |
| Claude Code | `.claude-plugin/agents/<name>.md` | Markdown body; `tools` is a comma-separated string (`Read, Grep, Glob, Bash`) of PascalCase Claude tool names. |
| Codex CLI | `.codex/agents/<name>.toml` | Pure TOML; prompt lives in `developer_instructions` (triple-quoted string). No top-level `tools` — tools inherit from session `config.toml`. |
| Gemini CLI | `agents/<name>.md` | Markdown body; `tools` is a YAML list (`- read_file`) of snake_case Gemini tool names. |
| OpenCode | `.opencode/agents/<name>.md` | Markdown body; `tools` is a dict (`read: true`) plus `mode: subagent`. |

The four `description` fields must match verbatim so agent-selection heuristics route to the same subagent regardless of host. Each dialect is enforced by a dedicated validator in `tools/validate-skills.py` (`validate_claude_agent`, `validate_codex_agent`, `validate_gemini_agent`, `validate_opencode_agent`) — mutual rejection catches drift (e.g., a Codex file with a top-level `tools = [...]` array fails CI).

### Skill Path Portability

Do not hard-code `.agents/` or `.agent/` inside a skill body. Hosts resolve Agent Skills through different directory names — Claude Code, OpenCode, VS Code/Copilot read `.agents/skills/`; Google Antigravity reads `.agent/skills/` (singular). Refer to skills by name, not path.

## Manifest Expansion Plans (v0.2+)

Several host-manifest fields are deferred from v0.1 to avoid shipping empty stubs that may trip strict validators:

- **`gemini-extension.json`**: `mcpServers` and `excludeTools` — added when the first Litestar MCP server ships (v0.2).
- **`.claude-plugin/plugin.json`**: `mcpServers` — same as above.
- **`.opencode/plugins/litestar-skills.js`**: currently a minimal `export default {}` stub. Real `@opencode-ai/plugin` integration may land if programmatic registration proves necessary; OpenCode's native `.claude/skills/` + `.agents/skills/` discovery covers v0.1 needs.

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
