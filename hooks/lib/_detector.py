"""Canonical Python detector for Litestar skill hooks.

Read by hooks/lib/detect-env.sh and hooks/lib/detect-env.ps1 (the .js variant
is a separate Node ESM port for OpenCode reuse — see detect-env.js).

Usage:
    python3 hooks/lib/_detector.py <project_root> <skill_map_path>

Emits JSON to stdout:
    {"detected_skills": [...], "context": "...", "project_root": "..."}
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_SKIP_DIRS = {
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    "plugins",
    ".git",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
}
_PY_FILE_CAP = 50
_PY_DEPTH_CAP = 4


def _normalize_dep_name(name: str) -> str:
    """Normalize a Python distribution name per PEP 503."""
    return re.sub(r"[-_.]+", "-", name.strip().lower())


def _extract_project_name(pyproject_text: str) -> str:
    """Extract normalized [project].name or [tool.poetry].name from pyproject.toml."""
    in_target_section = False
    for raw_line in pyproject_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            in_target_section = section in ("project", "tool.poetry")
            continue
        if in_target_section:
            match = re.match(r'^name\s*=\s*["\']([^"\']+)["\']', line)
            if match:
                return _normalize_dep_name(match.group(1))
    return ""


def _is_ignored_glob_candidate(root: Path, candidate: Path, pattern: str) -> bool:
    """Return True when a glob match traverses hidden or skipped directories."""
    rel_parts = candidate.relative_to(root).parts
    if any(p in _SKIP_DIRS or p.startswith(".") for p in rel_parts[:-1]):
        return True
    return bool(rel_parts and rel_parts[-1].startswith(".") and not Path(pattern).name.startswith("."))


def detect(root: Path, map_path: Path) -> dict[str, object]:
    """Detect Litestar ecosystem skills for ``root`` using ``map_path``."""
    map_data = json.loads(map_path.read_text())
    matchers = map_data["matchers"]
    intro = map_data.get("static_intro", "")

    pyproject_deps: dict[str, str] = {}
    pyproject_sections: list[tuple[str, str]] = []
    python_imports: dict[str, str] = {}
    python_regexes: list[tuple[re.Pattern[str], str]] = []
    file_globs: list[tuple[str, str]] = []
    own_package_to_skill: dict[str, tuple[str, str]] = {}
    for m in matchers:
        skill = m["skill"]
        own_pkg = m.get("own_package")
        if isinstance(own_pkg, str) and own_pkg.strip():
            own_package_to_skill[_normalize_dep_name(own_pkg)] = (own_pkg.strip(), skill)
        for pkg in m.get("own_packages", []):
            if isinstance(pkg, str) and pkg.strip():
                own_package_to_skill[_normalize_dep_name(pkg)] = (pkg.strip(), skill)
        for sig in m.get("signals", []):
            t = sig.get("type")
            if t == "pyproject_dep":
                pyproject_deps[sig["name"].lower()] = skill
            elif t == "pyproject_section":
                pyproject_sections.append((sig["section"], skill))
            elif t == "python_import":
                python_imports[sig["module"]] = skill
            elif t == "python_regex":
                try:
                    python_regexes.append((re.compile(sig["pattern"], re.MULTILINE | re.DOTALL), skill))
                except re.error:
                    continue
            elif t == "file_glob":
                file_globs.append((sig["pattern"], skill))

    detected: set[str] = set()

    pyproject = root / "pyproject.toml"
    pyproject_text = ""
    project_name = ""
    if pyproject.is_file():
        try:
            pyproject_text = pyproject.read_text(errors="ignore")
        except OSError:
            pyproject_text = ""
        project_name = _extract_project_name(pyproject_text)
        text_lower = pyproject_text.lower()
        for name, skill in pyproject_deps.items():
            if re.search(rf'["\']{re.escape(name)}(?:[\[\s>=<!~,"\']|$)', text_lower):
                detected.add(skill)
        for section, skill in pyproject_sections:
            pattern = rf"^\s*\[\s*{re.escape(section)}(?:\.|\s*\])"
            if re.search(pattern, pyproject_text, re.MULTILINE):
                detected.add(skill)

    if python_imports or python_regexes:
        patterns = {
            mod: re.compile(
                rf"^\s*(?:from\s+{re.escape(mod)}(?:\.|\s)|import\s+{re.escape(mod)}(?:\.|\s|$|,))",
                re.M,
            )
            for mod in python_imports
        }
        files_scanned = 0
        for path in root.rglob("*.py"):
            rel = path.relative_to(root).parts
            if len(rel) > _PY_DEPTH_CAP or any(p in _SKIP_DIRS or p.startswith(".") for p in rel[:-1]):
                continue
            files_scanned += 1
            if files_scanned > _PY_FILE_CAP:
                break
            try:
                content = path.read_text(errors="ignore")
            except OSError:
                continue
            for mod, skill in python_imports.items():
                if skill in detected:
                    continue
                if patterns[mod].search(content):
                    detected.add(skill)
            for pattern, skill in python_regexes:
                if skill in detected:
                    continue
                if pattern.search(content):
                    detected.add(skill)

    for pattern, skill in file_globs:
        if skill in detected:
            continue
        candidates = list(root.glob(pattern)) + list(root.glob(f"*/{pattern}")) + list(root.glob(f"*/*/{pattern}"))
        if any(c.exists() and not _is_ignored_glob_candidate(root, c, pattern) for c in candidates):
            detected.add(skill)

    own_entry = own_package_to_skill.get(project_name) if project_name else None
    if own_entry is not None:
        detected.discard(own_entry[1])

    ordered = [m["skill"] for m in sorted(matchers, key=lambda x: -int(x.get("priority", 0)))]
    final_skills = [s for s in ordered if s in detected]

    parts: list[str] = []
    if intro:
        parts.append(intro)
    if own_entry is not None:
        own_pkg_display, own_skill = own_entry
        parts.append(
            f"Upstream library workspace detected (`{own_pkg_display}`). "
            f"Do NOT rely on `litestar:{own_skill}` or consumer skills for `{own_pkg_display}` internals or APIs — "
            "you are working on the library itself; treat this repository's source code as the source of truth "
            "(changes here may require a follow-up update to `litestar-skills`)."
        )
        if final_skills:
            qualified = ", ".join(f"litestar:{s}" for s in final_skills)
            parts.append(
                f"Detected stack skills: {qualified} "
                f"(use only for sibling-library conventions, never for `{own_pkg_display}` internals)."
            )
    elif final_skills:
        qualified = ", ".join(f"litestar:{s}" for s in final_skills)
        parts.append(
            f"Detected stack skills: {qualified}. Load the matching skill before implementing or reviewing changes."
        )

    result: dict[str, object] = {
        "detected_skills": final_skills,
        "context": " ".join(parts),
        "project_root": str(root),
    }
    if own_entry is not None:
        result["suppressed_own_skill"] = own_entry[1]
    return result


def main(argv: list[str]) -> int:
    """CLI entrypoint for _detector.py."""
    if len(argv) < 3:
        print('{"error":"usage: _detector.py <project_root> <skill_map_path>"}', file=sys.stderr)
        return 2
    root = Path(argv[1])
    map_path = Path(argv[2])
    if not root.is_dir():
        print("{}")
        return 0
    print(json.dumps(detect(root, map_path), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
