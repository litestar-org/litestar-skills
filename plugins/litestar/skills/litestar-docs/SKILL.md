---
name: litestar-docs
description: "Auto-activate for zensical.toml, mkdocstrings, Griffe, docs/conf.py, Shibuya, objects.inv, llms.txt, or API reference docs. Not for OpenAPI route schemas."
---

# litestar-docs

Portfolio-wide documentation architecture for `litestar-org` and `cofin` repositories: **Zensical Free** (`zensical >= 0.0.71`, 100% MIT open source) + **`mkdocstrings-python` (Griffe static AST)** + **`mkdocstrings-typescript` (TypeDoc)** + first-party build gates (`tools/docs/generate_cli_docs.py`, `tools/docs/postbuild.py`, `tools/docs/verify_docs_artifacts.py`, `tools/docs/scan_public_docstrings.py`).

## Portfolio Stack Matrix

| Repository Category | Representative Packages | Documentation Stack |
| --- | --- | --- |
| Core Python frameworks & data libraries | `litestar`, `sqlspec`, `advanced-alchemy`, `polyfactory`, `pytest-databases` | `zensical` + `mkdocstrings-python` (`enable_inventory = true` for `objects.inv`) + `tools/docs/generate_cli_docs.py` + `tools/docs/postbuild.py` |
| First-party Python Litestar plugins | `litestar-granian`, `litestar-saq`, `litestar-htmx`, `litestar-email`, `litestar-queues`, `litestar-security`, `litestar-autowire` | Single `zensical.toml` + `mkdocstrings-python` cross-linking `litestar` and `sqlspec` `objects.inv` inventories |
| Polyglot Python + TypeScript | `litestar-vite`, `litestar-mcp`, `litestar-fullstack` | `zensical` + `mkdocstrings-python` + `mkdocstrings-typescript` in one unified navigation and search index |
| Rust + PyO3 (`.pyi` stubs) + C++/SQL | `vertebra`, `fast-query-parsers`, `bunfun`, `duckdb-oracle`, `pg_conduit` | `zensical` + Griffe `.pyi` stub parsing (`find_stubs_package = true`, zero Cargo compile in docs CI) + `/rustdoc/` mount |
| Markdown-native agent toolkits & demos | `litestar-skills`, `oracledb-vertexai-demo`, `postgres-vertexai-demo` | Native Markdown `zensical.toml` with `pymdownx.snippets` (`check_paths = true`) |

## Core Rules

- **Strictly Zensical Free (MIT open source).** Reason: `zensical`, `mkdocstrings-python`, `pymdown-extensions`, and `ruff` cover static AST API extraction, cross-repo `objects.inv`, and fast builds without commercial dependencies.
- **Enforce a `68–75ch` (`46rem`) reading column with persistent left and right sidebars.** Reason: uncapped prose columns and hidden right-hand `"On this page"` outlines destroy scannability on technical pages.
- **Cap guide pages at `<= 12` viewports (`~80–200` lines) and Reference pages at `<= 120 KB` HTML (`<= 14` TOC items).** Reason: monolithic `automodule` dumps with `15+` classes and `200+` inherited methods cause layout lag and bury primary constructors.
- **Set `inherited_members = false` globally on `mkdocstrings-python` and `show_bases = true`.** Reason: base driver or repository methods belong once on the base class Reference page and link from leaf subclasses via `show_bases`.
- **Document every public `TypedDict` and `msgspec.Struct` field with a PEP 257 inline docstring immediately below the field.** Reason: Griffe extracts per-field descriptions into structured parameter tables only when inline attribute docstrings are present.
- **Never write docstrings on `@overload` stubs or leak mypyc/C-extension notes into public docstrings.** Reason: Griffe renders overload docstrings ahead of the implementation docstring, and internal compiler workarounds confuse library consumers.
- **Execute standalone `docs/examples/**/*.py` modules in `pytest` and include them via `--8<--`.** Reason: inline Markdown snippets rot silently, whereas standalone modules checked by `ruff`, `pyright`, and `pytest` stay runnable.

## Quick Reference

