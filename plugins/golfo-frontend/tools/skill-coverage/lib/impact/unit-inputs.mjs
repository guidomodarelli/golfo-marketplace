/**
 * Computes the inputs of a functional unit for one skill: the transitive
 * closure of the parts its entries reach (same-file references, imports,
 * re-exports, packages), each with its hash. The closure is the unit's
 * "relevant code": its fingerprint decides whether coverage is current and
 * its keys say exactly which function, handler or constant changed.
 *
 * Input keys:
 * - `path#<module>`, `path#Name`, `path#Name~shell`, `path#Name/inner`,
 *   `path#Name~frame`, `path#Name.member`: parts from the module analyzer.
 * Entries can also name `Name~shell`: a component body without its inner
 * handlers, for a subflow made of the component's own rendering and data.
 *
 * - `path#*`: a file hashed as a whole (non-JS file, parse failure, no parser).
 * - `pkg:<name>`: an npm package at the version in the lockfile.
 * - `unresolved:<specifier>`: an import nobody could resolve.
 *
 * A literal `import('./x')` is followed as a whole-module import from the
 * part that contains it, like a static import of `* from './x'`.
 */
import { ANALYZER_VERSION, FILE_LEVEL_ANALYZER, INPUT_KEY_PREFIXES, MAX_UNIT_INPUT_ENTRIES, PACKAGE_METADATA_FILES } from '../constants.mjs';
import { fingerprintOf } from '../support.mjs';

const MISSING_HASH = 'missing';
const PACKAGE_MANIFEST_FILE = PACKAGE_METADATA_FILES.manifest;
const ROUTE_HANDLER_PATTERN = /(?:^|\/)route\.[cm]?[jt]sx?$/;
const REFERENCE_PATTERN = /^([^/.~]+)(?:\/([^/.]+)|\.(.+)|(~shell))?$/;

/**
 * Role assumed for an entry without one: API route handlers are server
 * code, everything else is UI.
 *
 * @param {{ path: string, role?: string }} entry
 * @returns {string}
 */
export function entryRole(entry) {
  return entry.role ?? (ROUTE_HANDLER_PATTERN.test(entry.path) ? 'server' : 'ui');
}

/**
 * Entries of a unit for a skill: its own entries, its explicit dependencies
 * and the shared inputs the config declares for that skill.
 *
 * @param {any} unit
 * @param {any} config
 * @param {string} skill
 * @returns {{ path: string, symbol?: string, role?: string, follow?: boolean }[]}
 */
export function unitEntries(unit, config, skill) {
  const shared = (config.sharedInputs ?? []).filter((input) => !input.skills || input.skills.includes(skill));
  return [...unit.entries, ...(unit.dependsOn ?? []), ...shared];
}

/**
 * @param {{ index: any, unit: any, config: any, policy: any }} input
 * @returns {{
 *   analyzer: string, fingerprint: string, inputs: Record<string, string>, files: Record<string, string>,
 *   signals: Record<string, Record<string, number>>, fileLevelFiles: Record<string, string>,
 *   unresolved: string[], warnings: string[], truncated: boolean, via: Record<string, string>,
 *   importers: Record<string, string[]>
 * }}
 */
