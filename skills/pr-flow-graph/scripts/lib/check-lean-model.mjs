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

/**
 * @typedef {object} LeanCheck
 * @property {'compiled' | 'not-installed' | 'unproven' | 'failed'} status Outcome of the check.
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
 * @returns {LeanCheck}
 */
export function checkLeanModel(leanFilePath, { command = LEAN_DEFAULT_COMMAND, commandArguments = [] } = {}) {
  const source = readFileSync(leanFilePath, 'utf8');
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

function findUnprovenKeyword(source) {
  const code = source.replace(LEAN_BLOCK_COMMENT_PATTERN, '').replace(LEAN_LINE_COMMENT_PATTERN, '');
  return LEAN_UNPROVEN_KEYWORDS.find((keyword) => new RegExp(`\\b${keyword}\\b`).test(code));
}
