#!/usr/bin/env bash
# Compatibility wrapper for the Python implementation.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "${repo_root}/tools/sync-codex-package.py" "$@"
