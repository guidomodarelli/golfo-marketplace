#!/usr/bin/env node

'use strict';

/**
 * Copies the files shared by several plugins from their canonical source in
 * `shared/` to every plugin that uses them, as declared in `shared/shared-files.json`.
 *
 * A plugin is installed on its own (Claude Code, Codex and Hermes each copy one plugin
 * directory), so a relative link to another plugin does not resolve at runtime: each
 * plugin carries its own copy. The copies are generated and never edited by hand.
 *
 * Usage:
 *   pnpm sync-shared-files            write the copies
 *   pnpm sync-shared-files --check    fail when a copy is missing, differs or is stale (CI)
 *   pnpm sync-shared-files --help
 */

const fs = require('fs');
const path = require('path');
const { paint, stderrOutput } = require('./lib/terminal-output');

const REPOSITORY_ROOT = path.join(__dirname, '..');
const SHARED_DIRECTORY_NAME = 'shared';
const CONFIG_FILE_NAME = 'shared-files.json';
const PLUGINS_DIRECTORY_NAME = 'plugins';
const CHECK_FLAG = '--check';
const HELP_FLAGS = ['--help', '-h'];
const ROOT_FLAG = '--root';
const SYNC_COMMAND = 'pnpm sync-shared-files';

const USAGE = `Usage: ${SYNC_COMMAND} [${CHECK_FLAG}] [${ROOT_FLAG} <repository>]

Copies shared/<source> to plugins/<plugin>/<source> for every entry of shared/${CONFIG_FILE_NAME}.
  ${CHECK_FLAG}   do not write; exit 1 when a copy is missing, differs or has extra files
  ${ROOT_FLAG}    repository root (default: this repository)`;

/**
 * Lists the files of a source, relative to it, skipping excluded top-level directories.
 *
 * @param {string} sourcePath Absolute file or directory.
 * @param {string[]} excluded Names of directories skipped at any depth.
 * @returns {string[]} Relative POSIX paths; `['']` when the source is a single file.
 */
function listFiles(sourcePath, excluded = []) {
  if (!fs.existsSync(sourcePath)) return [];
  if (fs.statSync(sourcePath).isFile()) return [''];
  const files = [];
  const walk = (directory, prefix) => {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        if (!excluded.includes(entry.name)) walk(path.join(directory, entry.name), `${prefix}${entry.name}/`);
      } else {
        files.push(`${prefix}${entry.name}`);
      }
    }
  };
  walk(sourcePath, '');
  return files.sort();
}

/**
 * Reads and validates the shared files configuration.
 *
 * @param {string} repositoryRoot
 * @returns {{source: string, plugins: string[], exclude?: string[]}[]}
 */
function readEntries(repositoryRoot) {
  const configPath = path.join(repositoryRoot, SHARED_DIRECTORY_NAME, CONFIG_FILE_NAME);
  let config;
  try {
    config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
  } catch (error) {
    throw new Error(`cannot read ${SHARED_DIRECTORY_NAME}/${CONFIG_FILE_NAME}: ${error.message}`, { cause: error });
  }
  if (!Array.isArray(config.entries)) throw new Error(`${SHARED_DIRECTORY_NAME}/${CONFIG_FILE_NAME} must have an "entries" array`);
  return config.entries;
}

/**
 * Compares or writes every copy declared in the configuration.
 *
 * @param {{repositoryRoot: string, check: boolean}} options
 * @returns {{problems: string[], written: string[], upToDate: number}}
 */
function syncSharedFiles({ repositoryRoot, check }) {
  const problems = [];
  const written = [];
  let upToDate = 0;
  for (const entry of readEntries(repositoryRoot)) {
    const sourcePath = path.join(repositoryRoot, SHARED_DIRECTORY_NAME, entry.source);
    const sourceFiles = listFiles(sourcePath, entry.exclude);
    if (sourceFiles.length === 0) {
      problems.push(`${SHARED_DIRECTORY_NAME}/${entry.source}: source does not exist`);
      continue;
    }
    for (const plugin of entry.plugins) {
      const pluginRoot = path.join(repositoryRoot, PLUGINS_DIRECTORY_NAME, plugin);
      if (!fs.existsSync(pluginRoot)) {
        problems.push(`${entry.source}: plugin ${plugin} does not exist`);
        continue;
      }
      const targetPath = path.join(pluginRoot, entry.source);
      const label = `${PLUGINS_DIRECTORY_NAME}/${plugin}/${entry.source}`;
      for (const relativeFile of sourceFiles) {
        const sourceFile = relativeFile ? path.join(sourcePath, relativeFile) : sourcePath;
        const targetFile = relativeFile ? path.join(targetPath, relativeFile) : targetPath;
        const shownTarget = relativeFile ? `${label}/${relativeFile}` : label;
        const expected = fs.readFileSync(sourceFile);
        const actual = fs.existsSync(targetFile) ? fs.readFileSync(targetFile) : null;
        if (actual && actual.equals(expected)) {
          upToDate += 1;
          continue;
        }
        if (check) {
          problems.push(`${shownTarget}: ${actual ? 'differs from' : 'missing copy of'} ${SHARED_DIRECTORY_NAME}/${entry.source}${relativeFile ? `/${relativeFile}` : ''}`);
        } else {
          fs.mkdirSync(path.dirname(targetFile), { recursive: true });
          fs.writeFileSync(targetFile, expected);
          written.push(shownTarget);
        }
      }
      if (sourceFiles[0] === '') continue;
      const expectedFiles = new Set(sourceFiles);
      for (const extraFile of listFiles(targetPath).filter((file) => !expectedFiles.has(file))) {
        if (check) {
          problems.push(`${label}/${extraFile}: not in ${SHARED_DIRECTORY_NAME}/${entry.source}`);
        } else {
          fs.rmSync(path.join(targetPath, extraFile));
          written.push(`${label}/${extraFile} (removed)`);
        }
      }
    }
  }
  return { problems, written, upToDate };
}

function main(argv) {
  if (argv.some((argument) => HELP_FLAGS.includes(argument))) {
    console.log(USAGE);
    return 0;
  }
  let repositoryRoot = REPOSITORY_ROOT;
  let check = false;
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === CHECK_FLAG) check = true;
    else if (argv[index] === ROOT_FLAG && argv[index + 1]) repositoryRoot = path.resolve(argv[++index]);
    else throw new Error(`invalid argument '${argv[index]}'; run ${SYNC_COMMAND} --help`);
  }
  const { problems, written, upToDate } = syncSharedFiles({ repositoryRoot, check });
  for (const file of written) console.log(`${paint('green', '✔')} wrote ${file}`);
  const isGitHubActions = process.env.GITHUB_ACTIONS === 'true';
  for (const problem of problems) {
    console.error(`${paint('red', '✖', stderrOutput)} ${problem}`);
    if (isGitHubActions) console.log(`::error::${problem}. Run ${SYNC_COMMAND} and commit the copies.`);
  }
  if (problems.length > 0) {
    console.error(paint('red', `${problems.length} shared file problem(s). Edit the source in ${SHARED_DIRECTORY_NAME}/ and run ${SYNC_COMMAND}.`, stderrOutput));
    return 1;
  }
  console.log(`${paint('green', '✔')} shared files in sync (${upToDate + written.length} copies).`);
  return 0;
}

if (require.main === module) {
  try {
    process.exitCode = main(process.argv.slice(2));
  } catch (error) {
    console.error(paint('red', `✖ sync-shared-files failed: ${error.message}`, stderrOutput));
    process.exitCode = 1;
  }
}

module.exports = { listFiles, syncSharedFiles };
