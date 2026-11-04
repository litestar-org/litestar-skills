import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const PLUGIN_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

function detectSkills(projectDir) {
  const skills = [];
  const add = (name) => {
    if (!skills.includes(name)) skills.push(name);
  };
  const pyproject = join(projectDir, "pyproject.toml");
  let ownPkg = "";
  if (existsSync(pyproject)) {
    const content = readFileSync(pyproject, "utf8");
    const match = content.match(/^\[project\][\s\S]*?^\s*name\s*=\s*"([^"]+)"/m);
    if (match) ownPkg = match[1].toLowerCase().replaceAll("_", "-");
    if (/litestar/i.test(content) && ownPkg !== "litestar") add("litestar");
    if (/advanced[-_]alchemy/i.test(content) && ownPkg !== "advanced-alchemy") add("advanced-alchemy");
    if (/sqlspec/i.test(content) && ownPkg !== "sqlspec") add("sqlspec");
    if (/msgspec/i.test(content) && ownPkg !== "msgspec") add("msgspec");
    if (/litestar[-_]granian|granian/i.test(content) && ownPkg !== "litestar-granian") add("litestar-granian");
    if (/litestar[-_]saq/i.test(content) && ownPkg !== "litestar-saq") add("litestar-saq");
    if (/litestar[-_]queues/i.test(content) && ownPkg !== "litestar-queues") add("litestar-queues");
    if (/litestar[-_]security/i.test(content) && ownPkg !== "litestar-security") add("litestar-security");
    if (/litestar[-_]autowire/i.test(content) && ownPkg !== "litestar-autowire") add("litestar-autowire");
    if (/litestar[-_]vite/i.test(content) && ownPkg !== "litestar-vite") add("litestar-vite");
    if (/litestar[-_]htmx/i.test(content) && ownPkg !== "litestar-htmx") add("litestar-htmx");
    if (/litestar[-_]mcp|google[-_]adk|google[-_]genai/i.test(content) && ownPkg !== "litestar-mcp") add("litestar-mcp");
    if (/litestar[-_]email/i.test(content) && ownPkg !== "litestar-email") add("litestar-email");
    if (/pytest/i.test(content)) add("litestar-testing");
    if (/pytest[-_]databases/i.test(content) && ownPkg !== "pytest-databases") add("pytest-databases");
    if (/polyfactory/i.test(content) && ownPkg !== "polyfactory") add("polyfactory");
    if (/zensical|mkdocstrings|shibuya|litestar[-_]sphinx[-_]theme/i.test(content)) add("litestar-docs");
  }
  if (existsSync(join(projectDir, "zensical.toml")) || existsSync(join(projectDir, "docs", "conf.py"))) {
    add("litestar-docs");
  }
  if (existsSync(join(projectDir, "vite.config.ts")) && ownPkg !== "litestar-vite") {
    add("litestar-vite");
  }
  if (existsSync(join(projectDir, "Dockerfile"))) {
    add("litestar-deployment");
  }
  return skills;
}

function buildContext(projectDir) {
  if (process.env.LITESTAR_SKILLS_HOOK_DISABLE === "1") return "";
  const skills = detectSkills(projectDir);
  const summary =
    skills.length > 0
      ? `Detected Litestar stack skills for this workspace: ${skills.join(" ")}.`
      : "Available Litestar skills: litestar, sqlspec, advanced-alchemy, msgspec, litestar-granian, litestar-saq, litestar-queues, litestar-security, litestar-autowire, litestar-vite, litestar-htmx, litestar-mcp, litestar-email, litestar-testing, pytest-databases, polyfactory, litestar-docs, litestar-build, litestar-deployment, litestar-styleguide.";

  return [
    "<EXTREMELY_IMPORTANT>",
    "Litestar Framework Ecosystem Active",
    summary,
    "- Activate the matching Litestar skill before writing, refactoring, or reviewing Litestar application or library code.",
    "- Match the project's existing stack (SQLSpec vs Advanced Alchemy, Provide vs Dishka, msgspec vs Pydantic, Zensical vs Sphinx).",
    "- Keep all route handlers, guards, dependencies, and I/O async; enforce PEP 604 unions (T | None).",
    "</EXTREMELY_IMPORTANT>",
  ].join("\n");
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
      ctx.session.hook("context", async () => {
        const projectDir = ctx?.project?.path || ctx?.directory || ctx?.worktree || process.cwd();
        return buildContext(projectDir);
      });
    }
  },
};
