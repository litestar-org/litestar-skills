#!/usr/bin/env bash
# litestar-skills — multi-host installer
#
# Installs litestar-skills for supported AI CLI tools. Hosts with CLIs
# (gemini, codex, opencode) get automated installs; hosts without
# (claude, cursor, vscode) get printed instructions since their plugin
# model requires in-app interaction the shell can't automate.
#
# Usage:
#   tools/install.sh [--dry-run] [--force] [--only <host>] [--skip <host>]
#   curl -fsSL https://raw.githubusercontent.com/litestar-org/litestar-skills/v0.1.2/tools/install.sh | bash
#
# Hosts:
#   claude     Claude Code        (prints instructions + optional settings edit)
#   gemini     Gemini CLI         (auto: gemini extensions install)
#   codex      OpenAI Codex CLI   (auto: clone to ~/.codex/plugins/)
#   opencode   OpenCode.ai        (auto: clone + symlink plugin)
#   cursor     Cursor IDE         (prints instructions)
#   vscode     VS Code / Copilot  (prints instructions)

set -euo pipefail

VERSION="0.1.2"
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
ANTIGRAVITY_SYMLINK=0

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
  --antigravity-symlink Create .agent -> .agents symlink in \$PWD so Google
                        Antigravity (singular .agent) discovers skills
                        installed under .agents/skills/. Opt-in only —
                        community workaround, not a Google-blessed
                        integration. Skipped if .agent already exists.
  --version             Print version and exit.
  --help                Print this message.

Hosts: claude, gemini, codex, opencode, cursor, vscode

Examples:
  $(basename "$0")                            # install for every detected host
  $(basename "$0") --only gemini --only codex
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
        --antigravity-symlink) ANTIGRAVITY_SYMLINK=1; shift ;;
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
    has_cli gemini   && detected+=("gemini")   || true
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

# ------ Gemini CLI ----------------------------------------------------------
install_gemini() {
    should_install gemini || return 0
    if ! has_cli gemini; then
        log_info "Gemini CLI not found — skipping."
        STATUSES+=("gemini:not-installed")
        return 0
    fi
    log_info "${BOLD}Installing for Gemini CLI...${NC}"

    # Check if already installed
    local already=0
    if gemini extensions list 2>/dev/null | grep -q "$PLUGIN_NAME"; then
        already=1
    fi

    if [ "$already" -eq 1 ]; then
        log_info "Extension already installed — updating"
        run gemini extensions update "$PLUGIN_NAME" || {
            log_warn "Update failed; try uninstall + reinstall"
            STATUSES+=("gemini:update-failed")
            return 0
        }
    else
        run gemini extensions install "$REPO_URL" --auto-update || {
            log_error "Gemini install failed"
            STATUSES+=("gemini:failed")
            return 0
        }
    fi
    log_ok "Gemini CLI: installed"
    STATUSES+=("gemini:installed")
}

# ------ Codex CLI -----------------------------------------------------------
install_codex() {
    should_install codex || return 0
    log_info "${BOLD}Installing for Codex CLI...${NC}"

    local target="${HOME}/.codex/plugins/${PLUGIN_NAME}"
    local marketplace="${HOME}/.agents/plugins/marketplace.json"

    run mkdir -p "${HOME}/.codex/plugins" "${HOME}/.agents/plugins"

    if [ -d "$target/.git" ]; then
        if [ "$FORCE" -eq 0 ]; then
            log_info "Already present at ${target} — pulling latest"
        fi
        run git -C "$target" fetch --quiet
        run git -C "$target" reset --hard origin/HEAD --quiet
    else
        if [ -e "$target" ] && [ "$FORCE" -eq 0 ]; then
            log_warn "${target} exists but is not a git repo. Use --force to overwrite."
            STATUSES+=("codex:path-conflict")
            return 0
        fi
        [ -e "$target" ] && run rm -rf "$target"
        run git clone --quiet --depth 1 "$REPO_URL" "$target"
    fi

    # Register in marketplace.json (merge if exists)
    if [ "$DRY_RUN" -eq 1 ]; then
        printf "%s Register %s in %s\n" "${YELLOW}[dry-run]${NC}" "$PLUGIN_NAME" "$marketplace"
    else
        python3 - "$marketplace" "$target" <<'PYEOF'
import json, sys, os
path, plugin_path = sys.argv[1], sys.argv[2]
data = {"name": "litestar", "plugins": []}
if os.path.exists(path):
    try:
        with open(path) as f: data = json.load(f)
    except Exception: pass
data.setdefault("name", "litestar")
plugins = data.setdefault("plugins", [])
plugins = [p for p in plugins if p.get("name") != "litestar"]
plugins.append({"name": "litestar", "source": plugin_path})
data["plugins"] = plugins
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, "w") as f: json.dump(data, f, indent=2)
PYEOF
    fi
    log_ok "Codex CLI: installed at ${target} (includes .codex/agents/litestar-reviewer.toml)"
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

# ------ Google Antigravity (opt-in workspace symlink) -----------------------
install_antigravity_symlink() {
    # Opt-in workaround: Antigravity reads `.agent/skills/` (singular) while
    # this repo + Claude/OpenCode/VS Code all use `.agents/skills/` (plural).
    # When the user passes --antigravity-symlink and `$PWD/.agents/skills`
    # exists, point `.agent` at `.agents`. This is a user-side workaround,
    # not a Google-blessed integration; the warning below labels it as such.
    if [ "$ANTIGRAVITY_SYMLINK" -eq 0 ]; then
        return 0
    fi
    log_info "${BOLD}Antigravity workspace symlink...${NC}"
    if [ ! -d "${PWD}/.agents/skills" ]; then
        log_warn "No .agents/skills/ in $PWD — install skills there first, then re-run with --antigravity-symlink"
        STATUSES+=("antigravity:no-skills-dir")
        return 0
    fi
    if [ -e "${PWD}/.agent" ] || [ -L "${PWD}/.agent" ]; then
        log_warn ".agent already exists in $PWD — refusing to overwrite (remove it manually if intentional)"
        STATUSES+=("antigravity:path-conflict")
        return 0
    fi
    run ln -s .agents "${PWD}/.agent"
    log_warn "Created .agent -> .agents symlink (community workaround; not a Google-blessed integration)"
    STATUSES+=("antigravity:symlinked")
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
            installed|instructions-printed|symlinked)
                printf "  %s %-12s %s\n" "$OK" "$host" "$status" ;;
            not-installed)
                printf "  %s %-12s %s\n" "$INFO" "$host" "CLI not present; skipped" ;;
            no-skills-dir)
                printf "  %s %-12s %s\n" "$INFO" "$host" "no .agents/skills/ in PWD; skipped" ;;
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

    install_gemini
    install_codex
    install_opencode
    install_claude
    install_cursor
    install_vscode
    install_antigravity_symlink

    print_summary

    # Exit code: 0 if all ok, 1 if any failed
    for entry in "${STATUSES[@]}"; do
        case "$entry" in *:*-failed|*:*-conflict) exit 1 ;; esac
    done
}

main
