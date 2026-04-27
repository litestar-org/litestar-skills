# Codex CLI — Install

> **Codex CLI 0.125+** is required. Earlier versions accept the `source: "./"` marketplace shape but newer versions reject it.

## Option 1: Marketplace install (recommended)

```bash
codex plugin marketplace add litestar-org/litestar-skills
```

Then in a Codex session:

```text
/plugins
```

Enable `litestar` from the list. The plugin manifest lives at `.agents/plugins/plugins/litestar/.codex-plugin/plugin.json`; the marketplace catalog is `.agents/plugins/marketplace.json` at the repo root.

## Option 2: Local marketplace (for development)

If you have the repo cloned and want Codex to pick up your local changes:

```bash
codex plugin marketplace add /path/to/litestar-skills
```

Codex auto-discovers the marketplace at `.agents/plugins/marketplace.json` and the nested plugin under `.agents/plugins/plugins/litestar/`.

## Option 3: User-level clone

```bash
git clone https://github.com/litestar-org/litestar-skills ~/.codex/plugins/litestar
```

Codex auto-discovers plugins under `~/.codex/plugins/`. Provided for environments where `codex plugin marketplace add` is unavailable.

## Custom agents

Codex custom agents live in `.codex/agents/*.toml` (pure TOML; tools inherited from session `config.toml`). The repo ships `litestar-reviewer` — invoke with `$agent litestar-reviewer` inside Codex.

The four host-dialect agent files are generated from canonical YAML sources at `tools/agent-sources/<name>.yaml`. Run `make agents` after editing the source.

## Updating

```bash
codex plugin marketplace upgrade litestar
```

For Option 3:

```bash
cd ~/.codex/plugins/litestar && git pull
```

## Verification

In a Codex session:

```text
$skill list | grep litestar
$agent list | grep litestar-reviewer
```

The SessionStart hook (`hooks/session-start.sh`, dispatched via `hooks/hooks-codex.json`) should inject project-aware Litestar skill reminders into the session context.

## Disabling specific skills

Edit `~/.codex/config.toml`:

```toml
[[skills.config]]
path = "/path/to/skill/SKILL.md"
enabled = false
```

## Why the nested layout

Codex CLI 0.125.0+ requires local marketplace `source.path` to:

1. Start with `./`
2. Be a non-empty subdirectory (rejects `./` alone)
3. Contain no `..` traversal

That's why the plugin lives under `./plugins/litestar` (relative to `.agents/plugins/marketplace.json`) instead of being collocated with the marketplace file.
