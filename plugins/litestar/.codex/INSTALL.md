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

Enable `litestar` from the list. The marketplace catalog lives at `.agents/plugins/marketplace.json`; its local `source.path` points at the committed generated package in `plugins/litestar/`.

## Option 2: Local marketplace (for development)

If you have the repo cloned and want Codex to pick up your local changes:

```bash
codex plugin marketplace add /path/to/litestar-skills
```

Codex reads the marketplace at `.agents/plugins/marketplace.json` and loads the generated package under `plugins/litestar/`.

## Custom agents

Codex custom agents live in `.codex/agents/*.toml` (pure TOML; tools inherited from session `config.toml`). The repo ships `litestar-reviewer` — invoke with `$agent litestar-reviewer` inside Codex.

The four host-dialect agent files are generated from canonical YAML sources at `tools/agent-sources/<name>.yaml`. Run `make agents` after editing the source.

## Skill and command names

Codex surfaces installed skills by displayed name. In `$`-trigger Codex surfaces, force the Litestar hub with `$litestar:litestar` and focused skills with `$litestar:<skill-name>` (for example `$litestar:litestar-routing`). Natural-language requests also work.

Codex plugins do not currently expose plugin-defined `/litestar:*` slash commands. Treat the shipped `commands/litestar/*.toml` files as host payload for slash-command-capable harnesses and as canonical prompts the `litestar` skill can follow in Codex.

## Updating

```bash
codex plugin marketplace upgrade litestar
```

To reinstall after a local package change:

```bash
codex plugin remove litestar@litestar
codex plugin add litestar@litestar
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

## Why the generated package layout

Codex CLI 0.125.0+ requires local marketplace `source.path` to:

1. Start with `./`
2. Be a non-empty subdirectory (rejects `./` alone)
3. Contain no `..` traversal

That's why the marketplace points at `./plugins/litestar` instead of the repo root. The directory is a committed generated payload copied from the canonical `.codex-plugin`, `skills`, `commands`, `.codex`, and `hooks` sources. After editing those sources, run:

```bash
make sync-codex-package
```

CI runs `make codex-package-check` through `make lint` so stale package output fails without mutating files.
