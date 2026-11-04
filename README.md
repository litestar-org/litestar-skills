# litestar-skills

> Opinionated, first-party agent skills, plugins, subagents, hooks, and rules for the **Litestar** framework and its ecosystem — published from a single-root repository across Google Antigravity, Claude Code, Codex CLI, Cursor, OpenCode, and VS Code / Copilot.

`litestar-skills` teaches AI coding agents how the Litestar team builds software. Dedicated package skills cover Litestar, SQLSpec, Advanced Alchemy, msgspec, Polyfactory, pytest-databases, Litestar Security, Litestar Autowire, Litestar Granian, Litestar SAQ, Litestar Queues, Litestar Vite, Litestar MCP, Litestar Email, Litestar HTMX, Litestar Docs (Sphinx & Zensical), Litestar Build, Litestar Deployment, Litestar Testing, and the Litestar Styleguide.

## Status

**v0.12.0** — Single-root multi-harness packaging, 20 skills. The plugin and namespace identifier is `litestar`. The Python package and repository remain `litestar-skills`.

## Host Artifacts

| Host | Entry Point |
| --- | --- |
| **Google Antigravity** | `plugin.json` + `hooks.json` + `rules/litestar-antigravity.md` + `agents/*.md` + `skills/` |
| **Claude Code** | `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` + `hooks/hooks-claude.json` + `agents/*.md` + `skills/` |
| **Codex CLI** | `.codex-plugin/plugin.json` + `.agents/plugins/marketplace.json` + `.codex/agents/*.toml` + `skills/` |
| **OpenCode V2** | `.opencode/plugins/litestar.js` + `skills/` |

## Harness Names

| Concept | Canonical Value |
| --- | --- |
| Plugin / marketplace identity | `litestar` |
| Skill directory names | `skills/<skill-name>/SKILL.md`, e.g. `skills/sqlspec/SKILL.md` |
| Hook and policy namespace | `litestar:<skill-name>`, e.g. `litestar:sqlspec` |
| Reviewer subagent | `agents/litestar-reviewer.md` and `.codex/agents/litestar-reviewer.toml` |

| Harness | Skill Trigger | Reviewer Agent Trigger |
| --- | --- | --- |
| **Google Antigravity** | Skills load from the `litestar` plugin or `.agents/skills/`. `SessionStart` in `hooks.json` and `rules/litestar-antigravity.md` inject `litestar:<skill-name>` context when project signals are detected. | `litestar-reviewer` from `agents/`. |
| **Claude Code** | `/litestar:litestar` for the hub skill; `/litestar:sqlspec` for focused skills. Plugin policy uses `Skill(litestar:<skill-name>)`. | `litestar-reviewer` from `agents/`. |
| **Codex CLI** | Force the hub with `$litestar:litestar` and focused skills with `$litestar:<skill-name>`, or use natural language. | `$agent litestar-reviewer` from `.codex/agents/`. |
| **OpenCode V2** | `.opencode/plugins/litestar.js` injects `litestar:<skill-name>` system reminders and registers `litestar-reviewer`; skills load from `.agents/skills/`. | `litestar-reviewer` registered via plugin. |

## Install

### Google Antigravity

```bash
agy plugin install https://github.com/litestar-org/litestar-skills
```

### Claude Code

```bash
claude plugin marketplace add litestar-org/litestar-skills
claude plugin install litestar@litestar
```

### Codex CLI

```bash
codex plugin marketplace add litestar-org/litestar-skills
codex plugin add litestar@litestar
```

To install the optional reviewer subagent in Codex:

```bash
cp .codex/agents/litestar-reviewer.toml ~/.codex/agents/
```

### OpenCode V2

```bash
opencode plugin add litestar-org/litestar-skills
```

## Optional: Google Developer Knowledge MCP

Google publishes an MCP server returning Firebase, Google Cloud, Android, and Maps documentation at `developerknowledge.googleapis.com`.

```bash
claude mcp add google-dev-knowledge --transport http \
  https://developerknowledge.googleapis.com/mcp \
  --header "X-Goog-Api-Key: YOUR_API_KEY"
```

Full reference: [`skills/litestar-styleguide/references/google-developer-knowledge-mcp.md`](skills/litestar-styleguide/references/google-developer-knowledge-mcp.md).

## Uninstall

- **Google Antigravity**: `agy plugin uninstall litestar` (or `rm -rf ~/.gemini/config/plugins/litestar`)
- **Claude Code**: `claude plugin uninstall litestar`
- **Codex CLI**: `codex plugin remove litestar@litestar && codex plugin marketplace remove litestar`
- **OpenCode V2**: `opencode plugin remove litestar-org/litestar-skills`

## Skill Catalog

20 skills with focused reference guides:

| Category | Skills |
| --- | --- |
| **Core** | `litestar` (routing, DTOs, OpenAPI, DI/Dishka, guards, middleware, exceptions, plugins, Channels/SSE/WebSockets, settings, data services, filters & pagination) |
| **Foundation** | `litestar-styleguide` |
| **Data & Serialization** | `sqlspec`, `advanced-alchemy`, `msgspec` |
| **Security & Auth** | `litestar-security` |
| **Tasks & Queues** | `litestar-queues`, `litestar-saq` |
| **Frontend** | `litestar-vite` (Vite + Inertia), `litestar-htmx` |
| **Server** | `litestar-granian` |
| **Integrations & Protocols** | `litestar-mcp`, `litestar-email`, `litestar-autowire` |
| **Documentation** | `litestar-docs` (Sphinx & Zensical) |
| **Packaging & Deployment** | `litestar-build`, `litestar-deployment` |
| **Testing** | `litestar-testing`, `pytest-databases`, `polyfactory` |

## Project Documents

- [Roadmap](docs/roadmap.md) — deferred items with explicit graduation triggers.
- [Policy & permissions](docs/policy.md) — per-host allow/ask/deny grammar and managed-settings paths. Drop-in template at [templates/managed-settings/claude-code.json](templates/managed-settings/claude-code.json).

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for skill authoring conventions, manifest sync rules, and validation gates.

## License

MIT — see [`LICENSE`](LICENSE).
