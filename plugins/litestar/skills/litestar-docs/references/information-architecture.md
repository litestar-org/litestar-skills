# Information Architecture & Page Budgets

Domain-oriented navigation, typography, and page-size budgets for `litestar-org` and `cofin` documentation sites.

## Top-Level Navigation Tabs

Organize `project.nav` into 5–6 task-oriented top-level tabs rather than exposing raw directory trees:

| Tab | Purpose | Page Budget |
| --- | --- | --- |
| `Learn` | SQLite-first Quickstart, First Steps, Core Concepts (`SQL`, Configuration & Pools, Async vs Sync, Query Builder, SQL Files, Migrations, Testing), and Production Recipes | `<= 12` viewports (`~80–200` Markdown lines) per page; 1 concept per page |
| `Databases` | Central Capability Matrix (`databases/index.md`) + 1-page setup, pool, and dialect guides per supported driver | `<= 10` viewports (`~80–140` Markdown lines) per adapter |
| `Integrations` | Unified framework and AI guides (`Litestar`, `Google ADK`, `Events`, `FastAPI`, `Flask`, `Starlette`, `Sanic`, `Dishka`) combining setup, DI, sessions, and stores | `<= 12` viewports per integration |
| `Reference` | Curated 1-class or cohesive-group `mkdocstrings` pages organized by domain (`SQLSpec & Config`, `Drivers`, `Core Pipeline`, `Query Builder`, `Subsystems`, `Extensions`, `Database Adapters`) | `<= 120 KB` built HTML and `<= 14` `"On this page"` TOC items per page |
| `Playground` | Embedded Pyodide + CodeMirror browser sandbox with prebuilt examples and instant execution | Full-bleed responsive 2-column layout (`max-width: 84rem`) |
| `Project` | Contributor Guide, Creating Adapters, Releases, and Changelog | Standard prose measure |

## Reading Measure & Sidebar Ergonomics (`docs/stylesheets/extra.css`)

- **Prose Measure (`68–75ch`)**: Cap `.md-content__inner` at `max-width: 46rem` (`~72ch`) so prose lines never stretch across ultrawide monitors.
- **Persistent Left & Right Sidebars**: Keep both `.md-sidebar--primary` (left section tree) and `.md-sidebar--secondary` (right `"On this page"` outline) visible on desktop viewports, with thin hover-reveal scrollbars (`scrollbar-width: thin`).
- **Bounded Secondary TOC (`<= 14` items)**:
  - Set `toc_depth = "2-3"`, `heading_level = 3`, and `show_symbol_type_toc = false` in `zensical.toml`.
  - Group Reference `:::` blocks under `2–5` `##` category headings so classes render at `###` and methods render at `<h4>` (omitted from the right-hand TOC while remaining deep-linkable via `summary = true` tables).
- **WCAG AAA High-Contrast Neutral Palette**:
  - Light mode (`[data-md-color-scheme="default"]`): `#0f172a` slate-900 ink on `#ffffff` background, `#1d4ed8` sapphire-blue underlined prose links (`text-underline-offset: 0.18em`), and crisp `#f8fafc` code surfaces.
  - Dark mode (`[data-md-color-scheme="slate"]`): `#f1f5f9` slate-100 ink on `#0f172a` / `#1e293b` neutral slate surfaces (never purple-tinted dark mode) with `#60a5fa` sky-blue underlined prose links.

## FastAPI-Style Progressive Tutorial Structure

Every `Learn` tutorial page follows a 4-part structure:

1. **Complete Runnable Example First**: Embed a standalone verified Python module from `docs/examples/<area>/<name>.py` via `pymdownx.snippets` (`--8<-- "docs/examples/..."`) with `hl_lines` highlighting the focal lines.
2. **Expected Output**: Show the exact terminal or return payload immediately beneath the snippet.
3. **Line-by-Line Walkthrough**: Explain the highlighted lines in 3–5 short paragraphs without repeating boilerplate.
4. **Recap**: Close with a 3-bullet summary and a link to the next guide or Reference page.

## Standalone Verified Examples (`docs/examples/` + `tests/unit/docs/test_examples.py`)

- Place every tutorial code sample in a standalone Python module under `docs/examples/<section>/<topic>.py` with a top-level docstring, `main()` function, `__all__ = ("main",)`, and zero inline `#` comments.
- Never leak pytest fixtures (`tmp_path`, `monkeypatch`) into `docs/examples/**/*.py`. When a snippet needs a temporary file or directory, use `tempfile.TemporaryDirectory()` inside `main()`.
- Execute every `docs/examples/**/*.py` module during unit testing via `tests/unit/docs/test_examples.py` (skipping only modules whose optional third-party driver is not installed in the current environment).
