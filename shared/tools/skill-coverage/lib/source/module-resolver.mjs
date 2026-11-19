/**
 * Resolves import specifiers the way the consumer's TypeScript config does:
 * relative paths, `compilerOptions.paths` aliases (for example `@/*`),
 * extension and `index` probing, and bare package names, whose installed
 * version comes from the lockfile so a dependency upgrade invalidates the
 * units that import it.
 */
import fs from 'node:fs';
import { builtinModules } from 'node:module';
import path from 'node:path';

import { PACKAGE_METADATA_FILES, RESOLUTION_EXTENSIONS } from '../constants.mjs';
import { entryHash } from '../support.mjs';

const BUILTINS = new Set(builtinModules);

/**
 * Removes comments and trailing commas from JSONC (tsconfig files).
 *
 * @param {string} text
 * @returns {string}
 */
export function stripJsonComments(text) {
  let output = '';
  let inString = false;
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (inString) {
      output += character;
      if (character === '\\') output += text[++index] ?? '';
      else if (character === '"') inString = false;
    } else if (character === '"') {
      inString = true;
      output += character;
    } else if (character === '/' && text[index + 1] === '/') {
      while (index < text.length && text[index] !== '\n') index += 1;
      output += '\n';
    } else if (character === '/' && text[index + 1] === '*') {
      index = text.indexOf('*/', index + 2);
      if (index === -1) break;
      index += 1;
    } else {
      output += character;
    }
  }
  return output.replace(/,(\s*[}\]])/g, '$1');
}

/**
 * Reads `paths` and `baseUrl` from tsconfig.json (one level of `extends`).
 * `hasBaseUrl` says whether `baseUrl` is configured: only then TypeScript
 * resolves bare specifiers relative to it.
 *
 * @param {string} projectRoot
 * @returns {{ baseUrl: string, hasBaseUrl: boolean, paths: Record<string, string[]> }}
 */
function readTsconfigAliases(projectRoot) {
  const read = (filePath) => {
    try {
      return JSON.parse(stripJsonComments(fs.readFileSync(filePath, 'utf8')));
    } catch {
      return undefined;
    }
  };
  const tsconfigPath = path.join(projectRoot, 'tsconfig.json');
  const tsconfig = read(tsconfigPath) ?? {};
  let compilerOptions = tsconfig.compilerOptions ?? {};
  if (typeof tsconfig.extends === 'string' && tsconfig.extends.startsWith('.')) {
    const parent = read(path.resolve(projectRoot, tsconfig.extends.endsWith('.json') ? tsconfig.extends : `${tsconfig.extends}.json`));
    compilerOptions = { ...(parent?.compilerOptions ?? {}), ...compilerOptions };
  }
  return { baseUrl: compilerOptions.baseUrl ?? '.', hasBaseUrl: typeof compilerOptions.baseUrl === 'string', paths: compilerOptions.paths ?? {} };
}

/**
 * Builds a version lookup from pnpm-lock.yaml, package-lock.json or, as a
 * last resort, the range declared in package.json.
 *
 * @param {string} projectRoot
 * @returns {(packageName: string) => string}
 */
function createPackageVersionLookup(projectRoot) {
  const versions = new Map();
  const declared = new Map();
  try {
    const manifest = JSON.parse(fs.readFileSync(path.join(projectRoot, PACKAGE_METADATA_FILES.manifest), 'utf8'));
    for (const field of ['dependencies', 'devDependencies', 'optionalDependencies', 'peerDependencies']) {
      for (const [name, range] of Object.entries(manifest[field] ?? {})) declared.set(name, `range:${range}`);
    }
  } catch {
    // No manifest: packages are tracked by name only.
  }
  try {
    const lockfile = fs.readFileSync(path.join(projectRoot, PACKAGE_METADATA_FILES.pnpmLockfile), 'utf8').replace(/\r\n?/g, '\n');
    const rootImporter = /\n {2}\.:\n([\s\S]*?)(?=\n {2}\S|\n\S|$)/.exec(lockfile.slice(lockfile.indexOf('\nimporters:')));
    if (rootImporter) {
      const entryPattern = /\n {6}'?([^'\n:]+)'?:\n {8}specifier: [^\n]*\n {8}version: ([^\n]+)/g;
      for (const match of rootImporter[1].matchAll(entryPattern)) versions.set(match[1], match[2].trim());
    }
  } catch {
    // Not a pnpm project.
  }
  if (!versions.size) {
    try {
      const lockfile = JSON.parse(fs.readFileSync(path.join(projectRoot, PACKAGE_METADATA_FILES.npmLockfile), 'utf8'));
      for (const [key, value] of Object.entries(lockfile.packages ?? {})) {
        if (key.startsWith('node_modules/') && !key.slice('node_modules/'.length).includes('node_modules/')) versions.set(key.slice('node_modules/'.length), value.version);
      }
    } catch {
      // Not an npm project either.
    }
  }
  return (packageName) => versions.get(packageName) ?? declared.get(packageName) ?? 'undeclared';
}