export function computeUnitInputs({ index, unit, config, policy }) {
  const inputs = {};
  const files = {};
  const signals = {};
  const fileLevelFiles = {};
  const unresolved = new Set();
  const warnings = [];
  const queue = [];
  const expansionScopes = new Map();
  const via = {};
  const importers = new Map();
  let truncated = false;
  let inputCount = 0;

  const maxDepth = (role) => policy.maxDepthByRole?.[role] ?? Infinity;

  /**
   * Claims the expansion of a queued reference, a part, a module shell or a
   * whole file with the traversal scope of `context`. Hashing an input is
   * idempotent, but following its dependencies depends on the scope it was
   * reached with: a server entry may reach a shared helper at its depth
   * limit before a UI entry reaches it with depth to spare, so the helper
   * must be expanded again for the broader scope. An earlier expansion
   * covers this one when it had at least as many cross-file hops left and
   * followed at least as much. Each key is expanded at most once per
   * distinct scope, which also ends circular barrel graphs (`a` re-exports
   * `b`, `b` re-exports `a`) whose re-exports add no parts.
   *
   * @param {string} key What is about to be expanded.
   * @param {any} context Traversal context that reached it.
   * @returns {boolean} Whether no earlier expansion already covered this scope.
   */
  const claimExpansion = (key, context) => {
    const scope = { follow: context.follow, remainingDepth: maxDepth(context.role) - context.depth };
    const previousScopes = expansionScopes.get(key) ?? [];
    if (previousScopes.some((previous) => previous.remainingDepth >= scope.remainingDepth && (previous.follow || !scope.follow))) return false;
    expansionScopes.set(key, [...previousScopes, scope]);
    return true;
  };

  const addInput = (key, hash, partSignals, from) => {
    if (!(key in inputs) && inputCount >= MAX_UNIT_INPUT_ENTRIES) {
      truncated = true;
      return false;
    }
    if (!(key in inputs)) inputCount += 1;
    inputs[key] = hash;
    if (from && !(key in via)) via[key] = from;
    if (partSignals && policy.tracksLoadSignals) signals[key] = partSignals;
    return true;
  };

  // Boundaries (composition roots, dependency containers) are hashed but
  // not followed: reaching one must not pull in every module it wires.
  const boundaries = config.boundaries ?? [];
  const isBoundary = (filePath, symbolName) => boundaries.some((boundary) => boundary.path === filePath && (boundary.symbol === '*' || boundary.symbol === symbolName));

  for (const entry of unitEntries(unit, config, policy.skill)) {
    if (!index.fileExists(entry.path)) {
      addInput(`${entry.path}#*`, MISSING_HASH);
      warnings.push(`entry ${entry.path} does not exist`);
      continue;
    }
    queue.push({ depth: 0, explicit: true, follow: entry.follow !== false, from: `entry:${entry.path}#${entry.symbol ?? '*'}`, path: entry.path, reference: entry.symbol ?? '*', role: entryRole(entry) });
  }
  // Context the policy derives from the project (for example the layouts and
  // boundaries that wrap the unit's routes): existing files only, subject to
  // the ignore list and the policy exclusions like any reached file.
  for (const entry of policy.contextEntries?.({ config, index, unit }) ?? []) {
    // A package the unit depends on without importing it (the framework that
    // runs its routes) is tracked at the version the project declares.
    if (entry.package) {
      const resolution = index.resolver.resolve(PACKAGE_MANIFEST_FILE, entry.package);
      if (resolution.kind === 'package') addInput(`${INPUT_KEY_PREFIXES.package}${resolution.name}`, resolution.versionHash, undefined, `context:${INPUT_KEY_PREFIXES.package}${entry.package}`);
      continue;
    }
    queue.push({ depth: 0, explicit: false, follow: entry.follow !== false, from: `context:${entry.path}#${entry.symbol ?? '*'}`, path: entry.path, reference: entry.symbol ?? '*', role: entry.role ?? entryRole(entry) });
  }

  /**
   * Queues a cross-file reference through an import binding.
   *
   * @param {any} context Current queue item.
   * @param {string} specifier Import source.
   * @param {string} targetReference Reference inside the target module.
   * @param {{ sameDepth?: boolean }} [options] Re-exports do not spend depth.
   */
  const followImport = (context, specifier, targetReference, options = {}) => {
    const resolution = index.resolver.resolve(context.path, specifier);
    if (resolution.kind === 'package') addInput(`${INPUT_KEY_PREFIXES.package}${resolution.name}`, resolution.versionHash, undefined, context.from);
    else if (resolution.kind === 'unresolved') {
      unresolved.add(`${specifier} (from ${context.path})`);
      addInput(`${INPUT_KEY_PREFIXES.unresolved}${specifier}`, MISSING_HASH, undefined, context.from);
    } else if (resolution.kind === 'file') {
      const depth = options.sameDepth ? context.depth : context.depth + 1;
      if (depth > maxDepth(context.role)) return;
      queue.push({ ...context, depth, explicit: false, follow: true, path: resolution.path, reference: targetReference });
    }
  };

  /**
   * @param {any} analysis
   * @param {string} reference `Name`, `Name.member` or a sibling `/inner` (already qualified by the caller).
   * @param {any} context
   */
  const followReference = (analysis, reference, context) => {
    const [name, ...rest] = reference.split('.');
    const member = rest.length ? rest.join('.') : undefined;
    if (analysis.symbols.has(name)) {
      expandReference(analysis, reference, context);
      return;
    }
    const binding = analysis.imports.get(name);
    if (!binding) return;
    let targetReference;
    if (binding.imported === '*') targetReference = member ?? '*';
    else targetReference = member ? `${binding.imported}.${member}` : binding.imported;
    followImport(context, binding.source, targetReference);
  };

  /**
   * @param {any} analysis
   * @param {string} symbolName
   * @param {string} partKey
   * @param {any} context
   * @param {boolean} followInnerReferences Whether `/inner` references are followed.
   */
  const addPart = (analysis, symbolName, partKey, context, followInnerReferences) => {
    const key = `${analysis.path}#${partKey}`;
    if (!claimExpansion(key, context)) return;
    const part = analysis.symbols.get(symbolName).parts.get(partKey);
    if (!addInput(key, part.hash, part.signals, context.from) || !context.follow || isBoundary(analysis.path, symbolName)) return;
    const childContext = { ...context, from: key };
    for (const reference of part.references) {
      if (reference.startsWith('/')) {
        if (followInnerReferences) expandReference(analysis, `${symbolName}${reference}`, childContext);
      } else {
        followReference(analysis, reference, childContext);
      }
    }
    for (const specifier of part.dynamicImportSources) followImport(childContext, specifier, '*');
  };

  /**
   * @param {any} analysis
   * @param {any} symbol
   * @param {any} context
   */
  const addWholeSymbol = (analysis, symbol, context) => {
    for (const partKey of symbol.parts.keys()) addPart(analysis, symbol.name, partKey, context, true);
  };

  /**
   * Expands `*`, `Name`, `Name/inner` or `Name.member` inside one module.
   *
   * @param {any} analysis
   * @param {string} reference
   * @param {any} context
   */
  const expandReference = (analysis, reference, context) => {
    if (reference === '*') {
      for (const symbol of analysis.symbols.values()) addWholeSymbol(analysis, symbol, context);
      for (const target of analysis.reExports.values()) followImport(context, target.source, target.imported, { sameDepth: true });
      for (const source of analysis.exportAllSources) followImport(context, source, '*', { sameDepth: true });
      return;
    }
    const match = REFERENCE_PATTERN.exec(reference);
    if (!match) {
      warnings.push(`cannot parse reference ${reference} in ${analysis.path}`);
      return;
    }
    const [, name, inner, member, shellOnly] = match;
    const suffix = inner ? `/${inner}` : member ? `.${member}` : shellOnly ?? '';
    const symbol = analysis.symbols.get(name);
    if (!symbol) {
      const local = analysis.localExports.get(name);
      // An export that names an imported binding (`import Child from './child';
      // export default Child`, `export { Child as View }`, `export { Child }`)
      // is followed to the imported module.
      if (local && analysis.imports.has(local)) {
        followReference(analysis, member ? `${local}.${member}` : local, context);
        return;
      }
      if (local && local !== name) {
        expandReference(analysis, `${local}${suffix}`, context);
        return;
      }
      const reExport = analysis.reExports.get(name);
      if (reExport) {
        followImport(context, reExport.source, reExport.imported === '*' ? member ?? '*' : `${reExport.imported}${suffix}`, { sameDepth: true });
        return;
      }
      if (analysis.exportAllSources.length) {
        for (const source of analysis.exportAllSources) followImport(context, source, reference, { sameDepth: true });
        return;
      }
      warnings.push(`symbol ${name} not found in ${analysis.path}; the whole file is tracked instead`);
      addInput(`${analysis.path}#*`, analysis.fileHash, undefined, context.from);
      return;
    }
    if (shellOnly && symbol.layout === 'container') {
      addPart(analysis, name, `${name}~shell`, context, false);
    } else if (inner && symbol.layout === 'container' && symbol.parts.has(`${name}/${inner}`)) {
      addPart(analysis, name, `${name}~shell`, context, false);
      addPart(analysis, name, `${name}/${inner}`, context, true);
    } else if (member && symbol.layout === 'object' && symbol.parts.has(`${name}.${member}`)) {
      addPart(analysis, name, `${name}~frame`, context, true);
      addPart(analysis, name, `${name}.${member}`, context, true);
    } else {
      if (inner) warnings.push(`inner function ${name}/${inner} not found in ${analysis.path}; the whole ${name} is tracked instead`);
      addWholeSymbol(analysis, symbol, context);
    }
  };

  while (queue.length && !truncated) {
    const context = queue.shift();
    if (!context.explicit && (index.isIgnored(context.path) || policy.excludesFile?.(context.path))) continue;
    // Every part that reaches a file, not only the first one `via` keeps: a
    // file shared by several consumers belongs to all of them.
    if (!importers.has(context.path)) importers.set(context.path, new Set());
    importers.get(context.path).add(context.from);
    if (!claimExpansion(`${context.path}\0${context.reference}`, context)) continue;
    const analysis = index.analyze(context.path);
    if (!analysis) {
      addInput(`${context.path}#*`, MISSING_HASH);
      continue;
    }
    files[context.path] = analysis.fileHash;

    if (analysis.analyzer === FILE_LEVEL_ANALYZER) {
      const key = `${context.path}#*`;
      if (!claimExpansion(key, context)) continue;
      addInput(key, analysis.fileHash, undefined, context.from);
      if (analysis.fallbackReason && !/not a JavaScript/.test(analysis.fallbackReason)) fileLevelFiles[context.path] = analysis.fallbackReason;
      if (context.follow) for (const source of analysis.importSources) followImport({ ...context, from: key }, source, '*');
      continue;
    }

    const shellKey = `${context.path}#<module>`;
    if (claimExpansion(shellKey, context)) {
      addInput(shellKey, analysis.moduleShell.hash, analysis.moduleShell.signals, context.from);
      if (context.follow) {
        const shellContext = { ...context, from: shellKey };
        for (const reference of analysis.moduleShell.references) followReference(analysis, reference, shellContext);
        for (const source of analysis.sideEffectImports) followImport(shellContext, source, '*');
        for (const specifier of analysis.moduleShell.dynamicImportSources) followImport(shellContext, specifier, '*');
      }
    }
    expandReference(analysis, context.reference, context);
  }

  if (truncated) warnings.push(`input closure truncated at ${MAX_UNIT_INPUT_ENTRIES} entries; narrow the unit entries`);
  return {
    analyzer: index.parser ? ANALYZER_VERSION : FILE_LEVEL_ANALYZER,
    fileLevelFiles,
    files,
    fingerprint: fingerprintOf(inputs),
    importers: Object.fromEntries([...importers].map(([filePath, parents]) => [filePath, [...parents].sort()])),
    inputs,
    signals,
    truncated,
    unresolved: [...unresolved].sort(),
    via,
    warnings,
  };
}

/**
 * Chain of parts through which a unit reaches an input, from the input back
 * to the unit entry (`entry:path#symbol`) or the policy context entry
 * (`context:path#symbol`).
 *
 * @param {Record<string, string>} via Parent of each input, from `computeUnitInputs`.
 * @param {string} key Input key.
 * @returns {string[]}
 */
export function dependencyChain(via, key) {
  const chain = [key];
  let current = key;
  while (via[current] && chain.length < 40 && !chain.includes(via[current])) {
    current = via[current];
    chain.push(current);
  }
  return chain;
}
