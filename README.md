# litestar-skills

> Opinionated, first-party agent skills, plugins, subagents, slash commands, and MCP servers for the **Litestar** framework and its ecosystem — publishable to **every major AI agent and IDE** from a single repo.

`litestar-skills` is a curated collection of agentic-development assets that teach AI coding agents how the Litestar team actually builds software. It covers the Litestar core plus first-party libraries (`sqlspec`, `advanced-alchemy`, `litestar-granian`, `litestar-saq`, `litestar-vite`, `litestar-mcp`, `litestar-email`, `litestar-htmx`, `litestar-asyncpg`, `litestar-oracledb`, and more).

## Status

**v0.4.0 — early access.** Multi-host plumbing, 28 skills, ~28,500 lines of canonical content. Full launch-skill catalog growing.

**Breaking host identity note:** host-facing marketplace, plugin, extension, managed-config, and skill namespace IDs are `litestar`. Existing installs under `litestar-skills` should be removed and reinstalled; no alias is shipped. The Python package and repository remain `litestar-skills`.

## Host Artifacts

This repo documents hosts by the artifacts it ships:

| Host | Entry Point |
| --- | --- |
| Claude Code | `.claude-plugin/plugin.json` + marketplace metadata + `.claude-plugin/agents/*.md` |
| Antigravity CLI | `plugin.json` + `agents/*.md` + `skills/` |
| Codex CLI | `.codex-plugin/plugin.json` + `.codex/agents/*.toml` |
| OpenCode | `.opencode/plugins/litestar.js` + `.opencode/agents/*.md` |
| Cursor | `.cursor-plugin/plugin.json` |
| VS Code / Copilot | Raw `skills/` path via `chat.skillsLocations` |
| OpenClaw | `.agents/skills/` + `AGENTS.md` |

## Harness Names And Commands

Different hosts expose the same repo assets with different command surfaces. Keep four names separate:

| Concept | Canonical Value |
| --- | --- |
| Plugin / marketplace identity | `litestar` |
| Skill directory names | `skills/<skill-name>/SKILL.md`, e.g. `skills/litestar-routing/SKILL.md` |
| Hook and policy namespace | `litestar:<skill-name>`, e.g. `litestar:litestar-routing` |
| Command files | `commands/litestar/{configure,new-app,new-domain,review}.toml` |

| Harness | Skill Manual Trigger | Command Trigger | Reviewer Agent Trigger |
| --- | --- | --- | --- |
| Claude Code | `/litestar:litestar` for the hub skill; `/litestar:litestar-routing` for focused skills. Plugin policy uses `Skill(litestar:<skill-name>)`. | `/litestar:configure`, `/litestar:new-app`, `/litestar:new-domain`, `/litestar:review` | Select `litestar-reviewer` from `.claude-plugin/agents/` where Claude exposes plugin subagents. |
| Antigravity CLI | Skills load from the `litestar` plugin or `.agents/skills/`; use the displayed skill/template name in Antigravity. | No TOML slash-command surface in the Antigravity plugin schema. Use prompts backed by the skills or reviewer agent. | `litestar-reviewer` from top-level `agents/`. |
| Codex CLI | Codex surfaces installed skills by displayed name. In `$`-trigger Codex surfaces, force the hub with `$litestar:litestar` and focused skills with `$litestar:<skill-name>`; natural language also works. | Codex plugins do not currently expose plugin-defined `/litestar:*` slash commands. Use natural language such as “Use Litestar review…” and the `litestar` skill router. | `$agent litestar-reviewer` from `.codex/agents/`. |
| OpenCode | `opencode skill list` shows project-local copied skills; use the displayed skill name in the OpenCode UI. Plugin reminders use `litestar:<skill-name>`. | No TOML command loader in the OpenCode plugin. Use natural-language prompts or project-local command support. | `litestar-reviewer` from `.opencode/agents/`. |
| Cursor | Skills are discovered from the plugin/rule path; use the displayed skill name in Cursor. | Host command support varies; shipped TOML commands remain under `commands/litestar/`. | No Cursor-specific reviewer dialect shipped. |
| VS Code / Copilot | Skills are discovered from `chat.skillsLocations`; use the displayed skill name in Copilot Chat. | No shipped command wrapper. | No VS Code-specific reviewer dialect shipped. |
| OpenClaw | Skills are discovered from `.agents/skills/`; use the displayed skill name. | No shipped command wrapper. | No OpenClaw-specific reviewer dialect shipped. |

Canonical agent source lives in `tools/agent-sources/litestar-reviewer.yaml`; run `make agents` after editing it, then `make sync-codex-package` before `make lint` so the generated Codex package copy stays current.

## Install

