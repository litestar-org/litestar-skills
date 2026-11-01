# Polyglot TypeScript, Rust, and Click CLI Documentation

Patterns for documenting Python + TypeScript packages (`litestar-vite`, `litestar-mcp`), Rust + PyO3 extensions (`vertebra`, `fast-query-parsers`, `bunfun`), and Click / `rich-click` CLIs (`sqlspec`, `litestar`) across both **Zensical** and **Sphinx**.

## Python + TypeScript Packages

### Zensical (`mkdocstrings-typescript`)

1. Add `mkdocstrings-typescript` to `[dependency-groups] doc` and `typedoc` to `package.json`.
2. Register both `python` and `typescript` handlers in `zensical.toml`:

   ```toml
   [project.plugins.mkdocstrings]
   default_handler = "python"

   [project.plugins.mkdocstrings.handlers.python]
   paths = ["src/py"]

   [project.plugins.mkdocstrings.handlers.typescript]
   paths = ["src/js"]
   ```

3. Render TypeScript symbols in `docs/reference/frontend/*.md` using `::: symbol_name` with `handler: typescript` so Python and TypeScript APIs share one unified search index.

### Sphinx (`TypeDoc` + `myst-parser`)

1. Run `npx typedoc --plugin typedoc-plugin-markdown --out docs/reference/frontend src/js/index.ts` before `sphinx-build`.
2. Include `myst_parser` in `extensions` inside `docs/conf.py` so generated TypeScript Markdown reference files compile alongside `.rst` pages.

## Rust + PyO3 Extensions (`.pyi` Stubs + `/rustdoc/`)

For Rust crates exposing Python bindings via PyO3 / `maturin`:

1. **Zero-Cargo Python API Extraction via PEP 561 `.pyi` Stubs**:
   - Ship typed `.pyi` stub files alongside the Python package (`python/<pkg>/__init__.pyi`) with Google-style docstrings.
   - In Zensical: Configure `[project.plugins.mkdocstrings.handlers.python.options]` with `find_stubs_package = true`. Griffe parses `.pyi` stub ASTs statically without running `cargo build` or `maturin develop` in docs CI.
   - In `maturin`-backed repositories, run `uv sync --no-install-project --group doc` with `PYTHONPATH=src/py:.` so `uv sync` does not trigger a full Cargo compile during docs-only CI.
2. **Optional Rust Crate Docs (`/rustdoc/`)**:
   - Run `cargo doc --workspace --no-deps` in CI and copy `target/doc` into `site/rustdoc/` during post-build processing.

## Click & `rich-click` CLI Reference Generation

### Sphinx (`sphinx-click`)

Use `sphinx-click` (`.. click::`) rather than `automodule`, which renders empty pages for Click command groups:

```rst
CLI Reference
=============

.. click:: litestar_vite.cli:vite_group
    :prog: litestar assets
    :nested: full
```

### Zensical (`tools/docs/generate_cli_docs.py`)

Do **not** use `mkdocs-click` on Click `>= 8.3`:

- Click `8.3+` uses `click._utils.Sentinel.UNSET` for unset option defaults, which `mkdocs-click` renders literally as `Default: Sentinel.UNSET`.
- `mkdocs-click` drops positional `click.Argument` tables, leaves `[dim]...[/]` Rich console markup in descriptions, and emits flat `###` headings that overflow the `<= 14` TOC item budget.

Use `tools/docs/generate_cli_docs.py` instead:

1. Expose the root `click.Group` lazily via PEP 562 `__getattr__("cli")` in `<pkg>/cli.py`.
2. Introspect `cli.params` and `cli.commands`:
   - Strip Rich markup tags (`re.sub(r"\[/?[a-zA-Z0-9_ #.,=-]+\]", "", text)`).
   - Filter out `--help` and `Sentinel.UNSET` defaults (`default is None or type(default).__name__ == "Sentinel"`).
   - Group subcommands under `2–4` logical `##` category headings using `<h4>` command headers (`#### sqlspec upgrade`) with Markdown tables for `Arguments` and `Options`.
3. Verify freshness in `Makefile` `docs` and CI via `uv run python -m tools.docs.generate_cli_docs --check`.
