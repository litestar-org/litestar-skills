# Claude Code — Install

## One-line install (recommended)

Inside a Claude Code session:

```text
/plugin marketplace add litestar-org/litestar-skills
/plugin install litestar@litestar
```

The `/plugin` commands run **inside** Claude Code — they cannot be automated from a shell. Claude prompts for any `userConfig` values on first install (none today), then enables the plugin.

## What gets loaded

| Path | Loaded by Claude as |
| --- | --- |
| `skills/<name>/SKILL.md` | Skills (description-based auto-activation; manual trigger `/litestar:<name>`) |
| `commands/<prefix>/<command>.toml` | Slash commands (e.g. `/litestar:new-app`) |
| `.claude-plugin/agents/<name>.md` | Subagents (PascalCase tool list dialect) |
| `hooks/hooks.json` → `hooks/session-start.sh` | SessionStart hook injecting Litestar skill reminders |

## Project-local install (less common)

If you want the plugin scoped to one project rather than your user directory:

```bash
git clone https://github.com/litestar-org/litestar-skills .claude-plugin-local
```

Then in `.claude/settings.json`:

```json
{
  "plugins": [".claude-plugin-local"]
}
```

Most users should prefer the marketplace install — Claude handles updates, version pinning, and `userConfig` migration for you.

## Updating

```text
/plugin marketplace update litestar
/plugin update litestar@litestar
```

## Verifying the install

In a Claude Code session:

```text
/status
```

Should show `litestar` under enabled plugins. Open a Litestar project (one with `litestar` in `pyproject.toml`) and a fresh session — the SessionStart hook injects a context paragraph naming `litestar:litestar` (plus any other detected skills). To force a plugin skill manually, use its namespaced slash command such as `/litestar:litestar-routing`.

## Restricting capabilities

Claude Code is the only host with a mature allow/ask/deny grammar. See [`docs/policy.md`](../docs/policy.md) for per-rule syntax and managed-settings paths. A drop-in template for org-managed installs lives at [`templates/managed-settings/claude-code.json`](../templates/managed-settings/claude-code.json).

To deny a specific litestar skill:

```json
{
  "permissions": {
    "deny": ["Skill(litestar:litestar-deployment)"]
  }
}
```

## Troubleshooting

- **`Unrecognized key: "displayName"`** — your local clone is on a stale revision. Pull main; root-level `displayName` was removed (it's only valid inside marketplace.json plugin entries, not in plugin.json).
- **Hook doesn't inject context** — ensure the session was started in a directory containing `pyproject.toml`. The hook short-circuits silently when no Litestar-ecosystem signals are detected. Override with `LITESTAR_SKILLS_HOOK_DISABLE=1` to confirm the hook is firing.
- **`/status` doesn't show the plugin** — `/plugin marketplace add` and `/plugin install` are separate steps. Run both.
