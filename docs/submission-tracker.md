# Registry Submission Tracker

Status of submissions to public registries / catalogs / awesome-lists. Update this file when filing or hearing back. Keep `Status` in: `pending`, `filed`, `under-review`, `accepted`, `rejected`, `blocked`.

> **Naming convention.** `litestar-skills` is the GitHub repo and the npm package name (when we publish). Marketplaces refer to the bundled artifact as `litestar-marketplace`. Plugin name in manifests is `litestar-skills`.

---

## Phase 1 — Zero gatekeeper

These ship the moment we tag v0.2 — no review, no waiting.

| Registry | Mechanism | Status | Filed | URL | Notes |
| --- | --- | --- | --- | --- | --- |
| GitHub topic `gemini-cli-extension` | Auto-applied by `release.yml` on tag | filed | (release.yml) | <https://geminicli.com/extensions/> | Crawled into Gemini gallery within ~24h of first tag. |
| GitHub topic `agent-skills` | Auto-applied by `release.yml` | filed | (release.yml) | — | Aids generic skill-bundle discoverability. |
| GitHub topic `claude-code-plugin` | Auto-applied by `release.yml` | filed | (release.yml) | <https://github.com/topics/claude-code-plugin> | Anthropic and community crawlers index this topic. |
| GitHub topic `litestar` | Auto-applied by `release.yml` | filed | (release.yml) | <https://github.com/topics/litestar> | Discoverability inside the Litestar org. |
| skills.sh (Vercel) | Install-volume ranking via `npx skills add` | filed | 2026-04-25 | <https://skills.sh> | No submission flow — ranking is install-count. README documents the `npx skills add litestar-org/litestar-skills` command. |
| awesome-litestar PR | PR adding entry under "AI tooling / Agent skills" | pending | — | <https://github.com/litestar-org/awesome-litestar> | Self-merge as Litestar-org member. |

---

## Phase 2 — Form / PR submissions

Filed within 2 weeks of v0.2 tag. Reviewed asynchronously by maintainers.

| Registry | Mechanism | Status | Filed | URL | Notes |
| --- | --- | --- | --- | --- | --- |
| Anthropic Claude Code community directory | Web form | pending | — | <https://clau.de/plugin-directory-submission> | Auto-security-scan + Anthropic approval; community/curated plugin dirs are read-only mirrors (PRs auto-closed). |
| OpenAI Codex official skills | PR to repo | pending | — | <https://github.com/openai/skills> | Add an entry under `.curated/` or `.experimental/`. Repo's `CONTRIBUTING.md` requires conformant SKILL.md format (we already do). |
| awesome-claude-code | PR | pending | — | <https://github.com/hesreallyhim/awesome-claude-code> | Add entry under "Skills" or "Plugins". |
| awesome-claude-skills (travisvn) | PR | pending | — | <https://github.com/travisvn/awesome-claude-skills> | Litestar/Python section if available. |
| awesome-claude-skills (ComposioHQ) | PR | pending | — | <https://github.com/ComposioHQ/awesome-claude-skills> | Same — different curator. |
| awesome-claude-plugins | PR | pending | — | <https://github.com/ComposioHQ/awesome-claude-plugins> | Plugin (not just skill) entry. |
| awesome-gemini-cli-extensions | PR | pending | — | <https://github.com/Piebald-AI/awesome-gemini-cli-extensions> | Backend / Python framework section. |
| awesome-opencode | PR | pending | — | <https://github.com/awesome-opencode/awesome-opencode> | Add under appropriate category. |

---

## Phase 3 — Async / blocked

Tracked but not actionable until a precondition resolves.

| Registry | Blocker / trigger | Status | Notes |
| --- | --- | --- | --- |
| Cursor marketplace | Public PR/manifest submission flow does not exist as of 2026-04. Submission is gated through Cursor staff via email. | blocked | Email `plugins@cursor.com` once we want public listing. Watch [cursor forum #156274](https://forum.cursor.com/t/cursor-plugin-submit-as-company-not-individual/156274) for the public-flow opening. |
| MCP Registry (registry.modelcontextprotocol.io) | We don't ship an MCP server yet (`mcp-servers/` is empty). | blocked | Submit via `mcp-publisher` CLI when the first MCP server ships. One entry per server. |
| npm publish (`@litestar/opencode-plugin`) | Maintainer bandwidth + decision on package layout. | blocked | Currently OpenCode plugin installs via git+symlink (see `.opencode/INSTALL.md`). Trigger: someone on the team owns the npm release process. |

---

## Submission templates

### awesome-litestar PR template

```markdown
### AI tooling / Agent skills

- [`litestar-skills`](https://github.com/litestar-org/litestar-skills) — Opinionated first-party agent skills, plugins, subagents, slash commands, and MCP servers for Litestar and its ecosystem (sqlspec, advanced-alchemy, msgspec, granian, saq, vite, mcp). Ships across Claude Code, Codex CLI, Cursor, Gemini CLI, and OpenCode.
```

### Generic awesome-list entry template

```markdown
- [`litestar-skills`](https://github.com/litestar-org/litestar-skills) — First-party agent skills for the Litestar Python framework. Multi-host (Claude Code, Codex, Cursor, Gemini, OpenCode). Ships skills, slash commands, subagents, and SessionStart hooks that inject project-aware context.
```

### Anthropic community-directory submission

Required fields per the form (capture before filing):

- Plugin name: `litestar-skills`
- Marketplace name: `litestar-marketplace`
- Source: `litestar-org/litestar-skills` (GitHub)
- Description: see plugin.json description
- Category: Development
- License: MIT
- Author: Litestar org / Cody Fincher <cofin@litestar.dev>
- Validation evidence: paste output of `claude plugin tag .claude-plugin --dry-run --force`

---

## Update protocol

When filing a submission:

1. Set `Status: filed`, fill in `Filed:` date.
2. Paste the PR / form-confirmation URL.
3. On approval: `Status: accepted` + commit the registry's badge / link to README if applicable.
4. On rejection: `Status: rejected` + note the reason in the Notes column.

Do not re-submit the same registry while `Status: filed` or `under-review`.
