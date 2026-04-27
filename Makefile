# Copyright 2026 Cody Fincher and litestar-skills contributors
#
# Licensed under the MIT License. See LICENSE for details.

SHELL := /bin/bash

# =============================================================================
# Configuration and Environment Variables
# =============================================================================

.DEFAULT_GOAL:=help
.ONESHELL:
.SHELLFLAGS := -ec
.EXPORT_ALL_VARIABLES:
MAKEFLAGS += --no-print-directory

# -----------------------------------------------------------------------------
# Display Formatting and Colors
# -----------------------------------------------------------------------------
BLUE := $(shell printf "\033[1;34m")
GREEN := $(shell printf "\033[1;32m")
RED := $(shell printf "\033[1;31m")
YELLOW := $(shell printf "\033[1;33m")
NC := $(shell printf "\033[0m")
INFO := $(shell printf "$(BLUE)ℹ$(NC)")
OK := $(shell printf "$(GREEN)✓$(NC)")
WARN := $(shell printf "$(YELLOW)⚠$(NC)")
ERROR := $(shell printf "$(RED)✖$(NC)")

# =============================================================================
# Help and Documentation
# =============================================================================

.PHONY: help
help:                                               ## Display this help text for Makefile
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z0-9_-]+:.*?##/ { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

# =============================================================================
# Installation and Environment Setup
# =============================================================================

.PHONY: install-uv
install-uv:                                         ## Install latest version of uv
	@echo "${INFO} Installing uv..."
	@curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1
	@echo "${OK} uv installed successfully"

.PHONY: install-bun
install-bun:                                        ## Install latest version of bun
	@echo "${INFO} Installing bun..."
	@curl -fsSL https://bun.sh/install | bash >/dev/null 2>&1
	@echo "${OK} bun installed successfully"

.PHONY: install-prek
install-prek:                                       ## Install prek (Rust pre-commit alternative)
	@echo "${INFO} Installing prek..."
	@uv tool install prek --quiet
	@echo "${OK} prek installed successfully"

.PHONY: install
install: destroy clean                              ## Install the project, dependencies, and pre-commit hooks
	@echo "${INFO} Starting fresh installation... 🚀"
	@uv python pin 3.10 >/dev/null 2>&1
	@uv venv >/dev/null 2>&1
	@uv sync --extra dev
	@bun install
	@uv tool install prek --quiet 2>/dev/null || true
	@prek install --overwrite >/dev/null 2>&1 || echo "${WARN} prek install failed (run 'uv tool install prek' and retry)"
	@echo "${OK} Installation complete! 🎉"

.PHONY: destroy
destroy:                                            ## Destroy the virtual environment and node_modules
	@echo "${INFO} Destroying virtual environment... 🗑️"
	@rm -rf .venv node_modules
	@echo "${OK} Virtual environment destroyed 🗑️"

# =============================================================================
# Dependency Management
# =============================================================================

.PHONY: upgrade
upgrade:                                            ## Upgrade all dependencies to latest stable versions
	@echo "${INFO} Updating all dependencies... 🔄"
	@uv lock --upgrade
	@bun update
	@echo "${OK} Dependencies updated 🔄"
	@uv run prek autoupdate || true
	@echo "${OK} Updated pre-commit hooks 🔄"

.PHONY: lock
lock:                                               ## Rebuild lockfiles from scratch
	@echo "${INFO} Rebuilding lockfiles... 🔄"
	@uv lock --upgrade >/dev/null 2>&1
	@bun install >/dev/null 2>&1
	@echo "${OK} Lockfiles updated"

# =============================================================================
# Cleaning and Maintenance
# =============================================================================

.PHONY: clean
clean:                                              ## Cleanup temporary build artifacts
	@echo "${INFO} Cleaning working directory... 🧹"
	@rm -rf .pytest_cache .ruff_cache .mypy_cache .cache build/ dist/ .eggs/ .coverage coverage.xml coverage.json htmlcov/ >/dev/null 2>&1
	@find . \( -path ./.venv -o -path ./.git -o -path ./node_modules \) -prune -o -name '*.egg-info' -exec rm -rf {} + >/dev/null 2>&1
	@find . \( -path ./.venv -o -path ./.git -o -path ./node_modules \) -prune -o -name '*.pyc' -exec rm -f {} + >/dev/null 2>&1
	@find . \( -path ./.venv -o -path ./.git -o -path ./node_modules \) -prune -o -type d -name '__pycache__' -exec rm -rf {} + >/dev/null 2>&1
	@echo "${OK} Working directory cleaned"

