// hooks/lib/detect-env.js
// Project-aware library detection for litestar-skills (Node ESM port of detect-env.sh).
//
// Designed to be both:
//   * Imported as ESM:  import { detectEnv } from "./detect-env.js";
//   * Run as CLI:        node hooks/lib/detect-env.js <project_root>
//
// Reused by the OpenCode plugin — keep ESM-clean.
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
  "plugins",
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

function normalizeDepName(name) {
  return name.trim().toLowerCase().replace(/[-_.]+/g, "-");
}

function extractProjectName(pyprojectText) {
  let inTargetSection = false;
  for (const rawLine of pyprojectText.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    if (line.startsWith("[") && line.endsWith("]")) {
      const section = line.slice(1, -1).trim();
      inTargetSection = section === "project" || section === "tool.poetry";
      continue;
    }
    if (inTargetSection) {
      const m = line.match(/^name\s*=\s*["']([^"']+)["']/);
      if (m) return normalizeDepName(m[1]);
    }
  }
  return "";
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
      if (entry.startsWith(".") || SKIP_DIRS.has(entry)) continue;
      const full = join(dir, entry);
      if (last) return true;
      if (isDir(full) && matchAtDir(full, parts, idx + 1)) return true;
    }
    return false;
  }
  if (segment.includes("*")) {
    const re = new RegExp("^" + segment.split("*").map(escapeRegex).join(".*") + "$");
    for (const entry of entries) {
      if ((!segment.startsWith(".") && entry.startsWith(".")) || SKIP_DIRS.has(entry)) continue;
      if (!re.test(entry)) continue;
      const full = join(dir, entry);
      if (last) return true;
      if (isDir(full) && matchAtDir(full, parts, idx + 1)) return true;
    }
    return false;
  }
  // literal segment
  if (!last && (segment.startsWith(".") || SKIP_DIRS.has(segment))) return false;
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
  const pythonRegexes = [];
  const fileGlobs = [];
  const ownPackageToSkill = new Map();
  for (const m of matchers) {
    if (typeof m.own_package === "string" && m.own_package.trim()) {
      ownPackageToSkill.set(normalizeDepName(m.own_package), [m.own_package.trim(), m.skill]);
    }
    for (const pkg of m.own_packages || []) {
      if (typeof pkg === "string" && pkg.trim()) {
        ownPackageToSkill.set(normalizeDepName(pkg), [pkg.trim(), m.skill]);
      }
    }
    for (const sig of m.signals || []) {
      if (sig.type === "pyproject_dep") pyprojectDeps.set(sig.name.toLowerCase(), m.skill);
      else if (sig.type === "pyproject_section") pyprojectSections.push([sig.section, m.skill]);
      else if (sig.type === "python_import") pythonImports.set(sig.module, m.skill);
      else if (sig.type === "python_regex") {
        try {
          pythonRegexes.push([new RegExp(sig.pattern, "ms"), m.skill]);
        } catch {
          // Ignore malformed optional signals; validation catches shipped map errors.
        }
      } else if (sig.type === "file_glob") fileGlobs.push([sig.pattern, m.skill]);
    }
  }

  const detected = new Set();

  // pyproject.toml
  let pyprojectText = "";
  let projectName = "";
  try {
    pyprojectText = readFileSync(join(root, "pyproject.toml"), "utf8");
  } catch {
    pyprojectText = "";
  }
  if (pyprojectText) {
    projectName = extractProjectName(pyprojectText);
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

  // python imports / regex content signals (capped)
  if (pythonImports.size > 0 || pythonRegexes.length > 0) {
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
      for (const [pattern, skill] of pythonRegexes) {
        if (detected.has(skill)) continue;
        if (pattern.test(text)) detected.add(skill);
      }
    }
  }

  // file globs
  for (const [pattern, skill] of fileGlobs) {
    if (detected.has(skill)) continue;
    if (globExists(root, pattern)) detected.add(skill);
  }

  const ownEntry = projectName ? ownPackageToSkill.get(projectName) : undefined;
  if (ownEntry) {
    detected.delete(ownEntry[1]);
  }

  // Order by priority (desc) then declaration order
  const ordered = matchers
    .map((m, i) => ({ m, i }))
    .sort((a, b) => (b.m.priority || 0) - (a.m.priority || 0) || a.i - b.i)
    .map(({ m }) => m.skill);
  const finalSkills = ordered.filter((s) => detected.has(s));

  const parts = [];
  if (intro) parts.push(intro);
  if (ownEntry) {
    const [ownPkgDisplay, ownSkill] = ownEntry;
    parts.push(
      `Upstream library workspace detected (\`${ownPkgDisplay}\`). Do NOT rely on \`litestar:${ownSkill}\` or consumer skills for \`${ownPkgDisplay}\` internals or APIs — you are working on the library itself; treat this repository's source code as the source of truth (changes here may require a follow-up update to \`litestar-skills\`).`,
    );
    if (finalSkills.length > 0) {
      const qualified = finalSkills.map((s) => `litestar:${s}`).join(", ");
      parts.push(
        `Detected stack skills: ${qualified} (use only for sibling-library conventions, never for \`${ownPkgDisplay}\` internals).`,
      );
    }
  } else if (finalSkills.length > 0) {
    const qualified = finalSkills.map((s) => `litestar:${s}`).join(", ");
    parts.push(
      `Detected stack skills: ${qualified}. Load the matching skill before implementing or reviewing changes.`,
    );
  }

  const result = {
    detected_skills: finalSkills,
    context: parts.join(" "),
    project_root: root,
  };
  if (ownEntry) {
    result.suppressed_own_skill = ownEntry[1];
  }
  return result;
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
