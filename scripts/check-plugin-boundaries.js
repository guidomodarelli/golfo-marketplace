#!/usr/bin/env node

'use strict';

/**
 * Checks that every plugin works when it is installed on its own.
 *
 * Claude Code, Codex and Hermes install each plugin in its own directory, so:
 * - a relative Markdown link in a plugin must resolve to a file inside that same
 *   plugin (a link into a sibling plugin breaks once installed);
 * - a skill that names a skill of another plugin declares that plugin in the
 *   `metadata.plugin-dependencies` field of its `SKILL.md` frontmatter (a
 *   comma-separated string, as the Agent Skills specification requires), and every
 *   declared plugin exists.
 *
 * Usage:
 *   pnpm check-plugin-boundaries [plugins-dir]   (default: plugins/)
 */

const fs = require('fs');
const path = require('path');
const YAML = require('yaml');
const { paint, stderrOutput } = require('./lib/terminal-output');

const REPOSITORY_ROOT = path.join(__dirname, '..');
const DEFAULT_PLUGINS_DIR = path.join(REPOSITORY_ROOT, 'plugins');
const SKILL_FILE_NAME = 'SKILL.md';
const DEPENDENCIES_FIELD = 'plugin-dependencies';
/** Directories whose Markdown is test or eval data, not instructions an installed agent reads. */
const IGNORED_DIRECTORIES = new Set(['evals', 'tests', 'node_modules', '.git']);
const MARKDOWN_LINK_PATTERN = /\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g;
const EXTERNAL_TARGET_PATTERN = /^(?:[a-z][a-z0-9+.-]*:|#|\/|<)/i;
/** A link target that is a file path; placeholders such as `{{run_url}}` or `...` are not. */
const FILE_TARGET_PATTERN = /^(?=.*[a-z])[\w%@.-]+(?:\/[\w%@.-]+)*\/?$/i;
const FENCED_CODE_PATTERN = /^(```|~~~)[\s\S]*?^\1/gm;
const INLINE_CODE_PATTERN = /`[^`\n]*`/g;
const FRONTMATTER_PATTERN = /^---\r?\n([\s\S]*?)\r?\n---/;
/**
 * Skills left out of the dependency check, with the reason. agent-ready-setup stays
 * out of the plugin reorganization on purpose; its mention of constants-refactor is
 * reviewed apart.
 */
const DEPENDENCY_CHECK_EXEMPTIONS = new Map([
  ['agent-ready-setup', 'fuera de la reorganización de plugins por decisión del usuario'],
]);

/**
 * @param {string} directory
 * @returns {string[]} Markdown files under the directory, skipping ignored directories.
 */
function listMarkdownFiles(directory) {
  const files = [];
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      if (!IGNORED_DIRECTORIES.has(entry.name)) files.push(...listMarkdownFiles(fullPath));
    } else if (entry.name.endsWith('.md')) {
      files.push(fullPath);
    }
  }
  return files;
}

/**
 * @param {string} pluginsDirectory
 * @returns {{name: string, root: string, skills: string[]}[]} Plugins with their skill names.
 */
function discoverPluginSkills(pluginsDirectory) {
  return fs.readdirSync(pluginsDirectory, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => {
      const root = path.join(pluginsDirectory, entry.name);
      const skillsRoot = path.join(root, 'skills');
      const skills = fs.existsSync(skillsRoot)
        ? fs.readdirSync(skillsRoot, { withFileTypes: true })
          .filter((skill) => skill.isDirectory() && fs.existsSync(path.join(skillsRoot, skill.name, SKILL_FILE_NAME)))
          .map((skill) => skill.name)
        : [];
      return { name: entry.name, root, skills };
    });
}

/**
 * Builds the pattern that finds a skill name written as code, a path segment or a
 * `plugin:skill` reference.
 *
 * @param {string} skill
 * @returns {RegExp}
 */
function skillMentionPattern(skill) {
  return new RegExp(`(?:\`|/|:)${skill.replace(/[-]/g, '\\-')}(?:\`|/|\\b)`);
}

/**
 * When a link resolves to `<plugin>/skills/<skill>/...` and that skill lives in a sibling
 * plugin, names that plugin.
 *
 * @param {{root: string}} plugin
 * @param {string} resolved Absolute target inside the plugin that does not exist.
 * @returns {string | undefined}
 */
function findPluginOwningPath(plugin, resolved) {
  const relative = path.relative(path.join(plugin.root, 'skills'), resolved).split(path.sep);
  if (relative[0] === '..' || relative.length === 0) return undefined;
  const pluginsDirectory = path.dirname(plugin.root);
  return fs.readdirSync(pluginsDirectory).find((name) => fs.existsSync(path.join(pluginsDirectory, name, 'skills', ...relative)));
}

/**
 * Finds the relative Markdown links of a plugin that do not resolve inside it.
 *
 * @param {{name: string, root: string}} plugin
 * @param {string} repositoryRoot
 * @returns {string[]} Problems with the file path relative to the repository.
 */
function findBrokenLinks(plugin, repositoryRoot) {
  const problems = [];
  for (const file of listMarkdownFiles(plugin.root)) {
    const text = fs.readFileSync(file, 'utf8').replace(FENCED_CODE_PATTERN, '').replace(INLINE_CODE_PATTERN, '');
    for (const match of text.matchAll(MARKDOWN_LINK_PATTERN)) {
      const target = match[1];
      if (EXTERNAL_TARGET_PATTERN.test(target)) continue;
      const targetPath = target.split('#')[0];
      if (!targetPath || !FILE_TARGET_PATTERN.test(targetPath)) continue;
      const resolved = path.resolve(path.dirname(file), decodeURI(targetPath));
      const where = path.relative(repositoryRoot, file).split(path.sep).join('/');
      if (!resolved.startsWith(plugin.root + path.sep)) {
        problems.push(`${where}: link to ${target} leaves plugin ${plugin.name}; name the skill and its plugin instead`);
      } else if (!fs.existsSync(resolved)) {
        const otherPlugin = findPluginOwningPath(plugin, resolved);
        problems.push(otherPlugin
          ? `${where}: link to ${target} points to a skill of ${otherPlugin}; name the skill and its plugin instead`
          : `${where}: link to ${target} does not exist`);
      }
    }
  }
  return problems;
}

/**
 * Reads the declared plugin dependencies of a skill.
 *
 * @param {string} skillFile
 * @returns {string[]}
 */
function readDeclaredDependencies(skillFile) {
  const frontmatter = FRONTMATTER_PATTERN.exec(fs.readFileSync(skillFile, 'utf8'));
  if (!frontmatter) return [];
  const value = YAML.parse(frontmatter[1])?.metadata?.[DEPENDENCIES_FIELD];
  if (typeof value !== 'string') return [];
  return value.split(',').map((name) => name.trim()).filter(Boolean);
}

/**
 * Lists, for one skill, the plugins of the other skills it names.
 *
 * @param {string} skillDirectory
 * @param {string} ownPlugin
 * @param {Map<string, string>} ownerBySkill
 * @returns {Map<string, string[]>} Plugin → skills of that plugin the skill names.
 */
function findRequiredPlugins(skillDirectory, ownPlugin, ownerBySkill) {
  const text = listMarkdownFiles(skillDirectory).map((file) => fs.readFileSync(file, 'utf8')).join('\n');
  const required = new Map();
  for (const [skill, plugin] of ownerBySkill) {
    if (plugin === ownPlugin || !skillMentionPattern(skill).test(text)) continue;
    required.set(plugin, [...(required.get(plugin) ?? []), skill]);
  }
  return required;
}

/**
 * Checks the dependency declarations of every skill.
 *
 * @param {{name: string, root: string, skills: string[]}[]} plugins
 * @param {string} repositoryRoot
 * @returns {string[]}
 */
function findDependencyProblems(plugins, repositoryRoot) {
  const ownerBySkill = new Map(plugins.flatMap((plugin) => plugin.skills.map((skill) => [skill, plugin.name])));
  const pluginNames = new Set(plugins.map((plugin) => plugin.name));
  const problems = [];
  for (const plugin of plugins) {
    for (const skill of plugin.skills) {
      if (DEPENDENCY_CHECK_EXEMPTIONS.has(skill)) continue;
      const skillDirectory = path.join(plugin.root, 'skills', skill);
      const skillFile = path.join(skillDirectory, SKILL_FILE_NAME);
      const where = path.relative(repositoryRoot, skillFile).split(path.sep).join('/');
      const declared = readDeclaredDependencies(skillFile);
      for (const name of declared) {
        if (!pluginNames.has(name)) problems.push(`${where}: metadata.${DEPENDENCIES_FIELD} names ${name}, which is not a plugin`);
        if (name === plugin.name) problems.push(`${where}: metadata.${DEPENDENCIES_FIELD} names its own plugin ${name}`);
      }
      for (const [requiredPlugin, skills] of findRequiredPlugins(skillDirectory, plugin.name, ownerBySkill)) {
        if (!declared.includes(requiredPlugin)) {
          problems.push(`${where}: names ${skills.join(', ')} of ${requiredPlugin}; add ${requiredPlugin} to metadata.${DEPENDENCIES_FIELD}`);
        }
      }
    }
  }
  return problems;
}

/**
 * @param {string} pluginsDirectory
 * @returns {string[]} Every boundary problem found.
 */
function checkPluginBoundaries(pluginsDirectory) {
  const repositoryRoot = path.dirname(pluginsDirectory);
  const plugins = discoverPluginSkills(pluginsDirectory);
  return [
    ...plugins.flatMap((plugin) => findBrokenLinks(plugin, repositoryRoot)),
    ...findDependencyProblems(plugins, repositoryRoot),
  ];
}

function main() {
  const pluginsDirectory = path.resolve(process.argv[2] || DEFAULT_PLUGINS_DIR);
  const problems = checkPluginBoundaries(pluginsDirectory);
  const isGitHubActions = process.env.GITHUB_ACTIONS === 'true';
  for (const problem of problems) {
    console.error(`${paint('red', '✖', stderrOutput)} ${problem}`);
    if (isGitHubActions) console.log(`::error file=${problem.split(':')[0]}::${problem}`);
  }
  if (problems.length > 0) {
    console.error(paint('red', `${problems.length} plugin boundary problem(s).`, stderrOutput));
    process.exitCode = 1;
    return;
  }
  console.log(`${paint('green', '✔')} every plugin links only inside itself and declares its plugin dependencies.`);
}

if (require.main === module) {
  try {
    main();
  } catch (error) {
    console.error(paint('red', `✖ check-plugin-boundaries failed: ${error.message}`, stderrOutput));
    process.exitCode = 1;
  }
}

module.exports = { checkPluginBoundaries, findRequiredPlugins, readDeclaredDependencies, skillMentionPattern, DEPENDENCIES_FIELD };
