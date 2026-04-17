# litestar-skills

> Opinionated, first-party agent skills, plugins, subagents, slash commands, and MCP servers for the **Litestar** framework and its ecosystem — publishable to **every major AI agent and IDE** from a single repo.

`litestar-skills` is a curated collection of agentic-development assets that teach AI coding agents how the Litestar team actually builds software. It covers the Litestar core plus first-party libraries (`sqlspec`, `advanced-alchemy`, `litestar-granian`, `litestar-saq`, `litestar-vite`, `litestar-mcp`, `litestar-email`, `litestar-htmx`, `litestar-asyncpg`, `litestar-oracledb`, and more).

## Status

**v0.0.1 — early access.** Multi-host plumbing, 13 skills, ~14,000 lines of canonical content. Full launch-skill catalog growing.

## Install

### One-shot multi-host installer (recommended)

Installs for every supported CLI it detects on your system. Auto-installs for Gemini CLI, Codex CLI, and OpenCode; prints instructions for Claude Code, Cursor, and VS Code.

```bash
curl -fsSL https://raw.githubusercontent.com/cofin/litestar-skills/main/tools/install.sh | bash
```

Options:

```bash
# Preview without executing
curl -fsSL https://raw.githubusercontent.com/cofin/litestar-skills/main/tools/install.sh | bash -s -- --dry-run

# Install for specific hosts only
curl -fsSL https://raw.githubusercontent.com/cofin/litestar-skills/main/tools/install.sh | bash -s -- --only gemini --only codex

# Also whitelist the Claude Code marketplace in ~/.claude/settings.json
curl -fsSL https://raw.githubusercontent.com/cofin/litestar-skills/main/tools/install.sh | bash -s -- --claude-settings
```

If you'd rather not pipe to `bash`, clone first:

```bash
git clone https://github.com/cofin/litestar-skills
cd litestar-skills
./tools/install.sh --help
```

### Windows (PowerShell 7+ only)

Native install without WSL. Requires PowerShell 7+ and Git for Windows (for hook dispatch).

```powershell
# From a Git for Windows or PowerShell 7 shell:
pwsh -File tools/install.ps1

# Preview:
pwsh -File tools/install.ps1 -DryRun

# Install for specific host(s):
pwsh -File tools/install.ps1 -Only gemini,codex
```

If PowerShell 7+ is not installed: `winget install Microsoft.PowerShell`.
If Git for Windows is not installed: download from <https://git-scm.com/download/win>.

### Per-host install

#### Claude Code

```text
/plugin marketplace add cofin/litestar-skills
/plugin install litestar-skills@litestar-marketplace
```

The `/plugin` commands run **inside** a Claude Code session — the installer can't automate this part. Pass `--claude-settings` to the installer to at least whitelist the repo ahead of time.

#### Gemini CLI

```bash
gemini extensions install https://github.com/cofin/litestar-skills --auto-update
```

Gemini auto-indexes this repo into its [extension gallery](https://geminicli.com/extensions/) via the `gemini-cli-extension` GitHub topic.

#### Codex CLI

User-level (recommended):

```bash
git clone https://github.com/cofin/litestar-skills ~/.codex/plugins/litestar-skills
```

Then inside Codex: `$skill list | grep litestar`. See [`.codex/INSTALL.md`](.codex/INSTALL.md) for project-scoped install.

#### OpenCode

```bash
git clone https://github.com/cofin/litestar-skills ~/.config/opencode/litestar-skills
ln -sf ~/.config/opencode/litestar-skills/.opencode/plugins/litestar-skills.js \
       ~/.config/opencode/plugins/litestar-skills.js
```

OpenCode also reads `.claude/skills/` and `.agents/skills/` natively, so for project-local install just copy the `skills/` tree there. See [`.opencode/INSTALL.md`](.opencode/INSTALL.md).

#### Cursor

```text
Cursor → Settings → Rules → Add Remote Rule → https://github.com/cofin/litestar-skills
```

#### VS Code / GitHub Copilot

```bash
git clone https://github.com/cofin/litestar-skills ~/.copilot/litestar-skills
```

Then in VS Code `settings.json`:

```json
{
  "chat.skillsLocations": {
    "~/.copilot/litestar-skills/skills": true
  }
}
```

## Discovery topics

This repo is tagged with GitHub topics so downstream registries and galleries auto-crawl it:

| Topic | Downstream effect |
|---|---|
| `gemini-cli-extension` | Gemini CLI's [extension gallery](https://geminicli.com/extensions/) auto-indexes tagged repos. |
| `litestar` | Framework discoverability — surfaces in Litestar-ecosystem GitHub searches. |
| `agent-skills` | Generic agent-skills discoverability for Claude Code / Copilot CLI skill indexes. |
| `claude-code-plugin` | Claude Code plugin discoverability (e.g., [claudeskills.info](https://claudeskills.info)). |

Topics are re-applied on every tagged release via `.github/workflows/release.yml`. The operation is idempotent; `gh repo edit --add-topic` is additive and deduplicates.

## Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/cofin/litestar-skills/main/tools/uninstall.sh | bash
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

**Symlink fails on Windows** — run the installer under WSL or Git Bash. Native Windows support is [backlog](https://github.com/cofin/litestar-skills).

**Permission denied on `~/.codex/plugins/`** — do NOT run with `sudo`; the installer refuses root. Ensure your user owns `~/.codex/` and `~/.config/`.

**Gemini says extension already exists** — the installer upgrades automatically. Use `--force` to re-install from scratch.

**Claude Code can't find the marketplace** — re-run with `--claude-settings` to whitelist, or inside Claude Code manually: `/plugin marketplace add cofin/litestar-skills`.

## What's In This Repo

13 skills, 58 reference files, ~14,000 lines of canonical content:

| Category | Skills |
|---|---|
| Core | `litestar` |
| Data | `advanced-alchemy`, `sqlspec`, `msgspec` |
| Server | `litestar-granian` |
| Tasks | `litestar-saq` |
| Frontend | `litestar-vite`, `litestar-inertia`, `litestar-htmx` |
| Integrations | `litestar-mcp`, `litestar-email` |
| Testing | `litestar-testing`, `pytest-databases` |

Each skill includes a `SKILL.md` plus focused references.

## Project documents

- [Launch checklist](docs/launch-checklist.md) — day-of v0.1 release playbook and post-launch verification
- [Roadmap](docs/roadmap.md) — shipped, v0.2 candidates, and explicitly-deferred items with graduation triggers

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for skill authoring conventions, manifest update rules, and the release process.

## License

MIT — see [`LICENSE`](LICENSE). Matches Litestar upstream.
