#!/usr/bin/env node
// hooks/session-start.js
// SessionStart hook for litestar-skills (Node ESM port).
// Detects host via env vars and emits the host-correct JSON shape.
//
// Hosts:
//   CLAUDE_PLUGIN_ROOT  -> Claude Code  -> hookSpecificOutput.additionalContext
//   CODEX_PLUGIN_ROOT   -> Codex CLI    -> hookSpecificOutput.additionalContext
//   CURSOR_PLUGIN_ROOT  -> Cursor       -> additional_context
//   GEMINI_CLI / GEMINI_EXTENSION_NAME -> Gemini CLI -> hookSpecificOutput + systemMessage
//   (none of the above) -> Unknown      -> additional_context (Cursor-shape fallback)

import { detectEnv } from "./lib/detect-env.js";

function pickHost(env) {
  if (env.CLAUDE_PLUGIN_ROOT) return "claude";
  if (env.CODEX_PLUGIN_ROOT) return "codex";
  if (env.CURSOR_PLUGIN_ROOT) return "cursor";
  if (env.GEMINI_CLI || env.GEMINI_EXTENSION_NAME) return "gemini";
  return "unknown";
}

function shape(host, context) {
  if (host === "claude" || host === "codex") {
    return {
      hookSpecificOutput: { hookEventName: "SessionStart", additionalContext: context },
    };
  }
  if (host === "gemini") {
    return {
      hookSpecificOutput: { hookEventName: "SessionStart", additionalContext: context },
      systemMessage: context,
    };
  }
  // cursor + unknown
  return { additional_context: context };
}

async function main() {
  const detector = await detectEnv(process.env.PWD || process.cwd());
  if (!detector || Object.keys(detector).length === 0) {
    process.stdout.write("{}\n");
    return;
  }
  const host = pickHost(process.env);
  const out = shape(host, detector.context || "");
  process.stdout.write(JSON.stringify(out) + "\n");
}

main().catch((err) => {
  process.stderr.write(JSON.stringify({ error: String(err) }) + "\n");
  process.exit(1);
});
