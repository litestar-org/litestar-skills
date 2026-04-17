# Roadmap

Every item deferred from v0.1 has a documented **graduation trigger** — not a date. Items promoted to a release move to the `## Shipped in v<N>` section with the release tag so future maintainers can run archaeology on when and why a feature landed. This file is the durable home for everything the repo intentionally chose not to build yet.

## Shipped in v0.1

Each entry is a topic-area outcome. Items move here when they land; the bullet describes what shipped and what infrastructure it produced.

### Skill content

- **Stack-consistency audit.** Match-Your-Stack principle encoded across every skill; forced-path language removed from 9 files; audit methodology established for future convention sweeps.
- **Serializers and msgspec.** Canonical msgspec patterns shipped; honest-scope section for MessagePack (available, not used in reference apps) set the precedent for "not yet canonical" callouts.
- **Realtime event system.** Full realtime stack landed: `RealtimeEvent` + `RealtimePublisher` pattern names preserved verbatim in code samples, with neutral-domain data shapes.
- **Worker patterns.** Worker 3-branch decision (SAQ, Celery, Dramatiq) documented; `WorkerPlugin` and `TaskService` canonical forms shipped.
- **SQLSpec observability and settings.** PEP 562 lazy config, `StatementObserver`, and 3-provider Dishka integration shipped; cross-skill TODO stubs cleared in the closing pass.
- **AI ADK patterns.** `ai-serving.md` + `vector-search.md` references shipped with `LlmAgent`, `Runner`, and `SQLSpecSessionService` patterns.

### Launch infrastructure

- **Litestar reviewer subagent.** `agents/litestar-reviewer.md` rewritten for Match-Your-Stack; frontmatter validator added; Makefile wired; verification runbook documented.
- **Discovery topics.** Manual GitHub topic pre-apply on the repo, `release.yml` topic-add step, and README discovery documentation.
- **Validation CI and smoke tests.** `tools/validate-skills.py` + `tools/sync-manifests.py`, Makefile wiring, `test.yml` smoke-test job, and local verify path.
- **Windows-native support.** `tools/install.ps1` + `run-hook.cmd` rewrite, `.gitattributes` normalization, `test.yml` Windows matrix, bumpversion addition, and README Windows install section — Windows is now a tier-1 install target.
- **Launch-day checklist and deferred-item docs.** This file plus `docs/launch-checklist.md`; consolidated every deferred item into the durable §Deferred section below with an explicit graduation trigger.

## v0.2 candidates

Not yet scheduled. Each requires a specific trigger before planning starts.

### Curated-catalog PRs

- **Status:** Deferred to post-v0.1.
- **Rationale:** Curated catalogs (`anthropics/claude-plugins-official`, `openai/skills`, etc.) require PR review and human-quality descriptions. Submitting before the product has real-world install proof wastes reviewer time and risks rejection.
- **Trigger:** At least **one external user reports a successful v0.1 install** (tracked in `docs/launch-checklist.md` §Post-launch). That signal unlocks the curated-catalog wave.
- **Target catalogs** (in priority order):
  1. `anthropics/claude-plugins-official` — Anthropic-curated visibility.
  2. `openai/skills` — `.curated/` or `.experimental/` subdir depending on reviewer guidance.
  3. `github/awesome-copilot` — broad GitHub discoverability.
  4. `VoltAgent/awesome-agent-skills` — community directory.
  5. `Piebald-AI/awesome-gemini-cli` — Gemini CLI-focused index.
  6. `awesome-opencode` — OpenCode-focused index.

## Deferred (explicit triggers)

Each item has a **Status**, a **Rationale**, a **Trigger**, and — where useful — an **Implementation sketch**.

### Telemetry

- **Status:** Deferred from v0.1. Default is no telemetry; the installer and plugin stubs do not phone home.
- **Rationale:** Privacy-by-default and scope-creep avoidance. Telemetry adds privacy surface area (what we collect, where it goes, how long we retain), dependency surface area (backend + pipeline + retention ops), and distraction (dashboards become the work). An opt-in flow is required to not be obnoxious, and that flow is non-trivial.
- **Trigger:** A concrete unanswered product question that **cannot** be resolved with GitHub-native signals (stars, forks, issue volume, `gh api .../traffic/clones`, `gh api .../traffic/popular/paths`, Gemini gallery install counter, skills.sh leaderboard position). Example: "Why does skill X activate often but reference Y is rarely fetched?" — activation-funnel questions need event-level data; GitHub traffic does not expose that.
- **Implementation sketch (if triggered):**
  - Opt-in only. Default `LITESTAR_SKILLS_TELEMETRY=0`; never auto-enable.
  - Anonymous. No user identifiers. Host-CLI version, OS, install outcome, timestamp only.
  - Ship logs, not a live pipeline. Write to `~/.cache/litestar-skills/telemetry.jsonl`; users inspect or send manually via `tools/send-telemetry.sh`.
  - Documented schema in README; explicit privacy disclosure; GDPR-safe defaults.
  - Backend: Cloudflare R2 + Workers or Fly.io; zero-ops is the bar.

### PyPI / npm publishing

