#!/usr/bin/env bash
# litestar-skills — multi-host installer
#
# Installs litestar-skills for supported AI CLI tools. Hosts with CLIs
# (antigravity, codex, opencode) get automated installs; hosts without
# (claude, cursor, vscode) get printed instructions since their plugin
# model requires in-app interaction the shell can't automate.
#
# Usage:
#   tools/install.sh [--dry-run] [--force] [--only <host>] [--skip <host>]
#   curl -fsSL https://raw.githubusercontent.com/litestar-org/litestar-skills/v0.4.0/tools/install.sh | bash
#
# Hosts:
#   claude     Claude Code        (prints instructions + optional settings edit)
#   antigravity Antigravity CLI   (auto: stage payload + agy plugin install)
#   codex      OpenAI Codex CLI   (auto: codex plugin marketplace add + plugin add)
#   opencode   OpenCode.ai        (auto: clone + symlink JS plugin on Unix)
#   cursor     Cursor IDE         (prints instructions)
#   vscode     VS Code / Copilot  (prints instructions)

set -euo pipefail

VERSION="0.4.0"
REPO_URL="https://github.com/litestar-org/litestar-skills"
REPO_SLUG="litestar-org/litestar-skills"
MARKETPLACE_NAME="litestar"
PLUGIN_NAME="litestar"

# =============================================================================
# Formatting
# =============================================================================
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    BLUE=$'\033[1;34m'
    GREEN=$'\033[1;32m'
    RED=$'\033[1;31m'
    YELLOW=$'\033[1;33m'
    BOLD=$'\033[1m'
    NC=$'\033[0m'
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
# Argument parsing
# =============================================================================
DRY_RUN=0
FORCE=0
ONLY_HOSTS=()
SKIP_HOSTS=()
UPDATE_CLAUDE_SETTINGS=0

usage() {
    cat <<USAGE
${BOLD}litestar-skills installer v${VERSION}${NC}

Usage: $(basename "$0") [options]

Options:
  --dry-run             Print planned actions without executing.
  --force               Overwrite existing installs without prompting.
  --only <host>         Install only for the named host (repeatable).
  --skip <host>         Skip the named host (repeatable).
  --claude-settings     Also update ~/.claude/settings.json to whitelist
                        this repo in extraKnownMarketplaces (opt-in).
  --version             Print version and exit.
  --help                Print this message.

Hosts: claude, antigravity, codex, opencode, cursor, vscode

Examples:
  $(basename "$0")                            # install for every detected host
  $(basename "$0") --only antigravity --only codex
  $(basename "$0") --dry-run                  # preview without changes
  $(basename "$0") --skip opencode --force    # overwrite, except OpenCode

Repo: ${REPO_URL}
USAGE
}

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run)          DRY_RUN=1; shift ;;
        --force)            FORCE=1; shift ;;
        --only)             ONLY_HOSTS+=("$2"); shift 2 ;;
        --skip)             SKIP_HOSTS+=("$2"); shift 2 ;;
        --claude-settings)  UPDATE_CLAUDE_SETTINGS=1; shift ;;
        --version)          echo "$VERSION"; exit 0 ;;
        --help|-h)          usage; exit 0 ;;
        *)                  log_error "Unknown argument: $1"; usage; exit 2 ;;
    esac
done

# =============================================================================
# Safety guards
# =============================================================================
if [ "$(id -u)" -eq 0 ]; then
    log_error "Do not run this installer as root. All installs go into user dirs."
    log_error "Re-run without sudo."
    exit 1
fi

