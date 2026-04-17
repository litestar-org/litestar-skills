/**
 * litestar-skills — OpenCode plugin entrypoint
 *
 * Registers the Litestar Skills collection with OpenCode. This file is
 * intentionally minimal: OpenCode reads `.agents/skills/` and `.claude/skills/`
 * natively, so consumers can use this repo's skills tree without programmatic
 * registration. Real `@opencode-ai/plugin` wiring will land here if and when
 * programmatic registration is needed (graduation trigger and rationale in
 * `docs/roadmap.md`).
 *
 * @see ../INSTALL.md for installation instructions.
 * @see ../../AGENTS.md for repo-wide agent context.
 */

export default {};
