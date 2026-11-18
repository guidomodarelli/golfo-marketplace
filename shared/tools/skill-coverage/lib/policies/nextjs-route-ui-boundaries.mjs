/**
 * Policy of `nextjs-route-ui-boundaries`: the skill decides the route
 * structure (segments, layouts, templates, route groups, parallel routes),
 * the boundaries of each navigation state (loading, error, not-found,
 * Suspense, skeletons) and the server/client split of what a route renders.
 *
 * Those decisions depend on files the unit does not import: the layouts the
 * route renders inside, the boundaries it inherits and the project
 * configuration. `contextEntries` adds them to the unit's closure, so a
 * shared layout invalidates every route under it and a handler of one route
 * invalidates nothing else. Classification is conservative: only moves
 * outside the route tree, copy members, styles that no skeleton or loading
 * boundary uses and translation catalogs leave coverage current; a route
 * file moved to another segment is relevant even with identical content.
 */
import path from 'node:path';

import { packageOfInputKey, partShape, splitInputKey, unresolvedSpecifierOfInputKey } from '../impact/input-diff.mjs';
import { isRouteConventionFile, routeContextFiles } from '../source/next-route-tree.mjs';
import { DEFAULT_DEFINITION_FILES, scopeByReviewFocus, signalIncreases, STYLE_FILE_PATTERN } from './base-policy.mjs';
import { isPresentationMember } from './presentation-members.mjs';

const NO_BOUNDARY_FILE_PATTERN = /\.(?:po|pot|md)$/;
const PROJECT_FILE_PATTERN = /^(?:next\.config\.[cm]?[jt]s|(?:src\/)?(?:middleware|proxy)\.[jt]s)$/;
const APP_DIRECTORIES = ['app', 'src/app'];

/** Names that mark code or styles as the UI shown while a segment loads. */
const LOADING_UI_PATTERN = /skeleton|fallback|loading|placeholder|shimmer/i;

/** Packages whose version decides which App Router APIs and conventions exist. */
const FRAMEWORK_PACKAGES = new Set(['next', 'react', 'react-dom']);

/** Sections of package.json whose entries the project installs. */
const DEPENDENCY_SECTIONS = ['dependencies', 'devDependencies', 'peerDependencies'];

/** A binding named in PascalCase is a component the page renders, not data it loads. */
const COMPONENT_BINDING_PATTERN = /^[A-Z]/;

/** Evidence kinds that only accredit when `evidence --exec` ran them. */
const EXECUTED_EVIDENCE_KINDS = new Set(['command', 'test']);

/** Load signals that add awaited work to the render path of a route. */
const RENDER_WAIT_SIGNALS = new Set(['awaits', 'awaitInLoop', 'fetch', 'database', 'projectCalls']);

/** Prefix of the labels of unit and context entries among the importers (`entry:` or `context:`). */
const ENTRY_LABEL_PREFIX_PATTERN = /^(?:entry|context):/;

/**
 * @param {string | null} filePath
 * @returns {boolean} Whether the file is a page, route handler, layout or boundary of the App Router.
 */
function isRouteFile(filePath) {
  return Boolean(filePath) && APP_DIRECTORIES.some((appDirectory) => isRouteConventionFile(appDirectory, filePath));
}

/**
 * Whether a style input is reached through a skeleton, a fallback or a
 * loading boundary, so it shapes what a navigation shows while it waits.
 * Walks every importer of the stylesheet and of the files that reach it,
 * not a single dependency path: a stylesheet shared by an ordinary
 * component and a skeleton is loading UI too.
 *
 * @param {string} key Style input key (`path#*`).
 * @param {Record<string, string[]>} importers Parts or entries that reach each current file.
 * @returns {boolean}
 */
