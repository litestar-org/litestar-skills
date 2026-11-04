# Information Architecture & Page Budgets

Domain-oriented navigation, typography, and page-size budgets for Litestar ecosystem documentation sites across both **Zensical** and **Sphinx**.

## Top-Level Navigation Tabs

Organize navigation into 5–6 task-oriented top-level tabs rather than exposing raw directory trees:

| Tab | Purpose | Page Budget |
| --- | --- | --- |
| `Learn` | Quickstart, First Steps, Core Concepts (`SQL`, Configuration & Pools, Async vs Sync, Query Builder, Migrations, Testing), and Production Recipes | `<= 12` viewports (`~80–200` lines) per page; 1 concept per page |
| `Databases` | Central Capability Matrix (`databases/index`) + 1-page setup, pool, and dialect guides per supported driver | `<= 10` viewports (`~80–140` lines) per adapter |
| `Integrations` | Unified framework and AI guides (`Litestar`, `Google ADK`, `Events`, `FastAPI`, `Flask`, `Starlette`, `Dishka`) combining setup, DI, sessions, and stores | `<= 12` viewports per integration |
| `Reference` | Curated 1-class or cohesive-group API reference pages organized by domain (`Config`, `Drivers`, `Core Pipeline`, `Query Builder`, `Extensions`, `Database Adapters`) | `<= 120 KB` built HTML and `<= 14` `"On this page"` TOC items per page |
| `Playground` | Embedded Pyodide + CodeMirror browser sandbox with prebuilt examples and instant execution | Full-bleed responsive 2-column layout (`max-width: 84rem`) |
| `Project` | Contributor Guide, Creating Adapters, Releases, and Changelog | Standard prose measure |

## Reading Measure, Headings, Tables & Sidebar Ergonomics

- **Wide Grid & Compact Sidebars**:
  - In Zensical (`docs/stylesheets/extra.css`): Set `.md-grid { max-width: 86rem; }`, `.md-sidebar--primary { width: 11rem; }`, and `.md-sidebar--secondary { width: 10.5rem; }` so code blocks, diagrams, and tables have generous horizontal room without cramping.
  - Hide `.md-sidebar--primary` automatically on single-page tab sections (`Home` / `docs/index.md` with `hide: [navigation]`) while keeping the right-hand `"On this page"` outline visible.
- **Home Hero Banner (`[data-md-color-scheme]` vs `<picture>`)**:
  - Never use `<picture><source media="(prefers-color-scheme: dark)">` inside `docs/index.md` (it only responds to OS-level dark mode, leaving dark-ink text invisible when Zensical's theme toggle switches to `[data-md-color-scheme="slate"]`). Render dual `.lv-hero-banner--light` and `.lv-hero-banner--dark` `<img>` tags toggled by `[data-md-color-scheme]`, omit redundant `# Project Name` `<h1>` headings above the banner logo, avoid buzzword headings (`60-Second Quick Start` -> `Installation and Setup`), and leave optional third-party server plugins out of the hero summary.
- **Heading, Code Pill & Table Discipline**:
  - Keep `##` and `###` headings unnumbered and free of inline `` `code` `` spans or parenthesized module paths (`## Browser Stream Primitives`, not `## 1. Browser Stream Primitives (\`litestar-vite-plugin/helpers\`)`).
  - Style plain inline `` `code` `` with a subtle borderless fill and reserve accented border pills strictly for clickable code links (`a > code`).
  - Keep Markdown tables to `2–4` columns (`Helper | Purpose` or `Symbol | Type | Description`).
  - Never write `\|` inside backticked code in Markdown table cells (Python-Markdown splits table cells on `|` before tokenizing backticks, rendering literal `\|` in `<code>`); write union values with `or` (`` `"open"` or `"closed"` ``) or a named type alias.
  - Keep tab switcher labels short (`white-space: nowrap`, no `(mode="...")` suffixes) so tab bars always fit on a single horizontal line.
- **Persistent Left & Right Sidebars**:
  - Keep both primary (left section tree on multi-page tabs) and secondary (right `"On this page"` outline) sidebars visible on desktop viewports.
  - Never set `.sy-rside { display: none; }` (Sphinx/Shibuya) or hide `.md-sidebar--secondary` (Zensical).
- **Bounded Secondary TOC (`<= 14` items)**:
  - Group API reference directives under `2–5` H2 (`##`) category headings so classes render at H3 (`###`) and methods render at H4 (`<h4>`), keeping individual methods out of the secondary TOC while preserving deep-link anchors.
- **WCAG AAA High-Contrast Neutral Palette (60-30-10 Rule)**:
  - **60% Canvas**: `#ffffff` light / `#0f172a` slate dark (never purple-tinted dark mode).
  - **30% Typography**: `#0f172a` slate-900 ink in light mode / `#f1f5f9` slate-100 ink in dark mode.
  - **10% Brand Accent**: Reserve Litestar Gold (`#EDB641`) for official logo marks, active tab indicators, and focus rings. Use high-contrast sapphire blue (`#1d4ed8` light / `#60a5fa` dark) with visible underlines (`text-underline-offset: 0.18em`) for inline links.

## Progressive Tutorial Structure

Every `Learn` tutorial page follows four parts:

1. **Complete Runnable Example First**:
   - Embed a standalone verified Python module from `docs/examples/<area>/<name>.py`.
   - Zensical: Use `pymdownx.snippets` (`--8<-- "docs/examples/...:example"`).
   - Sphinx: Use `.. literalinclude:: /examples/...` with `:start-after:` and `:end-before:`.
2. **Expected Output**: Show the exact terminal or return payload immediately beneath the snippet.
3. **Line-by-Line Walkthrough**: Explain the focal lines in 3–5 short paragraphs without repeating boilerplate.
4. **Recap**: Close with a 3-bullet summary and a link to the next guide or Reference page.

## Synchronized Package Manager Tabs

Present installation commands across `uv`, `pip`, `pdm`, and `poetry` using synchronized tabs:

- **Zensical (`pymdownx.tabbed` + `content.tabs.link`)**:

  ````markdown
  === "uv"

      ```bash
      uv add sqlspec
      ```

  === "pip"

      ```bash
      pip install sqlspec
      ```
  ````

- **Sphinx (`sphinx-design` `.. tab-set::`)**:

  ```rst
  .. tab-set::

      .. tab-item:: uv
          :sync: uv

          .. code-block:: bash

              uv add sqlspec

      .. tab-item:: pip
          :sync: pip

          .. code-block:: bash

              pip install sqlspec
  ```

## Standalone Verified Examples (`docs/examples/`)

- Place every tutorial code sample in a standalone Python module under `docs/examples/<section>/<topic>.py` with a top-level docstring, `main()` function, `__all__ = ("main",)`, and zero inline `#` comments.
- Never use pytest fixtures (`tmp_path`, `monkeypatch`) inside `docs/examples/**/*.py`; use `":memory:"` or `tempfile.TemporaryDirectory()` inside `main()`.
- Execute every `docs/examples/**/*.py` module during unit testing via `tests/unit/docs/test_examples.py`.
