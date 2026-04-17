# Codex CLI — Install

Three install paths.

## Option 1: User-level plugin (recommended)

```bash
git clone https://github.com/litestar-org/litestar-skills ~/.codex/plugins/litestar-skills
```

Codex auto-discovers plugins in `~/.codex/plugins/`. The clone includes `.codex/agents/litestar-reviewer.toml` (pure-TOML custom agent; tools inherited from your session `config.toml`).

## Option 2: Repo-scoped marketplace (team)

For a single project, clone into the repo's `plugins/` directory and register a local marketplace:

```bash
mkdir -p plugins
git clone https://github.com/litestar-org/litestar-skills plugins/litestar-skills
mkdir -p .codex
cat > .codex/marketplace.json <<'EOF'
{
  "name": "litestar-marketplace",
  "description": "The Litestar Marketplace — opinionated first-party skills, plugins, subagents, commands, and MCP servers for Litestar and its ecosystem",
  "plugins": [
    { "name": "litestar-skills", "source": "./plugins/litestar-skills" }
  ]
}
EOF
```

## Option 3: Skills-only via `.agents/skills/`

If you only want the skills (no plugin metadata or custom agent), clone and copy:

```bash
git clone --depth 1 https://github.com/litestar-org/litestar-skills /tmp/litestar-skills
mkdir -p .agents/skills
cp -r /tmp/litestar-skills/skills/* .agents/skills/
```

Codex reads `.agents/skills/` natively at session start.

## Custom agents

Codex custom agents live in `.codex/agents/*.toml` and are discovered automatically when the plugin is installed. The repo ships `litestar-reviewer` — invoke with `$agent litestar-reviewer` inside Codex.

## Updating

```bash
cd ~/.codex/plugins/litestar-skills && git pull
```

## Verification

Inside Codex:

```text
$skill list | grep litestar
$agent list | grep litestar-reviewer
```

## Disabling Specific Skills

Edit `~/.codex/config.toml`:

```toml
[[skills.config]]
path = "/path/to/skill/SKILL.md"
enabled = false
```