function stylesLoadingUi(key, importers) {
  const stylePath = splitInputKey(key).path;
  if (LOADING_UI_PATTERN.test(path.posix.basename(stylePath ?? ''))) return true;
  const pending = [stylePath];
  const visited = new Set(pending);
  while (pending.length) {
    for (const importer of importers[pending.shift()] ?? []) {
      const { part, path: importerPath } = splitInputKey(importer.replace(ENTRY_LABEL_PREFIX_PATTERN, ''));
      if (LOADING_UI_PATTERN.test(path.posix.basename(importerPath ?? '')) || LOADING_UI_PATTERN.test(part)) return true;
      if (importerPath && !visited.has(importerPath)) {
        visited.add(importerPath);
        pending.push(importerPath);
      }
    }
  }
  return false;
}

/**
 * Data and helpers a page awaits before rendering (`loadPayments`,
 * `getTribe`): the page's imports that are not components. The components
 * it renders stay out, so a handler of one section does not invalidate the
 * other subflows of the page.
 *
 * @param {any} index Project index.
 * @param {string} pagePath
 * @returns {{ path: string, symbol: string, role: string, follow: boolean }[]}
 */
function pageDataDependencies(index, pagePath) {
  const analysis = index.analyze(pagePath);
  if (!analysis?.imports) return [];
  const dependencies = [];
  for (const [localName, binding] of analysis.imports) {
    if (binding.typeOnly || COMPONENT_BINDING_PATTERN.test(localName)) continue;
    const resolution = index.resolver.resolve(pagePath, binding.source);
    if (resolution.kind === 'file') dependencies.push({ follow: true, path: resolution.path, role: 'route', symbol: binding.imported });
  }
  return dependencies;
}

/**
 * @param {any} index Project index.
 * @returns {string[]} Framework packages the project declares in package.json.
 */
function declaredFrameworkPackages(index) {
  let manifest;
  try {
    manifest = JSON.parse(index.readSource('package.json') ?? '{}');
  } catch {
    return [];
  }
  const declared = new Set(DEPENDENCY_SECTIONS.flatMap((section) => Object.keys(manifest?.[section] ?? {})));
  return [...FRAMEWORK_PACKAGES].filter((name) => declared.has(name));
}

/**
 * @param {string | null} filePath
 * @returns {string} App Router convention of a file (`loading` in `app/x/loading.tsx`).
 */
function conventionName(filePath) {
  return path.posix.basename(filePath ?? '', path.posix.extname(filePath ?? ''));
}

/**
 * @param {{ key: string, change: string }} change
 * @returns {string} What the next run must look at for this change.
 */
function reviewFocus(change) {
  const { part, path: filePath } = splitInputKey(change.key);
  if (change.change === 'relocated') return 'the segment and convention the file now has: URL, layouts it renders inside, loading, error or template boundary it defines, inherits or replaces';
  if (change.change === 'removed') return 'what the route lost: a layout, a boundary, a Suspense fallback or a client island; check that each state still has its boundary';
  const packageName = packageOfInputKey(change.key);
  if (packageName !== undefined) {
    return FRAMEWORK_PACKAGES.has(packageName)
      ? 'App Router APIs and conventions used by the route against the installed version (installed docs in node_modules/next/dist/docs/)'
      : 'whether what the route imports from this package runs on the server or needs a client island';
  }
  if (unresolvedSpecifierOfInputKey(change.key) !== undefined) return 'import that cannot be resolved: review the file that imports it as a whole';
  if (filePath && PROJECT_FILE_PATTERN.test(filePath)) return 'rendering, caching and navigation options that apply to every route (cacheComponents, partial prefetching, redirects, middleware or proxy matchers)';
  if (filePath && STYLE_FILE_PATTERN.test(filePath)) return 'skeleton that uses these styles: final shape, reserved heights and reduced motion';
  const { kind } = partShape(part);
  if (kind === 'module') return 'where the server/client boundary falls ("use client", "use server") and what the client bundle imports through it';
  if (isRouteFile(filePath)) return 'segment decisions of this file: layout chrome, Suspense, loading and error boundaries, route segment config and the data it awaits';
  if (kind === 'handler') return 'this handler: client leaf, Next.js navigation (Link, Form, router), server action calls and revalidation';
  if (kind === 'shell') return 'what this component renders: hooks that force a client island, awaited data, Suspense and the client components it imports';
  if (kind === 'member') return 'route configuration read from this member, in every segment that uses it';
  return 'server/client split and awaited work of this code in every route of the unit';
}

