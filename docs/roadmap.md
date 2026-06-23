# Roadmap

What this repo intentionally hasn't built yet, and what would have to be true for it to start.

Every deferred item below has a **trigger** instead of a date. Triggers are concrete signals — a user request, a missing capability, a specific question we can't answer with what we have today. When a trigger fires, the item moves into a release; until then, it sits here.

For what's already shipped, see the [GitHub Releases](https://github.com/litestar-org/litestar-skills/releases) page — release notes are the canonical record.

## v0.2 candidates

Not yet scheduled. Each requires a specific trigger before planning starts.

### Curated-catalog PRs

- **Status:** Deferred to post-v0.1.
- **Rationale:** Curated catalogs (`anthropics/claude-plugins-official`, `openai/skills`, etc.) require PR review and human-quality descriptions. Submitting before the product has real-world install proof wastes reviewer time and risks rejection.
- **Trigger:** At least **one external user reports a successful v0.1 install**. That signal unlocks the curated-catalog wave.
- **Target catalogs** (in priority order):
  1. `anthropics/claude-plugins-official` — Anthropic-curated visibility.
  2. `openai/skills` — `.curated/` or `.experimental/` subdir depending on reviewer guidance.
  3. `github/awesome-copilot` — broad GitHub discoverability.
  4. `VoltAgent/awesome-agent-skills` — community directory.
  5. Antigravity CLI-focused indexes once stable community directories exist.
  6. `awesome-opencode` — OpenCode-focused index.

## Deferred (with explicit triggers)

Each item has a **Status**, a **Rationale**, a **Trigger**, and — where useful — an **Implementation sketch**.

### Telemetry

- **Status:** Deferred. Default is no telemetry; the installer and plugin stubs do not phone home.
- **Rationale:** Privacy-by-default and scope-creep avoidance. Telemetry adds privacy surface area (what we collect, where it goes, how long we retain), dependency surface area (backend + pipeline + retention ops), and distraction (dashboards become the work). An opt-in flow is required to not be obnoxious, and that flow is non-trivial.
- **Trigger:** A concrete unanswered product question that **cannot** be resolved with GitHub-native signals (stars, forks, issue volume, `gh api .../traffic/clones`, `gh api .../traffic/popular/paths`, skills.sh leaderboard position). Example: "Why does skill X activate often but reference Y is rarely fetched?" — activation-funnel questions need event-level data; GitHub traffic does not expose that.
- **Implementation sketch (if triggered):**
  - Opt-in only. Default `LITESTAR_SKILLS_TELEMETRY=0`; never auto-enable.
  - Anonymous. No user identifiers. Host-CLI version, OS, install outcome, timestamp only.
  - Ship logs, not a live pipeline. Write to `~/.cache/litestar-skills/telemetry.jsonl`; users inspect or send manually via `tools/send-telemetry.sh`.
  - Documented schema in README; explicit privacy disclosure; GDPR-safe defaults.
  - Backend: Cloudflare R2 + Workers or Fly.io; zero-ops is the bar.

### PyPI / npm publishing

- **Status:** Deferred.
- **Rationale:** No runtime Python or JavaScript package currently ships from this repo. Every artifact is `SKILL.md` + references + hooks; agents fetch via host-native mechanisms (`git clone`, `gh` download, `agy plugin install`, or Codex marketplace install). Nothing needs `pip install` or `npm install`.
- **Trigger:** A real MCP server, helper CLI, or bundled runtime artifact ships from this repo. Concrete candidates: `litestar-skills-mcp-docs` (Python), a `litestar-skills scaffold` CLI, or a bundled `pipx install litestar-skills`.
- **Implementation sketch:**
  - **PyPI:** `pyproject.toml` already has hatchling + project metadata. Add `[project.scripts]` entry-point(s) for CLIs; decide package layout (`src/litestar_skills/` PyPI-style). `release.yml` gains `uv build` + `uv publish` via [PyPI Trusted Publishers](https://docs.pypi.org/trusted-publishers/) + GitHub OIDC — no static `PYPI_TOKEN` in secrets. Reference: <https://docs.astral.sh/uv/guides/publish/>.
  - **npm:** Relevant only if JS/TS code ships beyond the current OpenCode plugin entry point, or a VS Code extension. `package.json` already exists; add `files`, `bin`, `publishConfig`. Workflow step: `bun publish` or `npm publish --provenance` with `NPM_TOKEN`.

### Claude Code marketplace auto-add

- **Status:** Partial. `install.sh --claude-settings` (opt-in) whitelists `litestar-org/litestar-skills` in `~/.claude/settings.json`'s `extraKnownMarketplaces`, which means users only need `/plugin install litestar@litestar` inside Claude Code (no separate `/plugin marketplace add` required). Full headless auto-add is impossible today because `/plugin` is a TUI-only interaction.
- **Rationale:** `tools/install.sh` runs outside any Claude Code session; it cannot invoke in-session slash commands.
- **Trigger:** Anthropic ships a `claude plugin marketplace add <repo>` CLI subcommand (or equivalent) callable from outside a session. Less likely alternates: a host-agnostic `agentskills.io`-style config-file protocol, or a new `autoInstallPlugins` settings key that pre-installs rather than only whitelisting.
- **Monitor:** Claude Code [changelog](https://docs.anthropic.com/en/docs/claude-code/release-notes) and the Claude Code Discord `#plugin-dev` channel. When the subcommand ships, `tools/install.sh` gains a one-line invocation alongside the existing Antigravity, Codex, and OpenCode automation, and the README install section collapses from "two-step" to "one-shot".

### Passive-registry automation

- **Status:** Manual. Submissions to third-party registries (claudeskills.info, lobehub, awesome-* lists, the curated catalogs above) are filed by hand.
- **Rationale:** Each passive registry currently requires a different manual flow: web forms (claudeskills.info, lobehub), email (some listings), GitHub PR (curated catalogs). Automating a form-submit site against CAPTCHA is fragile and discouraged. Curated-catalog PRs need human-quality descriptions and screenshots; automation would hurt review quality.
- **Trigger:** 5+ registries provide CLI submission paths. Today only GitHub topic metadata and `gh pr create` (for PR-based catalogs) are scriptable.
- **Implementation sketch (if triggered):** Build a thin wrapper in `tools/submit-registries.sh` dispatching to each registry's CLI; keep the manual fallback for the registries that never get a CLI.

### Enterprise managed-settings pack

- **Status:** Deferred. The per-host policy reference at [`docs/policy.md`](policy.md) covers the building blocks; what's missing is a packaged drop-in for org-wide rollouts.
- **Rationale:** Production-ready org config (`allowManagedPermissionRulesOnly: true`, MCP allowlists, marketplace pinning, Jamf / Group Policy deployment guides) is meaningful work and we haven't seen the demand.
- **Trigger:** A user (internal Litestar team or external) opens an issue describing an enterprise rollout they need covered.

## Curation principles

Rules for keeping this file honest as the project grows:

- **Each deferred item has a trigger, not a date.** No promises about timeline — this repo is community-driven and triggers can take arbitrarily long or never fire at all. A dated roadmap lies to readers.
- **Shipped items belong in [GitHub Releases](https://github.com/litestar-org/litestar-skills/releases), not here.** This file is forward-looking only.
- **No speculative sections.** If an item does not have a concrete trigger written down, it does not belong in §Deferred — keep it out of this file until a trigger can be articulated.