# =============================================================================
# Testing and Quality Checks
# =============================================================================

.PHONY: test
test:                                               ## Run Python and JavaScript tests
	@echo "${INFO} Running test cases... 🧪"
	@uv run pytest tests
	@bun test 2>/dev/null || echo "${INFO} (no bun tests yet)"
	@echo "${OK} Tests complete ✨"

.PHONY: test-hooks
test-hooks:                                         ## Run hooks subset only (detect-env + session-start)
	@echo "${INFO} Running hook tests... 🪝"
	@uv run pytest tests/hooks -v
	@echo "${OK} Hook tests complete"

.PHONY: agents
agents:                                             ## Regenerate per-host agent dialects from canonical YAML sources
	@echo "${INFO} Regenerating agent dialects... 🤖"
	@uv run python tools/generate-agents.py
	@echo "${OK} Agents regenerated"

.PHONY: agents-check
agents-check:                                       ## CI drift gate — fail if generated output differs from on-disk
	@echo "${INFO} Checking agent dialect drift... 🔎"
	@uv run python tools/generate-agents.py --check
	@echo "${OK} No agent dialect drift"

.PHONY: coverage
coverage:                                           ## Run tests with coverage report
	@echo "${INFO} Running tests with coverage... 📊"
	@uv run pytest --cov --cov-report=term --cov-report=html --cov-report=xml
	@echo "${OK} Coverage report generated ✨"

# -----------------------------------------------------------------------------
# Type Checking
# -----------------------------------------------------------------------------

.PHONY: mypy
mypy:                                               ## Run mypy
	@echo "${INFO} Running mypy... 🔍"
	@uv run mypy tools tests
	@echo "${OK} mypy checks passed ✨"

.PHONY: pyright
pyright:                                            ## Run pyright
	@echo "${INFO} Running pyright... 🔍"
	@uv run pyright tools tests
	@echo "${OK} pyright checks passed ✨"

.PHONY: type-check
type-check: mypy pyright                            ## Run all type checking

# -----------------------------------------------------------------------------
# Linting and Formatting
# -----------------------------------------------------------------------------

.PHONY: fix
fix:                                                ## Run code formatters and auto-fixers
	@echo "${INFO} Running code formatters... 🔧"
	@uv run ruff check --fix --unsafe-fixes
	@uv run ruff format
	@echo "${OK} Code formatting complete ✨"

.PHONY: pre-commit
pre-commit:                                         ## Run pre-commit hooks via prek
	@echo "${INFO} Running pre-commit checks... 🔎"
	@prek run --color=always --all-files
	@echo "${OK} Pre-commit checks passed ✨"

.PHONY: ruff
ruff:                                               ## Run ruff linter and format check
	@echo "${INFO} Running ruff... 🔍"
	@uv run ruff check .
	@uv run ruff format --check .
	@echo "${OK} ruff checks passed ✨"

.PHONY: oxlint
oxlint:                                             ## Run oxlint on JavaScript and TypeScript
	@echo "${INFO} Running oxlint... 🔍"
	@bunx oxlint
	@echo "${OK} oxlint checks passed ✨"

.PHONY: markdownlint
markdownlint:                                       ## Run markdownlint on all markdown files
	@echo "${INFO} Running markdownlint... 🔍"
	@bunx markdownlint-cli2 "**/*.md" "#node_modules" "#.agents" "#.beads" "#plugins/litestar"
	@echo "${OK} markdownlint checks passed ✨"

.PHONY: lint
lint: ruff oxlint markdownlint codex-package-check  ## Run all linters
	@echo "${OK} All linting checks passed ✨"

# -----------------------------------------------------------------------------
# Skills Validation
# -----------------------------------------------------------------------------

