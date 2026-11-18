/**
 * Route tree of a Next.js App Router project, read from file paths: the app
 * directory, the URL of a route file, and the segment files (layouts,
 * templates, boundaries, slot fallbacks) and project files (`next.config`,
 * `middleware`/`proxy`) that wrap a route. Unit discovery and the
 * `nextjs-route-ui-boundaries` policy share it so both see the same tree.
 */
import path from 'node:path';

import { NEXT_PROJECT_FILES, NEXT_ROOT_SEGMENT_FILES, NEXT_SEGMENT_FILE_EXTENSIONS, NEXT_SEGMENT_FILES } from '../constants.mjs';

export const PAGE_FILE_PATTERN = /(?:^|\/)page\.[cm]?[jt]sx?$/;
export const ROUTE_HANDLER_FILE_PATTERN = /(?:^|\/)route\.[cm]?[jt]sx?$/;

/** Route groups `(name)` and parallel route slots `@name` do not add a URL segment. */
const INVISIBLE_SEGMENT_PATTERN = /^\(.*\)$|^@/;

/** HTTP method that prefixes the route of an API unit (`POST /api/providers`). */
const ROUTE_METHOD_PREFIX_PATTERN = /^[A-Z]+\s+/;

/** Base names (without extension) of every App Router convention file. */
const ROUTE_CONVENTION_NAMES = new Set(['page', 'route', ...NEXT_SEGMENT_FILES, ...NEXT_ROOT_SEGMENT_FILES]);

/** Directory listing of each project index, built once per index. */
const directoryListings = new WeakMap();

/**
 * @param {Set<string>} files Project files.
 * @returns {string} `src/app` or `app`.
 */
export function appDirectoryOf(files) {
  return files.has('src/app/layout.tsx') || [...files].some((file) => file.startsWith('src/app/')) ? 'src/app' : 'app';
}

/**
 * @param {string} appDirectory
 * @param {string} filePath Page, route handler or any file under the app directory.
 * @returns {{ route: string, segments: string[] }} URL of the file's segment and its visible segments.
 */
export function routeOfFile(appDirectory, filePath) {
  const segments = path.posix.dirname(filePath).slice(appDirectory.length).split('/').filter(Boolean)
    .filter((segment) => !INVISIBLE_SEGMENT_PATTERN.test(segment));
  return { route: `/${segments.join('/')}`, segments };
}

/**
 * @param {string} appDirectory
 * @param {string} filePath
 * @returns {boolean} Whether the file is an App Router convention file (page, route, layout, boundary...).
 */
export function isRouteConventionFile(appDirectory, filePath) {
  if (!filePath.startsWith(`${appDirectory}/`)) return false;
  const extension = path.posix.extname(filePath);
  return ROUTE_CONVENTION_NAMES.has(path.posix.basename(filePath, extension)) && /^\.[cm]?[jt]sx?$/.test(extension);
}

/**
 * @param {any} index Project index.
 * @returns {Map<string, Set<string>>} File names of each directory.
 */
function directoryListing(index) {
  if (!directoryListings.has(index)) {
    const listing = new Map();
    for (const filePath of index.files) {
      const directory = path.posix.dirname(filePath);
      if (!listing.has(directory)) listing.set(directory, new Set());
      listing.get(directory).add(path.posix.basename(filePath));
    }
    directoryListings.set(index, listing);
  }
  return directoryListings.get(index);
}

/**
 * @param {any} index
 * @param {string} directory
 * @param {string} name Base name without extension (`layout`, `loading`...).
 * @param {string[]} [extensions]
 * @returns {string | undefined} Path of the file, when the directory has one.
 */
function conventionFile(index, directory, name, extensions = NEXT_SEGMENT_FILE_EXTENSIONS) {
  const names = directoryListing(index).get(directory);
  const extension = names && extensions.find((candidate) => names.has(`${name}${candidate}`));
  return extension ? (directory === '.' ? `${name}${extension}` : `${directory}/${name}${extension}`) : undefined;
}