should_install() {
    local host="$1"
    if [ ${#ONLY_HOSTS[@]} -gt 0 ]; then
        for h in "${ONLY_HOSTS[@]}"; do
            [ "$h" = "$host" ] && return 0
        done
        return 1
    fi
    for h in "${SKIP_HOSTS[@]}"; do
        [ "$h" = "$host" ] && return 1
    done
    return 0
}

run() {
    if [ "$DRY_RUN" -eq 1 ]; then
        printf "%s %s\n" "${YELLOW}[dry-run]${NC}" "$*"
    else
        "$@"
    fi
}

# =============================================================================
# Source resolution
# =============================================================================
# When run from a clone, use $PROJECT_ROOT. When fetched via curl, clone first.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || echo "")"
CACHE_DIR="${HOME}/.cache/litestar-skills-install"
PROJECT_ROOT=""

resolve_source() {
    if [ -n "$SCRIPT_DIR" ] && [ -d "${SCRIPT_DIR}/../skills" ]; then
        PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
        log_info "Using local source: ${PROJECT_ROOT}"
    else
        log_info "Cloning ${REPO_URL} to ${CACHE_DIR}"
        if [ -d "$CACHE_DIR/.git" ]; then
            run git -C "$CACHE_DIR" fetch --quiet
            run git -C "$CACHE_DIR" reset --hard origin/HEAD --quiet
        else
            run git clone --quiet --depth 1 "$REPO_URL" "$CACHE_DIR"
        fi
        PROJECT_ROOT="$CACHE_DIR"
    fi
}

# =============================================================================
# Host detection
# =============================================================================
has_cli() {
    command -v "$1" >/dev/null 2>&1
}

probe_hosts() {
    log_info "${BOLD}Detecting installed CLIs...${NC}"
    local detected=()
    has_cli claude   && detected+=("claude")   || true
    has_cli agy      && detected+=("antigravity") || true
    has_cli codex    && detected+=("codex")    || true
    has_cli opencode && detected+=("opencode") || true
    has_cli cursor   && detected+=("cursor")   || true
    has_cli code     && detected+=("vscode")   || true

    if [ ${#detected[@]} -eq 0 ]; then
        log_warn "No supported CLIs detected. Instructions will still be printed."
    else
        log_ok "Detected: ${detected[*]}"
    fi
}

# =============================================================================
# Per-host installers
# =============================================================================

# ------ Antigravity CLI -----------------------------------------------------
prepare_antigravity_payload() {
    ANTIGRAVITY_PAYLOAD="${CACHE_DIR}/antigravity-plugin"
    run rm -rf "$ANTIGRAVITY_PAYLOAD"
    run mkdir -p "$ANTIGRAVITY_PAYLOAD/agents"
    run cp "${PROJECT_ROOT}/plugin.json" "${ANTIGRAVITY_PAYLOAD}/plugin.json"
    run cp "${PROJECT_ROOT}/hooks.json" "${ANTIGRAVITY_PAYLOAD}/hooks.json"
    run cp -R "${PROJECT_ROOT}/skills" "${ANTIGRAVITY_PAYLOAD}/skills"
    run cp -R "${PROJECT_ROOT}/commands" "${ANTIGRAVITY_PAYLOAD}/commands"
    run cp -R "${PROJECT_ROOT}/hooks" "${ANTIGRAVITY_PAYLOAD}/hooks"
    run cp "${PROJECT_ROOT}"/agents/*.md "${ANTIGRAVITY_PAYLOAD}/agents/"
}

install_antigravity() {
    should_install antigravity || return 0
    if ! has_cli agy; then
        log_info "Antigravity CLI not found — skipping."
        STATUSES+=("antigravity:not-installed")
        return 0
    fi
    log_info "${BOLD}Installing for Antigravity CLI...${NC}"

    local already=0
    if agy plugin list 2>/dev/null | grep -q "$PLUGIN_NAME"; then
        already=1
    fi

    if [ "$already" -eq 1 ]; then
        if [ "$FORCE" -eq 0 ]; then
            log_info "Antigravity plugin already installed — use --force to reinstall."
            STATUSES+=("antigravity:already-installed")
            return 0
        fi
        run agy plugin uninstall "$PLUGIN_NAME" || {
            log_error "Antigravity uninstall before reinstall failed"
            STATUSES+=("antigravity:failed")
            return 0
        }
    fi

    local ANTIGRAVITY_PAYLOAD
    prepare_antigravity_payload

    run agy plugin install "$ANTIGRAVITY_PAYLOAD" || {
        log_error "Antigravity install failed"
        STATUSES+=("antigravity:failed")
        return 0
    }
    log_ok "Antigravity CLI: installed from staged payload ${ANTIGRAVITY_PAYLOAD}"
    STATUSES+=("antigravity:installed")
}

# ------ Codex CLI -----------------------------------------------------------
install_codex() {
    should_install codex || return 0
    log_info "${BOLD}Installing for Codex CLI...${NC}"

    if ! has_cli codex; then
        log_info "Codex CLI not found — skipping."
        STATUSES+=("codex:not-installed")
        return 0
    fi

    if [ "$FORCE" -eq 1 ]; then
        run codex plugin remove "${PLUGIN_NAME}@${MARKETPLACE_NAME}" >/dev/null 2>&1 || true
        run codex plugin marketplace remove "$MARKETPLACE_NAME" >/dev/null 2>&1 || true
    fi

    if codex plugin marketplace list --json 2>/dev/null | grep -q "\"name\": \"${MARKETPLACE_NAME}\""; then
        log_info "Codex marketplace ${MARKETPLACE_NAME} already configured."
    else
        run codex plugin marketplace add "$PROJECT_ROOT" || {
            log_error "Codex marketplace add failed"
            STATUSES+=("codex:failed")
            return 0
        }
    fi

    if codex plugin list --json 2>/dev/null | grep -q "\"pluginId\": \"${PLUGIN_NAME}@${MARKETPLACE_NAME}\""; then
        log_info "Codex plugin ${PLUGIN_NAME}@${MARKETPLACE_NAME} already installed."
    else
        run codex plugin add "${PLUGIN_NAME}@${MARKETPLACE_NAME}" || {
            log_error "Codex plugin add failed"
            STATUSES+=("codex:failed")
            return 0
        }
    fi

    log_ok "Codex CLI: installed ${PLUGIN_NAME}@${MARKETPLACE_NAME} from ${PROJECT_ROOT}"
    STATUSES+=("codex:installed")
}

# ------ OpenCode ------------------------------------------------------------
install_opencode() {
    should_install opencode || return 0
    log_info "${BOLD}Installing for OpenCode...${NC}"

    local clone_dir="${HOME}/.config/opencode/${PLUGIN_NAME}"
    local plugin_link="${HOME}/.config/opencode/plugins/${PLUGIN_NAME}.js"

    run mkdir -p "${HOME}/.config/opencode/plugins"

    if [ -d "$clone_dir/.git" ]; then
        log_info "Pulling latest from ${clone_dir}"
        run git -C "$clone_dir" fetch --quiet
        run git -C "$clone_dir" reset --hard origin/HEAD --quiet
    else
        [ -e "$clone_dir" ] && run rm -rf "$clone_dir"
        run git clone --quiet --depth 1 "$REPO_URL" "$clone_dir"
    fi

    # Symlink plugin entrypoint
    if [ -L "$plugin_link" ] || [ -e "$plugin_link" ]; then
        if [ "$FORCE" -eq 0 ] && [ -L "$plugin_link" ]; then
            log_info "Plugin link already present"
        else
            run rm -f "$plugin_link"
            run ln -sf "${clone_dir}/.opencode/plugins/${PLUGIN_NAME}.js" "$plugin_link"
        fi
    else
        run ln -sf "${clone_dir}/.opencode/plugins/${PLUGIN_NAME}.js" "$plugin_link"
    fi

    log_ok "OpenCode: installed at ${clone_dir}, linked ${plugin_link}"
    STATUSES+=("opencode:installed")
}

# ------ Claude Code (instructions + optional settings edit) -----------------
install_claude() {
    should_install claude || return 0
    log_info "${BOLD}Claude Code setup...${NC}"

    if [ "$UPDATE_CLAUDE_SETTINGS" -eq 1 ]; then
        local settings="${HOME}/.claude/settings.json"
        run mkdir -p "${HOME}/.claude"
        if [ "$DRY_RUN" -eq 1 ]; then
            printf "%s Add %s to extraKnownMarketplaces in %s\n" "${YELLOW}[dry-run]${NC}" "$REPO_SLUG" "$settings"
        else
            python3 - "$settings" "$REPO_SLUG" <<'PYEOF'
import json, sys, os
path, slug = sys.argv[1], sys.argv[2]
data = {}
if os.path.exists(path):
    try:
        with open(path) as f: data = json.load(f)
    except Exception: pass
marketplaces = set(data.get("extraKnownMarketplaces", []))
marketplaces.add(slug)
data["extraKnownMarketplaces"] = sorted(marketplaces)
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, "w") as f: json.dump(data, f, indent=2)
PYEOF
            log_ok "Added ${REPO_SLUG} to ~/.claude/settings.json extraKnownMarketplaces"
        fi
    fi

    cat <<CLAUDE_INSTRUCTIONS

${BOLD}Next steps (inside Claude Code):${NC}

  /plugin marketplace add ${REPO_SLUG}
  /plugin install ${PLUGIN_NAME}@${MARKETPLACE_NAME}

Re-run this installer with ${BOLD}--claude-settings${NC} to whitelist the
marketplace ahead of time and skip the first command.

CLAUDE_INSTRUCTIONS
    STATUSES+=("claude:instructions-printed")
}

# ------ Cursor (instructions) -----------------------------------------------
install_cursor() {
    should_install cursor || return 0
    log_info "${BOLD}Cursor setup...${NC}"
    cat <<CURSOR_INSTRUCTIONS

Cursor reads SKILL.md from any path added as a Remote Rule:

  Cursor → Settings → Rules → Add Remote Rule → ${REPO_URL}

Cursor also reads .agents/skills/ and .cursor/skills/ natively in projects —
drop the skills/ tree from this repo into either path if you prefer local.

CURSOR_INSTRUCTIONS
    STATUSES+=("cursor:instructions-printed")
}

# ------ VS Code / Copilot (instructions) ------------------------------------
install_vscode() {
    should_install vscode || return 0
    log_info "${BOLD}VS Code / Copilot setup...${NC}"
    local target="${HOME}/.copilot/${PLUGIN_NAME}"
    cat <<VSCODE_INSTRUCTIONS

Clone the repo and point chat.skillsLocations at it:

  git clone ${REPO_URL} ${target}

Then in VS Code settings.json:

  "chat.skillsLocations": {
    "${target}/skills": true
  }

VS Code reads .github/skills/, .claude/skills/, and .agents/skills/ in any
open project natively if you prefer per-project install.

VSCODE_INSTRUCTIONS
    STATUSES+=("vscode:instructions-printed")
}

# =============================================================================
# Summary
# =============================================================================
print_summary() {
    echo ""
    echo "${BOLD}=== Install Summary ===${NC}"
    for entry in "${STATUSES[@]}"; do
        host="${entry%%:*}"
        status="${entry#*:}"
        case "$status" in
            installed|instructions-printed)
                printf "  %s %-12s %s\n" "$OK" "$host" "$status" ;;
            not-installed)
                printf "  %s %-12s %s\n" "$INFO" "$host" "CLI not present; skipped" ;;
            already-installed)
                printf "  %s %-12s %s\n" "$INFO" "$host" "$status" ;;
            *-failed|*-conflict)
                printf "  %s %-12s %s\n" "$ERROR" "$host" "$status" ;;
            *)
                printf "  %s %-12s %s\n" "$INFO" "$host" "$status" ;;
        esac
    done
    echo ""
    if [ "$DRY_RUN" -eq 1 ]; then
        log_info "Dry-run complete. Re-run without --dry-run to execute."
    else
        log_ok "Installation complete. 🎉"
    fi
}

# =============================================================================
# Main
# =============================================================================
STATUSES=()

main() {
    echo "${BOLD}litestar-skills installer v${VERSION}${NC}"
    echo ""

    resolve_source
    probe_hosts
    echo ""

    install_antigravity
    install_codex
    install_opencode
    install_claude
    install_cursor
    install_vscode
    print_summary

    # Exit code: 0 if all ok, 1 if any failed
    for entry in "${STATUSES[@]}"; do
        case "$entry" in *:*-failed|*:*-conflict) exit 1 ;; esac
    done
}

main
