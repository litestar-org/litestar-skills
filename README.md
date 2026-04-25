# litestar-skills

> Opinionated, first-party agent skills, plugins, subagents, slash commands, and MCP servers for the **Litestar** framework and its ecosystem — publishable to **every major AI agent and IDE** from a single repo.

`litestar-skills` is a curated collection of agentic-development assets that teach AI coding agents how the Litestar team actually builds software. It covers the Litestar core plus first-party libraries (`sqlspec`, `advanced-alchemy`, `litestar-granian`, `litestar-saq`, `litestar-vite`, `litestar-mcp`, `litestar-email`, `litestar-htmx`, `litestar-asyncpg`, `litestar-oracledb`, and more).

## Status

**v0.1.2 — early access.** Multi-host plumbing, 16 skills, ~22,800 lines of canonical content. Full launch-skill catalog growing.

## Support Tiers

Each host falls into one of three tiers:

- **First-class** — the repo ships maintained host-specific artifacts and install guidance. Currently: Claude Code, Gemini CLI, Codex CLI, OpenCode.
- **Compatible bundle** — the host consumes standard manifests or generic skill-discovery paths. Currently: Cursor, VS Code/Copilot, OpenClaw.
- **Free ride** — the host discovers generic Agent Skills without a dedicated integration. Currently: Google Antigravity.

## Install

