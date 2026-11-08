/**
 * Finds the agent-ready-setup engine of an installed golfo-kit plugin.
 *
 * The launcher never ships a copy of the engine: it runs the one that Claude Code,
 * Codex or Hermes already installed, so a person and their agents use the same version.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

export const MARKETPLACE_NAME = "golfo-marketplace";
export const PLUGIN_NAME = "golfo-kit";
export const SKILL_NAME = "agent-ready-setup";
export const ENGINE_ENTRY_POINT = join("scripts", "agent-ready");
/** Same variable the engine honors: a development checkout wins over every installation. */
export const SKILL_DIRECTORY_VARIABLE = "AGENT_READY_SETUP_SKILL_DIR";
const PLUGIN_MANIFESTS = ["plugin.json", join(".claude-plugin", "plugin.json"), join(".codex-plugin", "plugin.json")];
const SEMANTIC_VERSION = /^(\d+)\.(\d+)\.(\d+)/;

export const INSTALL_HINT = [
  "Install the golfo-kit plugin for one of your agents:",
  "  Claude Code: claude plugin marketplace add --scope user guidomodarelli/golfo-marketplace",
  "               claude plugin install --scope user golfo-kit@golfo-marketplace",
  "  Codex:       codex plugin marketplace add <a clone of guidomodarelli/golfo-marketplace>",
  "               codex plugin add golfo-kit@golfo-marketplace",
  "  Hermes:      hermes plugins install guidomodarelli/golfo-marketplace#plugins/golfo-kit --enable",
  `Or point ${SKILL_DIRECTORY_VARIABLE} at an agent-ready-setup directory.`,
].join("\n");

export const UPDATE_HINT = [
  "Update the plugin:",
  "  Claude Code: claude plugin marketplace update golfo-marketplace",
  "               claude plugin update golfo-kit@golfo-marketplace",
  "  Codex:       codex plugin marketplace upgrade golfo-marketplace",
  "  Hermes:      hermes plugins update golfo-kit",
].join("\n");

/** A configuration that names an engine that is not there; the launcher exits 1 with it. */
export class EngineError extends Error {}

/**
 * @param {string} skillDirectory
 * @returns {boolean} whether the directory holds the CLI of the engine
 */
export function isEngine(skillDirectory) {
  return isFile(join(skillDirectory, ENGINE_ENTRY_POINT));
}

function isFile(path) {
  try {
    return statSync(path).isFile();
  } catch {
    return false;
  }
}

/**
 * @param {string} skillDirectory
 * @returns {string | null} the golfo-kit version from the plugin manifest two levels up
 */
export function pluginVersion(skillDirectory) {
  const pluginRoot = join(skillDirectory, "..", "..");
  for (const manifest of PLUGIN_MANIFESTS) {
    try {
      const { version } = JSON.parse(readFileSync(join(pluginRoot, manifest), "utf8"));
      if (typeof version === "string") {
        return version;
      }
    } catch {
      // The next manifest may exist: Hermes keeps only the portable one.
    }
  }
  return null;
}

/**
 * Orders X.Y.Z versions numerically; a missing or unreadable version sorts first.
 * @param {string | null} left
 * @param {string | null} right
 * @returns {number}
 */
export function compareVersions(left, right) {
  const parse = (version) => (SEMANTIC_VERSION.exec(version ?? "") ?? []).slice(1).map(Number);
  const leftParts = parse(left);
  const rightParts = parse(right);
  if (!leftParts.length || !rightParts.length) {
    return leftParts.length - rightParts.length;
  }
  for (let index = 0; index < leftParts.length; index += 1) {
    if (leftParts[index] !== rightParts[index]) {
      return leftParts[index] - rightParts[index];
    }
  }
  return 0;
}

/** Skill directories of every version a provider cache holds. */
function cachedSkillDirectories(cacheRoot) {
  try {
    return readdirSync(cacheRoot, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => join(cacheRoot, entry.name, "skills", SKILL_NAME));
  } catch {
    return [];
  }
}

