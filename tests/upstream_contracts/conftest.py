"""Skip upstream contract modules when their package isn't installed.

The cross-platform ``test`` job installs only the ``dev`` extra, so the upstream
libraries these contracts import are absent there. The contracts run in the jobs
that install the ``validation`` extra (``make check`` and the upstream workflow).

A module is ignored only when its base package is missing entirely — when the
package is installed but an audited symbol has moved, the import still fails and
the contract reports the drift, which is the whole point of the suite.
"""

import importlib.util

# Each contract module imports one upstream package at load time. Map the module
# to that package so collection can be skipped when the package is unavailable.
_MODULE_PACKAGES: dict[str, str] = {
    "test_advanced_alchemy": "advanced_alchemy",
    "test_litestar": "litestar",
    "test_litestar_autowire": "litestar_autowire",
    "test_litestar_email": "litestar_email",
    "test_litestar_granian": "litestar_granian",
    "test_litestar_htmx": "litestar_htmx",
    "test_litestar_mcp": "litestar_mcp",
    "test_litestar_queues": "litestar_queues",
    "test_litestar_saq": "litestar_saq",
    "test_litestar_vite": "litestar_vite",
    "test_msgspec": "msgspec",
    "test_polyfactory": "polyfactory",
    "test_pytest_databases": "pytest_databases",
    "test_sqlspec": "sqlspec",
}


def _is_installed(package: str) -> bool:
    try:
        return importlib.util.find_spec(package) is not None
    except ModuleNotFoundError:
        return False


collect_ignore: list[str] = [
    f"{module}.py" for module, package in _MODULE_PACKAGES.items() if not _is_installed(package)
]