/**
 * Directories from `directory` up to the app directory, nearest first.
 *
 * @param {string} appDirectory
 * @param {string} directory
 * @returns {string[]}
 */
function segmentDirectories(appDirectory, directory) {
  const directories = [];
  let current = directory;
  while (current === appDirectory || current.startsWith(`${appDirectory}/`)) {
    directories.push(current);
    current = path.posix.dirname(current);
  }
  return directories;
}

/**
 * Nearest file of each boundary kind above a page (`loading`, `error`, ...).
 *
 * @param {any} index
 * @param {string} appDirectory
 * @param {string} pagePath
 * @param {string[]} names
 * @returns {string[]}
 */
export function nearestSegmentFiles(index, appDirectory, pagePath, names) {
  const directories = segmentDirectories(appDirectory, path.posix.dirname(pagePath));
  return names.map((name) => directories.map((directory) => conventionFile(index, directory, name)).find(Boolean)).filter(Boolean);
}

/**
 * Files that wrap the routes of a unit: the pages and route handlers its
 * `routes` resolve to, every segment file of each ancestor segment (layouts
 * and templates it renders inside, loading and error boundaries it inherits
 * or replaces, not-found/forbidden/unauthorized, slot fallbacks of parallel
 * routes), the root-only files and the project files that configure every
 * route. Route handlers render no layout, so only project files wrap them.
 *
 * @param {any} index Project index.
 * @param {{ entries: { path: string }[], dependsOn?: { path: string }[], routes?: string[] }} unit
 * @returns {{ pages: string[], segmentFiles: string[], projectFiles: string[] }}
 */
export function routeContextFiles(index, unit) {
  const appDirectory = appDirectoryOf(index.files);
  const appPrefix = `${appDirectory}/`;
  const unitPaths = [...unit.entries, ...(unit.dependsOn ?? [])].map((entry) => entry.path).filter((filePath) => filePath.startsWith(appPrefix));
  const unitRoutes = new Set((unit.routes ?? []).map((route) => route.replace(ROUTE_METHOD_PREFIX_PATTERN, '')));

  const pages = new Set();
  if (unitRoutes.size) {
    for (const filePath of index.files) {
      if (!filePath.startsWith(appPrefix) || !(PAGE_FILE_PATTERN.test(filePath) || ROUTE_HANDLER_FILE_PATTERN.test(filePath))) continue;
      if (unitRoutes.has(routeOfFile(appDirectory, filePath).route)) pages.add(filePath);
    }
  }

  const rendered = [...new Set([...unitPaths, ...pages])].filter((filePath) => !ROUTE_HANDLER_FILE_PATTERN.test(filePath));
  const segmentFiles = new Set();
  const listing = directoryListing(index);
  for (const filePath of rendered) {
    for (const directory of segmentDirectories(appDirectory, path.posix.dirname(filePath))) {
      for (const name of NEXT_SEGMENT_FILES) {
        const found = conventionFile(index, directory, name);
        if (found) segmentFiles.add(found);
      }
      // Parallel route slots rendered by this segment's layout fall back to
      // their `default` file on a hard navigation, wrapped by the slot's own
      // layout and boundaries.
      for (const child of listing.keys()) {
        if (path.posix.dirname(child) !== directory || !path.posix.basename(child).startsWith('@')) continue;
        if (!conventionFile(index, child, 'default')) continue;
        for (const name of NEXT_SEGMENT_FILES) {
          const found = conventionFile(index, child, name);
          if (found) segmentFiles.add(found);
        }
      }
    }
  }
  if (rendered.length) {
    for (const name of NEXT_ROOT_SEGMENT_FILES) {
      const found = conventionFile(index, appDirectory, name);
      if (found) segmentFiles.add(found);
    }
  }

  const projectFiles = NEXT_PROJECT_FILES.flatMap(({ directories, extensions, name }) => directories
    .map((directory) => conventionFile(index, directory ? directory.replace(/\/$/, '') : '.', name, extensions))
    .filter(Boolean));

  return { pages: [...pages].sort(), projectFiles: projectFiles.sort(), segmentFiles: [...segmentFiles].sort() };
}
