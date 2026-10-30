# Sphinx / Shibuya Migration & Legacy URL Redirects

Checklist for migrating legacy Sphinx + Shibuya `.rst` documentation to **Zensical Free** + **`mkdocstrings-python`**, plus transitional hotfixes for repositories not yet cut over.

## Zensical Cutover Checklist (`.rst` to Markdown)

1. **Replace Sphinx Dependencies in `pyproject.toml`**:
   - Remove `sphinx`, `shibuya`, `sphinx-autobuild`, `sphinx-copybutton`, `sphinx-design`, `sphinx-click`, `sphinx-datatables`, `sphinxcontrib-mermaid`, `auto-pytabs`, and any `[project.entry-points."pygments.styles"]` hooks.
   - Add `zensical>=0.0.71`, `mkdocstrings-python>=2.0.1`, `pymdown-extensions>=10.16`, and `ruff>=0.15.0` to `[dependency-groups] doc`.
2. **Remove `.pre-commit-config.yaml` and `pyproject.toml` Legacy Hooks**:
   - Remove `sphinx-lint` from `.pre-commit-config.yaml`.
   - Remove broad `"docs/**/*.*" = ["ERA", "D", ...]` ignores from `[tool.ruff.lint.per-file-ignores]` so `ERA001` (no commented-out code) and `D` (Google docstrings) are enforced on `docs/examples/**`.
3. **Delete Legacy Sphinx Files**:
   - `git rm` all `docs/**/*.rst`, `CONTRIBUTING.rst`, `docs/conf.py`, `docs/__init__.py`, `docs/_static/{custom.css,style.css,versioning.js,versions.json}`, `docs/_templates/**`, and `tools/sphinx_ext/**`.
   - Preserve `docs/_tapes/*.tape` and `docs/_static/demos/*.gif` if VHS terminal demos are used.
4. **Wire Dual Directory + Flat `.html` Redirects (`zensical.toml` + `tools/docs/postbuild.py`)**:
   - Map every moved or renamed route in `[project.plugins.redirects.redirect_maps]` (`getting_started/* -> learn/*`, `usage/* -> learn/*`, `extensions/* -> integrations/*`, underscore-to-hyphen slugs `cockroach_asyncpg.md -> cockroach-asyncpg.md`).
   - Do **not** map `"path/foo.md" = "path/foo/index.md"` in `redirect_maps` when `use_directory_urls = true` (both resolve to `site/path/foo/index.html`, creating a self-redirect loop). Let `tools/docs/postbuild.py` emit `site/path/foo.html -> /path/foo/` automatically for every built `site/<rel_dir>/index.html` page.
5. **Cut Over `.github/workflows/docs.yml` and `.github/workflows/ci.yml`**:
   - In `docs.yml`: remove `paths-ignore: ['*.md']`, replace `uv sync --all-extras --dev` with `uv sync --group doc`, run `make docs`, and upload `path: site` to `actions/upload-pages-artifact`.
   - In `ci.yml`: add a `docs_required` scope output (`true` when `docs/**`, `zensical.toml`, `CONTRIBUTING.md`, `tools/docs/**`, `<pkg>/**`, `pyproject.toml`, or `uv.lock` changes) and a fast `build-docs` PR job (`timeout-minutes: 10`, `uv sync --group doc`, `make docs`).

## Transitional Guardrails for Legacy Sphinx + Shibuya Repositories

If a repository must temporarily remain on Sphinx + Shibuya before its Zensical cutover, apply these five fixes immediately in `docs/conf.py` and `docs/_static/custom.css`:

1. **Never hide `.sy-rside` in `custom.css`**: Delete any `.sy-rside { display: none; }` rule so the right-hand `"On this page"` outline remains visible.
2. **Never uncap `.sy-main` to `100%` without a reading-width cap**: Keep prose measure bounded at `46rem` (`68–75ch`).
3. **Never load `numpydoc` or `sphinx_autodoc_typehints` alongside `sphinx.ext.napoleon`**: Use `sphinx.ext.napoleon` (`napoleon_google_docstring = True`, `napoleon_numpy_docstring = False`) with `autodoc_typehints = "description"` and `python_maximum_signature_line_length = 68`.
4. **Never place `:no-index:` on primary `.. automodule::` directives**: `:no-index:` suppresses cross-reference targets and breaks `:class:` / `:meth:` links across the site.
5. **Never combine `:inherited-members:` and `:undoc-members:` on adapter `automodule` blocks**: Curate explicit class directives and document every public `TypedDict` field with PEP 257 inline attribute docstrings.
