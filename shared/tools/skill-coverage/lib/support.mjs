/**
 * Small helpers shared by every layer: typed errors, hashing, path
 * normalization and sanitization of the free text stored in the registry.
 */
import { createHash } from 'node:crypto';
import path from 'node:path';

import { ENTRY_HASH_LENGTH, EXIT_CODES, MAX_STORED_TEXT_LENGTH } from './constants.mjs';

/**
 * Error raised for expected failures; the CLI prints its message and exits
 * with its code instead of a stack trace.
 */
export class CoverageError extends Error {
  /**
   * @param {string} message Actionable description, prefixed with the failing operation.
   * @param {{ exitCode?: number, cause?: unknown, details?: unknown }} [options]
   */
  constructor(message, options = {}) {
    super(message, options.cause === undefined ? undefined : { cause: options.cause });
    this.name = 'CoverageError';
    this.exitCode = options.exitCode ?? EXIT_CODES.failure;
    this.details = options.details;
  }
}

/**
 * Builds a usage error (exit code 2).
 *
 * @param {string} message What was wrong with the invocation.
 * @returns {CoverageError}
 */
export function usageError(message) {
  return new CoverageError(message, { exitCode: EXIT_CODES.usage });
}

/**
 * Full SHA-256 hex digest of a string.
 *
 * @param {string} text
 * @returns {string}
 */
export function sha256(text) {
  return createHash('sha256').update(text).digest('hex');
}

/**
 * Shortened SHA-256 used for individual input entries.
 *
 * @param {string} text
 * @returns {string}
 */
export function entryHash(text) {
  return sha256(text).slice(0, ENTRY_HASH_LENGTH);
}

/**
 * Normalizes line endings so the same content hashes the same on every OS
 * and with any `core.autocrlf` setting.
 *
 * @param {string} text
 * @returns {string}
 */
export function normalizeLineEndings(text) {
  return text.replace(/\r\n?/g, '\n');
}

/**
 * Converts a path to the repository-relative POSIX form used as registry key.
 *
 * @param {string} projectRoot Absolute repository root.
 * @param {string} filePath Absolute or root-relative path.
 * @returns {string}
 */
export function toProjectPath(projectRoot, filePath) {
  const absolutePath = path.isAbsolute(filePath) ? filePath : path.join(projectRoot, filePath);
  return path.relative(projectRoot, absolutePath).split(path.sep).join('/');
}

/**
 * Hash of a sorted key→hash map: the fingerprint of a set of inputs.
 *
 * @param {Record<string, string>} entries
 * @returns {string}
 */
export function fingerprintOf(entries) {
  const lines = Object.keys(entries).sort().map((key) => `${key}=${entries[key]}`);
  return `sha256:${sha256(lines.join('\n'))}`;
}

const SECRET_PATTERNS = [
  /\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}/gi,
  /\b(?:sk|pk|rk|ghp|gho|ghs|ghu|glpat|xox[abprs])[-_][A-Za-z0-9_-]{10,}/g,
  /\b(?:password|passwd|secret|token|api[-_]?key|authorization|cookie)\s*[:=]\s*\S+/gi,
  /\b[A-Fa-f0-9]{32,}\b/g,
  /\b[A-Za-z0-9+/]{48,}={0,2}/g,
  /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g,
];

/**
 * Redacts secrets and personal data from free text and truncates it, so
 * evidence summaries and limitations never store credentials or emails.
 *
 * @param {unknown} value Text supplied by the agent.
 * @returns {string}
 */
export function sanitizeText(value) {
  let text = String(value ?? '').replace(/\s+/g, ' ').trim();
  for (const pattern of SECRET_PATTERNS) text = text.replace(pattern, '[redacted]');
  return text.length > MAX_STORED_TEXT_LENGTH ? `${text.slice(0, MAX_STORED_TEXT_LENGTH - 1)}…` : text;
}

/**
 * Compares two semver strings by major, minor and patch.
 *
 * @param {string | undefined} left
 * @param {string | undefined} right
 * @returns {{ comparable: boolean, majorChanged: boolean, changed: boolean }}
 */
export function compareVersions(left, right) {
  const parse = (version) => /^(\d+)\.(\d+)\.(\d+)/.exec(version ?? '');
  const leftParts = parse(left);
  const rightParts = parse(right);
  if (!leftParts || !rightParts) return { changed: left !== right, comparable: false, majorChanged: left !== right };
  return { changed: left !== right, comparable: true, majorChanged: leftParts[1] !== rightParts[1] };
}

/**
 * Converts a simple glob (`*`, `**`, `?`) to an anchored regular expression.
 *
 * @param {string} pattern Glob over POSIX paths.
 * @returns {RegExp}
 */
export function globToRegExp(pattern) {
  const cached = globCache.get(pattern);
  if (cached) return cached;
  let source = '';
  for (let index = 0; index < pattern.length; index += 1) {
    const character = pattern[index];
    if (character === '*' && pattern[index + 1] === '*') {
      const followedBySlash = pattern[index + 2] === '/';
      source += followedBySlash ? '(?:.*/)?' : '.*';
      index += followedBySlash ? 2 : 1;
    } else if (character === '*') {
      source += '[^/]*';
    } else if (character === '?') {
      source += '[^/]';
    } else {
      source += character.replace(/[.+^${}()|[\]\\]/g, '\\$&');
    }
  }
  const expression = new RegExp(`^${source}$`);
  globCache.set(pattern, expression);
  return expression;
}

const globCache = new Map();

/**
 * Tells whether a POSIX path matches any of the globs.
 *
 * @param {string} filePath
 * @param {string[]} patterns
 * @returns {boolean}
 */
export function matchesAnyGlob(filePath, patterns) {
  return patterns.some((pattern) => globToRegExp(pattern).test(filePath));
}
