"""Cross-platform helpers for subprocess-based hook tests.

Windows ships a ``C:\\Windows\\System32\\bash.exe`` stub that prints a WSL
install banner instead of running scripts. The hook tests invoke bash to
exercise ``detect-env.sh`` / ``session-start.sh``, so they need to find the
real Git Bash and inherit a usable PATH.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def bash_executable() -> str:
    """Return a usable bash path. Prefers Git Bash on Windows over the WSL stub."""
    if sys.platform == "win32":
        for candidate in (
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files (x86)\Git\bin\bash.exe",
        ):
            if Path(candidate).is_file():
                return candidate
    return "bash"


def subprocess_env(*, overrides: dict[str, str] | None = None) -> dict[str, str]:
    """Build an env mapping for subprocess.run.

    On Windows, inherit ``os.environ`` so Git Bash and any uv-managed Python
    remain on PATH. On POSIX, lock PATH down to the canonical system dirs for
    determinism — these tests should not depend on the developer's shell.
    """
    if sys.platform == "win32":
        env = dict(os.environ)
    else:
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin"}
    if overrides:
        env.update(overrides)
    return env
