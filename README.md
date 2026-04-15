# litestar-skills

> Opinionated, first-party agent skills, plugins, subagents, slash commands, and MCP servers for the **Litestar** framework and its ecosystem — publishable to **every major AI agent and IDE** from a single repo.

`litestar-skills` is a curated collection of agentic-development assets that teach AI coding agents how the Litestar team actually builds software. It covers the Litestar core plus first-party libraries (`sqlspec`, `advanced-alchemy`, `litestar-granian`, `litestar-saq`, `litestar-vite`, `litestar-mcp`, `litestar-email`, `litestar-asyncpg`, `litestar-oracledb`, and more).

## Status

**v0.0.1 — scaffold only.** Multi-host plumbing, manifests, and tooling in place. Skill content lands in v0.2+.

## Install

<!-- finalized in Saga 6 — commands below are placeholders -->

### Claude Code

```bash
# Add the marketplace
/plugin marketplace add cofin/litestar-skills
/plugin install litestar-skills@litestar-marketplace
```

### Gemini CLI

```bash
gemini extensions install https://github.com/cofin/litestar-skills --auto-update
```

### Codex CLI

```bash
# Repo-local: clone into plugins/ and add .agents/plugins/marketplace.json
# User-level: clone to ~/.codex/plugins/litestar-skills
# See .codex/INSTALL.md for full instructions
```

### Cursor

```text
Settings → Rules → Add Remote Rule → https://github.com/cofin/litestar-skills
```

### OpenCode

```bash
# Clone + symlink .opencode/plugins/litestar-skills.js
# See .opencode/INSTALL.md
```

### VS Code / GitHub Copilot

```bash
# Clone anywhere, then add the path to chat.skillsLocations in VS Code settings
git clone https://github.com/cofin/litestar-skills ~/.copilot/litestar-skills
```

### One-shot multi-host installer

```bash
curl -fsSL https://raw.githubusercontent.com/cofin/litestar-skills/main/tools/install.sh | bash
```

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for skill authoring conventions, manifest update rules, and the release process.

## License

MIT — see [`LICENSE`](LICENSE). Matches Litestar upstream.
