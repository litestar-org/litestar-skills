/**
 * litestar-skills — OpenCode plugin
 *
 * Injects project-aware Litestar skill reminders into the OpenCode session
 * via `experimental.chat.system.transform` (OpenCode has no SessionStart
 * hook as of `@opencode-ai/plugin@1.3.x`; system-prompt transformation is
 * the supported context-bootstrap point).
 *
 * Reuses the same detect-env library that powers Claude / Codex / Cursor /
 * Gemini hooks (hooks/lib/detect-env.js), so the reminder text is identical
 * across all five hosts.
 *
 * Honors managed-config: if `ctx.config.managedConfig.disabledPlugins`
 * includes our name, OR `allowedPlugins` is set and excludes us, returns
 * an empty handler set. Don't fight org policy.
 *
 * @see ../INSTALL.md for installation instructions.
 * @see ../../hooks/lib/detect-env.js for the shared detection library.
 * @see ../../AGENTS.md for repo-wide agent context.
 */

import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { detectEnv } from "../../hooks/lib/detect-env.js";

const PLUGIN_NAME = "litestar-skills";
const __dirname = dirname(fileURLToPath(import.meta.url));
const PLUGIN_ROOT = resolve(__dirname, "../..");

function isPluginDisabledByManagedConfig(ctx) {
  const managed = ctx?.config?.managedConfig ?? ctx?.config?.managed ?? null;
  if (!managed) return false;
  if (Array.isArray(managed.disabledPlugins) && managed.disabledPlugins.includes(PLUGIN_NAME)) {
    return true;
  }
  if (Array.isArray(managed.allowedPlugins) && !managed.allowedPlugins.includes(PLUGIN_NAME)) {
    return true;
  }
  return false;
}

let _warnedNoTransform = false;

export default async (ctx) => {
  if (isPluginDisabledByManagedConfig(ctx)) return {};

  return {
    "experimental.chat.system.transform": async (_input, output) => {
      if (!output || !Array.isArray(output.system)) {
        if (!_warnedNoTransform) {
          _warnedNoTransform = true;
          // eslint-disable-next-line no-console
          console.warn(
            "[litestar-skills] experimental.chat.system.transform output shape unrecognised — skipping injection",
          );
        }
        return;
      }
      try {
        const cwd = ctx?.project?.path || ctx?.directory || ctx?.worktree || process.cwd();
        const detector = await detectEnv(cwd);
        const context = detector?.context;
        if (typeof context === "string" && context.length > 0) {
          output.system.push(context);
        }
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn(`[litestar-skills] detect-env failed: ${err}`);
      }
    },

    "shell.env": async () => ({
      env: { LITESTAR_SKILLS_PLUGIN_ROOT: PLUGIN_ROOT },
    }),
  };
};
