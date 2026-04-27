#!/usr/bin/env bash
# hooks/lib/detect-env.sh
# Project-aware library detection for litestar-skills.
#
# CLI usage:   bash hooks/lib/detect-env.sh <project_root>
# Sourced use: source hooks/lib/detect-env.sh; detect_env "<project_root>"
#
# Emits JSON to stdout:
#   { "detected_skills": [...], "context": "<reminder text>", "project_root": "<path>" }
#
# Honors LITESTAR_SKILLS_HOOK_DISABLE=1 (emits "{}" and exits 0).
#
# Detection logic lives in hooks/lib/_detector.py — this script is a thin
# bash wrapper that resolves paths and short-circuits when disabled.

set -euo pipefail

_lib_dir() { cd "$(dirname "${BASH_SOURCE[0]}")" && pwd; }
LIB_DIR="$(_lib_dir)"
SKILL_MAP_PATH="${LIB_DIR}/skill-map.json"
DETECTOR_PY="${LIB_DIR}/_detector.py"

# Resolve a working Python interpreter. Honors LITESTAR_SKILLS_PYTHON when set,
# then tries python3, then python. Each candidate is verified by importing the
# stdlib modules the detector actually uses — bare `command -v` is not enough
# because Windows ships a Microsoft Store python3 stub, and corrupted uv Python
# installs surface as `SRE module mismatch` only when stdlib is imported.
_resolve_python() {
    local candidates=()
    [[ -n "${LITESTAR_SKILLS_PYTHON:-}" ]] && candidates+=("${LITESTAR_SKILLS_PYTHON}")
    candidates+=(python3 python)
    local candidate
    for candidate in "${candidates[@]}"; do
        command -v "$candidate" >/dev/null 2>&1 || continue
        "$candidate" -c 'import json, re' >/dev/null 2>&1 || continue
        printf '%s' "$candidate"
        return 0
    done
    return 1
}

# Pure-bash JSON string escape (last-resort fallback when no python is usable).
_json_escape() {
    local s="$1"
    s="${s//\\/\\\\}"; s="${s//\"/\\\"}"
    s="${s//$'\n'/\\n}"; s="${s//$'\r'/\\r}"; s="${s//$'\t'/\\t}"
    printf '%s' "$s"
}

detect_env() {
    local project_root="${1:-$PWD}"
    [[ -d "$project_root" ]] || { echo "{}"; return 0; }
    if [[ "${LITESTAR_SKILLS_HOOK_DISABLE:-0}" == "1" ]]; then
        echo "{}"
        return 0
    fi
    local py
    if py=$(_resolve_python); then
        "$py" "$DETECTOR_PY" "$project_root" "$SKILL_MAP_PATH"
        return $?
    fi
    # Pure-bash fallback: emit minimal JSON with intro only.
    printf '{"detected_skills":[],"context":%s,"project_root":%s}\n' \
        "\"$(_json_escape "litestar loaded.")\"" \
        "\"$(_json_escape "$project_root")\""
}

# CLI mode (only when executed directly, not when sourced).
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    detect_env "${1:-$PWD}"
fi
