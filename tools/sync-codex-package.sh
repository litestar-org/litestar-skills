#!/usr/bin/env bash
# Assemble the Codex marketplace package at <repo-root>/plugins/litestar/.
#
# Codex 0.125+ resolves marketplace `source.path` relative to the marketplace
# ROOT (the repo), not relative to the marketplace.json file. So
# `./plugins/litestar` in .agents/plugins/marketplace.json must exist at
# <repo-root>/plugins/litestar/.
#
# We use whole-directory symlinks back to the canonical repo-root sources so
# nothing is duplicated and edits to skills/commands/hooks/agents flow into the
# Codex package automatically:
#
#   plugins/litestar/.codex-plugin -> ../../.codex-plugin
#   plugins/litestar/skills        -> ../../skills
#   plugins/litestar/commands      -> ../../commands
#   plugins/litestar/.codex        -> ../../.codex
#   plugins/litestar/hooks         -> ../../hooks
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
package="${repo_root}/plugins/litestar"

mkdir -p "${package}"
rm -rf \
  "${package}/.codex-plugin" \
  "${package}/skills" \
  "${package}/commands" \
  "${package}/.codex" \
  "${package}/hooks"

ln -s ../../.codex-plugin "${package}/.codex-plugin"
ln -s ../../skills "${package}/skills"
ln -s ../../commands "${package}/commands"
ln -s ../../.codex "${package}/.codex"
ln -s ../../hooks "${package}/hooks"

echo "assembled package at ${package}"
