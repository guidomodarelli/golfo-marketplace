/**
 * Policy of `measured-performance-optimization`: a change is relevant only
 * when it adds work (requests, queries, awaited steps, timers, listeners,
 * effects, dynamic imports, packages). Copy, styles and refactors that keep
 * the same load leave performance coverage current, matching the skill's own
 * activation rule. Every accredited run needs a real before/after
 * measurement under comparable conditions.
 */
import { packageOfInputKey, splitInputKey, unresolvedSpecifierOfInputKey } from '../impact/input-diff.mjs';
import { DEFAULT_DEFINITION_FILES, NON_EXECUTABLE_FILE_PATTERN, scopeByReviewFocus, signalIncreases } from './base-policy.mjs';

export const measuredPerformanceOptimizationPolicy = {
  definitionFiles: DEFAULT_DEFINITION_FILES,
  label: 'Performance',
  maxDepthByRole: {},
  modes: ['incremental', 'full'],
  skill: 'measured-performance-optimization',
  tracksLoadSignals: true,

  /** @param {string} filePath */
  excludesFile: (filePath) => NON_EXECUTABLE_FILE_PATTERN.test(filePath),

  /**
   * @param {{ key: string, change: string }} change
   * @param {{ previousSignals?: Record<string, any>, currentSignals: Record<string, any>, signalsRecorded: boolean }} context
   * @returns {{ relevant: boolean, reason: string }}
   */
  classifyChange(change, { previousSignals, currentSignals, signalsRecorded }) {
    const { part } = splitInputKey(change.key);
    if (change.change === 'relocated') return { reason: 'moved without changes', relevant: false };
    if (change.change === 'removed') return { reason: 'removes work: not a performance trigger', relevant: false };
    if (packageOfInputKey(change.key) !== undefined) {
      return { reason: change.change === 'added' ? 'new package in the flow (bundle or server cost)' : 'package version changed', relevant: true };
    }
    if (unresolvedSpecifierOfInputKey(change.key) !== undefined) return { reason: 'import that cannot be resolved: load unknown', relevant: true };
    if (part === '*') return { reason: 'file tracked as a whole: load cannot be classified', relevant: true };
    if (!signalsRecorded) return { reason: 'baseline has no load signals: load cannot be compared', relevant: true };
    const increases = signalIncreases(change, previousSignals, currentSignals);
    if (increases.length) return { reason: `adds load: ${increases.join(', ')}`, relevant: true };
    return { reason: change.change === 'added' ? 'new code without load signals' : 'same load (copy, style, types or refactor)', relevant: false };
  },

  evidenceRequirements: () => [['measurement'], ['test']],

  /**
   * A measurement accredits only with metric, tool, conditions and both
   * sides of the comparison (or a new flow compared with a reference).
   *
   * @param {any} item
   * @returns {string[]}
   */
  validateEvidence(item) {
    if (item.kind !== 'measurement' || item.outcome === 'fail') return [];
    const problems = [];
    const label = item.metric ? `measurement ${item.metric}` : 'measurement';
    for (const field of ['metric', 'tool', 'conditions', 'after']) if (!item[field]) problems.push(`${label} lacks ${field}`);
    if (!item.before && !(item.baselineKind === 'new-flow' && item.reference)) problems.push(`${label} lacks before (or --baseline-kind new-flow with --reference)`);
    return problems;
  },

  /**
   * @param {string} decision
   * @param {{ key: string, change: string, reason: string }[]} relevantChanges
   * @param {{ unit: any, baselineCommit?: string, history?: string }} context
   * @returns {string[]}
   */
  suggestScope(decision, relevantChanges, { unit, baselineCommit, baselineProvisional, history }) {
    const flow = unit.routes?.length ? unit.routes.join(', ') : unit.id;
    if (decision === 'full') return [`measure the complete flow ${flow} before and after, same build, data and throttling; median of 3 for noisy metrics`];
    const reachable = baselineCommit && ['same', 'ancestor', 'diverged'].includes(history);
    // A record made over uncommitted changes measured code that its commit
    // does not contain: that commit is not the measured revision.
    let before;
    if (!reachable) before = 'before = the revision without the new load (baseline commit not reachable)';
    else if (baselineProvisional) before = `before = the first revision that contains the last measured code (it was recorded over uncommitted changes on top of ${baselineCommit.slice(0, 12)}, which does not include them), or the revision without the new load`;
    else before = `before = revision ${baselineCommit.slice(0, 12)} (last measured)`;
    return [
      `measure the complete flow ${flow}: ${before}, after = working tree`,
      ...scopeByReviewFocus(relevantChanges, (change) => change.reason),
    ];
  },
};
