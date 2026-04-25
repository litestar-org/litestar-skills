// hooks/lib/detect-env.js
// Project-aware library detection for litestar-skills (Node ESM port of detect-env.sh).
//
// Designed to be both:
//   * Imported as ESM:  import { detectEnv } from "./detect-env.js";
//   * Run as CLI:        node hooks/lib/detect-env.js <project_root>
//
// Reused by the OpenCode plugin (Ch4) — keep ESM-clean.
// Honors LITESTAR_SKILLS_HOOK_DISABLE=1 (returns {} from detectEnv()).

import { readFileSync, readdirSync, statSync } from "node:fs";
import { readdir } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SKILL_MAP_PATH = join(__dirname, "skill-map.json");

const SKIP_DIRS = new Set([
  ".venv",
  "venv",
  "node_modules",
  "__pycache__",
  "dist",
  "build",
  ".git",
  ".mypy_cache",
  ".ruff_cache",
  ".pytest_cache",
]);
const PY_FILE_CAP = 50;
const PY_DEPTH_CAP = 4;

function escapeRegex(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function isDir(path) {
  try {
    return statSync(path).isDirectory();
  } catch {
    return false;
  }
}

function pathExists(path) {
  try {
    statSync(path);
    return true;
  } catch {
    return false;
  }
}

function readdirSafe(dir) {
  try {
    return readdirSync(dir);
  } catch {
    return [];
  }
}

async function walkPyFiles(root, cap, depthCap) {
  const out = [];
  async function walk(dir, depth) {
    if (depth > depthCap || out.length >= cap) return;
    let entries;
    try {
      entries = await readdir(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      if (out.length >= cap) return;
      if (entry.name.startsWith(".") || SKIP_DIRS.has(entry.name)) continue;
      const full = join(dir, entry.name);
      if (entry.isDirectory()) {
        await walk(full, depth + 1);
      } else if (entry.isFile() && entry.name.endsWith(".py")) {
        out.push(full);
      }
    }
  }
  await walk(root, 1);
  return out;
}

function matchAtDir(dir, parts, idx) {
  const segment = parts[idx];
  const last = idx === parts.length - 1;
  const entries = readdirSafe(dir);

  if (segment === "*") {
    for (const entry of entries) {
      const full = join(dir, entry);
      if (last) return true;
      if (isDir(full) && matchAtDir(full, parts, idx + 1)) return true;
    }
    return false;
  }
  if (segment.includes("*")) {
    const re = new RegExp("^" + segment.split("*").map(escapeRegex).join(".*") + "$");
    for (const entry of entries) {
      if (!re.test(entry)) continue;
      const full = join(dir, entry);
      if (last) return true;
      if (isDir(full) && matchAtDir(full, parts, idx + 1)) return true;
    }
    return false;
  }
  // literal segment
  const full = join(dir, segment);
  if (last) return pathExists(full);
  return isDir(full) && matchAtDir(full, parts, idx + 1);
}

function globExists(root, pattern) {
  // Probe at depth 0, 1, 2 (parity with bash detector's three-level expansion).
  const tries = [pattern, `*/${pattern}`, `*/*/${pattern}`];
  for (const t of tries) {
    if (matchAtDir(root, t.split("/"), 0)) return true;
  }
  return false;
}

export async function detectEnv(projectRoot) {
  if (process.env.LITESTAR_SKILLS_HOOK_DISABLE === "1") return {};
  const root = resolve(projectRoot || process.cwd());
  if (!isDir(root)) return {};

  const mapData = JSON.parse(readFileSync(SKILL_MAP_PATH, "utf8"));
  const matchers = mapData.matchers;
  const intro = mapData.static_intro || "";

  const pyprojectDeps = new Map();
  const pyprojectSections = [];
  const pythonImports = new Map();
  const fileGlobs = [];
  for (const m of matchers) {
    for (const sig of m.signals || []) {
      if (sig.type === "pyproject_dep") pyprojectDeps.set(sig.name.toLowerCase(), m.skill);
      else if (sig.type === "pyproject_section") pyprojectSections.push([sig.section, m.skill]);
      else if (sig.type === "python_import") pythonImports.set(sig.module, m.skill);
      else if (sig.type === "file_glob") fileGlobs.push([sig.pattern, m.skill]);
    }
  }

  const detected = new Set();

  // pyproject.toml
  let pyprojectText = "";
  try {
    pyprojectText = readFileSync(join(root, "pyproject.toml"), "utf8");
  } catch {
    pyprojectText = "";
  }
  if (pyprojectText) {
    const lower = pyprojectText.toLowerCase();
    for (const [name, skill] of pyprojectDeps) {
      const re = new RegExp(`["']${escapeRegex(name)}(?:[\\[\\s>=<!~,"']|$)`);
      if (re.test(lower)) detected.add(skill);
    }
    for (const [section, skill] of pyprojectSections) {
      const re = new RegExp(`^\\s*\\[\\s*${escapeRegex(section)}(?:\\.|\\s*\\])`, "m");
      if (re.test(pyprojectText)) detected.add(skill);
    }
  }

  // python imports (capped)
  if (pythonImports.size > 0) {
    const patterns = new Map();
    for (const [mod] of pythonImports) {
      patterns.set(
        mod,
        new RegExp(
          `^\\s*(?:from\\s+${escapeRegex(mod)}(?:\\.|\\s)|import\\s+${escapeRegex(mod)}(?:\\.|\\s|$|,))`,
          "m",
        ),
      );
    }
    const files = await walkPyFiles(root, PY_FILE_CAP, PY_DEPTH_CAP);
    for (const file of files) {
      let text = "";
      try {
        text = readFileSync(file, "utf8");
      } catch {
        continue;
      }
      for (const [mod, skill] of pythonImports) {
        if (detected.has(skill)) continue;
        if (patterns.get(mod).test(text)) detected.add(skill);
      }
    }
  }

  // file globs
  for (const [pattern, skill] of fileGlobs) {
    if (detected.has(skill)) continue;
    if (globExists(root, pattern)) detected.add(skill);
  }

  // Order by priority (desc) then declaration order
  const ordered = matchers
    .map((m, i) => ({ m, i }))
    .sort((a, b) => (b.m.priority || 0) - (a.m.priority || 0) || a.i - b.i)
    .map(({ m }) => m.skill);
  const finalSkills = ordered.filter((s) => detected.has(s));

  const matchersBySkill = Object.fromEntries(matchers.map((m) => [m.skill, m]));
  const parts = [];
  if (intro) parts.push(intro);
  for (const s of finalSkills) {
    const reminder = matchersBySkill[s]?.reminder;
    if (reminder) parts.push(reminder);
  }

  return {
    detected_skills: finalSkills,
    context: parts.join("\n\n"),
    project_root: root,
  };
}

// CLI entry: run only when invoked directly.
const isMainModule =
  import.meta.url === `file://${process.argv[1]}` ||
  process.argv[1] === fileURLToPath(import.meta.url);

if (isMainModule) {
  const projectRoot = process.argv[2] || process.cwd();
  detectEnv(projectRoot)
    .then((out) => {
      process.stdout.write(JSON.stringify(out) + "\n");
    })
    .catch((err) => {
      process.stderr.write(JSON.stringify({ error: String(err) }) + "\n");
      process.exit(1);
    });
}