| Slice | Reference File | Key Topics |
| --- | --- | --- |
| Zensical & mkdocstrings config | [`references/zensical-mkdocstrings.md`](references/zensical-mkdocstrings.md) | `zensical.toml`, `mkdocstrings-python` options, `postbuild.py`, `verify_docs_artifacts.py`, WCAG AAA CSS |
| Information architecture | [`references/information-architecture.md`](references/information-architecture.md) | Domain tabs (`Learn`, `Databases`, `Integrations`, `Reference`), page budgets, progressive tutorials |
| Python docstrings for Griffe | [`references/python-docstrings-griffe.md`](references/python-docstrings-griffe.md) | Google style, inline `TypedDict` / `msgspec.Struct` docstrings, custom `TypedDict` Jinja tables, leak scanner |
| Database adapter docs | [`references/database-adapters.md`](references/database-adapters.md) | Central Capability Matrix, concise 1-page per-driver guide template, own-symbols-only Reference pages |
| Polyglot TypeScript & Rust | [`references/polyglot-ts-rust.md`](references/polyglot-ts-rust.md) | `mkdocstrings-typescript`, PyO3 PEP 561 `.pyi` stub indexing, `/rustdoc/` mounting, Click CLI generator |
| Sphinx / Shibuya migration | [`references/sphinx-shibuya-migration.md`](references/sphinx-shibuya-migration.md) | Legacy Shibuya hotfixes, `.rst` to Zensical cutover checklist, dual directory + flat `.html` redirects |

<workflow>

## Workflow

### Step 1: Configure `zensical.toml` and dependency group

Define `[dependency-groups] doc` in `pyproject.toml` with `zensical>=0.0.71`, `mkdocstrings-python>=2.0.1`, `pymdown-extensions>=10.16`, and `ruff>=0.15.0`. Configure `zensical.toml` with `use_directory_urls = true`, `navigation.tabs`, `toc.follow`, `pymdownx.snippets` (`check_paths = true`), and `[project.plugins.mkdocstrings.handlers.python.options]` (`heading_level = 3`, `inherited_members = false`, `show_if_no_docstring = true`, `enable_inventory = true`). See [`references/zensical-mkdocstrings.md`](references/zensical-mkdocstrings.md).

### Step 2: Enforce docstring and `TypedDict` hygiene

Run `tools/docs/scan_public_docstrings.py --check-leaks --check-overloads --check-typeddicts <pkg>` before building docs. Ensure every public `TypedDict` and `msgspec.Struct` field has an inline PEP 257 docstring and zero duplicate class-level `Attributes:` blocks. See [`references/python-docstrings-griffe.md`](references/python-docstrings-griffe.md).

### Step 3: Structure domain tabs and standalone runnable examples

Organize top-level navigation into task-oriented tabs (`Learn`, `Databases` when multi-driver, `Integrations`, `Reference`, `Playground` when applicable, `Project`). Author runnable scripts under `docs/examples/<area>/<topic>.py` with `main()` entry points, include them with `--8<--`, and execute them in `tests/unit/docs/test_examples.py`. See [`references/information-architecture.md`](references/information-architecture.md).

### Step 4: Author curated Reference pages (`<= 120 KB` HTML, `<= 14` TOC items)

Group `::: <pkg>.<module>.<Symbol>` directives under `2–5` `##` category headings per Reference page with `heading_level = 3` and explicit `members` allowlists. Keep `inherited_members: false` on leaf classes so inherited base methods are documented once on the base class page. For Click / `rich-click` CLIs, generate `docs/reference/cli.md` with `tools/docs/generate_cli_docs.py`.

### Step 5: Run post-build emitters, HTML quality gates, and fast CI

In `Makefile` `docs`, run:

1. `scan_public_docstrings --check-leaks --check-overloads --check-typeddicts <pkg>`
2. `generate_cli_docs --check` (when the package exposes a Click CLI)
3. `zensical build --clean`
4. `tools/docs/postbuild.py` (compacting non-`<pre>` HTML indentation, generating `site/llms.txt` + `site/llms-full.txt`, and emitting flat `site/<old>.html` redirects)
5. `tools/docs/verify_docs_artifacts.py` (asserting `site/objects.inv`, `<= 120 KB` Reference HTML, `<= 14` TOC items, valid `#anchor` links, and zero `UnionType.__doc__` or compiler leaks)

Wire `.github/workflows/docs.yml` and `.github/workflows/ci.yml` to run `uv sync --group doc` and `make docs`.

</workflow>

<guardrails>

## Guardrails

