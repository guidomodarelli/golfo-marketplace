/**
 * Identity of a skill's normative definition: version from the SKILL.md
 * frontmatter and a hash of the files the policy declares (SKILL.md and its
 * references). The frontmatter `version` line is excluded from the hash, so
 * a bump without content changes does not invalidate coverage, while any
 * change to the rules does.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { entryHash, globToRegExp, normalizeLineEndings, sha256 } from './support.mjs';

/** Environment variable pointing to a directory that contains the skills (one folder per skill). */
export const SKILLS_DIRECTORY_ENVIRONMENT_VARIABLE = 'GOLFO_COVERAGE_SKILLS_DIR';

/** Root of the plugin that carries this copy of the tool (`<plugin>/tools/skill-coverage/lib` → `<plugin>`). */
const OWN_PLUGIN_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const DEFAULT_SKILLS_DIRECTORY = path.join(OWN_PLUGIN_ROOT, 'skills');
/**
 * Claude Code registry of the active installation of each plugin. It sits two levels above
 * the cache of a marketplace: `<plugins>/installed_plugins.json` next to
 * `<plugins>/cache/<marketplace>/<plugin>/<version>`.
 */
const CLAUDE_INSTALLED_PLUGINS_FILE = 'installed_plugins.json';

/**
 * @param {string} directory
 * @returns {string[]} Absolute paths of its subdirectories; empty when it cannot be read.
 */
function childDirectories(directory) {
  try {
    return fs.readdirSync(directory, { withFileTypes: true }).filter((entry) => entry.isDirectory()).map((entry) => path.join(directory, entry.name));
  } catch {
    return [];
  }
}

/**
 * Reads the install paths Claude Code marks as active.
 *
 * @param {string} cacheDirectory `<plugins>/cache`.
 * @returns {Set<string> | null} Normalized active install paths, or null when the registry is missing or unreadable.
 */
function readActiveInstallPaths(cacheDirectory) {
  const registryFile = path.join(path.dirname(cacheDirectory), CLAUDE_INSTALLED_PLUGINS_FILE);
  try {
    const registry = JSON.parse(fs.readFileSync(registryFile, 'utf8'));
    const installPaths = Object.values(registry.plugins ?? {})
      .flat()
      .map((installation) => installation?.installPath)
      .filter((installPath) => typeof installPath === 'string')
      .map((installPath) => path.resolve(installPath));
    return new Set(installPaths);
  } catch {
    return null;
  }
}

/**
 * Lists the `skills/` directories of the plugins installed next to this one, so a skill
 * that lives in another golfo plugin is still found. Covers the repository and Hermes
 * layout (`<plugins>/<plugin>/skills`) and the Claude Code cache layout
 * (`<marketplace>/<plugin>/<version>/skills`). The cache keeps old versions, so for each
 * cached plugin only its active version counts: the one `installed_plugins.json` names, or
 * the only version present. A plugin with several cached versions and no way to tell the
 * active one is left out, so the CLI reports the definition as not installed instead of
 * hashing outdated rules.
 *
 * @returns {string[]} Existing sibling skills directories, own plugin excluded.
 */
function siblingSkillsDirectories() {
  const parent = path.dirname(OWN_PLUGIN_ROOT);
  const candidates = [];
  for (const pluginDirectory of childDirectories(parent)) {
    if (pluginDirectory !== OWN_PLUGIN_ROOT) candidates.push(path.join(pluginDirectory, 'skills'));
  }
  const marketplaceDirectory = path.dirname(parent);
  let activeInstallPaths;
  for (const pluginDirectory of childDirectories(marketplaceDirectory)) {
    if (pluginDirectory === parent) continue;
    const versionDirectories = childDirectories(pluginDirectory).filter((directory) => fs.existsSync(path.join(directory, 'skills')));
    if (versionDirectories.length === 0) continue;
    if (versionDirectories.length === 1) {
      candidates.push(path.join(versionDirectories[0], 'skills'));
      continue;
    }
    activeInstallPaths ??= readActiveInstallPaths(path.dirname(marketplaceDirectory));
    const activeVersions = versionDirectories.filter((directory) => activeInstallPaths?.has(path.resolve(directory)));
    if (activeVersions.length === 1) candidates.push(path.join(activeVersions[0], 'skills'));
  }
  return candidates.filter((directory) => fs.existsSync(directory));
}

/**
 * Resolves the directory of a skill. An explicit directory (argument or
 * `GOLFO_COVERAGE_SKILLS_DIR`) is used as is; otherwise the skill is looked up in this
 * plugin first and then in the golfo plugins installed next to it.
 *
 * @param {string} skill
 * @param {string} [skillsDirectory]
 * @returns {string} Absolute skill directory (it may not exist).
 */
export function skillDirectory(skill, skillsDirectory) {
  const explicitDirectory = skillsDirectory ?? process.env[SKILLS_DIRECTORY_ENVIRONMENT_VARIABLE];
  if (explicitDirectory) return path.join(explicitDirectory, skill);
  const ownDirectory = path.join(DEFAULT_SKILLS_DIRECTORY, skill);
  if (fs.existsSync(path.join(ownDirectory, 'SKILL.md'))) return ownDirectory;
  const sibling = siblingSkillsDirectories()
    .map((directory) => path.join(directory, skill))
    .find((directory) => fs.existsSync(path.join(directory, 'SKILL.md')));
  return sibling ?? ownDirectory;
}

/**
 * @typedef {{ name: string, version: string | null, hash: string | null, files: Record<string, string>, available: boolean }} SkillDefinition
 */

/**
 * Reads the definition of a skill.
 *
 * @param {any} policy
 * @param {{ skillsDirectory?: string }} [options]
 * @returns {SkillDefinition} `available: false` when the skill files are not installed here.
 */
export function readSkillDefinition(policy, options = {}) {
  const directory = skillDirectory(policy.skill, options.skillsDirectory);
  const skillFile = path.join(directory, 'SKILL.md');
  if (!fs.existsSync(skillFile)) return { available: false, files: {}, hash: null, name: policy.skill, version: null };
  const patterns = policy.definitionFiles.map(globToRegExp);
  const relativeFiles = fs.readdirSync(directory, { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => path.relative(directory, path.join(entry.parentPath ?? entry.path, entry.name)).split(path.sep).join('/'))
    .filter((relativePath) => patterns.some((pattern) => pattern.test(relativePath)))
    .sort();
  const files = {};
  let version = null;
  for (const relativePath of relativeFiles) {
    let content = normalizeLineEndings(fs.readFileSync(path.join(directory, relativePath), 'utf8'));
    if (relativePath === 'SKILL.md') {
      version = /^\s*version:\s*["']?([^"'\n]+)["']?\s*$/m.exec(content)?.[1] ?? null;
      content = content.replace(/^\s*version:.*$/m, '');
    }
    files[relativePath] = entryHash(content);
  }
  const hash = `sha256:${sha256(Object.entries(files).map(([file, fileHash]) => `${file}=${fileHash}`).join('\n'))}`;
  return { available: true, files, hash, name: policy.skill, version };
}