/**
 * @param {string} specifier Bare import specifier.
 * @returns {string} Package name (`@scope/name` or `name`).
 */
function packageNameOf(specifier) {
  const segments = specifier.split('/');
  return specifier.startsWith('@') ? segments.slice(0, 2).join('/') : segments[0];
}

/**
 * @typedef {{ kind: 'file', path: string }
 *   | { kind: 'package', name: string, versionHash: string }
 *   | { kind: 'builtin' }
 *   | { kind: 'unresolved', specifier: string }} Resolution
 */

/**
 * Creates the resolver of one project.
 *
 * @param {string} projectRoot
 * @param {{ pathAliases?: Record<string, string[]> }} config
 * @param {(projectPath: string) => boolean} fileExists Existence check over project paths.
 */
export function createModuleResolver(projectRoot, config, fileExists) {
  const tsconfig = readTsconfigAliases(projectRoot);
  const aliasEntries = Object.entries(config.pathAliases ?? tsconfig.paths);
  const baseUrl = config.pathAliases ? '.' : tsconfig.baseUrl;
  const packageVersion = createPackageVersionLookup(projectRoot);
  const cache = new Map();

  /**
   * @param {string} candidate POSIX path relative to the root, maybe without extension.
   * @returns {string | undefined}
   */
  const probe = (candidate) => {
    const normalized = path.posix.normalize(candidate).replace(/^\.\//, '');
    if (normalized.startsWith('../')) return undefined;
    if (fileExists(normalized) && path.posix.extname(normalized)) return normalized;
    const withoutJsExtension = normalized.replace(/\.(?:js|jsx|mjs|cjs)$/, '');
    for (const base of new Set([normalized, withoutJsExtension])) {
      for (const extension of RESOLUTION_EXTENSIONS) if (fileExists(`${base}${extension}`)) return `${base}${extension}`;
    }
    for (const extension of RESOLUTION_EXTENSIONS) if (fileExists(`${normalized}/index${extension}`)) return `${normalized}/index${extension}`;
    return undefined;
  };

  /**
   * @param {string} specifier
   * @returns {string[]} Candidate paths produced by the aliases.
   */
  const aliasCandidates = (specifier) => {
    const candidates = [];
    for (const [pattern, targets] of aliasEntries) {
      const starIndex = pattern.indexOf('*');
      const prefix = starIndex === -1 ? pattern : pattern.slice(0, starIndex);
      const suffix = starIndex === -1 ? '' : pattern.slice(starIndex + 1);
      const matches = starIndex === -1 ? specifier === pattern : specifier.startsWith(prefix) && specifier.endsWith(suffix);
      if (!matches) continue;
      const captured = starIndex === -1 ? '' : specifier.slice(prefix.length, specifier.length - suffix.length);
      for (const target of targets) candidates.push(path.posix.join(baseUrl, target.replace('*', captured)));
    }
    return candidates;
  };

  return {
    /**
     * @param {string} fromPath Importing file (project path).
     * @param {string} specifier
     * @returns {Resolution}
     */
    resolve(fromPath, specifier) {
      const cacheKey = `${fromPath}\0${specifier}`;
      if (cache.has(cacheKey)) return cache.get(cacheKey);
      let resolution;
      if (specifier.startsWith('node:') || BUILTINS.has(specifier)) {
        resolution = { kind: 'builtin' };
      } else if (specifier.startsWith('.') || specifier.startsWith('/')) {
        const resolved = probe(specifier.startsWith('/') ? specifier.slice(1) : path.posix.join(path.posix.dirname(fromPath), specifier));
        resolution = resolved ? { kind: 'file', path: resolved } : { kind: 'unresolved', specifier };
      } else {
        // Same order as TypeScript: `paths` aliases, then `baseUrl`, then packages.
        const aliased = aliasCandidates(specifier);
        const resolved = aliased.map(probe).find(Boolean) ?? (tsconfig.hasBaseUrl ? probe(path.posix.join(tsconfig.baseUrl, specifier)) : undefined);
        if (resolved) resolution = { kind: 'file', path: resolved };
        else if (aliased.length) resolution = { kind: 'unresolved', specifier };
        else {
          const name = packageNameOf(specifier);
          resolution = { kind: 'package', name, versionHash: entryHash(`${name}@${packageVersion(name)}`) };
        }
      }
      cache.set(cacheKey, resolution);
      return resolution;
    },
  };
}
