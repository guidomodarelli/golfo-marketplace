/**
 * Builds a unit definition from command-line options (`add-unit`), so a skill
 * can create the unit it needs in any repository (APIs, jobs, backend or UI
 * outside Next.js App Router pages) without editing the registry by hand.
 * The definition is validated with the same schema as every saved unit.
 */
import fs from 'node:fs';
import path from 'node:path';

import { SCHEMA_VERSION } from '../constants.mjs';
import { usageError } from '../support.mjs';
import { validateUnit } from './schema.mjs';

/** Separator between the path and the symbol of an `--entry` value. */
const ENTRY_SYMBOL_SEPARATOR = ':';
/** Symbol used when an `--entry` names only a file. */
const WHOLE_FILE_SYMBOL = '*';

/**
 * Canonical repository-relative POSIX spelling (`./lib/a.ts` → `lib/a.ts`),
 * the form Git reports and `affected` compares against. Paths that escape the
 * repository keep their `..` so the schema rejects them.
 *
 * @param {string} entryPath
 * @returns {string}
 */
function canonicalEntryPath(entryPath) {
  if (!entryPath) return entryPath;
  return path.posix.normalize(entryPath).replace(/^(?:\.\/)+/, '').replace(/\/+$/, '');
}

/**
 * Parses `path[:symbol]`. The symbol grammar never contains `:`, so the last
 * separator splits both parts; without one the entry covers the whole file.
 *
 * @param {string} value
 * @returns {{ path: string, symbol: string }}
 */
export function parseEntryOption(value) {
  const separatorIndex = value.lastIndexOf(ENTRY_SYMBOL_SEPARATOR);
  if (separatorIndex === -1) return { path: canonicalEntryPath(value), symbol: WHOLE_FILE_SYMBOL };
  return { path: canonicalEntryPath(value.slice(0, separatorIndex)), symbol: value.slice(separatorIndex + 1) || WHOLE_FILE_SYMBOL };
}

/**
 * @param {string} absolutePath
 * @returns {boolean} Whether the path exists and is a regular file (the only entry the engine fingerprints).
 */
function isFile(absolutePath) {
  try {
    return fs.statSync(absolutePath).isFile();
  } catch {
    return false;
  }
}

/**
 * @param {{
 *   id: string, kind: string, module: string, subflow: string,
 *   page?: string, section?: string, description?: string,
 *   entries: string[], routes?: string[],
 * }} options Raw option values.
 * @param {string} projectRoot Absolute repository root, used to check that each entry file exists.
 * @returns {any} A unit definition ready for `registry.saveUnit`.
 */
export function buildUnitDefinition(options, projectRoot) {
  const entries = options.entries.map(parseEntryOption);
  const unit = {
    schemaVersion: SCHEMA_VERSION,
    id: options.id,
    kind: options.kind,
    hierarchy: { module: options.module, page: options.page ?? null, section: options.section ?? null, subflow: options.subflow },
    ...(options.description ? { description: options.description } : {}),
    ...(options.routes?.length ? { routes: options.routes } : {}),
    entries,
    origin: 'manual',
  };
  const errors = validateUnit(unit, `add-unit ${options.id}`);
  const missingFiles = entries.filter((entry) => !isFile(path.join(projectRoot, entry.path))).map((entry) => entry.path);
  if (missingFiles.length) errors.push(`add-unit ${options.id}: entry file(s) not found in the repository (directories are not entries; name each file): ${missingFiles.join(', ')}`);
  if (errors.length) throw usageError(errors.join('; '));
  return unit;
}
