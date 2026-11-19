/**
 * Durable JSON persistence: atomic writes (temp file + rename), directory
 * locks with stale-lock recovery, and reads that name the broken file.
 */
import fs from 'node:fs';
import path from 'node:path';

import { LOCK_RETRY_MS, LOCK_STALE_MS, LOCK_TIMEOUT_MS, RENAME_RETRY_COUNT } from '../constants.mjs';
import { CoverageError } from '../support.mjs';

/**
 * Blocks the thread for a few milliseconds without spinning the CPU.
 *
 * @param {number} milliseconds
 */
function sleepSync(milliseconds) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, milliseconds);
}

/**
 * Reads and parses a JSON file.
 *
 * @param {string} filePath Absolute path.
 * @returns {any} Parsed content, or `undefined` when the file does not exist.
 */
export function readJsonFile(filePath) {
  let text;
  try {
    text = fs.readFileSync(filePath, 'utf8');
  } catch (error) {
    if (error.code === 'ENOENT') return undefined;
    throw new CoverageError(`json-store:read failed for ${filePath}: ${error.message}`, { cause: error });
  }
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new CoverageError(`json-store:read found invalid JSON in ${filePath}: ${error.message}`, { cause: error });
  }
}

/**
 * Writes JSON atomically: the content goes to a temporary sibling file that
 * replaces the target in one rename, so readers never see a partial file.
 *
 * @param {string} filePath Absolute path.
 * @param {unknown} value Serializable value.
 */
export function writeJsonFileAtomic(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  const temporaryPath = `${filePath}.${process.pid}.${Date.now()}.${Math.random().toString(16).slice(2)}.tmp`;
  fs.writeFileSync(temporaryPath, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
  for (let attempt = 1; ; attempt += 1) {
    try {
      fs.renameSync(temporaryPath, filePath);
      return;
    } catch (error) {
      // Windows refuses the rename while another process holds the target open.
      if (attempt >= RENAME_RETRY_COUNT || !['EPERM', 'EACCES', 'EBUSY'].includes(error.code)) {
        fs.rmSync(temporaryPath, { force: true });
        throw new CoverageError(`json-store:write could not replace ${filePath}: ${error.message}`, { cause: error });
      }
      sleepSync(LOCK_RETRY_MS * attempt);
    }
  }
}

/**
 * Runs `operation` while holding an exclusive lock on `targetPath`. The lock
 * is a directory (`mkdir` is atomic on every platform); a lock older than
 * the stale limit belongs to a crashed process and is taken over.
 *
 * @template T
 * @param {string} targetPath File the lock protects.
 * @param {() => T} operation Read-modify-write to run under the lock.
 * @returns {T}
 */
export function withFileLock(targetPath, operation) {
  const lockPath = `${targetPath}.lock`;
  fs.mkdirSync(path.dirname(lockPath), { recursive: true });
  const deadline = Date.now() + LOCK_TIMEOUT_MS;
  for (;;) {
    try {
      fs.mkdirSync(lockPath);
      break;
    } catch (error) {
      if (error.code !== 'EEXIST') throw new CoverageError(`json-store:lock failed for ${targetPath}: ${error.message}`, { cause: error });
      const lockAge = lockAgeMs(lockPath);
      if (lockAge !== undefined && lockAge > LOCK_STALE_MS) {
        fs.rmSync(lockPath, { force: true, recursive: true });
        continue;
      }
      if (Date.now() > deadline) throw new CoverageError(`json-store:lock timed out waiting for ${lockPath}; remove it if no other skill-coverage process is running`);
      sleepSync(LOCK_RETRY_MS);
    }
  }
  try {
    return operation();
  } finally {
    fs.rmSync(lockPath, { force: true, recursive: true });
  }
}

/**
 * @param {string} lockPath
 * @returns {number | undefined} Age in milliseconds, or undefined if the lock vanished.
 */
function lockAgeMs(lockPath) {
  try {
    return Date.now() - fs.statSync(lockPath).mtimeMs;
  } catch {
    return undefined;
  }
}

/**
 * Lists the JSON files under a directory, recursively, as absolute paths.
 *
 * @param {string} directory
 * @returns {string[]} Sorted paths; empty when the directory does not exist.
 */
export function listJsonFiles(directory) {
  if (!fs.existsSync(directory)) return [];
  return fs.readdirSync(directory, { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith('.json'))
    .map((entry) => path.join(entry.parentPath ?? entry.path, entry.name))
    .sort();
}
