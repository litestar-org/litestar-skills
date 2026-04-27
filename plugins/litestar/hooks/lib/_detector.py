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
    ".git",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
}
_PY_FILE_CAP = 50
_PY_DEPTH_CAP = 4


def detect(root: Path, map_path: Path) -> dict[str, object]:
    map_data = json.loads(map_path.read_text())
    matchers = map_data["matchers"]
    intro = map_data.get("static_intro", "")

    pyproject_deps: dict[str, str] = {}
    pyproject_sections: list[tuple[str, str]] = []
    python_imports: dict[str, str] = {}
    python_regexes: list[tuple[re.Pattern[str], str]] = []
    file_globs: list[tuple[str, str]] = []
    for m in matchers:
        skill = m["skill"]
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
    if pyproject.is_file():
        try:
            pyproject_text = pyproject.read_text(errors="ignore")
        except OSError:
            pyproject_text = ""
        text_lower = pyproject_text.lower()
        for name, skill in pyproject_deps.items():
            if re.search(rf'["\']{re.escape(name)}(?:[\[\s>=<!~,"\']|$)', text_lower):
                detected.add(skill)
        for section, skill in pyproject_sections:
            # Match `[tool.sqlspec]` or `[tool.sqlspec.something]` (including under-bracket variants).
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
        if any(c.exists() for c in candidates):
            detected.add(skill)

    ordered = [m["skill"] for m in sorted(matchers, key=lambda x: -int(x.get("priority", 0)))]
    final_skills = [s for s in ordered if s in detected]

    matchers_by_skill = {m["skill"]: m for m in matchers}
    parts: list[str] = []
    if intro:
        parts.append(intro)
    for skill in final_skills:
        reminder = matchers_by_skill[skill].get("reminder")
        if reminder:
            parts.append(reminder)

    return {
        "detected_skills": final_skills,
        "context": "\n\n".join(parts),
        "project_root": str(root),
    }


def main(argv: list[str]) -> int:
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