Pick your host and run the one command below. If you use several agents, skip to the [multi-host installer](#one-shot-multi-host-installer).

### Claude Code

```text
/plugin marketplace add litestar-org/litestar-skills
/plugin install litestar-skills@litestar-marketplace
```

The `/plugin` commands run **inside** a Claude Code session — the installer can't automate this part.

### Gemini CLI

```bash
gemini extensions install https://github.com/litestar-org/litestar-skills --auto-update
```

Gemini auto-indexes this repo into its [extension gallery](https://geminicli.com/extensions/) via the `gemini-cli-extension` GitHub topic.

### Codex CLI

```bash
git clone https://github.com/litestar-org/litestar-skills ~/.codex/plugins/litestar-skills
```

Codex auto-discovers plugins under `~/.codex/plugins/`. Ships `.codex/agents/litestar-reviewer.toml` (pure TOML, tools inherited from session `config.toml`). Verify with `$skill list | grep litestar`. See [`.codex/INSTALL.md`](.codex/INSTALL.md) for project-scoped marketplace install.

### OpenCode

OpenCode reads `.opencode/skills/`, `.claude/skills/`, and `.agents/skills/` natively — the recommended install is project-local:

```bash
git clone --depth 1 https://github.com/litestar-org/litestar-skills /tmp/litestar-skills
mkdir -p .agents/skills
cp -r /tmp/litestar-skills/skills/* .agents/skills/
```

A global-plugin variant exists for users who want cross-project coverage, but the JS plugin entrypoint is a no-op stub today — skill discovery happens through the paths above either way. See [`.opencode/INSTALL.md`](.opencode/INSTALL.md).

### Google Antigravity

Antigravity reads Agent Skills from `.agent/skills/` (**singular** `.agent`, note the naming collision with the plural `.agents/skills/` used by Claude Code / OpenCode / VS Code) or from `~/.gemini/antigravity/skills/` globally. Since this repo ships the plural form, the recommended workspace-scope install is a symlink:

```bash
cd your-project
git clone --depth 1 https://github.com/litestar-org/litestar-skills /tmp/litestar-skills
mkdir -p .agents/skills
cp -r /tmp/litestar-skills/skills/* .agents/skills/
ln -s .agents .agent       # community workaround — not a Google-blessed integration
```

For global installs across all workspaces:

```bash
mkdir -p ~/.gemini/antigravity/skills
cp -r /tmp/litestar-skills/skills/* ~/.gemini/antigravity/skills/
```

See [Antigravity Skills docs](https://antigravity.google/docs/skills). The installer's `--antigravity-symlink` flag (below) automates the workspace symlink when you already have `.agents/skills/` present.

### OpenClaw

OpenClaw reads the generic Agent Skills tree; no OpenClaw-specific manifest is needed:

```bash
git clone --depth 1 https://github.com/litestar-org/litestar-skills /tmp/litestar-skills
mkdir -p .agents/skills
cp -r /tmp/litestar-skills/skills/* .agents/skills/
```

Compatible-bundle tier — the repo does not promise dedicated OpenClaw wrapper support, but the generic skills work unmodified.

### Cursor

```text
Cursor → Settings → Rules → Add Remote Rule → https://github.com/litestar-org/litestar-skills
```

### VS Code / GitHub Copilot

```bash
git clone https://github.com/litestar-org/litestar-skills ~/.copilot/litestar-skills
```

Then in VS Code `settings.json`:

```json
{
  "chat.skillsLocations": {
    "~/.copilot/litestar-skills/skills": true
  }
}
```

### One-shot multi-host installer

Installs for every supported CLI detected on your system. Auto-installs for Gemini CLI, Codex CLI, and OpenCode; prints instructions for Claude Code, Cursor, and VS Code.

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
curl -fsSL https://raw.githubusercontent.com/litestar-org/litestar-skills/main/tools/install.sh | bash -s -- --only gemini --only codex

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
pwsh -File tools/install.ps1 -Only gemini,codex
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

# Gemini CLI
gemini mcp add -t http -H "X-Goog-Api-Key: YOUR_API_KEY" \
  google-developer-knowledge \
  https://developerknowledge.googleapis.com/mcp --scope user
```

Generate the API key at `https://console.cloud.google.com/apis/credentials` and restrict it to the Developer Knowledge API. Full reference: [`skills/litestar-styleguide/references/google-developer-knowledge-mcp.md`](skills/litestar-styleguide/references/google-developer-knowledge-mcp.md).

## Discovery topics

This repo is tagged with GitHub topics so downstream registries and galleries auto-crawl it:

| Topic | Downstream effect |
| --- | --- |
| `gemini-cli-extension` | Gemini CLI's [extension gallery](https://geminicli.com/extensions/) auto-indexes tagged repos. |
| `litestar` | Framework discoverability — surfaces in Litestar-ecosystem GitHub searches. |
| `agent-skills` | Generic agent-skills discoverability for Claude Code / Copilot CLI skill indexes. |
| `claude-code-plugin` | Claude Code plugin discoverability (e.g., [claudeskills.info](https://claudeskills.info)). |

Topics are re-applied on every tagged release via `.github/workflows/release.yml`. The operation is idempotent; `gh repo edit --add-topic` is additive and deduplicates.

## Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/litestar-org/litestar-skills/main/tools/uninstall.sh | bash
```

Or from a clone: `./tools/uninstall.sh --help`. Same `--only`, `--skip`, `--dry-run`, `--force`, `--claude-settings` flags as the installer.

Per-host uninstall:

- **Claude Code**: `/plugin uninstall litestar-skills` inside Claude Code
- **Gemini CLI**: `gemini extensions uninstall litestar-skills`
- **Codex CLI**: `rm -rf ~/.codex/plugins/litestar-skills`
- **OpenCode**: `rm ~/.config/opencode/plugins/litestar-skills.js && rm -rf ~/.config/opencode/litestar-skills`
- **Cursor**: remove the Remote Rule from Settings → Rules
- **VS Code**: remove the `chat.skillsLocations` entry + delete the clone

## Troubleshooting

**"No supported CLIs detected"** — none of `claude`, `gemini`, `codex`, `opencode`, `cursor`, or `code` are on `$PATH`. Install at least one and re-run.

**Symlink fails on Windows** — run the installer under WSL or Git Bash. Native Windows support is [backlog](https://github.com/litestar-org/litestar-skills).

**Permission denied on `~/.codex/plugins/`** — do NOT run with `sudo`; the installer refuses root. Ensure your user owns `~/.codex/` and `~/.config/`.

**Gemini says extension already exists** — the installer upgrades automatically. Use `--force` to re-install from scratch.

**Claude Code can't find the marketplace** — re-run with `--claude-settings` to whitelist, or inside Claude Code manually: `/plugin marketplace add litestar-org/litestar-skills`.

## What's In This Repo

16 skills, 85 reference files, ~22,800 lines of canonical content:

| Category | Skills |
| --- | --- |
| Core | `litestar` |
| Foundation | `litestar-styleguide` |
| Data | `advanced-alchemy`, `sqlspec`, `msgspec` |
| Server | `litestar-granian` |
| Tasks | `litestar-saq` |
| Frontend | `litestar-vite`, `litestar-inertia`, `litestar-htmx` |
| Integrations | `litestar-mcp`, `litestar-email` |
| Packaging | `litestar-build` |
| Deployment | `litestar-deployment` |
| Testing | `litestar-testing`, `pytest-databases` |

Each skill includes a `SKILL.md` plus focused references.

## Project documents

- [Launch checklist](docs/launch-checklist.md) — day-of v0.1 release playbook and post-launch verification
- [Roadmap](docs/roadmap.md) — shipped, v0.2 candidates, and explicitly-deferred items with graduation triggers
- [Policy & permissions](docs/policy.md) — per-host allow/ask/deny grammar, managed-settings paths, and the cross-host policy bootstrap pattern. Sample managed config at [docs/managed-settings-example.json](docs/managed-settings-example.json).

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for skill authoring conventions, manifest update rules, and the release process.

## License

MIT — see [`LICENSE`](LICENSE). Matches Litestar upstream.
