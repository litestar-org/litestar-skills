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

## Reading Measure & Sidebar Ergonomics

- **Prose Measure (`68–75ch`)**:
  - In Zensical (`docs/stylesheets/extra.css`): Cap `.md-content__inner` at `max-width: 46rem`.
  - In Sphinx (`docs/_static/custom.css`): Cap `.sy-content` at `max-width: 46rem`.
  - Reason: Uncapped prose columns stretch across ultrawide monitors and degrade reading comprehension.
- **Persistent Left & Right Sidebars**:
  - Keep both primary (left section tree) and secondary (right `"On this page"` outline) sidebars visible on desktop viewports.
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
