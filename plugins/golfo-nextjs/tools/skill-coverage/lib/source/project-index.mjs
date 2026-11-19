/**
 * Per-process view of a consumer project: the file list (tracked plus
 * untracked, honoring .gitignore), one parser, one resolver and a cache of
 * module analyses shared by every unit evaluated in the same command.
 */
import fs from 'node:fs';
import path from 'node:path';

import { ALWAYS_IGNORED_PREFIXES } from '../constants.mjs';
import { matchesAnyGlob } from '../support.mjs';
import { analyzeModule } from './module-analyzer.mjs';
import { createModuleResolver } from './module-resolver.mjs';
import { loadParser } from './parser-loader.mjs';

/**
 * Lists project files without Git, skipping generated trees.
 *
 * @param {string} projectRoot
 * @returns {string[]}
 */
function walkProjectFiles(projectRoot) {
  return fs.readdirSync(projectRoot, { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => path.relative(projectRoot, path.join(entry.parentPath ?? entry.path, entry.name)).split(path.sep).join('/'))
    .filter((filePath) => !ALWAYS_IGNORED_PREFIXES.some((prefix) => filePath.startsWith(prefix) || filePath.includes(`/${prefix}`)));
}

/**
 * @param {string} filePath POSIX project path.
 * @returns {boolean} Whether the registry or a generated tree owns the path.
 */
export function isAlwaysIgnored(filePath) {
  return ALWAYS_IGNORED_PREFIXES.some((prefix) => filePath.startsWith(prefix));
}

/**
 * Creates the index of one project.
 *
 * @param {{ projectRoot: string, config: any, git: ReturnType<import('../git/git-repository.mjs').openGitRepository> }} input
 */
export function createProjectIndex({ projectRoot, config, git }) {
  const listed = git.listFiles() ?? walkProjectFiles(projectRoot);
  const files = new Set(listed.filter((filePath) => !isAlwaysIgnored(filePath)));
  const parser = loadParser(projectRoot);
  const ignorePatterns = config.ignore ?? [];
  const analyses = new Map();

  /** Existence check that also sees files created after the listing. */
  const fileExists = (projectPath) => files.has(projectPath) || (!isAlwaysIgnored(projectPath) && fs.existsSync(path.join(projectRoot, projectPath)) && fs.statSync(path.join(projectRoot, projectPath)).isFile());
  const resolver = createModuleResolver(projectRoot, config, fileExists);

  return {
    files,
    parser,
    parserName: parser?.name ?? null,
    projectRoot,
    resolver,
    fileExists,

    /** @param {string} filePath */
    isIgnored: (filePath) => isAlwaysIgnored(filePath) || matchesAnyGlob(filePath, ignorePatterns),

    /**
     * Reads a project file from the working tree (so staged, unstaged and
     * untracked edits are all seen).
     *
     * @param {string} filePath
     * @returns {string | undefined} Content, or undefined when the file does not exist.
     */
    readSource(filePath) {
      try {
        return fs.readFileSync(path.join(projectRoot, filePath), 'utf8');
      } catch {
        return undefined;
      }
    },

    /**
     * Cached module analysis; `undefined` when the file does not exist.
     *
     * @param {string} filePath
     */
    analyze(filePath) {
      if (analyses.has(filePath)) return analyses.get(filePath);
      const source = this.readSource(filePath);
      const analysis = source === undefined ? undefined : analyzeModule({ parser, path: filePath, resolver, source });
      analyses.set(filePath, analysis);
      return analysis;
    },

    /** Drops cached analyses so a second fingerprint sees later edits. */
    invalidate() {
      analyses.clear();
    },
  };
}
