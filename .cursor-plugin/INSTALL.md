# Cursor — Install

## In-editor install

Inside Cursor:

```text
/add-plugin
```

Then search for `litestar` (once the plugin is approved on the Cursor marketplace — submission is pending; see [docs/roadmap.md](../docs/roadmap.md)).

## Local-development install

Until the plugin lands on the Cursor marketplace, install it locally:

```bash
mkdir -p ~/.cursor/plugins/local
ln -s "$(pwd)" ~/.cursor/plugins/local/litestar
```

Then restart Cursor. The plugin manifest at `.cursor-plugin/plugin.json` is auto-discovered.

## What gets loaded

| Path | Loaded by Cursor as |
| --- | --- |
| `skills/<name>/SKILL.md` | Skills (agentskills.io standard, adopted in Cursor 2.4+) |
| `commands/<prefix>/<command>.toml` | Slash commands |
| `hooks/hooks-cursor.json` → `hooks/session-start.sh` | SessionStart hook |

## Updating

If installed via the local symlink, just `git pull` in the cloned directory:

```bash
cd ~/.cursor/plugins/local/litestar && git pull
```

## Restricting capabilities

Cursor has no documented public deny grammar today. Restriction options:

- Uninstall via `/remove-plugin`
- Team / Enterprise plans support private team marketplaces with central governance — talk to your Cursor admin

See [`docs/policy.md`](../docs/policy.md) for the full per-host reference.

## Troubleshooting

- **Plugin not discovered** — ensure the symlink target points at the repo root (the directory containing `.cursor-plugin/plugin.json`), not at `.cursor-plugin/` itself.
- **Hook doesn't fire** — Cursor's SessionStart hook reads `./hooks/hooks-cursor.json`; ensure the `hooks` field in `.cursor-plugin/plugin.json` is present (it is, as of v0.2).
