"""Verify upstream API references in shipped skill code samples.

Walks every Markdown file under ``skills/`` and ``commands/``, extracts Python
fenced code blocks, parses them with :mod:`ast`, and verifies that every
``from X import Y`` and ``import X`` whose root module is one we ship guidance
for actually resolves against the installed library version. Drift (a renamed
class, a moved module, a removed symbol) fails the check.

Why this exists: ``make validate-skills`` checks repo-internal vocabulary
rules; this script checks against external state (upstream library APIs).
The two compose — vocabulary check stops codename leaks, import check stops
API drift. See ``.agents/workflow.md`` §Upstream API Drift.

Exemptions:

- Append ``# pragma: legacy-example`` to a code block's opening fence (or to
  any line inside the block) to mark a sample as intentionally showing a
  deprecated form. The block is still parsed and any forbidden vocab still
  triggers; only the import-existence check is skipped for that block.
- Files in :data:`_IMPORT_CHECK_ALLOWLIST` are skipped entirely (rare — the
  tool's own tests would go here).

Behavior when a target library is **not installed**:

- The script logs a warning naming the missing library and continues, treating
  imports of that library as unverifiable rather than failing. CI installs the
  ``validation`` extra (``pip install -e '.[validation]'``) so missing-library
  warnings are the local-dev signal to opt in.

Exit codes:

- 0 — every checked import resolves (or was exempted).
- 1 — one or more imports failed to resolve.
- 2 — internal error (file read failure, AST parse error in the script
  itself, etc.).
"""

import ast
import importlib
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"
COMMANDS_DIR = REPO_ROOT / "commands"

# Root module names whose imports we verify against installed packages.
# Imports rooted in any other module (stdlib, third-party we don't ship guidance
# for, neutral placeholders like ``app`` or ``my_package``) are ignored.
TARGET_ROOTS: frozenset[str] = frozenset(
    {
        "advanced_alchemy",
        "dishka",
        "litestar",
        "litestar_granian",
        "litestar_mcp",
        "litestar_queues",
        "litestar_saq",
        "msgspec",
        "sqlalchemy",
        "sqlspec",
    }
)

# Files exempt from the import check entirely. Use sparingly.
_IMPORT_CHECK_ALLOWLIST: frozenset[str] = frozenset()

# Marker that exempts a code block from import verification. Place anywhere
# inside the block (or on the opening fence). The block is still scanned for
# forbidden vocabulary by ``check_forbidden_vocab`` in ``validate-skills.py``.
_LEGACY_PRAGMA = "# pragma: legacy-example"

# Match a Python fenced code block: ```python ... ```.
# Captures the block body including any pragma marker on the opening fence line.
_PYTHON_BLOCK_PATTERN = re.compile(
    r"^```python([^\n]*)\n(.*?)^```",
    re.MULTILINE | re.DOTALL,
)


class ImportRef(NamedTuple):
    """A single ``from X import Y`` or ``import X`` reference to check."""

    file: Path
    line_in_file: int  # 1-based line number where the import appears
    module: str
    name: str | None  # ``None`` for plain ``import X``; symbol name for ``from X import Y``
    raw: str  # the source line as written, for the error message


class Violation(NamedTuple):
    file: Path
    line: int
    message: str


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def iter_python_blocks(text: str, file_offset_lines: int = 0) -> Iterator[tuple[int, str, bool]]:
    """Yield ``(start_line, code, is_legacy)`` per Python fenced block.

    ``start_line`` is the 1-based line number in the source file where the
    block's first code line appears. ``is_legacy`` is True if the
    ``# pragma: legacy-example`` marker was found on the opening fence line
    or anywhere inside the block.
    """
    for match in _PYTHON_BLOCK_PATTERN.finditer(text):
        fence_extras = match.group(1) or ""
        body = match.group(2)
        # Line where the body begins is the line *after* the opening fence.
        before = text[: match.start()]
        opening_fence_line = before.count("\n") + 1
        body_start_line = opening_fence_line + 1 + file_offset_lines
        is_legacy = _LEGACY_PRAGMA in fence_extras or _LEGACY_PRAGMA in body
        yield body_start_line, body, is_legacy


