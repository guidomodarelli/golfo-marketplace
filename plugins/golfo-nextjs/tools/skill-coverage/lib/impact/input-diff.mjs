/**
 * Compares the inputs recorded for a coverage attempt with the current
 * inputs of the same unit. Content is compared through hashes, so the
 * comparison works with uncommitted edits, after rebases or squash merges
 * and without network access. A symbol that moved to another file with the
 * same content is reported as relocated, not as a change.
 */

import { INPUT_KEY_PREFIXES, PACKAGE_METADATA_FILES } from '../constants.mjs';

/**
 * @param {string} key Input key (`path#Part`, `pkg:name`, ...).
 * @returns {{ path: string | null, part: string }}
 */
export function splitInputKey(key) {
  const hashIndex = key.indexOf('#');
  if (hashIndex === -1) return { part: key, path: null };
  return { part: key.slice(hashIndex + 1), path: key.slice(0, hashIndex) };
}

/**
 * @param {string} key
 * @returns {string | undefined} Package name of a `pkg:<name>` key.
 */
export function packageOfInputKey(key) {
  return key.startsWith(INPUT_KEY_PREFIXES.package) ? key.slice(INPUT_KEY_PREFIXES.package.length) : undefined;
}

/**
 * @param {string} key
 * @returns {string | undefined} Import specifier of an `unresolved:<specifier>` key.
 */
export function unresolvedSpecifierOfInputKey(key) {
  return key.startsWith(INPUT_KEY_PREFIXES.unresolved) ? key.slice(INPUT_KEY_PREFIXES.unresolved.length) : undefined;
}

/** Separators the module analyzer puts after a top-level name: `/inner`, `.member`, `~shell`, `~frame`. */
const PART_SEPARATOR_PATTERN = /[/~.]/;

/**
 * @typedef {{ kind: 'file' | 'module' | 'handler' | 'member' | 'shell' | 'frame' | 'declaration', owner: string, member?: string }} PartShape
 */

/**
 * Classifies the part of a file input key by the names the module analyzer
 * gives it: `*` (whole file), `<module>`, `Name/inner` (handler),
 * `Name.member`, `Name~shell`, `Name~frame` or a top-level declaration.
 *
 * @param {string} part
 * @returns {PartShape} `owner` is the top-level name (a JS identifier, so it never holds `/`, `~` or `.`); `member` is set for members.
 */
export function partShape(part) {
  if (part === '*') return { kind: 'file', owner: part };
  if (part === '<module>') return { kind: 'module', owner: part };
  const owner = part.split(PART_SEPARATOR_PATTERN)[0];
  if (part.includes('/')) return { kind: 'handler', owner };
  if (part.includes('.')) return { kind: 'member', member: part.slice(part.indexOf('.') + 1), owner };
  if (part.endsWith('~shell')) return { kind: 'shell', owner };
  if (part.endsWith('~frame')) return { kind: 'frame', owner };
  return { kind: 'declaration', owner };
}

/**
 * Lists the project paths an input snapshot depends on: the files read when
 * it was computed and the paths of its inputs, including the ones recorded as
 * missing (`path#*`), so a deleted dependency still belongs to the snapshot.
 * A snapshot with package inputs (`pkg:<name>`) also depends on the package
 * metadata files their versions are read from.
 *
 * @param {{ files: Record<string, string>, inputs: Record<string, string> }} snapshot Current inputs or an attempt baseline.
 * @returns {string[]} Sorted unique paths.
 */
export function snapshotPaths(snapshot) {
  const inputKeys = Object.keys(snapshot.inputs);
  const inputPaths = inputKeys.map((key) => splitInputKey(key).path).filter(Boolean);
  const packageMetadataPaths = inputKeys.some((key) => packageOfInputKey(key) !== undefined) ? Object.values(PACKAGE_METADATA_FILES) : [];
  return [...new Set([...Object.keys(snapshot.files), ...inputPaths, ...packageMetadataPaths])].sort();
}

/**
 * @typedef {{ key: string, change: 'modified' | 'added' | 'removed' | 'relocated', previousHash?: string, currentHash?: string, from?: string }} InputChange
 */

/**
 * Lists the differences between two input maps.
 *
 * @param {Record<string, string>} previous Inputs stored in the attempt.
 * @param {Record<string, string>} current Inputs computed now.
 * @returns {InputChange[]}
 */
export function diffInputs(previous, current) {
  const changes = [];
  const removed = [];
  const added = [];
  for (const [key, previousHash] of Object.entries(previous)) {
    if (!(key in current)) removed.push(key);
    else if (current[key] !== previousHash) changes.push({ change: 'modified', currentHash: current[key], key, previousHash });
  }
  for (const key of Object.keys(current)) if (!(key in previous)) added.push(key);

  // A part that disappeared from one file and appeared with the same hash in
  // another one moved (component extracted or file renamed): not a change.
  const removedBySignature = new Map();
  for (const key of removed) {
    const { part, path } = splitInputKey(key);
    if (path === null || part === '<module>' || part === '*') continue;
    removedBySignature.set(`${part}\0${previous[key]}`, key);
  }
  const relocatedSources = new Set();
  for (const key of added) {
    const { part, path } = splitInputKey(key);
    const source = path === null ? undefined : removedBySignature.get(`${part}\0${current[key]}`);
    if (source && !relocatedSources.has(source)) {
      relocatedSources.add(source);
      changes.push({ change: 'relocated', currentHash: current[key], from: source, key });
    } else {
      changes.push({ change: 'added', currentHash: current[key], key });
    }
  }
  for (const key of removed) {
    if (!relocatedSources.has(key)) changes.push({ change: 'removed', key, previousHash: previous[key] });
  }

  // Moved parts bring the module shell of their new file (directives such as
  // "use client"). When it equals the shell of the file they came from, the
  // move kept the module context: the shell is relocated too.
  const relocatedFiles = new Map();
  for (const change of changes) {
    if (change.change === 'relocated') relocatedFiles.set(splitInputKey(change.key).path, splitInputKey(change.from).path);
  }
  for (const addedShell of changes.filter((change) => change.change === 'added' && splitInputKey(change.key).part === '<module>')) {
    const fromPath = relocatedFiles.get(splitInputKey(addedShell.key).path);
    const fromShellKey = `${fromPath}#<module>`;
    if (fromPath === undefined || previous[fromShellKey] !== addedShell.currentHash) continue;
    addedShell.change = 'relocated';
    addedShell.from = fromShellKey;
    const removedShell = changes.find((change) => change.change === 'removed' && change.key === fromShellKey);
    if (removedShell) changes.splice(changes.indexOf(removedShell), 1);
  }
  return changes.sort((left, right) => left.key.localeCompare(right.key));
}

/**
 * Files whose content differs between two `files` maps.
 *
 * @param {Record<string, string>} previous
 * @param {Record<string, string>} current
 * @returns {string[]}
 */
export function diffFiles(previous, current) {
  const paths = new Set([...Object.keys(previous), ...Object.keys(current)]);
  return [...paths].filter((filePath) => previous[filePath] !== current[filePath]).sort();
}
