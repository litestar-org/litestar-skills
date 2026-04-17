# OpenCode — Install

OpenCode reads SKILL.md from `.opencode/skills/`, `.claude/skills/`, and `.agents/skills/` natively. The recommended install is project-local — drop the `skills/` tree into any of those paths.

## Option 1: Project-local skills (recommended)

```bash
git clone --depth 1 https://github.com/litestar-org/litestar-skills /tmp/litestar-skills
mkdir -p .agents/skills
cp -r /tmp/litestar-skills/skills/* .agents/skills/
```

OpenCode discovers the skills at session start. This path also works for any other host that reads `.agents/skills/` (Claude Code, VS Code/Copilot with `chat.skillsLocations`).

## Option 2: Project-local subagents

To also use the repo's reviewer subagent, copy the OpenCode dialect file:

```bash
mkdir -p .opencode/agents
cp /tmp/litestar-skills/.opencode/agents/litestar-reviewer.md .opencode/agents/
```

## Option 3: Global plugin symlink (optional)

A global plugin entrypoint exists but is a **no-op stub today** — skill discovery still happens through the native paths above. Install only if you want the plugin to appear in OpenCode's extension listing:

```bash
git clone https://github.com/litestar-org/litestar-skills ~/.config/opencode/litestar-skills
ln -sf ~/.config/opencode/litestar-skills/.opencode/plugins/litestar-skills.js \
       ~/.config/opencode/plugins/litestar-skills.js
```

The JS plugin wrapper ships as a stub (`export default {}`); real programmatic registration is on the v0.2+ roadmap and is not required for skill discovery.

## Updating

```bash
# Option 1/2 — re-run the copy
rm -rf .agents/skills && git clone --depth 1 https://github.com/litestar-org/litestar-skills /tmp/litestar-skills \
  && mkdir -p .agents/skills && cp -r /tmp/litestar-skills/skills/* .agents/skills/

# Option 3 — pull in place
cd ~/.config/opencode/litestar-skills && git pull
```

## Verification

```bash
opencode skill list | grep litestar
```

## Tool Mapping

OpenCode uses its native `skill` tool — no special configuration needed. Skills authored in the Anthropic SKILL.md format work unchanged.
