---
name: litestar-styleguide
description: "Shared code-style baseline for every skill in this plugin. Use when authoring or reviewing code in a Litestar / Python / TypeScript project — PEP 604 unions, async I/O, Google docstrings, msgspec over Pydantic, ruff / mypy / pyright tooling, pytest conventions, CI/CD rules. Produces: links to language-specific style references consumed by sibling skills via their `Shared Styleguide Baseline` sections. Use when: writing a new skill, reviewing code in this repo or a consumer project, or resolving a style disagreement. Not for framework-specific guidance (see the individual skills: litestar, sqlspec, advanced-alchemy, msgspec, etc.) — this skill is the cross-cutting baseline, not a framework guide."
---

# litestar-styleguide

This is the **shared style baseline** that every other skill in this plugin references. It exists so that cross-cutting rules (PEP 604 unions, async I/O, ruff + mypy + pyright, test file naming, CI/CD conventions) live in exactly one place — and individual skills stay focused on their framework or tool-specific surface.

## What's in here

Each reference covers one slice of the code-style baseline. A sibling skill links to only the files relevant to its language / framework mix.

- [`references/general.md`](references/general.md) — Cross-language principles (simplicity over cleverness, error handling, naming, DRY-when-it-pays)
- [`references/python.md`](references/python.md) — Python conventions (PEP 604 unions, docstrings, imports, ruff / mypy / pyright configuration)
- [`references/litestar.md`](references/litestar.md) — Litestar-specific baseline (guards, DTOs, DI, plugin use)
- [`references/typescript.md`](references/typescript.md) — TypeScript conventions (when paired with a frontend skill)
- [`references/testing.md`](references/testing.md) — Testing conventions (pytest, vitest, fixtures, coverage)
- [`references/ci-cd.md`](references/ci-cd.md) — CI/CD conventions (GitHub Actions, matrix builds, caching)

## How sibling skills consume this

Every `SKILL.md` in this plugin has a `## Shared Styleguide Baseline` section near the bottom. That section links to a subset of these references — only the ones that apply to the skill's language / framework mix. For example:

- `skills/litestar/SKILL.md` links to `general.md` + `python.md` + `litestar.md`
- `skills/litestar-vite/SKILL.md` links to `general.md` + `typescript.md` + `litestar.md`
- `skills/litestar-testing/SKILL.md` links to `general.md` + `testing.md` + `python.md` + `litestar.md`

The sibling skill extends the baseline with its own tool-specific Code Style Rules, Quick Reference, Guardrails, and Validation — but it does not duplicate the baseline. If a convention is generic (type hints, naming, imports), it belongs here.

## When to update this skill

- A rule becomes contentious across two or more sibling skills → pull it into the right baseline reference file here.
- A new language lands (Rust, Mojo, etc.) → add a new `references/<lang>.md` and link from skills that use it.
- A tool is swapped out (e.g., ruff replaces flake8 + black) → update `python.md` once; all sibling skills inherit it.

## Authoring rule for this skill

- Keep references **terse, imperative, authoritative**. No hedging ("you might want to…"). State the preferred choice and the one-line reason.
- Every "never do X" rule has a one-line *why* (perf, runtime introspection, OpenAPI alignment, etc.). No folklore.
- Examples are copy-pasteable and minimal. No pseudo-code.

<workflow>

## Workflow — consuming this baseline

1. Open the sibling skill you are editing (`skills/<name>/SKILL.md`).
2. Look at its `## Shared Styleguide Baseline` section — it already lists a subset of the references here.
3. When adding a rule to the sibling, ask: is it generic (language/tooling) or framework-specific? Generic → land it in the right file under `references/` here. Specific → keep it in the sibling.
4. Cross-link bidirectionally if a rule here is amplified in the sibling.

</workflow>

<guardrails>

## Guardrails

- **No duplication across skills.** A rule lives in exactly one file; sibling skills link to it.
- **No folklore.** Every rule has a one-line justification (perf, runtime introspection, OpenAPI alignment, etc.). Delete rules you cannot justify.
- **Terse and imperative.** Bullets are ≤ 2 sentences. If a topic needs more, split it into its own reference file.
- **Examples are minimal and copy-pasteable.** No pseudo-code; no multi-hundred-line fixtures.

</guardrails>

<validation>

## Validation Checkpoint

- [ ] Every sibling skill's `## Shared Styleguide Baseline` section resolves to files that exist under `references/`
- [ ] No rule is duplicated between two reference files (check via grep when editing)
- [ ] Each "never do X" rule has a one-line `Reason:` explanation
- [ ] New language support lands as a single new `references/<lang>.md` — not scattered into sibling skills

</validation>

<example>

## Example — adding a new rule

A reviewer finds that two sibling skills independently wrote "use `ruff format` not `black`". Instead of leaving duplicates, pull the rule into `references/python.md`:

```markdown
- **Use `ruff format`, never `black`.** Reason: ruff is the single toolchain for
  lint + format; running two formatters produces style drift.
```

Then in each sibling's `SKILL.md`, replace the duplicate with a pointer:

```markdown
## Shared Styleguide Baseline

- [Python](../litestar-styleguide/references/python.md)
```

</example>

## Official References

- <https://peps.python.org/pep-0604/> — PEP 604 union syntax
- <https://docs.astral.sh/ruff/> — ruff linter / formatter
- <https://microsoft.github.io/pyright/> — pyright type checker
- <https://docs.pytest.org/> — pytest
