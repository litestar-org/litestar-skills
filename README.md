# litestar-skills

> Opinionated, first-party agent skills, plugins, subagents, hooks, and rules for the **Litestar** framework and its ecosystem — published from a single-root repository across Google Antigravity, Claude Code, Codex CLI, Cursor, OpenCode, and VS Code / Copilot.

`litestar-skills` teaches AI coding agents how the Litestar team builds software. Dedicated package skills cover Litestar, SQLSpec, Advanced Alchemy, msgspec, Polyfactory, pytest-databases, Litestar Security, Litestar Autowire, Litestar Granian, Litestar SAQ, Litestar Queues, Litestar Vite, Litestar MCP, Litestar Email, Litestar HTMX, Litestar AI, Litestar Docs (Sphinx & Zensical), Litestar Build, Litestar Deployment, Litestar Testing, and the Litestar Styleguide.

## Status

**v0.11.0** — Single-root multi-harness packaging, 21 skills. The plugin and namespace identifier is `litestar`. The Python package and repository remain `litestar-skills`.

## Host Artifacts

| Host | Entry Point |
| --- | --- |
| **Google Antigravity** | `plugin.json` + `hooks.json` + `rules/litestar-antigravity.md` + `agents/*.md` + `skills/` |
| **Claude Code** | `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` + `hooks/hooks-claude.json` + `agents/*.md` + `skills/` |
| **Codex CLI** | `.codex-plugin/plugin.json` + `.agents/plugins/marketplace.json` + `.codex/agents/*.toml` + `skills/` |
| **Cursor** | `.cursor-plugin/plugin.json` + `hooks/hooks-cursor.json` + `agents/*.md` + `skills/` |
| **OpenCode** | `.opencode/plugins/litestar.js` + `skills/` |
| **VS Code / Copilot** | Raw `skills/` path via `chat.skillsLocations` |

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
| **Cursor** | Skills and `sessionStart` hook load from `.cursor-plugin/plugin.json`. | `litestar-reviewer` from `agents/`. |
| **OpenCode** | `.opencode/plugins/litestar.js` injects `litestar:<skill-name>` system reminders; skills load from `.agents/skills/`. | Use the `litestar` skill review workflow. |
| **VS Code / Copilot** | Skills load from `chat.skillsLocations`. | Use the `litestar` skill review workflow. |

## Install

### Google Antigravity

```bash
git clone --depth 1 https://github.com/litestar-org/litestar-skills ~/.gemini/config/plugins/litestar
```

For workspace-scoped skills only, copy `skills/*` into `.agents/skills/`.

### Claude Code

```text
/plugin marketplace add litestar-org/litestar-skills
/plugin install litestar@litestar-skills
```

### Codex CLI

```bash
codex plugin marketplace add litestar-org/litestar-skills
```

Then enable `litestar` inside a Codex session via `/plugins`.

### Cursor

```text
Cursor → Settings → Rules / Plugins → Add Remote Repository → https://github.com/litestar-org/litestar-skills
```

### OpenCode

```bash
git clone https://github.com/litestar-org/litestar-skills ~/.config/opencode/litestar
ln -sf ~/.config/opencode/litestar/.opencode/plugins/litestar.js \
       ~/.config/opencode/plugins/litestar.js
```

### VS Code / GitHub Copilot

```bash
git clone https://github.com/litestar-org/litestar-skills ~/.copilot/litestar
```

Add to VS Code `settings.json`:

```json
{
  "chat.skillsLocations": {
    "~/.copilot/litestar/skills": true
  }
}
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

- **Google Antigravity**: `rm -rf ~/.gemini/config/plugins/litestar`
- **Claude Code**: `/plugin uninstall litestar` inside Claude Code
- **Codex CLI**: `codex plugin remove litestar@litestar-skills && codex plugin marketplace remove litestar-skills`
- **Cursor**: Remove the plugin from Cursor Settings
- **OpenCode**: `rm ~/.config/opencode/plugins/litestar.js && rm -rf ~/.config/opencode/litestar`
- **VS Code**: Remove the `chat.skillsLocations` entry and delete `~/.copilot/litestar`

## Skill Catalog

21 skills with focused reference guides:

| Category | Skills |
| --- | --- |
| **Core** | `litestar` (routing, DTOs, OpenAPI, DI/Dishka, guards, middleware, exceptions, plugins, Channels/SSE/WebSockets, settings, data services, filters & pagination) |
| **Foundation** | `litestar-styleguide` |
| **Data & Serialization** | `sqlspec`, `advanced-alchemy`, `msgspec` |
| **Security & Auth** | `litestar-security` |
| **Tasks & Queues** | `litestar-queues`, `litestar-saq` |
| **Frontend** | `litestar-vite` (Vite + Inertia), `litestar-htmx` |
| **Server** | `litestar-granian` |
| **Integrations & AI** | `litestar-mcp`, `litestar-email`, `litestar-autowire`, `litestar-ai` |
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
