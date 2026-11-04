#!/bin/sh
# Litestar SessionStart context hook — 100% POSIX sh + awk (zero Python/jq dependencies).
# Supports: --harness <agy|claude|cursor|opencode|json> --project <dir>

set -eu

if [ "${LITESTAR_SKILLS_HOOK_DISABLE:-0}" = "1" ] || [ "${LITESTAR_SKILLS_HOOK_DISABLE:-}" = "true" ]; then
  printf '{}\n'
  exit 0
fi

HARNESS="claude"
PROJECT_DIR=""

while [ $# -gt 0 ]; do
  case "$1" in
    --harness)
      HARNESS="${2:-claude}"
      shift 2
      ;;
    --harness=*)
      HARNESS="${1#*=}"
      shift 1
      ;;
    --project)
      PROJECT_DIR="${2:-}"
      shift 2
      ;;
    --project=*)
      PROJECT_DIR="${1#*=}"
      shift 1
      ;;
    *)
      shift
      ;;
  esac
done

# Suppress duplicate Claude hook execution when running inside Cursor IDE.
if [ "$HARNESS" = "claude" ] && [ -n "${CURSOR_VERSION:-}" ]; then
  printf '{"continue":true}\n'
  exit 0
fi

STDIN_JSON=""
if [ ! -t 0 ]; then
  STDIN_JSON=$(cat || true)
fi

