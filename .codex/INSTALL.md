# Codex CLI — Install

Three install paths.

## Option 1: User-level plugin (recommended)

```bash
git clone https://github.com/cofin/litestar-skills ~/.codex/plugins/litestar-skills
```

Codex auto-discovers plugins in `~/.codex/plugins/`.

## Option 2: Repo-scoped (team)

For a single project, clone into the repo's `plugins/` directory and create a marketplace entry:

```bash
mkdir -p plugins
git clone https://github.com/cofin/litestar-skills plugins/litestar-skills
mkdir -p .agents/plugins
cat > .agents/plugins/marketplace.json <<'EOF'
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

If you only want the skills (no plugin metadata), clone and symlink:

```bash
git clone --depth 1 https://github.com/cofin/litestar-skills /tmp/litestar-skills
mkdir -p .agents/skills
cp -r /tmp/litestar-skills/skills/* .agents/skills/
```

Codex reads `.agents/skills/` natively.

## Updating

```bash
cd ~/.codex/plugins/litestar-skills && git pull
```

## Verification

Inside Codex:

```text
$skill list | grep litestar
```

## Disabling Specific Skills

Edit `~/.codex/config.toml`:

```toml
[[skills.config]]
path = "/path/to/skill/SKILL.md"
enabled = false
```
