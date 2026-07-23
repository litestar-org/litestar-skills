"""Fail when audited package releases drift from PyPI or local validation state."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

if sys.version_info >= (3, 11):
    import tomllib as _tomllib
else:  # pragma: no cover - py310 fallback path
    import tomli as _tomllib  # type: ignore[import-not-found,unused-ignore]

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "tools" / "upstream-releases.toml"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
LOCK_PATH = REPO_ROOT / "uv.lock"
PYPI_URL = "https://pypi.org/pypi/{name}/json"


@dataclass(frozen=True)
class UpstreamPackage:
    """One audited distribution and its shipped guidance."""

    pypi: str
    version: str
    date: str
    tag: str
    skills: tuple[str, ...]
    imports: tuple[str, ...]


def select_latest_final(releases: dict[str, list[dict[str, Any]]]) -> Version:
    """Return the newest final release containing a non-yanked artifact."""
    candidates = [
        Version(raw_version)
        for raw_version, artifacts in releases.items()
        if not Version(raw_version).is_prerelease
        and not Version(raw_version).is_devrelease
        and artifacts
        and any(not artifact.get("yanked", False) for artifact in artifacts)
    ]
    if not candidates:
        msg = "PyPI project has no non-yanked final releases"
        raise ValueError(msg)
    return max(candidates)


def validation_floor(requirement: str) -> str | None:
    """Return the explicit inclusive lower bound from a requirement."""
    parsed = Requirement(requirement)
    floors = [Version(spec.version) for spec in parsed.specifier if spec.operator in {">=", "=="}]
    return str(max(floors)) if floors else None


def load_manifest(path: Path = MANIFEST_PATH) -> tuple[UpstreamPackage, ...]:
    """Load and validate the release manifest's structural fields."""
    with path.open("rb") as file:
        data = _tomllib.load(file)
    packages: list[UpstreamPackage] = []
    for raw in data.get("package", []):
        packages.append(
            UpstreamPackage(
                pypi=str(raw["pypi"]),
                version=str(raw["version"]),
                date=str(raw["date"]),
                tag=str(raw["tag"]),
                skills=tuple(str(value) for value in raw["skills"]),
                imports=tuple(str(value) for value in raw["imports"]),
            )
        )
    return tuple(packages)


def load_validation_requirements(path: Path = PYPROJECT_PATH) -> dict[str, str]:
    """Return direct requirements in the validation optional dependency group."""
    with path.open("rb") as file:
        data = _tomllib.load(file)
    requirements = data["project"]["optional-dependencies"]["validation"]
    return {canonicalize_name(Requirement(raw).name): raw for raw in requirements}


def load_locked_versions(path: Path = LOCK_PATH) -> dict[str, str]:
    """Return exact versions recorded in uv.lock."""
    with path.open("rb") as file:
        data = _tomllib.load(file)
    return {canonicalize_name(str(package["name"])): str(package["version"]) for package in data.get("package", [])}


def fetch_pypi_releases(package: str) -> dict[str, list[dict[str, Any]]]:
    """Fetch a project's release artifact map from the official PyPI API."""
    with urlopen(PYPI_URL.format(name=package), timeout=30) as response:  # noqa: S310
        payload = cast("dict[str, Any]", json.load(response))
    return cast("dict[str, list[dict[str, Any]]]", payload["releases"])


def check_package(
    package: UpstreamPackage,
    *,
    root: Path,
    pypi_releases: dict[str, list[dict[str, Any]]],
    validation_requirements: dict[str, str],
    locked_versions: dict[str, str],
) -> list[str]:
    """Return all freshness and local-consistency errors for one package."""
    errors: list[str] = []
    expected = Version(package.version)
    latest = select_latest_final(pypi_releases)
    if latest != expected:
        errors.append(f"{package.pypi}: PyPI latest final is {latest}, manifest is {expected}")

    canonical_name = canonicalize_name(package.pypi)
    requirement = validation_requirements.get(canonical_name)
    if requirement is None:
        errors.append(f"{package.pypi}: missing direct validation dependency")
    else:
        floor = validation_floor(requirement)
        if floor != package.version:
            errors.append(f"{package.pypi}: validation floor is {floor or 'unset'}, manifest is {package.version}")

    locked = locked_versions.get(canonical_name)
    if locked != package.version:
        errors.append(f"{package.pypi}: lock version is {locked or 'missing'}, manifest is {package.version}")

    if not package.tag:
        errors.append(f"{package.pypi}: immutable tag is empty")
    if not package.date:
        errors.append(f"{package.pypi}: audit date is empty")
    if not package.imports:
        errors.append(f"{package.pypi}: import roots are empty")
    for skill in package.skills:
        if not (root / skill).is_dir():
            errors.append(f"{package.pypi}: canonical skill path is missing: {skill}")
    return errors


def check(root: Path = REPO_ROOT) -> list[str]:
    """Check every manifest entry against PyPI, pyproject, lock, and skill paths."""
    packages = load_manifest(root / "tools" / "upstream-releases.toml")
    validation = load_validation_requirements(root / "pyproject.toml")
    locked = load_locked_versions(root / "uv.lock")
    errors: list[str] = []
    for package in packages:
        try:
            releases = fetch_pypi_releases(package.pypi)
            errors.extend(
                check_package(
                    package,
                    root=root,
                    pypi_releases=releases,
                    validation_requirements=validation,
                    locked_versions=locked,
                )
            )
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            errors.append(f"{package.pypi}: PyPI check failed: {exc}")
    return errors


def main(argv: list[str] | None = None) -> int:
    """Run the release freshness checker."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    errors = check()
    for error in errors:
        print(f"[FAIL] {error}", file=sys.stderr)
    if errors:
        print(f"\n{len(errors)} upstream release consistency error(s)", file=sys.stderr)
        return 1
    print(f"[ OK ] {len(load_manifest())} upstream releases match PyPI, validation floors, and uv.lock")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
