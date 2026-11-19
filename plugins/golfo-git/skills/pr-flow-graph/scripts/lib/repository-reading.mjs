import { spawnSync } from 'node:child_process';

import {
  EVIDENCE_CONTEXT_LINE_COUNT,
  GIT_REMOTE_REF_PREFIX,
  NAME_TOKEN_MIN_LENGTH,
  NAME_TOKEN_SUBSTRING_MIN_LENGTH,
} from './flow-graph-constants.mjs';

/**
 * Reading helpers shared by the two repository checks: the one of a pull request
 * (`check-evidence-in-repository.mjs`) and the one of an RFC (`check-rfc-in-repository.mjs`).
 */

const GIT_COMMAND = 'git';
const LINE_BREAK_PATTERN = /\r?\n/;
const IDENTIFIER_WORD_PATTERN = /[A-Za-z_][A-Za-z0-9_]*/g;
export const SHORT_COMMIT_LENGTH = 7;

/**
 * @param {string} repositoryPath Path of a clone.
 * @returns {(gitArguments: string[]) => import('node:child_process').SpawnSyncReturns<string>}
 */
export function createGitRunner(repositoryPath) {
  return (gitArguments) =>
    spawnSync(GIT_COMMAND, ['-C', repositoryPath, '-c', 'core.quotePath=false', ...gitArguments], { encoding: 'utf8', maxBuffer: Infinity });
}

/** @returns {boolean} Whether the runner points at a git repository. */
export function isGitRepository(runGit) {
  return runGit(['rev-parse', '--git-dir']).status === 0;
}

/**
 * Resolves a ref to a commit, trying it as written and as a remote branch, so a ref the clone only
 * has as `origin/<name>` still resolves.
 *
 * @returns {string | null} Full commit hash, or null when the ref is not in the clone.
 */
export function resolveRef(refName, runGit) {
  for (const candidate of [refName, `${GIT_REMOTE_REF_PREFIX}${refName}`]) {
    const result = runGit(['rev-parse', '--verify', '--quiet', `${candidate}^{commit}`]);
    if (result.status === 0) return result.stdout.trim();
  }
  return null;
}

/**
 * Splits text into lines; a text that ends with a line break has no empty line after its last one.
 *
 * @param {string} text Content of a file.
 * @returns {string[]}
 */
export function splitLines(text) {
  const lines = text.split(LINE_BREAK_PATTERN);
  if (lines.at(-1) === '') lines.pop();
  return lines;
}

/** @returns {(commit: string, filePath: string) => string[] | null} Lines of a file, or null when it is not there. */
export function createFileReader(runGit) {
  const linesByFile = new Map();
  return (commit, filePath) => {
    const cacheKey = `${commit}:${filePath}`;
    if (!linesByFile.has(cacheKey)) {
      const result = runGit(['show', cacheKey]);
      linesByFile.set(cacheKey, result.status === 0 ? splitLines(result.stdout) : null);
    }
    return linesByFile.get(cacheKey);
  };
}

/**
 * @param {string[]} lines Lines of a file.
 * @param {number} lineNumber Line the evidence points at, from 1.
 * @returns {string} That line with the lines around it that a relationship may be written across.
 */
export function readNearbyLines(lines, lineNumber) {
  return lines.slice(Math.max(lineNumber - 1 - EVIDENCE_CONTEXT_LINE_COUNT, 0), lineNumber + EVIDENCE_CONTEXT_LINE_COUNT).join('\n');
}

/**
 * Whether a text names a node, by `symbol` or by `label`. Short words prove nothing, and longer
 * ones also count inside a longer identifier (`OrderRepository` in `orderRepositoryImpl`).
 */
export function mentionsNode(text, node) {
  const textWords = new Set((text.match(IDENTIFIER_WORD_PATTERN) ?? []).map((word) => word.toLowerCase()));
  const nameWords = ((node.symbol ?? node.label).match(IDENTIFIER_WORD_PATTERN) ?? [])
    .map((word) => word.toLowerCase())
    .filter((word) => word.length >= NAME_TOKEN_MIN_LENGTH);
  return nameWords.some(
    (nameWord) =>
      textWords.has(nameWord) ||
      (nameWord.length >= NAME_TOKEN_SUBSTRING_MIN_LENGTH && [...textWords].some((textWord) => textWord.includes(nameWord))),
  );
}

/** Every element of the model that may carry evidence, with its location for the messages. */
export function listElementsWithLocation(model) {
  const withLocation = (elements, listLocation) => (elements ?? []).map((element, index) => ({ element, location: `${listLocation}[${index}]` }));
  return [
    ...withLocation(model.nodes, 'nodes'),
    ...withLocation(model.edges, 'edges'),
    ...withLocation(model.businessFlow?.states, 'businessFlow.states'),
    ...withLocation(model.businessFlow?.transitions, 'businessFlow.transitions'),
  ];
}
