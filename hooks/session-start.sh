#!/usr/bin/env bash
# hooks/session-start.sh
# SessionStart / PreInvocation hook for litestar-skills. Detects host via env
# vars and emits the host-correct JSON shape with project-aware skill reminders.
#
# Hosts:
#   CLAUDE_PLUGIN_ROOT      -> Claude Code     -> hookSpecificOutput.additionalContext
#   CODEX_PLUGIN_ROOT       -> Codex CLI       -> hookSpecificOutput.additionalContext
#   ANTIGRAVITY_PLUGIN_ROOT -> Antigravity CLI -> injectSteps[].ephemeralMessage
#   CURSOR_PLUGIN_ROOT      -> Cursor          -> additional_context
#   (none of the above)     -> Unknown         -> additional_context (Cursor-shape fallback)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=hooks/lib/detect-env.sh
source "${SCRIPT_DIR}/lib/detect-env.sh"

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
if _resolve_python >/dev/null 2>&1; then
    _session_python="$(_resolve_python)"
fi

stdin_payload=""
if [[ ! -t 0 ]]; then
    if (( BASH_VERSINFO[0] >= 4 )); then
        IFS= read -r -t 0.05 -d '' stdin_payload || true
    else
        IFS= read -r -t 1 -d '' stdin_payload || true
    fi
fi

has_stdin="0"
if [[ -n "${stdin_payload//[[:space:]]/}" ]]; then
    has_stdin="1"
fi

# Determine project root: prefer workspacePaths[0] from stdin JSON when present, else cwd.
project_root="${PWD}"

if [[ "$has_stdin" == "1" && -n "$_session_python" ]]; then
    stdin_info="$("$_session_python" - "$host" "$stdin_payload" <<'PY'
import json, sys
host = sys.argv[1]
raw = sys.argv[2]
try:
    payload = json.loads(raw)
except Exception:
    payload = {}
if not isinstance(payload, dict):
    payload = {}

inv = payload.get("invocationNum", 1)
try:
    inv_num = int(inv)
except Exception:
    inv_num = 1

if host == "antigravity" and inv_num > 1:
    print("SKIP")
    sys.exit(0)

ws = payload.get("workspacePaths")
if isinstance(ws, list) and ws and isinstance(ws[0], str) and ws[0].strip():
    print(ws[0].strip())
PY
)"
    if [[ "$stdin_info" == "SKIP" ]]; then
        echo "{}"
        exit 0
    elif [[ -n "$stdin_info" && -d "$stdin_info" ]]; then
        project_root="$stdin_info"
    fi
fi

# Run detection -> JSON ({"detected_skills": [...], "context": "...", "project_root": "..."}).
detector_output="$(detect_env "$project_root")"

# Short-circuit if disabled (detector returned "{}").
if [[ "$detector_output" == "{}" ]]; then
    echo "{}"
    exit 0
fi

if [[ -n "$_session_python" ]]; then
    "$_session_python" - "$host" "$detector_output" "$has_stdin" <<'PY'
import json, sys
host = sys.argv[1]
data = json.loads(sys.argv[2])
has_stdin = sys.argv[3] == "1"
context = data.get("context", "")
detected_skills = data.get("detected_skills") or []
suppressed_own = data.get("suppressed_own_skill")

if host in ("claude", "codex"):
    out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}
elif host == "antigravity":
    if has_stdin and not detected_skills and not suppressed_own:
        out = {}
    else:
        out = {"injectSteps": [{"ephemeralMessage": context}]}
else:
    out = {"additional_context": context}

print(json.dumps(out, ensure_ascii=False))
PY
else
    # Pure-bash fallback (Python should be present, but stay safe).
    case "$host" in
        claude|codex)
            printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":""}}\n' ;;
        antigravity)
            printf '{"injectSteps":[{"ephemeralMessage":""}]}\n' ;;
        *)
            printf '{"additional_context":""}\n' ;;
    esac
fi