- **Never hide `.md-sidebar--secondary` or `.sy-rside` in custom CSS.** Reason: hiding the right-hand `"On this page"` outline traps readers on multi-section guides and API pages.
- **Never enable `inherited_members: true` on leaf adapter or plugin classes.** Reason: repeating 40+ base driver methods across 20 adapter pages inflates HTML past `400 KB` and duplicates search results; only enable `inherited_members: true` on a leaf `TypedDict` that inherits fields from a private `_Base*` `TypedDict`.
- **Never use `mkdocs-click` on Click `>= 8.3`.** Reason: `mkdocs-click` renders literal `Sentinel.UNSET` defaults, drops positional argument tables, and emits flat `###` headings that overflow the TOC budget; use `tools/docs/generate_cli_docs.py` instead.
- **Never map `"path/foo.md" = "path/foo/index.md"` in `redirect_maps` when `use_directory_urls = true`.** Reason: Zensical resolves both keys to `site/path/foo/index.html` and overwrites the real page with a self-redirect loop; emit flat `site/path/foo.html -> /path/foo/` stubs in `postbuild.py` instead.
- **Never run `uv sync --all-extras --dev` in docs CI.** Reason: Griffe parses Python ASTs statically; `uv sync --group doc` builds docs in seconds without compiling 20 native database drivers.
- **Never leave `paths-ignore: ['*.md']` in `.github/workflows/docs.yml`.** Reason: ignoring `*.md` prevents Markdown documentation edits from deploying to GitHub Pages.

</guardrails>

<validation>

## Validation Checkpoint

- [ ] `uv run python -m tools.docs.scan_public_docstrings --check-leaks --check-overloads --check-typeddicts <pkg>` exits `0`
- [ ] `make docs` (`zensical build --clean` + `postbuild.py` + `verify_docs_artifacts.py`) exits `0`
- [ ] `site/objects.inv`, `site/llms.txt`, and `site/llms-full.txt` exist and are non-empty
- [ ] Every built `site/reference/**/*.html` file is `<= 120,000` bytes with `<= 14` `"On this page"` TOC items
- [ ] `uv run pytest tests/unit/docs/ tests/unit/tools/ -q` passes with zero inline comments in `docs/examples/`
- [ ] Legacy URLs resolve via both directory (`site/<old>/index.html`) and flat `.html` (`site/<old>.html`) redirects preserving URL hashes

</validation>

<example>

## Example — Curated Adapter Reference Page (`docs/reference/adapters/asyncpg.md`)

````markdown
# AsyncPG API Reference

```python
from sqlspec.adapters.asyncpg import AsyncpgConfig, AsyncpgDriver
```

API reference for the `sqlspec.adapters.asyncpg` package. For installation, pool configuration, and PostgreSQL dialect usage, see the [AsyncPG Database Guide](../../databases/postgres/asyncpg.md). Full execution methods inherited by `AsyncpgDriver` are documented on [`AsyncDriverAdapterBase`](../driver/async.md).

## Configuration & Parameter Types

::: sqlspec.adapters.asyncpg.AsyncpgConfig
    options:
      members:
        - provide_connection
        - provide_session
        - provide_pool
        - create_pool
        - close_pool

::: sqlspec.adapters.asyncpg.config.AsyncpgPoolConfig

::: sqlspec.adapters.asyncpg.config.AsyncpgConnectionConfig

::: sqlspec.adapters.asyncpg.config.AsyncpgDriverFeatures

## Driver & Exception Handling

::: sqlspec.adapters.asyncpg.AsyncpgDriver
    options:
      inherited_members: false
      show_bases: true
      members:
        - dialect
        - data_dictionary

::: sqlspec.adapters.asyncpg.driver.AsyncpgExceptionHandler
````

</example>

## References Index

- [Zensical & mkdocstrings Configuration](references/zensical-mkdocstrings.md)
- [Information Architecture & Page Budgets](references/information-architecture.md)
- [Python Docstrings & Griffe Rendering](references/python-docstrings-griffe.md)
- [Database Adapter Documentation](references/database-adapters.md)
- [Polyglot TypeScript, Rust, and Click CLI Docs](references/polyglot-ts-rust.md)
- [Sphinx / Shibuya Migration & Redirects](references/sphinx-shibuya-migration.md)

## Official References

- <https://zensical.org/docs/> — Zensical documentation
- <https://mkdocstrings.github.io/python/> — mkdocstrings-python & Griffe options
- <https://mkdocstrings.github.io/griffe/> — Griffe static AST parser

## Shared Styleguide Baseline

- [General Principles](../litestar-styleguide/references/general.md)
- [Python](../litestar-styleguide/references/python.md)
- [CI/CD](../litestar-styleguide/references/ci-cd.md)
