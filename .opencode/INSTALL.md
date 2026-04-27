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

## Option 3: Global plugin install (recommended for cross-project coverage)

The repo ships a real OpenCode plugin at `.opencode/plugins/litestar.js` that injects project-aware Litestar skill reminders into the session via `experimental.chat.system.transform`. The plugin honors `managedConfig.disabledPlugins` / `allowedPlugins` (org policy wins) and exposes `LITESTAR_SKILLS_PLUGIN_ROOT` to spawned shells via `shell.env`.

```bash
git clone https://github.com/litestar-org/litestar-skills ~/.config/opencode/litestar
ln -sf ~/.config/opencode/litestar/.opencode/plugins/litestar.js \
       ~/.config/opencode/plugins/litestar.js
```

No npm publish yet — install path stays git+symlink. The plugin reuses the same `hooks/lib/detect-env.js` detection library that powers Claude / Codex / Cursor / Gemini hooks, so the reminder text is identical across all five hosts.

## Updating

```bash
# Option 1/2 — re-run the copy
rm -rf .agents/skills && git clone --depth 1 https://github.com/litestar-org/litestar-skills /tmp/litestar-skills \
  && mkdir -p .agents/skills && cp -r /tmp/litestar-skills/skills/* .agents/skills/

# Option 3 — pull in place
cd ~/.config/opencode/litestar && git pull
```

## Verification

```bash
opencode skill list | grep litestar
```

After Option 3, in a Litestar project, the SessionStart system prompt should include a paragraph naming `litestar:litestar` (and any other matched skills like `litestar:sqlspec`).

## Tool Mapping

OpenCode uses its native `skill` tool — no special configuration needed. Skills authored in the Anthropic SKILL.md format work unchanged.

## Disabling via managed config

For Jamf / Kandji / FleetDM org-managed Macs, the plugin honors `ai.opencode.managed` PayloadType:

```json
{
  "managedConfig": {
    "disabledPlugins": ["litestar"]
  }
}
```

Or restrict to an allowlist:

```json
{
  "managedConfig": {
    "allowedPlugins": ["other-org-plugin"]
  }
}
```

The plugin early-returns `{}` when disabled — no skill reminder injection, no env vars exposed.