export const nextjsRouteUiBoundariesPolicy = {
  definitionFiles: DEFAULT_DEFINITION_FILES,
  label: 'Next.js',
  // Route context (layouts, boundaries, configuration) is followed two hops:
  // the chrome or skeleton components it renders and their styles or leaves.
  maxDepthByRole: { contract: Infinity, route: 2, server: 1, ui: Infinity },
  modes: ['lightweight', 'incremental', 'full'],
  skill: 'nextjs-route-ui-boundaries',
  tracksLoadSignals: true,

  /** @param {string} filePath */
  excludesFile: (filePath) => NO_BOUNDARY_FILE_PATTERN.test(filePath),

  /**
   * Pages of the unit's routes (their own parts and the data they await,
   * not the other components they render), every segment file that wraps
   * them, the project configuration, followed with the `route` role, and the
   * framework packages the project declares, whose version decides the App
   * Router conventions even when no file imports them.
   *
   * @param {{ index: any, unit: any }} input
   * @returns {({ path: string, symbol: string, role: string, follow: boolean } | { package: string })[]}
   */
  contextEntries({ index, unit }) {
    const { pages, projectFiles, segmentFiles } = routeContextFiles(index, unit);
    return [
      ...pages.map((filePath) => ({ follow: false, path: filePath, role: 'route', symbol: '*' })),
      ...pages.flatMap((filePath) => pageDataDependencies(index, filePath)),
      ...[...segmentFiles, ...projectFiles].map((filePath) => ({ follow: true, path: filePath, role: 'route', symbol: '*' })),
      ...declaredFrameworkPackages(index).map((name) => ({ package: name })),
    ];
  },

  /**
   * @param {{ key: string, change: string, from?: string }} change
   * @param {{ previousSignals?: Record<string, any>, currentSignals?: Record<string, any>, currentImporters?: Record<string, string[]> }} context
   * @returns {{ relevant: boolean, reason: string }}
   */
  classifyChange(change, { previousSignals = {}, currentSignals = {}, currentImporters = {} }) {
    const { part, path: filePath } = splitInputKey(change.key);
    if (change.change === 'relocated') {
      const fromPath = splitInputKey(change.from).path;
      if (isRouteFile(filePath) || isRouteFile(fromPath)) {
        if (path.posix.dirname(fromPath ?? '') !== path.posix.dirname(filePath ?? '')) return { reason: 'route file moved to another segment: its URL, layouts and inherited boundaries may have changed', relevant: true };
        if (conventionName(fromPath) !== conventionName(filePath)) return { reason: `route convention changed (${conventionName(fromPath)} → ${conventionName(filePath)}): the boundary the segment defines changed`, relevant: true };
      }
      return { reason: 'moved without changes outside the route tree', relevant: false };
    }
    if (change.change === 'removed') return { reason: 'code no longer reached by the route: a layout, boundary or client island may have been removed', relevant: true };
    const packageName = packageOfInputKey(change.key);
    if (packageName !== undefined) {
      if (FRAMEWORK_PACKAGES.has(packageName)) return { reason: `framework package ${change.change === 'added' ? 'added' : 'version changed'} (${packageName}): App Router APIs may differ`, relevant: true };
      return { reason: change.change === 'added' ? 'new package in the route: it may need a client island' : 'package version changed: its server or client requirements may differ', relevant: true };
    }
    if (unresolvedSpecifierOfInputKey(change.key) !== undefined) return { reason: 'import that cannot be resolved: boundary impact unknown, reviewed conservatively', relevant: true };
    if (filePath && PROJECT_FILE_PATTERN.test(filePath)) return { reason: 'project configuration of rendering, caching or navigation changed: applies to every route', relevant: true };
    if (filePath && STYLE_FILE_PATTERN.test(filePath)) {
      if (stylesLoadingUi(change.key, currentImporters)) return { reason: 'styles of a skeleton or loading boundary changed', relevant: true };
      return { reason: 'styles outside skeletons and loading boundaries: no route boundary or server/client decision depends on them', relevant: false };
    }
    const shape = partShape(part);
    const hasSignals = Boolean(currentSignals[change.key] || previousSignals[change.key]);
    if (shape.kind === 'member' && !isRouteFile(filePath)) {
      // A member named as loading UI (`content.fallback`) can hold the JSX of a
      // Suspense fallback even inside a copy dictionary: it stays relevant.
      if (!hasSignals && !LOADING_UI_PATTERN.test(shape.member) && isPresentationMember(shape.owner, shape.member)) return { reason: 'copy or display member: no route boundary depends on it', relevant: false };
      return { reason: 'object member read by the route changed: route configuration impact unknown', relevant: true };
    }
    if (shape.kind === 'module') return { reason: 'module directives ("use client", "use server") or side-effect imports changed', relevant: true };
    const waits = shape.kind === 'handler' ? [] : signalIncreases(change, previousSignals, currentSignals, RENDER_WAIT_SIGNALS);
    if (waits.length) return { reason: `adds awaited work to the render path (${waits.join(', ')}): navigation may wait without a loading boundary`, relevant: true };
    if (isRouteFile(filePath)) return { reason: change.change === 'added' ? 'new route file: segment, layout or boundary added' : 'route file changed: segment layout, boundary or page', relevant: true };
    if (shape.kind === 'file') return { reason: 'file tracked as a whole: boundary impact cannot be classified', relevant: true };
    if (shape.kind === 'handler') return { reason: change.change === 'added' ? 'new interactive handler in the route' : 'interactive handler changed: navigation or server action calls may differ', relevant: true };
    if (shape.kind === 'shell') return { reason: 'component render changed: hooks, Suspense or client imports may differ', relevant: true };
    return { reason: change.change === 'added' ? 'new code rendered by the route' : 'code rendered by the route changed', relevant: true };
  },

  /**
   * Lightweight runs need a review and a build, lint, typecheck or test run;
   * incremental and full runs also need the navigation states exercised in a
   * browser or by a test.
   *
   * @param {string} mode
   * @returns {string[][]}
   */
  evidenceRequirements(mode) {
    if (mode === 'lightweight') return [['review'], ['command', 'test']];
    return [['review'], ['command'], ['browser', 'test']];
  },

  /**
   * A build, lint, typecheck or test run accredits only when the tool ran it.
   *
   * @param {any} item
   * @returns {string[]}
   */
  validateEvidence(item) {
    if (!EXECUTED_EVIDENCE_KINDS.has(item.kind) || item.outcome === 'fail' || item.source === 'witnessed') return [];
    return [`${item.kind} evidence (build, lint, typecheck or tests) must be run with evidence --exec, not declared`];
  },

  /**
   * @param {string} decision
   * @param {{ key: string, change: string }[]} relevantChanges
   * @param {{ unit: any }} context
   * @returns {string[]}
   */
  suggestScope(decision, relevantChanges, { unit }) {
    if (decision === 'full') {
      const routes = unit.routes?.length ? ` (${unit.routes.join(', ')})` : '';
      return [`whole unit ${unit.id}${routes}: map the segments that wrap it (layouts, templates, loading, error, not-found), decide the server/client split of each element and the skeleton of each loading state, check the Next.js APIs against the installed version, and verify build, sibling navigation, error containment with retry and the server-rendered shell`];
    }
    return scopeByReviewFocus(relevantChanges, reviewFocus);
  },
};
