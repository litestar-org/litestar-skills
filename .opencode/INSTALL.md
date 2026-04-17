# OpenCode — Install

Three install paths depending on your preference.

## Option 1: Global plugin (recommended)

Clone the repo and symlink the plugin entrypoint into OpenCode's plugin directory.

```bash
git clone https://github.com/cofin/litestar-skills ~/.config/opencode/litestar-skills
ln -sf ~/.config/opencode/litestar-skills/.opencode/plugins/litestar-skills.js \
       ~/.config/opencode/plugins/litestar-skills.js
```

OpenCode auto-discovers plugins in `~/.config/opencode/plugins/`.

## Option 2: Project-local skills only

Drop SKILL.md files into one of OpenCode's auto-discovery paths inside your project:

```bash
mkdir -p .agents/skills
git clone --depth 1 https://github.com/cofin/litestar-skills /tmp/litestar-skills
cp -r /tmp/litestar-skills/skills/* .agents/skills/
```

OpenCode reads `.opencode/skills/`, `.claude/skills/`, and `.agents/skills/` natively.

## Option 3: User-level via shared agent path

```bash
git clone https://github.com/cofin/litestar-skills ~/.agents/litestar-skills
ln -sf ~/.agents/litestar-skills/skills/* ~/.agents/skills/
```

## Updating

```bash
cd ~/.config/opencode/litestar-skills && git pull
```

## Verification

```bash
opencode skill list | grep litestar
```

## Tool Mapping

OpenCode uses its native `skill` tool — no special configuration needed. Skills authored in the Anthropic SKILL.md format work unchanged.