.PHONY: validate-skills
validate-skills:                                    ## Validate SKILL.md + commands + agents frontmatter, XML tags, cross-links
	@echo "${INFO} Validating skills... 🔍"
	@uv run python tools/validate-skills.py
	@echo "${OK} Skills validation complete ✨"

.PHONY: sync-manifests
sync-manifests:                                     ## Verify all bump-my-version tracked files are in sync
	@echo "${INFO} Checking manifest version sync... 🔍"
	@uv run python tools/sync-manifests.py
	@echo "${OK} Manifests in sync ✨"

.PHONY: check-upstream-imports
check-upstream-imports:                             ## Verify every Python import in skill code samples resolves against installed upstream library versions (requires .[validation] extras)
	@echo "${INFO} Checking upstream API imports in skill code samples... 🔍"
	@uv run python tools/check-upstream-imports.py
	@echo "${OK} Upstream imports verified ✨"

.PHONY: sync-codex-package
sync-codex-package:                                 ## Assemble the committed Codex plugin package at plugins/litestar/
	@echo "${INFO} Syncing Codex package payload... 🔗"
	@uv run python tools/sync-codex-package.py
	@echo "${OK} Codex package assembled"

.PHONY: codex-package-check
codex-package-check:                                ## Verify plugins/litestar/ matches generated Codex package payload
	@echo "${INFO} Checking Codex package payload... 🔍"
	@uv run python tools/sync-codex-package.py --check
	@echo "${OK} Codex package payload is current"

.PHONY: validate-codex-manifest
validate-codex-manifest:                            ## Validate Codex marketplace + plugin manifests for Codex CLI 0.125+
	@echo "${INFO} Validating Codex manifests... 🔍"
	@uv run python tools/validate-codex-manifest.py
	@echo "${OK} Codex manifests valid"

.PHONY: validate
validate: agents-check validate-skills sync-manifests validate-codex-manifest check-upstream-imports  ## Run all repo-integrity validators
	@echo "${OK} All validators passed ✨"

# -----------------------------------------------------------------------------
# Aggregate Targets
# -----------------------------------------------------------------------------

.PHONY: check
check: lint type-check test validate                ## Run all checks (lint, type-check, test, validate) — CI parity
	@echo "${OK} All checks passed successfully ✨"

# =============================================================================
# Build and Release
# =============================================================================

.PHONY: build
build:                                              ## Build the package
	@echo "${INFO} Building package... 📦"
	@uv build >/dev/null 2>&1
	@echo "${OK} Package build complete"

.PHONY: release
release:                                            ## Bump version and create release tag (e.g. make release bump=patch)
	@if [ -z "$(bump)" ]; then \
		echo "${ERROR} Usage: make release bump=patch|minor|major"; \
		exit 1; \
	fi
	@echo "${INFO} Preparing for release... 📦"
	@make clean
	@uv run bump-my-version bump $(bump)
	@make build
	@echo "${OK} Release complete 🎉"

.PHONY: pre-release
pre-release:                                        ## Start/advance a pre-release (e.g. make pre-release version=0.1.0a1)
	@if [ -z "$(version)" ]; then \
		echo "${ERROR} Usage: make pre-release version=X.Y.Z{a|b|rc}N"; \
		echo ""; \
		echo "Pre-release workflow:"; \
		echo "  1. Start alpha:     make pre-release version=0.1.0a1"; \
		echo "  2. Next alpha:      make pre-release version=0.1.0a2"; \
		echo "  3. Move to beta:    make pre-release version=0.1.0b1"; \
		echo "  4. Move to rc:      make pre-release version=0.1.0rc1"; \
		echo "  5. Final release:   make release bump=patch (from rc) OR bump=minor (from stable)"; \
		exit 1; \
	fi
	@echo "${INFO} Preparing pre-release $(version)... 🧪"
	@make clean
	@uv run bump-my-version bump --new-version $(version) pre_l
	@make build
	@echo "${OK} Pre-release $(version) complete 🧪"
	@echo ""
	@echo "${INFO} Next steps:"
	@echo "  1. Push: git push origin HEAD --tags"
	@echo "  2. Create a GitHub pre-release: gh release create v$(version) --prerelease --generate-notes --title 'v$(version)'"

# =============================================================================
# End of Makefile
# =============================================================================
