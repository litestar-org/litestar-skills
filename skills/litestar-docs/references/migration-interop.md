# Engine Interoperability, Syntax Translation & Redirects

Reference for translating directives between **Sphinx** and **Zensical**, maintaining cross-engine `objects.inv` links, and preserving historical URLs.

## Directive & Syntax Translation Matrix

| Capability | Sphinx (`.rst`) | Zensical (`.md`) |
| --- | --- | --- |
| **Class API Reference** | `.. autoclass:: pkg.Mod\n   :members:` | `::: pkg.Mod\n    options:\n      members: true` |
| **Function API Reference** | `.. autofunction:: pkg.fn` | `::: pkg.fn` |
| **Type Alias Reference** | `.. autotype:: pkg.Alias` (or `.. py:type::`) | `::: pkg.Alias` |
| **Constant (No Value)** | `.. autodata:: pkg.CONST\n   :no-value:` | `::: pkg.CONST\n    options:\n      show_source: false` |
| **Cross-Reference Link** | `:class:` (`~pkg.Mod`) / `:meth:` (`~pkg.Mod.fn`) | `[pkg.Mod][]` / `[pkg.Mod.fn][]` |
| **Runnable File Include** | `.. literalinclude:: /examples/ex.py\n   :language: python` | `--8<-- "docs/examples/ex.py:example"` |
| **Synchronized Tabs** | `.. tab-set::` + `.. tab-item:: uv\n   :sync: uv` | `=== "uv"` (with `content.tabs.link`) |
| **Admonition Callout** | `.. note::\n   Body text.` | `!!! note\n    Body text.` |
| **Collapsible Callout** | `.. dropdown:: Title` (`sphinx-design`) | `??? note "Title"` (`pymdownx.details`) |
| **Grid Cards** | `.. grid:: 2` + `.. grid-item-card::` | `<div class="grid cards" markdown>` |
| **Mermaid Diagram** | `.. mermaid::` (`sphinxcontrib-mermaid`) | ```` ```mermaid ```` (`pymdownx.superfences`) |
| **Click CLI Docs** | `.. click:: pkg.cli:group\n   :prog: cmd\n   :nested: full` | Generated via `tools/docs/generate_cli_docs.py` |

## Cross-Engine `objects.inv` Interoperability

Both Sphinx (`sphinx.ext.intersphinx`) and Zensical (`mkdocstrings` with `enable_inventory = true`) emit and consume the standard Sphinx v2 `objects.inv` binary format:

- A Sphinx site can link to a Zensical site (`https://sqlspec.dev/objects.inv`) via `intersphinx_mapping`.
- A Zensical site can link to a Sphinx site (`https://docs.litestar.dev/latest/objects.inv`) via `inventories` under `[project.plugins.mkdocstrings.handlers.python]`.
- Always verify that `site/objects.inv` is generated in `verify_docs_artifacts.py` so downstream ecosystem packages never break cross-references.

## Preserving URLs & Redirects Across Route Changes

When reorganizing documentation pages or switching engines:

1. **Directory URLs (`/<section>/<page>/`)**:
   - Map moved routes in `[project.plugins.redirects.redirect_maps]` (Zensical) or `sphinx-reredirects` / custom stub emitters (Sphinx).
   - Never map `"path/foo.md" = "path/foo/index.md"` in Zensical `redirect_maps` when `use_directory_urls = true`; both resolve to `site/path/foo/index.html` and create a self-redirect loop.
2. **Flat `.html` Redirect Stubs (`site/<path>.html -> /<path>/`)**:
   - Emit lightweight HTML redirect stubs in `tools/docs/postbuild.py` that preserve `window.location.hash` so deep links to `#class-method` anchors continue to resolve cleanly.
