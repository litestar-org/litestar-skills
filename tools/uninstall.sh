#!/usr/bin/env bash
# litestar-skills — multi-host uninstaller
#
# Reverses tools/install.sh. Removes symlinks, clones, and marketplace
# entries for hosts we auto-installed. Prints revert instructions for
# hosts where install was instruction-only (claude/cursor/vscode).

set -euo pipefail

VERSION="0.0.1"
PLUGIN_NAME="litestar-skills"
REPO_SLUG="cofin/litestar-skills"

# =============================================================================
# Formatting (same as install.sh)
# =============================================================================
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    BLUE=$'\033[1;34m'; GREEN=$'\033[1;32m'; RED=$'\033[1;31m'
    YELLOW=$'\033[1;33m'; BOLD=$'\033[1m'; NC=$'\033[0m'
else
    BLUE=""; GREEN=""; RED=""; YELLOW=""; BOLD=""; NC=""
fi

INFO="${BLUE}ℹ${NC}"
OK="${GREEN}✓${NC}"
WARN="${YELLOW}⚠${NC}"
ERROR="${RED}✖${NC}"

log_info()  { printf "%s %s\n" "$INFO" "$*"; }
log_ok()    { printf "%s %s\n" "$OK"   "$*"; }
log_warn()  { printf "%s %s\n" "$WARN" "$*" >&2; }
log_error() { printf "%s %s\n" "$ERROR" "$*" >&2; }

# =============================================================================
# Args
# =============================================================================
DRY_RUN=0
FORCE=0
ONLY_HOSTS=()
SKIP_HOSTS=()
CLEAN_CLAUDE_SETTINGS=0

usage() {
    cat <<USAGE
${BOLD}litestar-skills uninstaller v${VERSION}${NC}

Usage: $(basename "$0") [options]

Options:
  --dry-run            Print planned removals without executing.
  --force              Skip confirmations.
  --only <host>        Uninstall only for the named host (repeatable).
  --skip <host>        Skip the named host (repeatable).
  --claude-settings    Also remove the repo from
                       ~/.claude/settings.json extraKnownMarketplaces.
  --version            Print version.
  --help               Print this message.

Hosts: claude, gemini, codex, opencode, cursor, vscode
USAGE
}

# shellcheck disable=SC2034  # FORCE kept for install.sh API parity; uninstall is inherently idempotent
while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run)          DRY_RUN=1; shift ;;
        --force)            FORCE=1; shift ;;
        --only)             ONLY_HOSTS+=("$2"); shift 2 ;;
        --skip)             SKIP_HOSTS+=("$2"); shift 2 ;;
        --claude-settings)  CLEAN_CLAUDE_SETTINGS=1; shift ;;
        --version)          echo "$VERSION"; exit 0 ;;
        --help|-h)          usage; exit 0 ;;
        *)                  log_error "Unknown argument: $1"; usage; exit 2 ;;
    esac
done

if [ "$(id -u)" -eq 0 ]; then
    log_error "Do not run uninstaller as root."
    exit 1
fi

