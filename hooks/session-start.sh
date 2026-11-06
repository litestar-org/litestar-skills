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
IS_PLUGIN_REPO=0
IS_UPSTREAM=0
HAS_CORE=0

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

  case "$OWN_PACKAGE" in
    litestar-skills)
      IS_PLUGIN_REPO=1
      ;;
    litestar|advanced-alchemy|sqlspec|msgspec|litestar-granian|litestar-saq|litestar-queues|litestar-security|litestar-autowire|litestar-vite|litestar-htmx|litestar-mcp|litestar-email|pytest-databases|polyfactory)
      IS_UPSTREAM=1
      HAS_CORE=1
      ;;
  esac

  if [ "$IS_PLUGIN_REPO" -eq 1 ]; then
    add_skill "litestar-styleguide"
  else
    grep -qi "litestar" "$PYPROJECT" 2>/dev/null && { HAS_CORE=1; [ "$OWN_PACKAGE" != "litestar" ] && add_skill "litestar" || true; }
    grep -Eq "advanced[-_]alchemy" "$PYPROJECT" 2>/dev/null && { HAS_CORE=1; [ "$OWN_PACKAGE" != "advanced-alchemy" ] && add_skill "advanced-alchemy" || true; }
    grep -qi "sqlspec" "$PYPROJECT" 2>/dev/null && { HAS_CORE=1; [ "$OWN_PACKAGE" != "sqlspec" ] && add_skill "sqlspec" || true; }
    grep -qi "msgspec" "$PYPROJECT" 2>/dev/null && { HAS_CORE=1; [ "$OWN_PACKAGE" != "msgspec" ] && add_skill "msgspec" || true; }
    grep -Eq "litestar[-_]granian" "$PYPROJECT" 2>/dev/null && { HAS_CORE=1; [ "$OWN_PACKAGE" != "litestar-granian" ] && add_skill "litestar-granian" || true; }
    grep -Eq "litestar[-_]saq" "$PYPROJECT" 2>/dev/null && { HAS_CORE=1; [ "$OWN_PACKAGE" != "litestar-saq" ] && add_skill "litestar-saq" || true; }
    grep -Eq "litestar[-_]queues" "$PYPROJECT" 2>/dev/null && { HAS_CORE=1; [ "$OWN_PACKAGE" != "litestar-queues" ] && add_skill "litestar-queues" || true; }
    grep -Eq "litestar[-_]security" "$PYPROJECT" 2>/dev/null && { HAS_CORE=1; [ "$OWN_PACKAGE" != "litestar-security" ] && add_skill "litestar-security" || true; }
    grep -Eq "litestar[-_]autowire" "$PYPROJECT" 2>/dev/null && { HAS_CORE=1; [ "$OWN_PACKAGE" != "litestar-autowire" ] && add_skill "litestar-autowire" || true; }
    grep -Eq "litestar[-_]vite" "$PYPROJECT" 2>/dev/null && { HAS_CORE=1; [ "$OWN_PACKAGE" != "litestar-vite" ] && add_skill "litestar-vite" || true; }
    grep -Eq "litestar[-_]htmx" "$PYPROJECT" 2>/dev/null && { HAS_CORE=1; [ "$OWN_PACKAGE" != "litestar-htmx" ] && add_skill "litestar-htmx" || true; }
    grep -Eq "litestar[-_]mcp" "$PYPROJECT" 2>/dev/null && { HAS_CORE=1; [ "$OWN_PACKAGE" != "litestar-mcp" ] && add_skill "litestar-mcp" || true; }
    grep -Eq "litestar[-_]email" "$PYPROJECT" 2>/dev/null && { HAS_CORE=1; [ "$OWN_PACKAGE" != "litestar-email" ] && add_skill "litestar-email" || true; }
    grep -Eq "pytest[-_]databases" "$PYPROJECT" 2>/dev/null && { HAS_CORE=1; [ "$OWN_PACKAGE" != "pytest-databases" ] && add_skill "pytest-databases" || true; }
    grep -qi "polyfactory" "$PYPROJECT" 2>/dev/null && { HAS_CORE=1; [ "$OWN_PACKAGE" != "polyfactory" ] && add_skill "polyfactory" || true; }
    grep -Eq "litestar[-_]sphinx[-_]theme" "$PYPROJECT" 2>/dev/null && { HAS_CORE=1; add_skill "litestar-docs"; }

    if [ "$HAS_CORE" -eq 1 ]; then
      grep -qi "granian" "$PYPROJECT" 2>/dev/null && [ "$OWN_PACKAGE" != "litestar-granian" ] && add_skill "litestar-granian" || true
      grep -Eq "google[-_]adk|google[-_]genai" "$PYPROJECT" 2>/dev/null && [ "$OWN_PACKAGE" != "litestar-mcp" ] && add_skill "litestar-mcp" || true
      grep -qi "pytest" "$PYPROJECT" 2>/dev/null && add_skill "litestar-testing" || true
      grep -Eq "zensical|mkdocstrings|shibuya" "$PYPROJECT" 2>/dev/null && add_skill "litestar-docs" || true
    fi
  fi
