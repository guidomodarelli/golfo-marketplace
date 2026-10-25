/**
 * Assisted discovery of functional units in a Next.js App Router project.
 *
 * For each `page.*` it follows the UI code the page renders (pages,
 * containers and components, never domain or infrastructure code) and
 * proposes:
 *
 * - one unit per *action* of a section component when the section has two or
 *   more independent actions (inner handlers that call I/O helpers or fetch),
 *   so they get independent coverage;
 * - one unit per section component with a single action or its own data
 *   loading;
 * - a `view` unit for the page load when the page itself loads data.
 *
 * Proposals reuse the id of an existing unit with the same entry, and report
 * moved symbols so the unit keeps its id. Discovery never records coverage.
 */
import path from 'node:path';

import { ROUTE_BOUNDARY_FILES, SCHEMA_VERSION } from '../constants.mjs';
import { partShape, splitInputKey } from '../impact/input-diff.mjs';
import { computeUnitInputs } from '../impact/unit-inputs.mjs';
import { PAGE_FILE_PATTERN, ROUTE_HANDLER_FILE_PATTERN, appDirectoryOf, nearestSegmentFiles, routeOfFile } from '../source/next-route-tree.mjs';

const HTTP_METHODS = ['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'];
/** Route exports every page or route handler shares: their name alone never identifies a moved entry. */
const ROUTE_EXPORT_SYMBOLS = new Set(['default', ...HTTP_METHODS]);
const ACTION_SIGNALS = ['projectCalls', 'fetch', 'database', 'awaitInLoop'];
const DATA_LOADING_SIGNALS = ['fetch', 'projectCalls', 'database', 'awaits'];
const DISCOVERY_DEPTH = 4;
const UNIT_FILE_EXISTS_REASON = 'a unit file with this id already exists in the registry';

/**
 * @param {string} text
 * @returns {string} ASCII kebab-case.
 */
