#!/usr/bin/env node

'use strict';

/**
 * Validates that every marketplace plugin can be installed as an Agent Plugins v1
 * portable package (the format Hermes installs with `hermes plugins install`).
 *
 * For each plugin under `plugins/` it checks:
 * - a root `plugin.json` exists, declares the Agent Plugins v1 schema, uses the
 *   directory name as `name`, and only contains fields the spec defines;
 * - its version matches the Claude manifest;
 * - every `skills/<name>/SKILL.md` frontmatter satisfies the Agent Skills
 *   constraints that portable runtimes enforce (Hermes silently drops a skill
 *   that breaks them);
 * - no other `SKILL.md` sits where Hermes would install it as a skill of its own.
 *   Hermes walks `skills/` recursively and, inside a directory with a `SKILL.md`,
 *   only skips its support directories, so a template or an example elsewhere in a
 *   skill becomes a real skill.
 *
 * Usage:
 *   pnpm validate-portable-plugins [plugins-dir]   (default: plugins/)
 */

const fs = require('fs');
const path = require('path');
const YAML = require('yaml');
const {
  AGENT_PLUGINS_SCHEMA_V1,
  PORTABLE_MANIFEST_FIELDS,
  PORTABLE_PLUGIN_NAME_PATTERN,
  SKILL_DESCRIPTION_MAX_CHARACTERS,
  SKILL_NAME_MAX_CHARACTERS,
  SKILL_NAME_PATTERN,
  discoverPlugins,
  readManifest,
} = require('./lib/plugin-manifests');

const REPOSITORY_ROOT = path.join(__dirname, '..');
const DEFAULT_PLUGINS_DIR = path.join(REPOSITORY_ROOT, 'plugins');
const SKILL_FILE_NAME = 'SKILL.md';
// Directories Hermes skips inside a skill (SKILL_SUPPORT_DIRS in its agent/skill_utils.py).
const SKILL_SUPPORT_DIRECTORIES = new Set(['references', 'templates', 'assets', 'scripts']);
const FRONTMATTER_PATTERN = /^---\r?\n([\s\S]*?)\r?\n---\s*(?:\r?\n|$)/;

/**
 * Counts Unicode code points, matching how portable runtimes measure string limits.
 *
 * @param {string} text Text to measure.
 * @returns {number} Number of code points.
 */
function countCharacters(text) {
  return [...text].length;
}

/**
 * Validates the portable root manifest of a plugin.
 *
 * @param {{ name: string, claudePath: string, portablePath: string | null }} plugin Plugin descriptor.
 * @returns {string[]} Problems found.
 */
function validatePortableManifest(plugin) {
  if (!plugin.portablePath) {
    return ['Missing portable root plugin.json (Agent Plugins v1), so Hermes cannot install this plugin.'];
  }

  let manifest;
  try {
    manifest = JSON.parse(fs.readFileSync(plugin.portablePath, 'utf8'));
  } catch (error) {
    return [`Portable plugin.json is not valid JSON: ${error.message}`];
  }

  const problems = [];
  if (manifest.$schema !== AGENT_PLUGINS_SCHEMA_V1) {
    problems.push(`Portable plugin.json must declare "$schema": "${AGENT_PLUGINS_SCHEMA_V1}".`);
  }
  if (manifest.name !== plugin.name || !PORTABLE_PLUGIN_NAME_PATTERN.test(manifest.name)) {
    problems.push(`Portable plugin.json name must be "${plugin.name}" and match ${PORTABLE_PLUGIN_NAME_PATTERN}.`);
  }
  const unknownFields = Object.keys(manifest).filter((field) => !PORTABLE_MANIFEST_FIELDS.has(field));
  if (unknownFields.length > 0) {
    problems.push(`Portable plugin.json has fields outside Agent Plugins v1: ${unknownFields.join(', ')}.`);
  }
  const claudeVersion = readManifest(plugin.claudePath).version;
  if (manifest.version !== claudeVersion) {
    problems.push(
      `Portable plugin.json version ${manifest.version} differs from the Claude manifest version ${claudeVersion}.`
    );
  }
  return problems;
}

/**
 * Validates one skill's frontmatter against the Agent Skills constraints.
 *
 * @param {string} skillDirectory Absolute path to the skill directory.
 * @returns {string[]} Problems found, prefixed with the skill name.
 */
