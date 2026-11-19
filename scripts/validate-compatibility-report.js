#!/usr/bin/env node

'use strict';

/**
 * Validates the agent compatibility report of the golfo plugins:
 * - the JSON report against its versioned JSON Schema,
 * - the consistency rules (status derivation, evidence, incompatibility IDs,
 *   summary counts, one entry per skill directory),
 * - the Markdown report against the JSON (same skills, statuses and
 *   incompatibility IDs, and identical to the rendering).
 *
 * Usage:
 *   node scripts/validate-compatibility-report.js [--report <json>] [--markdown <md>]
 *     [--schema <json>] [--plugins-dir <dir>]
 *
 * Exit codes: 0 valid, 1 violations found, 2 usage or unreadable input.
 */

const fs = require('fs');
const path = require('path');
const { validateSchema } = require('./lib/json-schema-subset');
const { checkConsistency, checkMarkdownSync } = require('./lib/compatibility-report');

const REPOSITORY_ROOT = path.join(__dirname, '..');
const REFERENCES_DIR = path.join(REPOSITORY_ROOT, 'plugins', 'golfo-kit', 'references');
const DEFAULT_PATHS = {
  report: path.join(REFERENCES_DIR, 'compatibility-report.json'),
  markdown: path.join(REFERENCES_DIR, 'compatibility-report.md'),
  schema: path.join(REFERENCES_DIR, 'compatibility-report.schema.json'),
  'plugins-dir': path.join(REPOSITORY_ROOT, 'plugins'),
};
const EXIT_INVALID = 1;
const EXIT_USAGE = 2;

/**
 * Parses `--name value` flags over the defaults.
 *
 * @param {string[]} args Command-line arguments.
 * @returns {Record<string, string>} Resolved paths by option name.
 */
function parseArguments(args) {
  const options = { ...DEFAULT_PATHS };
  for (let index = 0; index < args.length; index += 2) {
    const optionName = (args[index] || '').replace(/^--/, '');
    if (!(optionName in DEFAULT_PATHS) || !args[index].startsWith('--') || args[index + 1] === undefined) {
      throw new Error(`invalid argument '${args[index]}'; expected --report, --markdown, --schema or --plugins-dir followed by a path`);
    }
    options[optionName] = path.resolve(args[index + 1]);
  }
  return options;
}

/**
 * Reads and parses a JSON file, naming the file on failure.
 *
 * @param {string} filePath JSON file path.
 * @returns {unknown} Parsed JSON.
 */
function readJson(filePath) {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch (error) {
    throw new Error(`could not read JSON ${filePath}: ${error.message}`, { cause: error });
  }
}

/**
 * Maps every skill of every plugin to its path relative to the repository.
 *
 * @param {string} pluginsDirectory Directory with one folder per plugin.
 * @returns {Record<string, string>} Skill id → `plugins/<plugin>/skills/<id>/SKILL.md`.
 */
function listSkillPaths(pluginsDirectory) {
  const skillPaths = {};
  for (const plugin of fs.readdirSync(pluginsDirectory, { withFileTypes: true }).filter((entry) => entry.isDirectory())) {
    const skillsDirectory = path.join(pluginsDirectory, plugin.name, 'skills');
    if (!fs.existsSync(skillsDirectory)) continue;
    for (const skill of fs.readdirSync(skillsDirectory, { withFileTypes: true })) {
      if (!skill.isDirectory() || !fs.existsSync(path.join(skillsDirectory, skill.name, 'SKILL.md'))) continue;
      if (skillPaths[skill.name]) throw new Error(`skill ${skill.name} exists in two plugins: ${skillPaths[skill.name]} and plugins/${plugin.name}`);
      skillPaths[skill.name] = `plugins/${plugin.name}/skills/${skill.name}/SKILL.md`;
    }
  }
  return skillPaths;
}

function main() {
  let options;
  let report;
  let schema;
  let markdown;
  let skillPathsOnDisk;
  try {
    options = parseArguments(process.argv.slice(2));
    schema = readJson(options.schema);
    report = readJson(options.report);
    markdown = fs.readFileSync(options.markdown, 'utf8');
    skillPathsOnDisk = listSkillPaths(options['plugins-dir']);
  } catch (error) {
    console.error(`validate-compatibility-report: ${error.message}`);
    process.exit(EXIT_USAGE);
  }

  const schemaErrors = validateSchema(schema, report).map((message) => `schema ${message}`);
  // Consistency rules assume the shape the schema guarantees.
  const errors = schemaErrors.length
    ? schemaErrors
    : [...checkConsistency(report, { skillPathsOnDisk }), ...checkMarkdownSync(report, markdown)];
  if (errors.length) {
    console.error(`Compatibility report is invalid (${errors.length} problem${errors.length === 1 ? '' : 's'}):`);
    for (const message of errors) console.error(`  - ${message}`);
    process.exit(EXIT_INVALID);
  }
  console.log(`Compatibility report is valid: ${report.skills.length} skills, schema ${report.schema_version}, Markdown in sync.`);
}

main();