function toKebab(text) {
  return text
    .normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .replace(/[^A-Za-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .toLowerCase();
}

/**
 * @param {string} appDirectory `app` or `src/app`.
 * @param {string} filePath Page or route file.
 * @returns {{ route: string, idSegments: string[] }}
 */
function routeOf(appDirectory, filePath) {
  const { route, segments } = routeOfFile(appDirectory, filePath);
  const idSegments = segments.filter((segment) => !segment.startsWith('[')).map(toKebab).filter(Boolean);
  return { idSegments: idSegments.length ? idSegments : ['root'], route };
}

/**
 * @param {Record<string, number> | undefined} signals
 * @param {string[]} names
 * @returns {boolean}
 */
function hasSignal(signals, names) {
  return Boolean(signals) && names.some((name) => (signals[name] ?? 0) > 0);
}

/**
 * Whether an entry defines the unit's identity. Composition-only entries
 * (`follow: false`, such as the page that renders a section) only place the
 * unit in its page and must not make another flow look like this unit.
 *
 * @param {{ follow?: boolean }} entry
 * @returns {boolean}
 */
function isFunctionalEntry(entry) {
  return entry.follow !== false;
}

/**
 * First id free of collisions: `baseId`, then `baseId-2`, `baseId-3`, ...
 *
 * @param {string} baseId
 * @param {Set<string>} usedIds Registered ids and ids already given in this pass.
 * @returns {string}
 */
function firstFreeId(baseId, usedIds) {
  if (!usedIds.has(baseId)) return baseId;
  let suffix = 2;
  while (usedIds.has(`${baseId}-${suffix}`)) suffix += 1;
  return `${baseId}-${suffix}`;
}

/**
 * @param {string} innerName Handler name such as `handleSubmit` or `onRetry`.
 * @returns {string}
 */
function actionSlug(innerName) {
  return toKebab(innerName.replace(/^(?:handle|on)(?=[A-Z])/, '')) || toKebab(innerName);
}

/**
 * @param {any} context Project context.
 * @param {{ scope?: string, includeApi?: boolean }} options
 */
export function discoverUnits(context, options = {}) {
  const index = context.index;
  const appDirectory = appDirectoryOf(index.files);
  const uiPrefixes = [`${appDirectory}/`, 'components/', 'src/components/', 'hooks/', 'src/hooks/'];
  const isUiFile = (filePath) => uiPrefixes.some((prefix) => filePath.startsWith(prefix));
  const inScope = (filePath) => !options.scope || filePath.startsWith(options.scope.replace(/\\/g, '/').replace(/\/?$/, '/')) || filePath === options.scope;
  const { units: existingUnits, errors } = context.registry.loadUnits();

  const existingByEntry = new Map();
  for (const unit of existingUnits) for (const entry of unit.entries.filter(isFunctionalEntry)) existingByEntry.set(`${entry.path}#${entry.symbol ?? '*'}`, unit.id);

  const discoveryPolicy = {
    excludesFile: (filePath) => !isUiFile(filePath),
    maxDepthByRole: { server: 0, ui: DISCOVERY_DEPTH },
    skill: 'discovery',
    tracksLoadSignals: true,
  };

  const proposals = [];
  const pages = [...index.files].filter((filePath) => filePath.startsWith(`${appDirectory}/`) && PAGE_FILE_PATTERN.test(filePath) && inScope(filePath)).sort();

  // First pass: the UI closure of every page and which pages reach each component.
  const pageClosures = pages.map((pagePath) => ({
    closure: computeUnitInputs({ config: context.config, index, policy: discoveryPolicy, unit: { entries: [{ path: pagePath, symbol: 'default' }] } }),
    pagePath,
  }));
  const pagesBySymbol = new Map();
  for (const { closure, pagePath } of pageClosures) {
    for (const key of Object.keys(closure.inputs)) {
      const { path: filePath, part } = splitInputKey(key);
      const shape = partShape(part);
      if (!filePath || shape.kind === 'module' || shape.kind === 'file') continue;
      const symbolKey = `${filePath}#${shape.owner}`;
      if (!pagesBySymbol.has(symbolKey)) pagesBySymbol.set(symbolKey, new Set());
      pagesBySymbol.get(symbolKey).add(pagePath);
    }
  }

  /**
   * Inner functions the component's own markup or effects call (user
   * actions), with I/O directly or through a sibling helper.
   */
  const actionsOf = (filePath, name) => {
    const symbol = index.analyze(filePath)?.symbols?.get(name);
    const shell = symbol?.parts.get(`${name}~shell`);
    if (!shell) return [];
    const innerHasIo = (innerName) => hasSignal(symbol.parts.get(`${name}/${innerName}`)?.signals, ACTION_SIGNALS);
    return shell.references.filter((reference) => reference.startsWith('/')).map((reference) => reference.slice(1)).filter((innerName) => {
      const part = symbol.parts.get(`${name}/${innerName}`);
      return part && (innerHasIo(innerName) || part.references.some((reference) => reference.startsWith('/') && innerHasIo(reference.slice(1))));
    }).sort();
  };

  const parentOf = (filePath, name) => {
    for (const symbol of index.analyze(filePath)?.symbols?.values() ?? []) {
      if (symbol.name === name) continue;
      for (const part of symbol.parts.values()) if (part.references.includes(name)) return symbol.name;
    }
    return undefined;
  };

  for (const { closure, pagePath } of pageClosures) {
    const { idSegments, route } = routeOf(appDirectory, pagePath);
    const moduleLabel = idSegments[0];
    const pageDirectory = path.posix.dirname(pagePath);
    const pageEntry = { follow: false, path: pagePath, symbol: 'default' };

    const symbols = new Map();
    for (const key of Object.keys(closure.inputs)) {
      const { path: filePath, part } = splitInputKey(key);
      const shape = partShape(part);
      if (!filePath || !isUiFile(filePath) || filePath === pagePath || shape.kind === 'module' || shape.kind === 'file') continue;
      const name = shape.owner;
      const symbolKey = `${filePath}#${name}`;
      const analysisSymbol = index.analyze(filePath)?.symbols?.get(name);
      if (!/^[A-Z]/.test(name) || !analysisSymbol?.callable) continue;
      const sharedAcrossPages = (pagesBySymbol.get(symbolKey)?.size ?? 0) > 1 && !filePath.startsWith(`${pageDirectory}/`);
      if (sharedAcrossPages) continue;
      if (!symbols.has(symbolKey)) symbols.set(symbolKey, { filePath, loads: false, name });
      const signals = closure.signals[key];
      if (shape.kind !== 'handler' && (hasSignal(signals, ['effects']) && hasSignal(signals, DATA_LOADING_SIGNALS) || hasSignal(signals, ACTION_SIGNALS))) symbols.get(symbolKey).loads = true;
    }

    const pageProposals = [];
    for (const symbol of symbols.values()) {
      const actions = actionsOf(symbol.filePath, symbol.name);
      if (!actions.length && !symbol.loads) continue;
      const sectionSlug = toKebab(symbol.name.replace(/(?:Section|Container|Panel|Component)$/, '')) || toKebab(symbol.name);
      const parent = parentOf(symbol.filePath, symbol.name);
      const composition = [pageEntry, ...(parent ? [{ follow: false, path: symbol.filePath, symbol: parent }] : [])];
      const hierarchy = { module: moduleLabel, page: route, section: symbol.name };
      if (actions.length >= 2) {
        for (const action of actions) {
          pageProposals.push({
            confidence: 'medium',
            entries: [{ path: symbol.filePath, symbol: `${symbol.name}/${action}` }, ...composition],
            hierarchy: { ...hierarchy, subflow: action },
            id: [...idSegments, sectionSlug, actionSlug(action)].join('.'),
            kind: 'ui-flow',
            routes: [route],
            signals: [`independent action ${action} in ${symbol.name}`],
          });
        }
      } else {
        pageProposals.push({
          confidence: actions.length ? 'high' : 'medium',
          entries: [{ path: symbol.filePath, symbol: symbol.name }, ...composition],
          hierarchy: { ...hierarchy, subflow: actions[0] ?? symbol.name },
          id: [...idSegments, sectionSlug].join('.'),
          kind: 'ui-flow',
          routes: [route],
          signals: [actions.length ? `single action ${actions[0]}` : 'loads its own data'],
        });
      }
    }

    const pageAnalysis = index.analyze(pagePath);
    const pageDefault = pageAnalysis?.localExports?.get('default');
    const pageSymbol = pageDefault ? pageAnalysis.symbols?.get(pageDefault) : undefined;
    const pageLoadsData = pageSymbol && [...pageSymbol.parts.values()].some((part) => hasSignal(part.signals, DATA_LOADING_SIGNALS));
    if (pageLoadsData || !pageProposals.length) {
      pageProposals.push({
        confidence: pageProposals.length ? 'medium' : 'low',
        entries: [{ path: pagePath, symbol: 'default' }, ...nearestSegmentFiles(index, appDirectory, pagePath, ROUTE_BOUNDARY_FILES).map((boundary) => ({ path: boundary, symbol: 'default' }))],
        hierarchy: { module: moduleLabel, page: route, section: null, subflow: 'view' },
        id: [...idSegments, 'view'].join('.'),
        kind: 'ui-flow',
        routes: [route],
        signals: [pageLoadsData ? 'page loads data on the server' : 'no section with actions found: the page is one unit'],
      });
    }
    proposals.push(...pageProposals);
  }

  if (options.includeApi) {
    const routes = [...index.files].filter((filePath) => filePath.startsWith(`${appDirectory}/`) && ROUTE_HANDLER_FILE_PATTERN.test(filePath) && inScope(filePath)).sort();
    for (const routePath of routes) {
      const { idSegments, route } = routeOf(appDirectory, routePath);
      const analysis = index.analyze(routePath);
      const methods = analysis?.localExports ? HTTP_METHODS.filter((method) => analysis.localExports.has(method)) : [];
      for (const method of methods) {
        proposals.push({
          confidence: 'high',
          entries: [{ path: routePath, role: 'server', symbol: method }],
          hierarchy: { module: 'api', page: route, section: null, subflow: method },
          id: ['api', ...idSegments, method.toLowerCase()].join('.'),
          kind: 'api',
          routes: [`${method} ${route}`],
          signals: [`route handler ${method}`],
        });
      }
    }
  }

  /** Whether a file still declares or exports the root of an entry symbol. */
  const declaresSymbol = (filePath, symbol) => {
    const analysis = index.fileExists(filePath) ? index.analyze(filePath) : undefined;
    if (!analysis) return false;
    if (!analysis.symbols) return true;
    const name = symbol.split(/[/.~]/)[0];
    return analysis.symbols.has(name) || analysis.localExports.has(name) || analysis.reExports.has(name);
  };

  // Reuse existing ids; report units whose primary entry moved. A move needs
  // a symbol name that identifies the entry (not a shared route export) and a
  // one-to-one match: an ambiguous proposal stays a new unit instead of
  // rewriting an existing one.
  const moveCandidates = [];
  for (const proposal of proposals) {
    const primary = proposal.entries[0];
    proposal.existingId = existingByEntry.get(`${primary.path}#${primary.symbol}`) ?? null;
    if (proposal.existingId || ROUTE_EXPORT_SYMBOLS.has(primary.symbol.split(/[/.~]/)[0])) continue;
    for (const unit of existingUnits) {
      const moved = unit.entries.find((entry) => isFunctionalEntry(entry) && entry.symbol === primary.symbol && entry.path !== primary.path && !declaresSymbol(entry.path, entry.symbol));
      if (moved) moveCandidates.push({ from: moved.path, proposal, unitId: unit.id });
    }
  }
  const candidateCount = (matches) => moveCandidates.filter(matches).length;
  const relocations = [];
  for (const candidate of moveCandidates) {
    const { from, proposal, unitId } = candidate;
    if (candidateCount((other) => other.proposal === proposal) !== 1 || candidateCount((other) => other.unitId === unitId) !== 1) continue;
    proposal.existingId = unitId;
    relocations.push({ from, symbol: proposal.entries[0].symbol, to: proposal.entries[0].path, unitId });
  }

  // Registered ids and the ids of proposals that match a unit are reserved
  // before naming new proposals, so a new route never takes the id of an
  // existing unit, whatever the page order.
  const usedIds = new Set(existingUnits.map((unit) => unit.id));
  for (const proposal of proposals) if (proposal.existingId) usedIds.add(proposal.id);
  for (const proposal of proposals) {
    if (proposal.existingId) continue;
    proposal.id = firstFreeId(proposal.id, usedIds);
    usedIds.add(proposal.id);
  }
  return { errors, proposals, relocations };
}

/**
 * Writes new proposals as units and applies relocations, never touching
 * coverage records.
 *
 * @param {any} context
 * @param {{ proposals: any[], relocations: any[] }} discovery
 * @returns {{ created: string[], relocated: string[], skipped: { id: string, reason: string }[] }}
 */
export function writeDiscoveredUnits(context, discovery) {
  const created = [];
  const relocated = [];
  const skipped = [];
  context.registry.initialize();
  for (const proposal of discovery.proposals) {
    if (proposal.existingId) continue;
    const unit = {
      description: `Discovered from ${proposal.routes.join(', ')}: ${proposal.signals.join('; ')}. Review the boundaries and labels.`,
      discovery: { confidence: proposal.confidence, signals: proposal.signals },
      entries: proposal.entries,
      hierarchy: proposal.hierarchy,
      id: proposal.id,
      kind: proposal.kind,
      origin: 'discovered',
      routes: proposal.routes,
      schemaVersion: SCHEMA_VERSION,
    };
    if (context.registry.saveUnit(unit)) created.push(unit.id);
    else skipped.push({ id: unit.id, reason: UNIT_FILE_EXISTS_REASON });
  }
  for (const relocation of discovery.relocations) {
    const unit = context.registry.loadUnit(relocation.unitId);
    unit.entries = unit.entries.map((entry) => (entry.path === relocation.from && entry.symbol === relocation.symbol ? { ...entry, path: relocation.to } : entry));
    context.registry.saveUnit(unit, { overwrite: true });
    relocated.push(relocation.unitId);
  }
  return { created, relocated, skipped };
}