/** Where Claude Code keeps the marketplace snapshot: its own registry says, or the default. */
function claudeMarketplaceRoot(configDirectory) {
  try {
    const known = JSON.parse(readFileSync(join(configDirectory, "plugins", "known_marketplaces.json"), "utf8"));
    const location = known?.[MARKETPLACE_NAME]?.installLocation;
    if (typeof location === "string") {
      return location;
    }
  } catch {
    // Without the registry, Claude Code uses the default location.
  }
  return join(configDirectory, "plugins", "marketplaces", MARKETPLACE_NAME);
}

/**
 * Every place where a provider installs golfo-kit, the same ones the session hook reads.
 * @param {NodeJS.ProcessEnv} environment
 * @param {string} home
 * @returns {{ provider: string, skillDirectory: string }[]}
 */
export function engineCandidates(environment, home) {
  const claudeDirectory = environment.CLAUDE_CONFIG_DIR || join(home, ".claude");
  const codexDirectory = environment.CODEX_HOME || join(home, ".codex");
  const hermesDirectories = [
    environment.HERMES_HOME,
    join(home, ".hermes"),
    environment.LOCALAPPDATA && join(environment.LOCALAPPDATA, "hermes"),
  ].filter(Boolean);
  const pluginSkill = (root) => join(root, "plugins", PLUGIN_NAME, "skills", SKILL_NAME);
  const cache = (providerDirectory) => join(providerDirectory, "plugins", "cache", MARKETPLACE_NAME, PLUGIN_NAME);
  return [
    ...cachedSkillDirectories(cache(claudeDirectory)).map((skillDirectory) => ({ provider: "claude", skillDirectory })),
    { provider: "claude", skillDirectory: pluginSkill(claudeMarketplaceRoot(claudeDirectory)) },
    ...cachedSkillDirectories(cache(codexDirectory)).map((skillDirectory) => ({ provider: "codex", skillDirectory })),
    { provider: "codex", skillDirectory: pluginSkill(join(codexDirectory, ".tmp", "marketplaces", MARKETPLACE_NAME)) },
    ...hermesDirectories.map((hermesHome) => ({ provider: "hermes", skillDirectory: pluginSkill(hermesHome) })),
  ];
}

/**
 * The newest installation that predates the CLI: it has the skill but not its entry point.
 * @param {NodeJS.ProcessEnv} environment
 * @param {string} home
 * @returns {{ provider: string, skillDirectory: string, version: string | null } | null}
 */
export function newestInstallationWithoutEngine(environment, home) {
  let newest = null;
  for (const candidate of engineCandidates(environment, home)) {
    if (isEngine(candidate.skillDirectory) || !isFile(join(candidate.skillDirectory, "SKILL.md"))) {
      continue;
    }
    const version = pluginVersion(candidate.skillDirectory);
    if (!newest || compareVersions(version, newest.version) > 0) {
      newest = { ...candidate, version };
    }
  }
  return newest;
}

/**
 * The engine to run: the override, or else the newest golfo-kit any provider installed.
 * @param {NodeJS.ProcessEnv} environment
 * @param {string} home
 * @returns {{ provider: string, skillDirectory: string, version: string | null } | null}
 */
export function resolveEngine(environment, home) {
  const override = environment[SKILL_DIRECTORY_VARIABLE];
  if (override) {
    if (!isEngine(override)) {
      throw new EngineError(`${SKILL_DIRECTORY_VARIABLE} points to ${override}, which has no ${ENGINE_ENTRY_POINT}`);
    }
    return { provider: "override", skillDirectory: override, version: pluginVersion(override) };
  }
  let newest = null;
  for (const candidate of engineCandidates(environment, home)) {
    if (!isEngine(candidate.skillDirectory)) {
      continue;
    }
    const version = pluginVersion(candidate.skillDirectory);
    // On a tie the earlier candidate stays, in the order the session hook prefers them.
    if (!newest || compareVersions(version, newest.version) > 0) {
      newest = { ...candidate, version };
    }
  }
  return newest;
}
