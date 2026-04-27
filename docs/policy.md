# Policy & Permissions Reference

Per-host quick reference for restricting what the `litestar` plugin (and any other plugin) can do. Each host has different enforcement primitives — this page documents what each one supports today and what we ship as opinionated defaults.

> **Asymmetry warning.** Claude Code is the only host with a mature allow/ask/deny grammar plus org-level managed settings. Gemini ships denylist-only via `excludeTools`. OpenCode has a tri-state `permission` block. Cursor and Codex have no public deny grammar — restriction is uninstall-only. Don't expect uniform enforcement across hosts.

---

## Claude Code

**Settings precedence (highest first):**

1. Managed settings (org-deployed JSON file or OS policy — see paths below)
2. CLI flags
3. `.claude/settings.local.json` (per-developer, gitignored)
4. `.claude/settings.json` (project, committed)
5. `~/.claude/settings.json` (user)

**Permission rule grammar** (`permissions.{allow,ask,deny}[]`):

| Rule form | Matches |
| --- | --- |
| `Bash(npm run *)` | `npm run` followed by anything |
| `Bash(curl *)` | any `curl` invocation |
| `Read(./.env)` | reading `.env` in cwd |
| `Read(./secrets/**)` | any file under `./secrets/` |
| `Read(~/.zshrc)` | absolute home path |
| `Edit(./build/*)` | edits inside `./build/` only |
| `WebFetch(domain:github.com)` | fetches scoped to `github.com` |
| `MCP(github)` | calls into the `github` MCP server |
| `Agent(name)` | the named subagent |
| `Skill(name)` | the named skill |
| `Skill(name *)` | skill plus any of its allowed-tool wildcards |

Evaluation order is **deny → ask → allow**, first match wins.

**Example — minimal `.claude/settings.json` (project) that's strict by default but lets the litestar hooks run:**

```json
{
  "permissions": {
    "allow": [
      "Skill(litestar:*)",
      "Bash(make *)",
      "Bash(uv *)",
      "Bash(bun *)"
    ],
    "ask": [
      "Bash(curl *)",
      "Bash(wget *)",
      "Bash(npm install *)"
    ],
    "deny": [
      "Bash(sudo *)",
      "Bash(rm -rf /*)",
      "Bash(rm -rf $HOME*)",
      "Bash(rm -rf ~*)",
      "Bash(curl * | sh)",
      "Bash(curl * | bash)",
      "Bash(wget * | sh)",
      "Bash(wget * | bash)",
      "Read(./.env)",
      "Read(./.env.*)",
      "Read(./secrets/**)"
    ]
  }
}
```

**Managed settings (org-wide, cannot be overridden):**

| OS | Path |
| --- | --- |
| macOS | `/Library/Application Support/ClaudeCode/managed-settings.json` |
| macOS (drop-in) | `/Library/Application Support/ClaudeCode/managed-settings.d/*.json` |
| macOS (MDM) | `com.anthropic.claudecode` plist via Jamf/Kandji/Mosyle/etc. |
| Linux / WSL | `/etc/claude-code/managed-settings.json` |
| Linux / WSL (drop-in) | `/etc/claude-code/managed-settings.d/*.json` |
| Windows | `C:\Program Files\ClaudeCode\managed-settings.json` |
| Windows (Group Policy) | `HKLM\SOFTWARE\Policies\ClaudeCode` or `HKCU\SOFTWARE\Policies\ClaudeCode` |

**Managed-only fields** (cannot be overridden by lower scopes):

- `allowManagedPermissionRulesOnly` — locks the rule set; user can't add their own.
- `allowManagedHooksOnly` — only hooks declared in managed scope run.
- `allowManagedMcpServersOnly` + `allowedMcpServers` / `deniedMcpServers`.
- `strictKnownMarketplaces` + `blockedMarketplaces` — pin which marketplaces can be added.
- `disableSkillShellExecution` — block any shell execution invoked by a skill.
- `pluginTrustMessage` — banner shown to users on plugin install.

A copy-pasteable starting point lives at [`templates/managed-settings/claude-code.json`](../templates/managed-settings/claude-code.json).

**To deny a specific litestar capability for an org:**

```json
{
  "permissions": {
    "deny": [
      "Skill(litestar:litestar-deployment)",
      "Skill(litestar:litestar-build)"
    ]
  },
  "allowManagedPermissionRulesOnly": true
}
```

Run `/status` in a Claude Code session to inspect the active layers.

---

## Gemini CLI

**Mechanism:** denylist via `excludeTools` in `gemini-extension.json`. There is no allow/ask grammar.

**Syntax:** `tool(arg)` — argument is a glob pattern.

