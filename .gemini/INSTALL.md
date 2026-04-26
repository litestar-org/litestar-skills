# Gemini CLI — Install

## One-line install (recommended)

```bash
gemini extensions install https://github.com/litestar-org/litestar-skills --auto-update
```

Gemini auto-indexes the repo into its [extension gallery](https://geminicli.com/extensions/) via the `gemini-cli-extension` GitHub topic.

## What gets loaded

| Path | Loaded by Gemini as |
| --- | --- |
| `skills/<name>/SKILL.md` | Skills (agentskills.io standard) |
| `commands/<prefix>/<command>.toml` | Slash commands |
| `agents/<name>.md` | Subagents (YAML-list tool dialect) |
| `hooks/hooks.json` (auto-discovered) → `hooks/session-start.sh` | SessionStart hook |
| `gemini-extension.json` `excludeTools` | Tool denylist (sudo, rm -rf, curl\|sh, etc.) |
| `GEMINI.md` | Per-host context file (auto-loaded) |

The hook manifest at `hooks/hooks.json` uses Gemini's `${extensionPath}${/}` substitution + a `bun || node || bash` multi-runtime fallback so the SessionStart hook works on any machine.

## Updating

```bash
gemini extensions update litestar-skills
```

## Verifying the install

In a Gemini session, ask: *"What Litestar skills are available?"* — Gemini should list the skills loaded from this extension. Or check the gallery:

```bash
gemini extensions list | grep litestar
```

## Restricting capabilities

Gemini ships a denylist via `excludeTools` in `gemini-extension.json`. The repo ships defenses against:

- All `sudo` invocations (bare, prefixed, semicolon-chained, embedded, piped)
- Destructive `rm -rf` against root, `$HOME`, and `~`
- `curl | sh`, `wget | sh`, and any `*|sh`/`*|bash` install-script piping

See [`docs/policy.md`](../docs/policy.md) for the full pattern list.

**Caveat:** Gemini's `excludeTools` does NOT apply to MCP servers bundled with the extension itself ([gemini-cli #8481](https://github.com/google-gemini/gemini-cli/issues/8481)). Treat it as belt-and-suspenders, not a hard guarantee.

## Troubleshooting

- **`gemini extensions install` fails on a fresh clone** — the manifest is `gemini-extension.json` at the repo root (sibling of `README.md`). If the file isn't present, your checkout may be on a pre-Gemini-support revision.
- **Hook doesn't inject context** — the hook short-circuits silently when no Litestar-ecosystem signals are detected in the cwd. Override with `LITESTAR_SKILLS_HOOK_DISABLE=1` to confirm it's firing. The hook scans `pyproject.toml`, Python imports (capped), and a curated set of file globs (`Dockerfile`, `Chart.yaml`, `*.tf`, etc.).
- **`bun`/`node` not found at hook time** — the multi-runtime fallback ends with `bash` so a system without Bun or Node still gets the hook.