should_uninstall() {
    local host="$1"
    if [ ${#ONLY_HOSTS[@]} -gt 0 ]; then
        for h in "${ONLY_HOSTS[@]}"; do [ "$h" = "$host" ] && return 0; done
        return 1
    fi
    for h in "${SKIP_HOSTS[@]}"; do [ "$h" = "$host" ] && return 1; done
    return 0
}

run() {
    if [ "$DRY_RUN" -eq 1 ]; then
        printf "%s %s\n" "${YELLOW}[dry-run]${NC}" "$*"
    else
        "$@"
    fi
}

has_cli() { command -v "$1" >/dev/null 2>&1; }

STATUSES=()

# =============================================================================
# Per-host uninstallers
# =============================================================================

uninstall_gemini() {
    should_uninstall gemini || return 0
    if ! has_cli gemini; then
        STATUSES+=("gemini:cli-not-found")
        return 0
    fi
    log_info "${BOLD}Uninstalling from Gemini CLI...${NC}"
    if gemini extensions list 2>/dev/null | grep -q "$PLUGIN_NAME"; then
        run gemini extensions uninstall "$PLUGIN_NAME" || {
            STATUSES+=("gemini:failed")
            return 0
        }
        log_ok "Gemini extension removed"
        STATUSES+=("gemini:removed")
    else
        log_info "Extension not installed"
        STATUSES+=("gemini:not-present")
    fi
}

uninstall_codex() {
    should_uninstall codex || return 0
    log_info "${BOLD}Uninstalling from Codex CLI...${NC}"
    local target="${HOME}/.codex/plugins/${PLUGIN_NAME}"
    local marketplace="${HOME}/.agents/plugins/marketplace.json"

    if [ -d "$target" ]; then
        run rm -rf "$target"
    fi

    if [ -f "$marketplace" ]; then
        if [ "$DRY_RUN" -eq 1 ]; then
            printf "%s Remove %s entry from %s\n" "${YELLOW}[dry-run]${NC}" "$PLUGIN_NAME" "$marketplace"
        else
            python3 - "$marketplace" <<'PYEOF'
import json, sys, os
path = sys.argv[1]
with open(path) as f:
    data = json.load(f)
plugins = [p for p in data.get("plugins", []) if p.get("name") != "litestar-skills"]
data["plugins"] = plugins
with open(path, "w") as f:
    json.dump(data, f, indent=2)
PYEOF
        fi
    fi
    log_ok "Codex plugin removed from ${target}"
    STATUSES+=("codex:removed")
}

uninstall_opencode() {
    should_uninstall opencode || return 0
    log_info "${BOLD}Uninstalling from OpenCode...${NC}"
    local clone_dir="${HOME}/.config/opencode/${PLUGIN_NAME}"
    local plugin_link="${HOME}/.config/opencode/plugins/${PLUGIN_NAME}.js"

    if [ -L "$plugin_link" ] || [ -e "$plugin_link" ]; then
        run rm -f "$plugin_link"
    fi
    if [ -d "$clone_dir" ]; then
        run rm -rf "$clone_dir"
    fi
    log_ok "OpenCode plugin removed"
    STATUSES+=("opencode:removed")
}

uninstall_claude() {
    should_uninstall claude || return 0
    log_info "${BOLD}Claude Code teardown...${NC}"

    if [ "$CLEAN_CLAUDE_SETTINGS" -eq 1 ]; then
        local settings="${HOME}/.claude/settings.json"
        if [ -f "$settings" ]; then
            if [ "$DRY_RUN" -eq 1 ]; then
                printf "%s Remove %s from extraKnownMarketplaces in %s\n" "${YELLOW}[dry-run]${NC}" "$REPO_SLUG" "$settings"
            else
                python3 - "$settings" "$REPO_SLUG" <<'PYEOF'
import json, sys
path, slug = sys.argv[1], sys.argv[2]
with open(path) as f:
    data = json.load(f)
mks = [m for m in data.get("extraKnownMarketplaces", []) if m != slug]
data["extraKnownMarketplaces"] = mks
with open(path, "w") as f:
    json.dump(data, f, indent=2)
PYEOF
                log_ok "Removed ${REPO_SLUG} from ~/.claude/settings.json"
            fi
        fi
    fi

    cat <<CLAUDE_INSTRUCTIONS

${BOLD}Next step (inside Claude Code):${NC}

  /plugin uninstall ${PLUGIN_NAME}
  /plugin marketplace remove litestar-marketplace

CLAUDE_INSTRUCTIONS
    STATUSES+=("claude:instructions-printed")
}

uninstall_cursor() {
    should_uninstall cursor || return 0
    log_info "${BOLD}Cursor teardown...${NC}"
    cat <<CURSOR_INSTRUCTIONS

Remove the Remote Rule in Cursor:

  Cursor → Settings → Rules → Delete the litestar-skills rule

If you cloned the skills/ tree into .agents/skills/ or .cursor/skills/,
remove those directories manually.

CURSOR_INSTRUCTIONS
    STATUSES+=("cursor:instructions-printed")
}

uninstall_vscode() {
    should_uninstall vscode || return 0
    log_info "${BOLD}VS Code / Copilot teardown...${NC}"
    local target="${HOME}/.copilot/${PLUGIN_NAME}"
    cat <<VSCODE_INSTRUCTIONS

Remove the clone and the chat.skillsLocations entry:

  rm -rf ${target}
  # Remove the "${target}/skills" key from chat.skillsLocations in settings.json

VSCODE_INSTRUCTIONS
    STATUSES+=("vscode:instructions-printed")
}

# =============================================================================
# Summary
# =============================================================================
print_summary() {
    echo ""
    echo "${BOLD}=== Uninstall Summary ===${NC}"
    for entry in "${STATUSES[@]}"; do
        host="${entry%%:*}"
        status="${entry#*:}"
        case "$status" in
            removed|instructions-printed)
                printf "  %s %-10s %s\n" "$OK" "$host" "$status" ;;
            not-present|cli-not-found)
                printf "  %s %-10s %s\n" "$INFO" "$host" "$status" ;;
            *-failed)
                printf "  %s %-10s %s\n" "$ERROR" "$host" "$status" ;;
            *)
                printf "  %s %-10s %s\n" "$INFO" "$host" "$status" ;;
        esac
    done
    echo ""
    if [ "$DRY_RUN" -eq 1 ]; then
        log_info "Dry-run complete."
    else
        log_ok "Uninstall complete."
    fi
}

main() {
    echo "${BOLD}litestar-skills uninstaller v${VERSION}${NC}"
    echo ""

    uninstall_gemini
    uninstall_codex
    uninstall_opencode
    uninstall_claude
    uninstall_cursor
    uninstall_vscode

    print_summary

    for entry in "${STATUSES[@]}"; do
        case "$entry" in *:*-failed) exit 1 ;; esac
    done
}

main
