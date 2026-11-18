import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';

import {
  LEAN_CHECK_TIMEOUT_MS,
  LEAN_DEFAULT_COMMAND,
  LEAN_STATUS,
  LEAN_UNPROVEN_KEYWORDS,
} from './flow-graph-constants.mjs';

const MISSING_EXECUTABLE_ERROR_CODE = 'ENOENT';
const LEAN_LINE_COMMENT_PATTERN = /--.*$/gm;
const LEAN_BLOCK_COMMENT_PATTERN = /\/-[\s\S]*?-\//g;
const THEOREM_PATTERN = /\btheorem\b/;

/**
 * @typedef {object} LeanCheck
 * @property {'compiled' | 'incomplete' | 'not-installed' | 'unproven' | 'failed'} status Outcome of the check.
 * @property {string} detail One line a person can act on.
 * @property {string} [source] The Lean source, present only when it compiled.
 */

/**
 * Decides whether a Lean model may be shown: it has to compile and prove what it states.
 *
 * A formal model that does not compile, or that closes a theorem with `sorry`, reads as rigorous
 * and proves nothing, so the graph leaves it out instead of showing it with a caveat.
 *
 * @param {string} leanFilePath Path of the `.lean` file.
 * @param {object} [options]
 * @param {string} [options.command] Executable that checks the file.
 * @param {string[]} [options.commandArguments] Arguments placed before the file path.
 * @param {string[]} [options.expectedStateIds] Identifiers of the business states the model has
 *   to name, each as a lowerCamelCase word (`save-failed` is looked up as `saveFailed`).
 * @returns {LeanCheck}
 */
export function checkLeanModel(leanFilePath, { command = LEAN_DEFAULT_COMMAND, commandArguments = [], expectedStateIds = [] } = {}) {
  const source = readFileSync(leanFilePath, 'utf8');
  const code = stripComments(source);
  if (!THEOREM_PATTERN.test(code)) {
    return { status: LEAN_STATUS.incomplete, detail: 'The Lean model states no `theorem`, so it proves nothing about the flow.' };
  }
  const missingStateNames = expectedStateIds.map(toLowerCamelCase).filter((name) => !new RegExp(`\\b${name}\\b`).test(code));
  if (missingStateNames.length > 0) {
    return {
      status: LEAN_STATUS.incomplete,
      detail: `The Lean model does not name these business states: ${missingStateNames.join(', ')}. Add one constructor of \`State\` per state, named after its id in lowerCamelCase.`,
    };
  }
  const unprovenKeyword = findUnprovenKeyword(source);
  if (unprovenKeyword) {
    return {
      status: LEAN_STATUS.unproven,
      detail: `The Lean model uses \`${unprovenKeyword}\`, so it states properties without proving them.`,
    };
  }

  const result = spawnSync(command, [...commandArguments, leanFilePath], {
    encoding: 'utf8',
    timeout: LEAN_CHECK_TIMEOUT_MS,
  });

  if (result.error?.code === MISSING_EXECUTABLE_ERROR_CODE) {
    return {
      status: LEAN_STATUS.notInstalled,
      detail: `\`${command}\` is not installed, so the Lean model could not be checked.`,
    };
  }
  if (result.error || result.status !== 0) {
    const output = `${result.stdout ?? ''}${result.stderr ?? ''}`.trim();
    const firstLine = output.split('\n')[0] || result.error?.message || `exit code ${result.status}`;
    return { status: LEAN_STATUS.failed, detail: `\`${command}\` rejected the Lean model: ${firstLine}` };
  }
  return { status: LEAN_STATUS.compiled, detail: `\`${command}\` accepted the Lean model.`, source };
}

function stripComments(source) {
  return source.replace(LEAN_BLOCK_COMMENT_PATTERN, '').replace(LEAN_LINE_COMMENT_PATTERN, '');
}

function toLowerCamelCase(identifier) {
  return identifier.replace(/-([a-z0-9])/g, (match, character) => character.toUpperCase());
}

function findUnprovenKeyword(source) {
  const code = stripComments(source);
  return LEAN_UNPROVEN_KEYWORDS.find((keyword) => new RegExp(`\\b${keyword}\\b`).test(code));
}
