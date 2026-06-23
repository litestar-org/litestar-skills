#!/usr/bin/env bash
# hooks/session-start.sh
# SessionStart hook for litestar-skills. Detects host via env vars and emits the
# host-correct JSON shape with project-aware skill reminders.
#
# Hosts:
#   CLAUDE_PLUGIN_ROOT  -> Claude Code  -> hookSpecificOutput.additionalContext
#   CODEX_PLUGIN_ROOT   -> Codex CLI    -> hookSpecificOutput.additionalContext
#   ANTIGRAVITY_PLUGIN_ROOT -> Antigravity CLI -> hookSpecificOutput.additionalContext
#   CURSOR_PLUGIN_ROOT  -> Cursor       -> additional_context
#   (none of the above) -> Unknown      -> additional_context (Cursor-shape fallback)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=hooks/lib/detect-env.sh
source "${SCRIPT_DIR}/lib/detect-env.sh"

# Determine project root: prefer cwd; the detector resolves further.
project_root="${PWD}"

# Run detection -> JSON ({"detected_skills": [...], "context": "...", "project_root": "..."}).
detector_output="$(detect_env "$project_root")"

# Short-circuit if disabled (detector returned "{}").
if [[ "$detector_output" == "{}" ]]; then
    echo "{}"
    exit 0
fi

# Host-specific output shaping using a single Python pass for safe JSON handling.
host="unknown"
if [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
    host="claude"
elif [[ -n "${CODEX_PLUGIN_ROOT:-}" ]]; then
    host="codex"
elif [[ -n "${ANTIGRAVITY_PLUGIN_ROOT:-}" || -n "${AGY_PLUGIN_ROOT:-}" ]]; then
    host="antigravity"
elif [[ -n "${CURSOR_PLUGIN_ROOT:-}" ]]; then
    host="cursor"
fi

_session_python=""
if _session_python=$(_resolve_python); then
    "$_session_python" - "$host" "$detector_output" <<'PY'
import json, sys
host = sys.argv[1]
data = json.loads(sys.argv[2])
context = data.get("context", "")

if host in ("claude", "codex", "antigravity"):
    out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}
else:
    # cursor + unknown share the same shape
    out = {"additional_context": context}

print(json.dumps(out, ensure_ascii=False))
PY
else
    # Pure-bash fallback (Python should be present, but stay safe).
    case "$host" in
        claude|codex)
            printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":""}}\n' ;;
        *)
            printf '{"additional_context":""}\n' ;;
    esac
fi
