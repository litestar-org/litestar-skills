"""Verify keyword arguments in shipped skill code samples resolve upstream.

Walks every Markdown file under ``skills/`` and ``commands/``, extracts Python
fenced code blocks, and for each call to a symbol imported from a library we
ship guidance for, checks that every keyword argument exists in that symbol's
real signature.

Why this exists: ``tools/check-upstream-imports.py`` proves that
``from X import Y`` still resolves, which catches renamed or removed symbols.
It cannot catch a symbol that survived a release with a *renamed parameter* --
the import succeeds and the sample still teaches a ``TypeError``. That is the
drift this script catches, and it is the common shape of an upstream minor
release: the class stays, one keyword changes.

Exemptions:

- ``# pragma: legacy-example`` on a block's opening fence (or any line inside
  it) skips that block, matching ``check-upstream-imports.py``.
- A callable accepting ``**kwargs`` is treated as permissive and skipped.
- A symbol that is not a class or function (a re-exported instance, a typing
  alias) is skipped, since it has no meaningful signature to check.

Behavior when a target library is not installed: the symbol simply fails to
resolve and is skipped, so this script never fails for a missing dependency.
Run it with the ``validation`` extra installed for full coverage.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import inspect
import re
import sys
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
SEARCH_ROOTS: Final = ("skills", "commands")

#: Root modules this repository ships guidance for.
UPSTREAM_ROOTS: Final = frozenset(
    {
        "advanced_alchemy",
        "litestar",
        "litestar_autowire",
        "litestar_email",
        "litestar_granian",
        "litestar_htmx",
        "litestar_mcp",
        "litestar_queues",
        "litestar_saq",
        "litestar_security",
        "litestar_vite",
        "msgspec",
        "polyfactory",
        "pytest_databases",
        "sqlspec",
    }
)

PYTHON_FENCE: Final = re.compile(r"```python(?P<info>[^\n]*)\n(?P<code>.*?)```", re.DOTALL)
LEGACY_PRAGMA: Final = "pragma: legacy-example"


def _is_upstream(module: str) -> bool:
    return module.split(".")[0] in UPSTREAM_ROOTS


def _resolve(module: str, name: str) -> object | None:
    try:
        imported = importlib.import_module(module)
    except Exception:  # noqa: BLE001 - any import failure means "unverifiable"
        return None
    return getattr(imported, name, None)


def _accepted_keywords(obj: object) -> set[str] | None:
    """Return accepted keyword names, or ``None`` when the call is permissive."""
    try:
        signature = inspect.signature(obj)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    accepted: set[str] = set()
    for parameter in signature.parameters.values():
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            return None
        if parameter.kind in {
            inspect.Parameter.KEYWORD_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        }:
            accepted.add(parameter.name)
    return accepted


def _collect_imports(tree: ast.Module) -> dict[str, tuple[str, str]]:
    imports: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and _is_upstream(node.module):
            for alias in node.names:
                imports[alias.asname or alias.name] = (node.module, alias.name)
    return imports


def _check_block(code: str, path: Path) -> list[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    imports = _collect_imports(tree)
    if not imports:
        return []

    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        target = imports.get(node.func.id)
        if target is None:
            continue
        obj = _resolve(*target)
        if obj is None or not (inspect.isclass(obj) or inspect.isfunction(obj)):
            continue
        accepted = _accepted_keywords(obj)
        if accepted is None:
            continue
        for keyword in node.keywords:
            if keyword.arg is None or keyword.arg in accepted:
                continue
            options = ", ".join(sorted(accepted)) or "no keyword arguments"
            violations.append(
                f"{path.relative_to(REPO_ROOT)}:{node.lineno} "
                f"{node.func.id}(...) got unknown keyword {keyword.arg!r} "
                f"(accepts: {options})"
            )
    return violations


def _iter_markdown() -> list[Path]:
    files: list[Path] = []
    for root in SEARCH_ROOTS:
        files.extend(sorted((REPO_ROOT / root).rglob("*.md")))
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    violations: list[str] = []
    blocks = 0
    for path in _iter_markdown():
        text = path.read_text(encoding="utf-8")
        for match in PYTHON_FENCE.finditer(text):
            code = match.group("code")
            if LEGACY_PRAGMA in match.group("info") or LEGACY_PRAGMA in code:
                continue
            blocks += 1
            violations.extend(_check_block(code, path))

    if violations:
        for violation in violations:
            print(f"[FAIL] {violation}")
        print(f"\n{len(violations)} keyword argument error(s) in skill code samples")
        return 1

    print(f"[ OK ] checked keyword arguments across {blocks} Python blocks — no signature drift")
    return 0


if __name__ == "__main__":
    sys.exit(main())