Pick your host and run the one command below. If you use several agents, skip to the [multi-host installer](#one-shot-multi-host-installer).

### Claude Code

```text
/plugin marketplace add litestar-org/litestar-skills
/plugin install litestar@litestar
```

The `/plugin` commands run **inside** a Claude Code session — the installer can't automate this part.

### Antigravity CLI

```bash
git clone --depth 1 https://github.com/litestar-org/litestar-skills ~/.config/antigravity/litestar
agy plugin install ~/.config/antigravity/litestar
```

Existing legacy Google CLI extension installs should migrate through Antigravity CLI's plugin import flow; fresh installs use the `plugin.json` path above.

### Codex CLI

> **Codex CLI 0.125+** required. The marketplace lives at `.agents/plugins/marketplace.json` and points at the committed generated package under `plugins/litestar/`.

```bash
codex plugin marketplace add litestar-org/litestar-skills
```

Then enable inside a Codex session via `/plugins`. See [`.codex/INSTALL.md`](.codex/INSTALL.md) for local-development install paths.

### OpenCode

OpenCode reads `.opencode/skills/`, `.claude/skills/`, and `.agents/skills/` natively. Two install paths:

```bash
# Option 1: project-local skills (no plugin features)
git clone --depth 1 https://github.com/litestar-org/litestar-skills /tmp/litestar-skills
mkdir -p .agents/skills
cp -r /tmp/litestar-skills/skills/* .agents/skills/

# Option 2: global plugin (recommended) — injects project-aware skill reminders
git clone https://github.com/litestar-org/litestar-skills ~/.config/opencode/litestar
ln -sf ~/.config/opencode/litestar/.opencode/plugins/litestar.js \
       ~/.config/opencode/plugins/litestar.js
```

Option 2 ships a real `experimental.chat.system.transform` handler that injects targeted Litestar skill reminders into the system prompt and honors managed-config policy. See [`.opencode/INSTALL.md`](.opencode/INSTALL.md).

### Antigravity workspace skills

Antigravity CLI reads workspace skills from `.agents/skills/` and global skills from `~/.gemini/antigravity-cli/skills/`. For skills-only workspace installs:

```bash
cd your-project
git clone --depth 1 https://github.com/litestar-org/litestar-skills /tmp/litestar-skills
mkdir -p .agents/skills
cp -r /tmp/litestar-skills/skills/* .agents/skills/
```

For global installs across all workspaces:

```bash
mkdir -p ~/.gemini/antigravity-cli/skills
cp -r /tmp/litestar-skills/skills/* ~/.gemini/antigravity-cli/skills/
```

Use the full plugin install above when you want the reviewer subagent in addition to raw skills.

### OpenClaw

OpenClaw reads the generic Agent Skills tree; no OpenClaw-specific manifest is needed:

```bash
git clone --depth 1 https://github.com/litestar-org/litestar-skills /tmp/litestar-skills
mkdir -p .agents/skills
cp -r /tmp/litestar-skills/skills/* .agents/skills/
```

OpenClaw consumes the shipped generic Agent Skills tree and `AGENTS.md`; no OpenClaw-specific wrapper is shipped.

### Cursor

```text
Cursor → Settings → Rules → Add Remote Rule → https://github.com/litestar-org/litestar-skills
```

### VS Code / GitHub Copilot

```bash
git clone https://github.com/litestar-org/litestar-skills ~/.copilot/litestar
```

Then in VS Code `settings.json`:

```json
{
  "chat.skillsLocations": {
    "~/.copilot/litestar/skills": true
  }
}
```

### One-shot multi-host installer

Installs for every supported CLI detected on your system. Auto-installs for Antigravity CLI via a staged payload, Codex CLI via `codex plugin marketplace add` + `codex plugin add`, and OpenCode via the host-specific plugin path; prints instructions for Claude Code, Cursor, and VS Code.

```bash
curl -fsSL https://raw.githubusercontent.com/litestar-org/litestar-skills/main/tools/install.sh | bash
```

<!-- markdownlint-disable -->
<details>
<summary>Options, clone-first usage, and Windows PowerShell</summary>
<!-- markdownlint-restore -->

**Flags:**

```bash
# Preview without executing
curl -fsSL https://raw.githubusercontent.com/litestar-org/litestar-skills/main/tools/install.sh | bash -s -- --dry-run

# Install for specific hosts only
curl -fsSL https://raw.githubusercontent.com/litestar-org/litestar-skills/main/tools/install.sh | bash -s -- --only antigravity --only codex

# Also whitelist the Claude Code marketplace in ~/.claude/settings.json
curl -fsSL https://raw.githubusercontent.com/litestar-org/litestar-skills/main/tools/install.sh | bash -s -- --claude-settings
```

**If you'd rather not pipe to `bash`, clone first:**

```bash
git clone https://github.com/litestar-org/litestar-skills
cd litestar-skills
./tools/install.sh --help
```

**Windows (PowerShell 7+ only):** native install without WSL. Requires PowerShell 7+ and Git for Windows (for hook dispatch).

```powershell
pwsh -File tools/install.ps1

# Preview:
pwsh -File tools/install.ps1 -DryRun

# Install for specific host(s):
pwsh -File tools/install.ps1 -Only antigravity,codex
```

If PowerShell 7+ is not installed: `winget install Microsoft.PowerShell`. If Git for Windows is not installed: <https://git-scm.com/download/win>.

</details>

## Optional: Google Developer Knowledge MCP

Google publishes an MCP server that returns fresh Firebase / Google Cloud / Android / Maps docs at `developerknowledge.googleapis.com`. Useful when a Litestar project depends on a Google-managed service. No manifest is shipped; users opt in per host.

```bash
# Claude Code
claude mcp add google-dev-knowledge --transport http \
  https://developerknowledge.googleapis.com/mcp \
  --header "X-Goog-Api-Key: YOUR_API_KEY"
```

Generate the API key at `https://console.cloud.google.com/apis/credentials` and restrict it to the Developer Knowledge API. Full reference: [`skills/litestar-styleguide/references/google-developer-knowledge-mcp.md`](skills/litestar-styleguide/references/google-developer-knowledge-mcp.md).

## Discovery topics

This repo is tagged with GitHub topics so downstream registries and galleries auto-crawl it:

| Topic | Downstream effect |
| --- | --- |
| `litestar` | Framework discoverability — surfaces in Litestar-ecosystem GitHub searches. |
| `agent-skills` | Generic agent-skills discoverability for Claude Code / Copilot CLI skill indexes. |
| `claude-code-plugin` | Claude Code plugin discoverability (e.g., [claudeskills.info](https://claudeskills.info)). |

Topics are re-applied on every tagged release via `.github/workflows/release.yml`. The operation is idempotent; `gh repo edit --add-topic` is additive and deduplicates.

### Vercel skills.sh

[skills.sh](https://skills.sh) ranks skill bundles by install volume from the `npx skills` CLI — there is no submission flow. To install via that path:

```bash
npx skills add litestar-org/litestar-skills
```

Each install increments the repo's ranking.

## Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/litestar-org/litestar-skills/main/tools/uninstall.sh | bash
```

Or from a clone: `./tools/uninstall.sh --help`. Same `--only`, `--skip`, `--dry-run`, `--force`, `--claude-settings` flags as the installer.

Per-host uninstall:

- **Claude Code**: `/plugin uninstall litestar` inside Claude Code
- **Antigravity CLI**: `agy plugin uninstall litestar`
- **Codex CLI**: `codex plugin remove litestar@litestar && codex plugin marketplace remove litestar`
- **OpenCode**: `rm ~/.config/opencode/plugins/litestar.js && rm -rf ~/.config/opencode/litestar`
- **Cursor**: remove the Remote Rule from Settings → Rules
- **VS Code**: remove the `chat.skillsLocations` entry + delete the clone

## Troubleshooting

**"No supported CLIs detected"** — none of `claude`, `agy`, `codex`, `opencode`, `cursor`, or `code` are on `$PATH`. Install at least one and re-run.

**OpenCode symlink fails on Windows** — run the PowerShell installer, which copies the OpenCode plugin entrypoint instead of creating a symlink. The Antigravity, Claude, and Codex install paths do not rely on symlinks.

**Codex marketplace add fails** — do NOT run with `sudo`; the installer refuses root. Ensure your user owns `~/.codex/`, `~/.agents/`, and Codex's cache directory.

**Antigravity plugin already installed** — re-run the installer with `--force` to uninstall and reinstall the plugin.

**Claude Code can't find the marketplace** — re-run with `--claude-settings` to whitelist, or inside Claude Code manually: `/plugin marketplace add litestar-org/litestar-skills`.

## What's In This Repo

28 skills, focused references, ~28,500+ lines of canonical content:

| Category | Skills |
| --- | --- |
| Core | `litestar` |
| Litestar app surfaces | `litestar-routing`, `litestar-dto-openapi`, `litestar-auth-guards`, `litestar-di`, `litestar-data-services`, `litestar-settings`, `litestar-exceptions`, `litestar-middleware`, `litestar-plugins`, `litestar-realtime`, `litestar-ai-serving` |
| Foundation | `litestar-styleguide` |
| Data | `advanced-alchemy`, `sqlspec`, `msgspec` |
| Server | `litestar-granian` |
| Tasks | `litestar-saq` |
| Frontend | `litestar-vite`, `litestar-inertia`, `litestar-htmx` |
| Integrations | `litestar-mcp`, `litestar-email` |
| Packaging | `litestar-build` |
| Deployment | `litestar-deployment` |
| Testing | `litestar-testing`, `pytest-databases`, `polyfactory` |

Each skill includes a `SKILL.md` plus focused references.

## Project documents

- [Roadmap](docs/roadmap.md) — v0.2 candidates and explicitly-deferred items with graduation triggers.
- [Policy & permissions](docs/policy.md) — per-host allow/ask/deny grammar, managed-settings paths, and the cross-host policy bootstrap pattern. Drop-in template at [templates/managed-settings/claude-code.json](templates/managed-settings/claude-code.json).

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for skill authoring conventions, manifest update rules, and the release process.

## License

MIT — see [`LICENSE`](LICENSE). Matches Litestar upstream.