def extract_imports(code: str, file: Path, body_start_line: int) -> Iterator[ImportRef]:
    """Yield :class:`ImportRef` for every import in a Python code block.

    Lines that fail to parse (e.g., snippets with ellipses for brevity) are
    silently skipped — those don't represent shipped API claims.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return
    code_lines = code.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue  # relative import like ``from . import x`` — not our target
            line_in_block = node.lineno - 1  # ast lineno is 1-based; index is 0-based
            raw = code_lines[line_in_block] if 0 <= line_in_block < len(code_lines) else ""
            for alias in node.names:
                yield ImportRef(
                    file=file,
                    line_in_file=body_start_line + line_in_block,
                    module=node.module,
                    name=alias.name,
                    raw=raw.strip(),
                )
        elif isinstance(node, ast.Import):
            line_in_block = node.lineno - 1
            raw = code_lines[line_in_block] if 0 <= line_in_block < len(code_lines) else ""
            for alias in node.names:
                yield ImportRef(
                    file=file,
                    line_in_file=body_start_line + line_in_block,
                    module=alias.name,
                    name=None,
                    raw=raw.strip(),
                )


def is_target_import(ref: ImportRef) -> bool:
    """True if ``ref`` should be verified (root module is in TARGET_ROOTS)."""
    root = ref.module.split(".")[0]
    return root in TARGET_ROOTS


def _parent_chain(dotted: str) -> tuple[str, ...]:
    """Return all ancestor module names for a dotted path.

    ``_parent_chain("a.b.c")`` → ``("a.b", "a")``. Used to decide whether a
    ``ModuleNotFoundError`` names the module the skill referenced (a real
    drift) or a different module somewhere in its import chain (a transitive
    extras issue).
    """
    parts = dotted.split(".")
    return tuple(".".join(parts[:i]) for i in range(len(parts) - 1, 0, -1))


def verify_import(ref: ImportRef, _module_cache: dict[str, object | str] | None = None) -> str | None:
    """Return ``None`` if the import resolves; otherwise an error message.

    The cache memoises ``importlib.import_module`` results so repeated lookups
    of the same module don't re-import. ``None`` cached value means "tried and
    failed to import" — distinguish from "not yet attempted" with the cache
    key's presence rather than its value.
    """
    cache = _module_cache if _module_cache is not None else {}
    if ref.module in cache:
        cached = cache[ref.module]
        if isinstance(cached, str):
            # Cache holds the failure classification string from the first
            # attempt — return it unchanged so repeat encounters stay in the
            # same bucket (violation vs. transitive-missing).
            return cached
        mod = cached
    else:
        try:
            mod = importlib.import_module(ref.module)
        except ModuleNotFoundError as exc:
            # The module itself doesn't exist — this is a real API drift,
            # not a missing-extras case. Distinguish by checking whether the
            # failing name matches the module we tried to import; a transitive
            # ModuleNotFoundError (``sqlspec.adapters.duckdb`` failing because
            # ``duckdb`` isn't installed) names a DIFFERENT module.
            failing_name = exc.name or ""
            if failing_name == ref.module or failing_name in _parent_chain(ref.module):
                error = f"module {ref.module!r} does not exist"
            else:
                error = f"library not importable ({type(exc).__name__}: {exc})"
            cache[ref.module] = error
            return error
        except ImportError as exc:
            error = f"library not importable ({type(exc).__name__}: {exc})"
            cache[ref.module] = error
            return error
        cache[ref.module] = mod
    if ref.name is None:
        # ``import X`` — already verified by importlib above
        return None
    if ref.name == "*":
        return None  # star imports — can't statically check
    if not hasattr(mod, ref.name):
        return f"module {ref.module!r} has no attribute {ref.name!r}"
    return None


def iter_skill_markdown() -> Iterator[Path]:
    if SKILLS_DIR.is_dir():
        yield from sorted(SKILLS_DIR.rglob("*.md"))
    if COMMANDS_DIR.is_dir():
        yield from sorted(COMMANDS_DIR.rglob("*.md"))


def main() -> int:
    violations: list[Violation] = []
    # ``missing_libs`` tracks root packages not installed at all. ``partial_libs``
    # tracks submodules that fail to import even when their root does — usually
    # because a transitive dep (e.g., duckdb, fastapi) needs an extra. The two
    # have different remediations, so keep them separate rather than conflating
    # them into one warning.
    missing_libs: set[str] = set()
    partial_libs: set[str] = set()
    # Cache values are one of:
    #   - the imported module object (success),
    #   - a ``str`` holding the failure classification (reused on repeat hits).
    module_cache: dict[str, object | str] = {}
    files_checked = 0
    blocks_checked = 0
    blocks_legacy = 0
    imports_checked = 0

    for md_file in iter_skill_markdown():
        rel = _rel(md_file)
        if rel in _IMPORT_CHECK_ALLOWLIST:
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"[ERROR] could not read {rel}: {exc}", file=sys.stderr)
            return 2
        files_checked += 1
        for body_start, code, is_legacy in iter_python_blocks(text):
            blocks_checked += 1
            if is_legacy:
                blocks_legacy += 1
                continue
            for ref in extract_imports(code, md_file, body_start):
                if not is_target_import(ref):
                    continue
                imports_checked += 1
                error = verify_import(ref, module_cache)
                if error is None:
                    continue
                if "does not exist" in error:
                    # The module the skill referenced genuinely doesn't exist
                    # upstream — this IS a violation (real API drift).
                    violations.append(
                        Violation(
                            file=md_file,
                            line=ref.line_in_file,
                            message=f"broken import — {ref.raw!r}: {error}",
                        )
                    )
                    continue
                if "library not importable" in error:
                    root = ref.module.split(".")[0]
                    # Distinguish "root package itself not installed" from
                    # "submodule fails to import because a transitive dep is
                    # missing." If the root imports cleanly, the skill's
                    # reference is to the right API — we just need a different
                    # extras install to verify it.
                    try:
                        importlib.import_module(root)
                    except ImportError:
                        missing_libs.add(root)
                    else:
                        partial_libs.add(ref.module)
                    continue  # not a violation — opt-in to verify
                violations.append(
                    Violation(
                        file=md_file,
                        line=ref.line_in_file,
                        message=f"broken import — {ref.raw!r}: {error}",
                    )
                )

    for v in violations:
        print(f"[FAIL] {_rel(v.file)}:{v.line}: {v.message}")

    if missing_libs:
        print(
            f"\n[WARN] {len(missing_libs)} target librar{'y' if len(missing_libs) == 1 else 'ies'} "
            f"not installed — imports rooted in {sorted(missing_libs)} were NOT verified.",
            file=sys.stderr,
        )
        print(
            "       Install with: uv pip install -e '.[validation]'  (or add via pyproject.toml extras)",
            file=sys.stderr,
        )
    if partial_libs:
        print(
            f"\n[INFO] {len(partial_libs)} submodule(s) could not be imported "
            "(transitive dependency missing — install the matching library extra):",
            file=sys.stderr,
        )
        for mod in sorted(partial_libs):
            print(f"         - {mod}", file=sys.stderr)

    if violations:
        print(f"\n{len(violations)} broken import(s) across {files_checked} files", file=sys.stderr)
        return 1

    print(
        f"[ OK ] checked {imports_checked} imports across {blocks_checked} Python blocks "
        f"in {files_checked} files ({blocks_legacy} legacy-example blocks skipped) — no broken imports"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
