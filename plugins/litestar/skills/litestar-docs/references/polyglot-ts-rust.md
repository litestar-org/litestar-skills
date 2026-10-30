# Polyglot TypeScript, Rust, and Click CLI Documentation

Unified Zensical Free patterns for Python + TypeScript packages (`litestar-vite`, `litestar-mcp`), Rust + PyO3 extensions (`vertebra`, `fast-query-parsers`, `bunfun`), and Click / `rich-click` CLIs (`sqlspec`, `litestar`).

## Python + TypeScript (`mkdocstrings-typescript`)

For packages shipping both a Python backend plugin and a TypeScript/Vite package:

1. Add `mkdocstrings-typescript` to `[dependency-groups] doc` and install `typedoc` in `package.json`.
2. Register both `python` and `typescript` handlers in `zensical.toml`:

```toml
[project.plugins.mkdocstrings]
default_handler = "python"

[project.plugins.mkdocstrings.handlers.python]
paths = ["src/py"]

[project.plugins.mkdocstrings.handlers.typescript]
paths = ["src/js"]
```

Render TypeScript symbols in `docs/reference/frontend/*.md` using `::: symbol_name` with `handler: typescript` so Python and TypeScript APIs share one unified search index and navigation tree.

## Rust + PyO3 Extensions (`.pyi` Stubs + `/rustdoc/`)

For Rust crates exposing Python bindings via PyO3 / `maturin`:

1. **Zero-Cargo Python API Extraction via PEP 561 `.pyi` Stubs**:
   - Ship typed `.pyi` stub files alongside the Python package (`python/<pkg>/__init__.pyi`) with Google-style docstrings.
   - Configure `[project.plugins.mkdocstrings.handlers.python.options]` with `find_stubs_package = true`.
   - Griffe parses `.pyi` stub ASTs statically in milliseconds without running `cargo build` or `maturin develop` in docs CI.
2. **Optional Rust Crate Docs (`/rustdoc/`)**:
   - When documenting public Rust traits/structs alongside Python bindings, run `cargo doc --workspace --no-deps` in CI and copy `target/doc` into `site/rustdoc/` inside `tools/docs/postbuild.py`.

## Pure-Markdown Click / `rich-click` CLI Generator (`tools/docs/generate_cli_docs.py`)

Do **not** use `mkdocs-click` on Click `>= 8.3`:

- Click `8.3+` uses `click._utils.Sentinel.UNSET` for unset option defaults, which `mkdocs-click` `0.9.0` renders literally as ``Default: `Sentinel.UNSET` `` (`mkdocs/mkdocs-click#95`).
- `mkdocs-click` drops positional `click.Argument` tables, leaves `[dim]...[/]` Rich console markup in descriptions, and emits flat `###` headings that overflow the `<= 14` `"On this page"` TOC cap.

Use the first-party `tools/docs/generate_cli_docs.py` script instead:

1. Expose the root `click.Group` lazily via PEP 562 `__getattr__("cli")` in `<pkg>/cli.py` so importing `<pkg>.cli` does not eagerly construct command groups at runtime.
2. Introspect `cli.params` and `cli.commands` in `tools/docs/generate_cli_docs.py`:
   - Strip Rich markup tags (`re.sub(r"\[/?[a-zA-Z0-9_ #.,=-]+\]", "", text)`).
   - Filter out `--help` and `Sentinel.UNSET` defaults (`default is None or type(default).__name__ == "Sentinel"`).
   - Group subcommands under `2–4` logical `##` category headings using `<h4>` command headers (`#### sqlspec upgrade`) with Markdown tables for `Arguments` and `Options`.
3. Enforce freshness in `Makefile` `docs` and PR CI via `uv run python -m tools.docs.generate_cli_docs --check`.
