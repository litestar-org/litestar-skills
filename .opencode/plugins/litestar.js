import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const PLUGIN_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

const UPSTREAM_PACKAGES = new Set([
  "litestar",
  "advanced-alchemy",
  "sqlspec",
  "msgspec",
  "litestar-granian",
  "litestar-saq",
  "litestar-queues",
  "litestar-security",
  "litestar-autowire",
  "litestar-vite",
  "litestar-htmx",
  "litestar-mcp",
  "litestar-email",
  "pytest-databases",
  "polyfactory",
]);

function detectWorkspace(projectDir) {
  const skills = [];
  const add = (name) => {
    if (!skills.includes(name)) skills.push(name);
  };
  const pyproject = join(projectDir, "pyproject.toml");
  let ownPkg = "";
  let isPluginRepo = false;
  let isUpstream = false;
  let hasCore = false;

  if (existsSync(pyproject)) {
    const content = readFileSync(pyproject, "utf8");
    const match = content.match(/^\[project\][\s\S]*?^\s*name\s*=\s*"([^"]+)"/m);
    if (match) ownPkg = match[1].toLowerCase().replaceAll("_", "-");

    if (ownPkg === "litestar-skills") {
      isPluginRepo = true;
      add("litestar-styleguide");
    } else {
      if (UPSTREAM_PACKAGES.has(ownPkg)) {
        isUpstream = true;
        hasCore = true;
      }
      if (/litestar/i.test(content)) {
        hasCore = true;
        if (ownPkg !== "litestar") add("litestar");
      }
      if (/advanced[-_]alchemy/i.test(content)) {
        hasCore = true;
        if (ownPkg !== "advanced-alchemy") add("advanced-alchemy");
      }
      if (/sqlspec/i.test(content)) {
        hasCore = true;
        if (ownPkg !== "sqlspec") add("sqlspec");
      }
      if (/msgspec/i.test(content)) {
        hasCore = true;
        if (ownPkg !== "msgspec") add("msgspec");
      }
      if (/litestar[-_]granian/i.test(content)) {
        hasCore = true;
        if (ownPkg !== "litestar-granian") add("litestar-granian");
      }
      if (/litestar[-_]saq/i.test(content)) {
        hasCore = true;
        if (ownPkg !== "litestar-saq") add("litestar-saq");
      }
      if (/litestar[-_]queues/i.test(content)) {
        hasCore = true;
        if (ownPkg !== "litestar-queues") add("litestar-queues");
      }
      if (/litestar[-_]security/i.test(content)) {
        hasCore = true;
        if (ownPkg !== "litestar-security") add("litestar-security");
      }
      if (/litestar[-_]autowire/i.test(content)) {
        hasCore = true;
        if (ownPkg !== "litestar-autowire") add("litestar-autowire");
      }
      if (/litestar[-_]vite/i.test(content)) {
        hasCore = true;
        if (ownPkg !== "litestar-vite") add("litestar-vite");
      }
      if (/litestar[-_]htmx/i.test(content)) {
        hasCore = true;
        if (ownPkg !== "litestar-htmx") add("litestar-htmx");
      }
      if (/litestar[-_]mcp/i.test(content)) {
        hasCore = true;
        if (ownPkg !== "litestar-mcp") add("litestar-mcp");
      }
      if (/litestar[-_]email/i.test(content)) {
        hasCore = true;
        if (ownPkg !== "litestar-email") add("litestar-email");
      }
      if (/pytest[-_]databases/i.test(content)) {
        hasCore = true;
        if (ownPkg !== "pytest-databases") add("pytest-databases");
      }
      if (/polyfactory/i.test(content)) {
        hasCore = true;
        if (ownPkg !== "polyfactory") add("polyfactory");
      }
      if (/litestar[-_]sphinx[-_]theme/i.test(content)) {
        hasCore = true;
        add("litestar-docs");
      }

      if (hasCore) {
        if (/granian/i.test(content) && ownPkg !== "litestar-granian") add("litestar-granian");
        if (/google[-_]adk|google[-_]genai/i.test(content) && ownPkg !== "litestar-mcp") add("litestar-mcp");
        if (/pytest/i.test(content)) add("litestar-testing");
        if (/zensical|mkdocstrings|shibuya/i.test(content)) add("litestar-docs");
      }
    }
  }

  if (hasCore && !isPluginRepo) {
    if (existsSync(join(projectDir, "zensical.toml")) || existsSync(join(projectDir, "docs", "conf.py"))) {
      add("litestar-docs");
    }
    if (
      (existsSync(join(projectDir, "vite.config.ts")) ||
        existsSync(join(projectDir, "vite.config.js")) ||
        existsSync(join(projectDir, "vite.config.mjs"))) &&
      ownPkg !== "litestar-vite"
    ) {
      add("litestar-vite");
    }
    if (
      existsSync(join(projectDir, "alembic.ini")) &&
      ownPkg !== "advanced-alchemy" &&
      ownPkg !== "sqlspec"
    ) {
      add("advanced-alchemy");
    }
    if (existsSync(join(projectDir, "Dockerfile")) || existsSync(join(projectDir, "Containerfile"))) {
      add("litestar-deployment");
    }
    add("litestar-styleguide");
  }

  return { skills, ownPkg, isPluginRepo, isUpstream, hasCore };
}

function buildContext(projectDir) {
  if (
    process.env.LITESTAR_SKILLS_HOOK_DISABLE === "1" ||
    process.env.LITESTAR_SKILLS_HOOK_DISABLE === "true"
  ) {
    return "";
  }
  const { skills, ownPkg, isPluginRepo, isUpstream } = detectWorkspace(projectDir);
  if (skills.length === 0 && !isUpstream && !isPluginRepo) {
    return "";
  }
  const skillList = skills.join(" ");
  if (isPluginRepo) {
    return `Litestar skills plugin workspace (skills: ${skillList}). Follow skills/litestar-styleguide and validate all changes with make check.`;
  }
  if (isUpstream) {
    return `Litestar upstream package workspace ('${ownPkg}'; companion skills: ${skillList}). Treat this repository's own source code and tests as the authority over its consumer skill; keep async I/O and PEP 604 unions (T | None).`;
  }
  return `Litestar ecosystem detected in workspace (skills: ${skillList}). Load the matching skill before writing, refactoring, or reviewing code; match the project's existing stack (SQLSpec vs Advanced Alchemy, Provide vs Dishka, msgspec vs Pydantic, Zensical vs Sphinx); keep handlers, guards, dependencies, and I/O async with PEP 604 unions (T | None).`;
}

export default {
  id: "litestar",
  async setup(ctx) {
    if (ctx?.agent?.transform) {
      ctx.agent.transform((agents) => {
        agents["litestar-reviewer"] = {
          name: "litestar-reviewer",
          description:
            "Use when reviewing Litestar PRs/code for stack-aware DTOs, guards, DI, data services, pagination, settings, async I/O, plugins, and wire format. Not for non-Litestar reviews.",
          promptFile: resolve(PLUGIN_ROOT, "agents/litestar-reviewer.md"),
          mode: "subagent",
          permissions: {
            edit: "deny",
            terminal: "deny",
            web: "deny",
          },
        };
      });
    }

    if (ctx?.session?.hook) {
      ctx.session.hook("context", async (event) => {
        const projectDir = ctx?.project?.path || ctx?.directory || ctx?.worktree || process.cwd();
        const context = buildContext(projectDir);
        if (context && event && Array.isArray(event.system)) {
          event.system.push({ type: "text", text: context });
        }
        return context;
      });
    }
  },
};