- **Status:** Deferred from v0.1.
- **Rationale:** No runtime Python or JavaScript package currently ships from this repo. Every artifact is `SKILL.md` + references + hooks; agents fetch via host-native mechanisms (`git clone`, `gh` download, `gemini extensions install`). Nothing needs `pip install` or `npm install`.
- **Trigger:** A real MCP server, helper CLI, or bundled runtime artifact ships from this repo. Concrete candidates: `litestar-skills-mcp-docs` (Python), a `litestar-skills scaffold` CLI, or a bundled `pipx install litestar-skills`.
- **Implementation sketch:**
  - **PyPI:** `pyproject.toml` already has hatchling + project metadata. Add `[project.scripts]` entry-point(s) for CLIs; decide package layout (`src/litestar_skills/` PyPI-style). `release.yml` gains `uv build` + `uv publish` via [PyPI Trusted Publishers](https://docs.pypi.org/trusted-publishers/) + GitHub OIDC — no static `PYPI_TOKEN` in secrets. Reference: <https://docs.astral.sh/uv/guides/publish/>.
  - **npm:** Relevant only if JS/TS code ships (real OpenCode plugin beyond the current `export default {}` stub, or a VS Code extension). `package.json` already exists; add `files`, `bin`, `publishConfig`. Workflow step: `bun publish` or `npm publish --provenance` with `NPM_TOKEN`.

### Claude Code marketplace auto-add

- **Status:** Partial. `install.sh --claude-settings` (opt-in) whitelists `litestar-org/litestar-skills` in `~/.claude/settings.json`'s `extraKnownMarketplaces`, which means users only need `/plugin install litestar-skills@litestar-marketplace` inside Claude Code (no separate `/plugin marketplace add` required). Full headless auto-add is impossible today because `/plugin` is a TUI-only interaction.
- **Rationale:** `tools/install.sh` runs outside any Claude Code session; it cannot invoke in-session slash commands.
- **Trigger:** Anthropic ships a `claude plugin marketplace add <repo>` CLI subcommand (or equivalent) callable from outside a session. Less likely alternates: a host-agnostic `agentskills.io`-style config-file protocol, or a new `autoInstallPlugins` settings key that pre-installs rather than only whitelisting.
- **Monitor:** Claude Code [changelog](https://docs.anthropic.com/en/docs/claude-code/release-notes) and the Claude Code Discord `#plugin-dev` channel. When the subcommand ships, `tools/install.sh` gains a one-line invocation alongside the Gemini path and README install section collapses from "two-step" to "one-shot".

### Passive-registry automation

- **Status:** Manual at v0.1 launch + curated-catalog PR wave post-launch (see §v0.2 candidates). Day-of manual submissions live in `docs/launch-checklist.md` §Day-of submissions.
- **Rationale:** Each passive registry currently requires a different manual flow: web forms (claudeskills.info, lobehub), email (some listings), GitHub PR (curated catalogs). Automating a form-submit site against CAPTCHA is fragile and discouraged. Curated-catalog PRs need human-quality descriptions and screenshots; automation would hurt review quality.
- **Trigger:** 5+ registries provide CLI submission paths. Today only GitHub topic (for Gemini auto-crawl) and `gh pr create` (for PR-based catalogs) are scriptable.
- **Implementation sketch (if triggered):** Build a thin wrapper in `tools/submit-registries.sh` dispatching to each registry's CLI; keep the manual form fallback in `docs/launch-checklist.md` for the registries that never get a CLI.

## Windows-native support — shipped in v0.1

Windows-native install was originally deferred from v0.1 on the grounds that real support (PowerShell installer, symlink-free plugin layout, `cmd.exe` compatibility) was a meaningful chunk of work and v0.1 users were projected to be overwhelmingly macOS/Linux. The deferral was revisited late in the launch-readiness pass and **shipped** instead: `tools/install.ps1` mirrors `install.sh`, `hooks/run-hook.cmd` is a real `cmd.exe` dispatcher, symlinks are replaced with file copies for OpenCode's plugin directory, `.gitattributes` enforces `eol=lf` to prevent CRLF corruption of shell scripts, and CI adds a `windows-latest` matrix entry. Windows is a tier-1 install target as of v0.1.

## Curation principles

Rules for keeping this file honest as the project grows:

- **Each deferred item has a trigger, not a date.** No promises about timeline — this repo is community-driven and triggers can take arbitrarily long or never fire at all. A dated roadmap lies to readers.
- **Each shipped item moves to `## Shipped in v<N>` with the release tag.** Never delete entries from the deferred section silently; graduation into a Shipped section is the visible audit trail.
- **No speculative sections.** If an item does not have a concrete trigger written down, it does not belong in `## Deferred` — keep it out of this file until a trigger can be articulated.
- **Quarterly review recommended.** Re-read this file every quarter; confirm triggers are still relevant and statuses have not drifted. Items that move between sections leave their audit trail in this file (deferred entries gain a "shipped in v<N>" line; shipped entries cite the chapter or PR that delivered them).
- **Link, don't duplicate.** `docs/launch-checklist.md` owns the day-of playbook; this file owns forward-looking scope. Cross-link when sections overlap (e.g., §Passive-registry automation → checklist §Day-of submissions).
