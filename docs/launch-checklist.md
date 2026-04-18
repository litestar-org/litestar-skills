# v0.1 Launch checklist

Day-of playbook for cutting `v0.1.0` of `litestar-skills`. Walks a maintainer from the pre-tag gate through tag-day release, manual submissions, first-48h verification on a fresh machine, two-week post-launch monitoring, and the rollback procedure if something goes wrong. Keep this file updated after every launch — the items with dates become the launch log.

## Pre-tag gate

Before running `make release`, every box below must be checked:

- [ ] `make check` is green on `main` (ruff, mypy, pyright, markdownlint, oxlint, shellcheck).
- [ ] Every shipped roadmap item is reflected in `docs/roadmap.md` §Shipped, and every in-flight item is either flagged in-progress or removed from the launch blocker list.
- [ ] GitHub Actions has **no failing runs** on `main` in the last 10 pushes (`gh run list --branch main --limit 10`).
- [ ] No open issues labeled `launch-blocker` on `github.com/litestar-org/litestar-skills/issues`.

## Tag-day playbook

Numbered sequence — do not skip steps. Each step produces an artifact that the next step verifies.

1. **Pull `main` clean.** `git checkout main && git pull --ff-only`. Confirm `git status` is empty.
2. **Cut the release locally.** `make release bump=minor` — `bump-my-version` rewrites every tracked manifest, creates the `v0.1.0` commit, and the annotated tag.
3. **Push commit and tag atomically.** `git push origin main --follow-tags`. The tag push triggers `.github/workflows/release.yml`.
4. **Watch the release workflow.** `gh run watch --exit-status` — workflow must end in `success`. If it fails, do NOT re-tag; investigate, commit a fix with `bump=patch`, and re-tag as `v0.1.1`.
5. **Verify the GitHub Release.** `gh release view v0.1.0` — confirm body, assets, and auto-generated release notes are present.
6. **Verify GitHub topics applied.** `gh repo view --json repositoryTopics` — must include `agent-skills`, `claude-code-plugin`, `gemini-cli-extension`, and `litestar`. If any are missing, run `gh repo edit --add-topic <topic>` and re-check.
7. **Verify Gemini extensions gallery crawl.** Gemini indexes the `gemini-cli-extension` topic within ≤24h. Open <https://geminicli.com/extensions/> and search for `litestar-skills`. If absent after 24h, file an issue with Gemini support.
8. **Post to launch channels.** Litestar Discord `#announcements`, Twitter/X, and any maintainer personal channels. Include the GitHub Release URL and a one-line pitch.

## Day-of submissions (manual web forms)

Third-party registries that require a human-filled form or GitHub PR. Do these within 24h of the tag so traffic lines up with the announcement:

- [ ] [claudeskills.info](https://claudeskills.info) — fill the submission form (name, one-line description, GitHub URL, one screenshot).
- [ ] [lobehub.com/skills](https://lobehub.com/skills) — submit via the listing flow; include the four GitHub topics as tags.
- [ ] [skills.sh](https://skills.sh) — **no action required**; skills.sh auto-crawls public GitHub. Verify appearance on the leaderboard within 1 week; if absent by day 7, email their maintainer.

## Verification (first 48h)

Within 48 hours of tag push, reproduce a cold install on a fresh environment. This catches bugs that only surface on machines that have never cloned the repo.

```bash
# On a clean VM (GitHub Codespace, fresh Docker container, or spare laptop):
curl -fsSL https://raw.githubusercontent.com/litestar-org/litestar-skills/main/tools/install.sh | bash

# Open Claude Code, run:  /plugin marketplace add litestar-org/litestar-skills
# Then:                    /plugin install litestar-skills@litestar-marketplace
# Confirm the plugin appears in /plugin list.

# Open Gemini CLI:
gemini extensions list
# Confirm litestar-skills is present with status "installed".

# Open Codex CLI:
$skill list | grep litestar
# Confirm at least one skill appears.
```

Document any install-time failure as a GitHub issue labeled `install-bug` — these block the next patch release.

## Post-launch (first 2 weeks)

Light-touch monitoring. Check once per weekday; log findings in the graduation log of `docs/roadmap.md`.

- [ ] GitHub Issues: scan for install-failure reports (label `install-bug`) and respond within 24h.
- [ ] Repo topics still applied: `gh repo view --json repositoryTopics` — someone with write access could have removed them inadvertently.
- [ ] Gemini extensions gallery still lists the repo: <https://geminicli.com/extensions/>.
- [ ] At least **one external user reports a successful install** — this is the trigger that unlocks the v0.2 curated-catalog PR wave (see `docs/roadmap.md` §v0.2 candidates).
- [ ] `gh api repos/litestar-org/litestar-skills/traffic/clones` shows non-zero clones from sources outside the maintainer's machines.

## Rollback plan

If a critical bug is discovered in `v0.1.0` within the first 48h:

1. Delete the GitHub Release: `gh release delete v0.1.0 --cleanup-tag`.
2. Or, if `--cleanup-tag` is unavailable in your `gh` version, delete the tag explicitly: `git tag -d v0.1.0 && git push origin :refs/tags/v0.1.0`.
3. Investigate the failure; add a regression test (`tests/` or `make validate-skills`).
4. Commit the fix on `main`.
5. Re-release as `v0.1.1` via `make release bump=patch` — never re-use the `v0.1.0` tag; re-using causes caching weirdness in every downstream registry.
6. Notify every channel where `v0.1.0` was announced; briefly explain the defect and the upgrade path.

Prefer re-release to silent deletion: registries have already crawled the original tag, so a visible `v0.1.1` with release notes citing the fix is clearer than a disappearing `v0.1.0`.