**Defaults shipped by the Litestar extension** (`gemini-extension.json`):

```json
{
  "excludeTools": [
    "run_shell_command(sudo)",
    "run_shell_command(sudo *)",
    "run_shell_command(sudo;*)",
    "run_shell_command(* sudo *)",
    "run_shell_command(*|sudo*)",
    "run_shell_command(rm -rf /*)",
    "run_shell_command(rm -rf $HOME*)",
    "run_shell_command(rm -rf ~*)",
    "run_shell_command(curl * | sh)",
    "run_shell_command(curl * | bash)",
    "run_shell_command(wget * | sh)",
    "run_shell_command(wget * | bash)",
    "run_shell_command(*|sh)",
    "run_shell_command(*|bash)"
  ]
}
```

**Caveat (important):** `excludeTools` does NOT apply to MCP servers bundled with the extension itself ([gemini-cli #8481](https://github.com/google-gemini/gemini-cli/issues/8481)). Treat it as belt-and-suspenders, not a hard guarantee.

**To extend for your org:** add additional patterns to your project's own `gemini-extension.json` or to user/workspace settings. There's no public managed-settings file analogous to Claude Code's.

---

## OpenCode

**Mechanism:** tri-state `permission` block in `opencode.json` (`allow`, `ask`, `deny`); per-agent `tools` map; managed-config layer for org enforcement.

**Project-local example** (`opencode.json`):

```json
{
  "permission": {
    "edit": "ask",
    "bash": {
      "*": "ask",
      "make *": "allow",
      "uv *": "allow",
      "bun *": "allow",
      "rm -rf *": "deny",
      "sudo *": "deny",
      "curl * | sh": "deny",
      "curl * | bash": "deny"
    }
  }
}
```

**Per-agent restrictions** (in agent frontmatter):

```yaml
mode: subagent
tools:
  read: true
  grep: true
  glob: true
  bash: false      # this agent cannot run shell commands
  edit: false      # ...or modify files
```

**Managed-config layer:** deployed via `ai.opencode.managed` PayloadType (macOS `.mobileconfig` — Jamf, Kandji, FleetDM). Loaded last; highest precedence. Cannot be overridden.

**The `litestar` OpenCode plugin honors `managedConfig.disabledPlugins` and `managedConfig.allowedPlugins`** — early-returns `{}` if disabled. Org policy wins.

---

## Codex CLI

**Public deny grammar:** none documented as of Codex CLI 0.125. The `interface.capabilities` array on plugin manifests is metadata, not enforcement.

**To restrict `litestar` on Codex:** uninstall the plugin (`codex plugin marketplace remove litestar`) or omit it from your marketplace allowlist. There is no per-plugin tool denylist.

---

## Cursor

**Public deny grammar:** none documented. Cursor relies on its built-in trust model and manual marketplace review.

**To restrict `litestar` on Cursor:** uninstall the plugin via the Cursor command palette (`/remove-plugin`), or — for Team/Enterprise installs — use a private team marketplace with central governance.

---

## Cross-host policy bootstrap pattern

Each host has knobs only the user can flip — there's no plugin-author hook for default permissions outside the per-host manifests. The recommended pattern for project-local policy bootstrapping is an **opt-in `/setup`-style flow** that detects installed hosts and prompts to merge recommended settings.

| Host | Target file | Merge keys |
| --- | --- | --- |
| Claude Code | `.claude/settings.local.json` (per-developer, gitignored) | `permissions.allow`, `permissions.deny` |
| OpenCode | `opencode.json` | `permission`, `instructions` |
| Codex | `~/.codex/config.toml` (global) — **DO NOT auto-write**; recommend the trust prompt instead | n/a |
| Gemini | `.gemini/policies/<name>-overrides.toml`, `.geminiignore` | tool allowlist, ignore allowlist |

**Critical rules for any merge step**:

1. ALWAYS back up to `.bak` before editing.
2. ALWAYS merge — never overwrite user keys.
3. Use `jq` when available; fall back to a Python helper.
4. Prompt opt-in (Yes / Skip), not default-yes-with-undo.
5. Reruns must be idempotent (`unique` on arrays).
6. Never auto-write Codex config — Codex's trust prompt is the right surface.

---

## Enterprise managed-settings pack

A production-ready `docs/enterprise/managed-settings.json` for org-wide rollouts — with `allowManagedPermissionRulesOnly: true`, MCP server allowlists, marketplace pinning, and Jamf / Group Policy deployment guides — is on the roadmap but not yet shipped. If you need it for an enterprise rollout, open an issue describing the scope you need covered and we'll prioritize.