if [ -z "$PROJECT_DIR" ] && [ -n "$STDIN_JSON" ]; then
  PROJECT_DIR=$(printf '%s\n' "$STDIN_JSON" | awk '
    {
      buf = buf " " $0
    }
    END {
      if (match(buf, /"workspacePaths"[[:space:]]*:[[:space:]]*\[[[:space:]]*"[^"]+"/)) {
        s = substr(buf, RSTART, RLENGTH)
        sub(/^.*"workspacePaths"[[:space:]]*:[[:space:]]*\[[[:space:]]*"/, "", s)
        sub(/"$/, "", s)
        gsub(/\\\\/, "/", s)
        print s
        exit
      }
      if (match(buf, /"workspace_roots"[[:space:]]*:[[:space:]]*\[[[:space:]]*"[^"]+"/)) {
        s = substr(buf, RSTART, RLENGTH)
        sub(/^.*"workspace_roots"[[:space:]]*:[[:space:]]*\[[[:space:]]*"/, "", s)
        sub(/"$/, "", s)
        gsub(/\\\\/, "/", s)
        print s
        exit
      }
      if (match(buf, /"cwd"[[:space:]]*:[[:space:]]*"[^"]+"/)) {
        s = substr(buf, RSTART, RLENGTH)
        sub(/^.*"cwd"[[:space:]]*:[[:space:]]*"/, "", s)
        sub(/"$/, "", s)
        gsub(/\\\\/, "/", s)
        print s
        exit
      }
      if (match(buf, /"workspaceRoot"[[:space:]]*:[[:space:]]*"[^"]+"/)) {
        s = substr(buf, RSTART, RLENGTH)
        sub(/^.*"workspaceRoot"[[:space:]]*:[[:space:]]*"/, "", s)
        sub(/"$/, "", s)
        gsub(/\\\\/, "/", s)
        print s
        exit
      }
    }
  ')
fi

if [ -z "$PROJECT_DIR" ]; then
  PROJECT_DIR="${CURSOR_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-$(pwd)}}"
fi

json_escape() {
  awk '
    BEGIN { ORS = "" }
    {
      gsub(/\\/, "\\\\")
      gsub(/"/, "\\\"")
      gsub(/\r/, "")
      gsub(/\t/, "\\t")
      if (NR > 1) printf "\\n"
      printf "%s", $0
    }
  '
}

SKILLS=""
SKILLS_JSON=""

add_skill() {
  skill_name="$1"
  case " $SKILLS " in
    *" $skill_name "*) return ;;
  esac
  if [ -z "$SKILLS" ]; then
    SKILLS="$skill_name"
    SKILLS_JSON="\"$skill_name\""
  else
    SKILLS="$SKILLS $skill_name"
    SKILLS_JSON="$SKILLS_JSON, \"$skill_name\""
  fi
}

PYPROJECT="$PROJECT_DIR/pyproject.toml"
OWN_PACKAGE=""
if [ -f "$PYPROJECT" ]; then
  OWN_PACKAGE=$(awk '
    /^\[project\]/ { in_proj=1; next }
    /^\[/ { in_proj=0 }
    in_proj && /^[[:space:]]*name[[:space:]]*=/ {
      line = $0
      sub(/^[^=]*=[[:space:]]*"/, "", line)
      sub(/".*$/, "", line)
      gsub(/_/, "-", line)
      print tolower(line)
      exit
    }
  ' "$PYPROJECT" 2>/dev/null || true)

  grep -qi "litestar" "$PYPROJECT" 2>/dev/null && [ "$OWN_PACKAGE" != "litestar" ] && add_skill "litestar"
  grep -Eq "advanced[-_]alchemy" "$PYPROJECT" 2>/dev/null && [ "$OWN_PACKAGE" != "advanced-alchemy" ] && add_skill "advanced-alchemy"
  grep -qi "sqlspec" "$PYPROJECT" 2>/dev/null && [ "$OWN_PACKAGE" != "sqlspec" ] && add_skill "sqlspec"
  grep -qi "msgspec" "$PYPROJECT" 2>/dev/null && [ "$OWN_PACKAGE" != "msgspec" ] && add_skill "msgspec"
  grep -Eq "litestar[-_]granian|granian" "$PYPROJECT" 2>/dev/null && [ "$OWN_PACKAGE" != "litestar-granian" ] && add_skill "litestar-granian"
  grep -Eq "litestar[-_]saq" "$PYPROJECT" 2>/dev/null && [ "$OWN_PACKAGE" != "litestar-saq" ] && add_skill "litestar-saq"
  grep -Eq "litestar[-_]queues" "$PYPROJECT" 2>/dev/null && [ "$OWN_PACKAGE" != "litestar-queues" ] && add_skill "litestar-queues"
  grep -Eq "litestar[-_]security" "$PYPROJECT" 2>/dev/null && [ "$OWN_PACKAGE" != "litestar-security" ] && add_skill "litestar-security"
  grep -Eq "litestar[-_]autowire" "$PYPROJECT" 2>/dev/null && [ "$OWN_PACKAGE" != "litestar-autowire" ] && add_skill "litestar-autowire"
  grep -Eq "litestar[-_]vite" "$PYPROJECT" 2>/dev/null && [ "$OWN_PACKAGE" != "litestar-vite" ] && add_skill "litestar-vite"
  grep -Eq "litestar[-_]htmx" "$PYPROJECT" 2>/dev/null && [ "$OWN_PACKAGE" != "litestar-htmx" ] && add_skill "litestar-htmx"
  grep -Eq "litestar[-_]mcp|google[-_]adk|google[-_]genai" "$PYPROJECT" 2>/dev/null && [ "$OWN_PACKAGE" != "litestar-mcp" ] && add_skill "litestar-mcp"
  grep -Eq "litestar[-_]email" "$PYPROJECT" 2>/dev/null && [ "$OWN_PACKAGE" != "litestar-email" ] && add_skill "litestar-email"
  grep -qi "pytest" "$PYPROJECT" 2>/dev/null && add_skill "litestar-testing"
  grep -Eq "pytest[-_]databases" "$PYPROJECT" 2>/dev/null && [ "$OWN_PACKAGE" != "pytest-databases" ] && add_skill "pytest-databases"
  grep -qi "polyfactory" "$PYPROJECT" 2>/dev/null && [ "$OWN_PACKAGE" != "polyfactory" ] && add_skill "polyfactory"
  grep -Eq "zensical|mkdocstrings|shibuya|litestar[-_]sphinx[-_]theme" "$PYPROJECT" 2>/dev/null && add_skill "litestar-docs"
fi

if [ -f "$PROJECT_DIR/zensical.toml" ] || [ -f "$PROJECT_DIR/docs/conf.py" ]; then
  add_skill "litestar-docs"
fi
if [ -f "$PROJECT_DIR/vite.config.ts" ] && [ "$OWN_PACKAGE" != "litestar-vite" ]; then
  add_skill "litestar-vite"
fi
if [ -f "$PROJECT_DIR/Dockerfile" ]; then
  add_skill "litestar-deployment"
fi

if [ -n "$SKILLS" ]; then
  SKILL_SUMMARY="Detected Litestar stack skills for this workspace: ${SKILLS}."
else
  SKILL_SUMMARY="Available Litestar skills: litestar, sqlspec, advanced-alchemy, msgspec, litestar-granian, litestar-saq, litestar-queues, litestar-security, litestar-autowire, litestar-vite, litestar-htmx, litestar-mcp, litestar-email, litestar-testing, pytest-databases, polyfactory, litestar-docs, litestar-build, litestar-deployment, litestar-styleguide."
fi

CONTEXT="<EXTREMELY_IMPORTANT>
Litestar Framework Ecosystem Active
${SKILL_SUMMARY}
- Activate the matching Litestar skill before writing, refactoring, or reviewing Litestar application or library code.
- Match the project's existing stack (SQLSpec vs Advanced Alchemy, Provide vs Dishka, msgspec vs Pydantic, Zensical vs Sphinx).
- Keep all route handlers, guards, dependencies, and I/O async; enforce PEP 604 unions (T | None).
</EXTREMELY_IMPORTANT>"

ESCAPED=$(printf '%s' "$CONTEXT" | json_escape)

case "$HARNESS" in
  agy|antigravity)
    printf '{"injectSteps":[{"systemMessage":{"systemMessage":"%s"}}]}\n' "$ESCAPED"
    ;;
  cursor)
    printf '{"continue":true,"additional_context":"%s"}\n' "$ESCAPED"
    ;;
  opencode)
    printf '%s\n' "$CONTEXT"
    ;;
  json)
    printf '{"detected_skills":[%s],"context":"%s"}\n' "$SKILLS_JSON" "$ESCAPED"
    ;;
  claude|vscode|*)
    printf '{"continue":true,"systemMessage":"%s","hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$ESCAPED" "$ESCAPED"
    ;;
esac
