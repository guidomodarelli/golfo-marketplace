/**
 * Policy of `ui-ux-flow-patterns`: every visible or interactive change is
 * relevant, however small (copy, a handler, a style, a component package).
 * Server code matters only at its boundary (the route handler that returns
 * the errors and states the UI shows), not deep inside repositories.
 */
import { packageOfInputKey, partShape, splitInputKey } from '../impact/input-diff.mjs';
import { DEFAULT_DEFINITION_FILES, scopeByReviewFocus, STYLE_FILE_PATTERN } from './base-policy.mjs';

/**
 * @param {{ key: string, change: string }} change
 * @returns {string} What the next run must look at for this change.
 */
function reviewFocus(change) {
  const { part, path } = splitInputKey(change.key);
  if (packageOfInputKey(change.key) !== undefined) return 'components and hooks used from this package: states, feedback and accessibility after the upgrade';
  if (path && STYLE_FILE_PATTERN.test(path)) return 'visual states that use the changed classes (contrast, focus, loading and error styles)';
  const { kind } = partShape(part);
  if (kind === 'handler') return 'the action of this handler: pending state, double submit, feedback channel, error recovery and stale errors, with its component states as context';
  if (kind === 'shell') return 'the states this component renders (loading, empty, data, error, partial, no permission) and their copy';
  if (kind === 'member') return 'copy or configuration read from this member, in every state that shows it';
  if (kind === 'module') return 'client/server boundary and side effects of the module';
  return 'behavior of this code in every state of the unit that uses it';
}

export const uiUxFlowPatternsPolicy = {
  definitionFiles: DEFAULT_DEFINITION_FILES,
  label: 'UI/UX',
  maxDepthByRole: { contract: Infinity, server: 1, ui: Infinity },
  modes: ['lightweight', 'incremental', 'full'],
  skill: 'ui-ux-flow-patterns',
  tracksLoadSignals: false,

  excludesFile: () => false,

  /**
   * @param {{ key: string, change: string }} change
   * @returns {{ relevant: boolean, reason: string }}
   */
  classifyChange(change) {
    if (change.change === 'relocated') return { reason: 'moved without changes', relevant: false };
    if (change.change === 'removed') return { reason: 'code no longer reached by the unit: check that no state lost its feedback', relevant: true };
    return { reason: change.change === 'added' ? 'new visible or interactive code' : 'visible or interactive code changed', relevant: true };
  },

  /**
   * @param {string} mode
   * @returns {string[][]}
   */
  evidenceRequirements(mode) {
    if (mode === 'lightweight') return [['review'], ['test', 'browser']];
    return [['review'], ['test'], ['browser', 'accessibility']];
  },

  validateEvidence: () => [],

  /**
   * @param {string} decision
   * @param {{ key: string, change: string }[]} relevantChanges
   * @param {{ unit: any }} context
   * @returns {string[]}
   */
  suggestScope(decision, relevantChanges, { unit }) {
    if (decision === 'full') {
      return [`whole unit ${unit.id}: state matrix of every region (loading, empty, data, error, partial, no permission), feedback channel per event, copy and browser walk-through`];
    }
    return scopeByReviewFocus(relevantChanges, reviewFocus);
  },
};