function validateSkill(skillDirectory) {
  const skillName = path.basename(skillDirectory);
  const contents = fs.readFileSync(path.join(skillDirectory, SKILL_FILE_NAME), 'utf8').replace(/^﻿/, '');
  const frontmatterMatch = contents.match(FRONTMATTER_PATTERN);
  if (!frontmatterMatch) {
    return [`skill ${skillName}: SKILL.md has no YAML frontmatter.`];
  }

  let frontmatter;
  try {
    frontmatter = YAML.parse(frontmatterMatch[1]);
  } catch (error) {
    return [`skill ${skillName}: invalid YAML frontmatter: ${error.message}`];
  }
  if (!frontmatter || typeof frontmatter !== 'object') {
    return [`skill ${skillName}: YAML frontmatter must be an object.`];
  }

  const problems = [];
  const { name, description } = frontmatter;
  if (
    name !== skillName ||
    countCharacters(name) > SKILL_NAME_MAX_CHARACTERS ||
    !SKILL_NAME_PATTERN.test(name)
  ) {
    problems.push(`skill ${skillName}: frontmatter name must equal the directory name and match ${SKILL_NAME_PATTERN}.`);
  }
  if (typeof description !== 'string' || description.length === 0) {
    problems.push(`skill ${skillName}: description must be a non-empty string.`);
  } else if (countCharacters(description) > SKILL_DESCRIPTION_MAX_CHARACTERS) {
    problems.push(
      `skill ${skillName}: description has ${countCharacters(description)} characters; ` +
        `the limit is ${SKILL_DESCRIPTION_MAX_CHARACTERS}.`
    );
  }
  return problems;
}

/**
 * Validates every skill shipped by a plugin.
 *
 * @param {{ rootPath: string }} plugin Plugin descriptor.
 * @returns {string[]} Problems found.
 */
function validateSkills(plugin) {
  const skillsRoot = path.join(plugin.rootPath, 'skills');
  if (!fs.existsSync(skillsRoot)) {
    return [];
  }
  return fs
    .readdirSync(skillsRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => path.join(skillsRoot, entry.name))
    .filter((skillDirectory) => fs.existsSync(path.join(skillDirectory, SKILL_FILE_NAME)))
    .flatMap(validateSkill);
}

/**
 * Lists every `SKILL.md` that Hermes would load from a skills directory, walking it the
 * way Hermes does: recursively, skipping the support directories only inside a
 * directory that holds a `SKILL.md`. Symlinked directories are not followed.
 *
 * @param {string} directory Absolute path of the directory to walk.
 * @returns {string[]} Absolute paths of the directories that hold a discovered `SKILL.md`.
 */
function discoverHermesSkillDirectories(directory) {
  const entries = fs.readdirSync(directory, { withFileTypes: true });
  const holdsSkill = entries.some((entry) => entry.isFile() && entry.name === SKILL_FILE_NAME);
  const nested = entries
    .filter((entry) => entry.isDirectory() && !(holdsSkill && SKILL_SUPPORT_DIRECTORIES.has(entry.name)))
    .flatMap((entry) => discoverHermesSkillDirectories(path.join(directory, entry.name)));
  return holdsSkill ? [directory, ...nested] : nested;
}

/**
 * Rejects a `SKILL.md` that Hermes would install as a separate skill: anything other
 * than `skills/<name>/SKILL.md`, such as an example or a template outside the support
 * directories of its skill.
 *
 * @param {{ rootPath: string }} plugin Plugin descriptor.
 * @returns {string[]} Problems found, with the path relative to the skills directory.
 */
function validateNestedSkills(plugin) {
  const skillsRoot = path.join(plugin.rootPath, 'skills');
  if (!fs.existsSync(skillsRoot)) {
    return [];
  }
  const supportDirectories = [...SKILL_SUPPORT_DIRECTORIES].map((name) => `${name}/`).join(', ');
  return discoverHermesSkillDirectories(skillsRoot)
    .filter((skillDirectory) => path.dirname(skillDirectory) !== skillsRoot)
    .map((skillDirectory) => {
      const relativePath = path.relative(skillsRoot, path.join(skillDirectory, SKILL_FILE_NAME)).split(path.sep).join('/');
      return (
        `nested ${relativePath} would install as a separate skill in Hermes; ` +
        `move it under one of the support directories of its skill (${supportDirectories}).`
      );
    });
}

function main() {
  const pluginsDirectory = path.resolve(process.argv[2] || DEFAULT_PLUGINS_DIR);
  const isGitHubActions = process.env.GITHUB_ACTIONS === 'true';
  let failureCount = 0;

  for (const plugin of discoverPlugins(pluginsDirectory)) {
    const problems = [...validatePortableManifest(plugin), ...validateSkills(plugin), ...validateNestedSkills(plugin)];
    if (problems.length === 0) {
      console.log(`✔ ${plugin.name}: portable package is valid.`);
      continue;
    }

    failureCount += problems.length;
    const annotatedFile = path
      .relative(REPOSITORY_ROOT, plugin.portablePath || plugin.claudePath)
      .split(path.sep)
      .join('/');
    for (const problem of problems) {
      console.error(`✖ ${plugin.name}: ${problem}`);
      if (isGitHubActions) {
        console.log(`::error file=${annotatedFile}::${plugin.name}: ${problem}`);
      }
    }
  }

  if (failureCount > 0) {
    process.exit(1);
  }
}

try {
  main();
} catch (error) {
  console.error(`validate-portable-plugins failed: ${error.message}`);
  process.exit(1);
}
