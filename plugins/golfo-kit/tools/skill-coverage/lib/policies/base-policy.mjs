/**
 * Building blocks shared by skill policies. A policy tells the common engine
 * what a skill considers relevant, which evidence accredits each execution
 * mode and how to scope the next run; the engine never hardcodes a skill.
 *
 * Policy contract:
 * - `skill`, `label`: skill name and short report label.
 * - `definitionFiles`: globs, relative to the skill directory, whose content
 *   is the normative definition hashed into every record.
 * - `modes`: execution modes the skill supports.
 * - `maxDepthByRole`: cross-file hops followed from each entry role.
 * - `excludesFile(path)`: files outside the skill's concern.
 * - `tracksLoadSignals`: whether part load signals are stored.
 * - `classifyChange(change, context)`: `{ relevant, reason }`.
 * - `evidenceRequirements(mode)`: groups of evidence kinds; each group needs
 *   one passing item.
 * - `validateEvidence(evidence)`: extra checks of one evidence item.
 * - `suggestScope(decision, relevantChanges, context)`: next run's scope.
 * - `contextEntries({ unit, index, config })` (optional): extra entries the
 *   unit's closure needs for this skill and that the unit does not declare,
 *   such as the layouts and boundaries wrapping its routes. Each entry is
 *   `{ path, symbol, role, follow }` naming an existing file, or
 *   `{ package }` for a package the unit runs on without importing it
 *   (tracked at the version the project declares).
 *
 * `classifyChange` receives `previousSignals`, `currentSignals`,
 * `signalsRecorded` and `currentImporters` (every part or entry that reaches
 * each current file, `entry:`/`context:` labels included).
 */
import { packageOfInputKey, partShape, splitInputKey, unresolvedSpecifierOfInputKey } from '../impact/input-diff.mjs';

/** Files, relative to the skill directory, that hold a skill's normative definition. */
export const DEFAULT_DEFINITION_FILES = ['SKILL.md', 'references/**/*.md'];

/** Stylesheets. */
export const STYLE_FILE_PATTERN = /\.(?:s?css|sass|less)$/;

/** Files that run no code: stylesheets, translation catalogs and docs. */
export const NON_EXECUTABLE_FILE_PATTERN = /\.(?:s?css|sass|less|po|pot|md|mdx)$/;

/**
 * Turns an input key into a short human description.
 *
 * @param {string} key
 * @returns {string}
 */
export function describeInputKey(key) {
  const packageName = packageOfInputKey(key);
  if (packageName !== undefined) return `package ${packageName}`;
  const specifier = unresolvedSpecifierOfInputKey(key);
  if (specifier !== undefined) return `unresolved import ${specifier}`;
  const { path, part } = splitInputKey(key);
  const shape = partShape(part);
  if (shape.kind === 'file') return `${path} (whole file)`;
  if (shape.kind === 'module') return `${path} (module directives and side effects)`;
  if (shape.kind === 'shell') return `${path} › ${shape.owner} (component body outside its handlers)`;
  if (shape.kind === 'frame') return `${path} › ${shape.owner} (object structure)`;
  return `${path} › ${part.replace('/', ' › ')}`;
}

/**
 * Incremental scope shared by the policies: each relevant change, described,
 * with what the next run must look at for it.
 *
 * @param {{ key: string }[]} relevantChanges
 * @param {(change: any) => string} reviewFocus
 * @returns {string[]}
 */
export function scopeByReviewFocus(relevantChanges, reviewFocus) {
  return relevantChanges.map((change) => `${describeInputKey(change.key)} — ${reviewFocus(change)}`);
}

/** Human description of each load signal the module analyzer counts. */
const SIGNAL_LABELS = {
  awaitInLoop: 'awaited calls inside a loop',
  awaits: 'awaited steps',
  database: 'database queries',
  dynamicImports: 'dynamic imports',
  effects: 'effects',
  fetch: 'requests',
  listeners: 'listeners or subscriptions',
  projectCalls: 'calls to I/O helpers',
  timers: 'timers or polling',
};

/**
 * Load signals a change increased; an added part is compared with no load.
 *
 * @param {{ key: string, change: string }} change
 * @param {Record<string, Record<string, number>>} previousSignals Signals of the baseline, by input key.
 * @param {Record<string, Record<string, number>>} currentSignals Current signals, by input key.
 * @param {Set<string>} [countedSignals] Signals to compare; every signal when omitted.
 * @returns {string[]} Increased signals, described.
 */
export function signalIncreases(change, previousSignals = {}, currentSignals = {}, countedSignals) {
  const previous = change.change === 'added' ? {} : previousSignals[change.key] ?? {};
  return Object.entries(currentSignals[change.key] ?? {})
    .filter(([name, count]) => (!countedSignals || countedSignals.has(name)) && count > (previous[name] ?? 0))
    .map(([name, count]) => `+${count - (previous[name] ?? 0)} ${SIGNAL_LABELS[name] ?? name}`);
}

/**
 * Checks evidence against requirement groups.
 *
 * @param {any[]} evidence Evidence items of a run.
 * @param {string[][]} groups Each group lists kinds; one passing item per group is required.
 * @param {(item: any) => string[]} validateItem Extra validation per item.
 * @returns {string[]} Missing or invalid evidence descriptions; empty when accredited.
 */
export function missingEvidence(evidence, groups, validateItem) {
  const problems = [];
  const failing = evidence.filter((item) => item.outcome === 'fail');
  for (const item of failing) problems.push(`${item.kind} evidence failed: ${item.summary || item.command || 'no summary'}`);
  for (const item of evidence) for (const problem of validateItem(item)) problems.push(problem);
  for (const group of groups) {
    const satisfied = evidence.some((item) => group.includes(item.kind) && ['pass', 'measured'].includes(item.outcome) && validateItem(item).length === 0);
    if (!satisfied) problems.push(`missing passing evidence of kind ${group.join(' or ')}`);
  }
  return problems;
}