fi

if [ "$HAS_CORE" -eq 1 ] && [ "$IS_PLUGIN_REPO" -eq 0 ]; then
  if [ -f "$PROJECT_DIR/zensical.toml" ] || [ -f "$PROJECT_DIR/docs/conf.py" ]; then
    add_skill "litestar-docs"
  fi
  if [ -f "$PROJECT_DIR/vite.config.ts" ] || [ -f "$PROJECT_DIR/vite.config.js" ] || [ -f "$PROJECT_DIR/vite.config.mjs" ]; then
    [ "$OWN_PACKAGE" != "litestar-vite" ] && add_skill "litestar-vite" || true
  fi
  if [ -f "$PROJECT_DIR/alembic.ini" ] && [ "$OWN_PACKAGE" != "advanced-alchemy" ] && [ "$OWN_PACKAGE" != "sqlspec" ]; then
    add_skill "advanced-alchemy"
  fi
  if [ -f "$PROJECT_DIR/Dockerfile" ] || [ -f "$PROJECT_DIR/Containerfile" ]; then
    add_skill "litestar-deployment"
  fi
  add_skill "litestar-styleguide"
fi

if [ -z "$SKILLS" ] && [ "$IS_UPSTREAM" -eq 0 ] && [ "$IS_PLUGIN_REPO" -eq 0 ]; then
  case "$HARNESS" in
    agy|antigravity)
      printf '{}\n'
      ;;
    cursor)
      printf '{"continue":true}\n'
      ;;
    opencode)
      ;;
    json)
      printf '{"detected_skills":[],"context":""}\n'
      ;;
    claude|vscode|*)
      printf '{"continue":true}\n'
      ;;
  esac
  exit 0
fi

if [ "$IS_PLUGIN_REPO" -eq 1 ]; then
  CONTEXT="Litestar skills plugin workspace (skills: ${SKILLS}). Follow skills/litestar-styleguide and validate all changes with make check."
elif [ "$IS_UPSTREAM" -eq 1 ]; then
  CONTEXT="Litestar upstream package workspace ('${OWN_PACKAGE}'; companion skills: ${SKILLS}). Treat this repository's own source code and tests as the authority over its consumer skill; keep async I/O and PEP 604 unions (T | None)."
else
  CONTEXT="Litestar ecosystem detected in workspace (skills: ${SKILLS}). Load the matching skill before writing, refactoring, or reviewing code; match the project's existing stack (SQLSpec vs Advanced Alchemy, Provide vs Dishka, msgspec vs Pydantic, Zensical vs Sphinx); keep handlers, guards, dependencies, and I/O async with PEP 604 unions (T | None)."
fi

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
    printf '{"continue":true,"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$ESCAPED"
    ;;
esac
