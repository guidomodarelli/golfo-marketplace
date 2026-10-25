/**
 * Policy of `optimistic-action-mutations`: a change is relevant when it can
 * alter an operation's lifecycle (handlers, component state and render,
 * helpers, API contracts, server code, cache keys, timing configuration).
 * Styles, translation catalogs and object members positively identified as
 * presentation cannot, so they leave the coverage current; any other object
 * member and anything the analyzer cannot classify is relevant. Server
 * code is followed completely because idempotency, transactions and the
 * reconciliation payload live there.
 */
import { packageOfInputKey, partShape, splitInputKey, unresolvedSpecifierOfInputKey } from '../impact/input-diff.mjs';
import { DEFAULT_DEFINITION_FILES, NON_EXECUTABLE_FILE_PATTERN, scopeByReviewFocus } from './base-policy.mjs';
import { isPresentationMember } from './presentation-members.mjs';

const SERVER_FILE_PATTERN = /(?:^|\/)(?:route|actions?)\.[cm]?[jt]sx?$|(?:^|\/)(?:api|server|actions)\//;

/**
 * Members of constant objects whose name points to lifecycle configuration
 * (timing, limits, retries, endpoints, cache keys, statuses) instead of copy.
 */
const LIFECYCLE_MEMBER_PATTERN = /delay|debounce|throttle|timeout|interval|retr(?:y|ies)|backoff|cooldown|ttl|expir|limit|max|min|attempt|concurren|batch|poll|url|endpoint|path|route|method|query|key|status|code|version|idempoten/i;

/**
 * @param {Record<string, number> | undefined} signals
 * @returns {boolean} Whether a part performs I/O, timers, effects or subscriptions.
 */
function hasOperationSignals(signals) {
  return Boolean(signals && Object.keys(signals).length);
}

/**
 * @param {{ key: string, change: string }} change
 * @returns {string} What the next run must look at for this change.
 */
function reviewFocus(change) {
  const { part, path } = splitInputKey(change.key);
  if (change.change === 'removed') return 'an operation was removed or moved: check that no pending intent, timer, rollback or cache entry still points to it';
  if (packageOfInputKey(change.key) !== undefined) return 'mutation, cache and cancellation primitives of this package after the change (onMutate, rollback, invalidation, retries)';
  if (unresolvedSpecifierOfInputKey(change.key) !== undefined) return 'import that cannot be resolved: review the operations it may perform';
  if (path && SERVER_FILE_PATTERN.test(path)) return 'server contract of the operation: idempotency, transactions, minimal reconciliation payload, versions and permission rejections';
  const { kind } = partShape(part);
  if (kind === 'file') return 'every operation in the file: class, concurrency, rollback and reconciliation';
  if (kind === 'handler') return 'the action of this handler: class (optimistic, pending-first or server-confirmed), double submit, stale responses, rollback, unknown outcome and reconciliation';
  if (kind === 'shell') return 'how the component state and render show pending, optimistic and confirmed values, and what is cleaned up on unmount or context change';
  if (kind === 'member') return 'lifecycle configuration read from this member (timing, limits, endpoints, cache keys) in every operation that uses it';
  if (kind === 'module') return 'module directives ("use client", "use server") and side effects that change where the operation runs';
  return 'operations that reach this code: intent, concurrency, rollback and reconciliation';
}

export const optimisticActionMutationsPolicy = {
  definitionFiles: DEFAULT_DEFINITION_FILES,
  label: 'Optimistic',
  maxDepthByRole: {},
  modes: ['lightweight', 'incremental', 'full'],
  skill: 'optimistic-action-mutations',
  tracksLoadSignals: true,

  /** @param {string} filePath */
  excludesFile: (filePath) => NON_EXECUTABLE_FILE_PATTERN.test(filePath),

  /**
   * @param {{ key: string, change: string }} change
   * @param {{ previousSignals?: Record<string, any>, currentSignals: Record<string, any> }} context
   * @returns {{ relevant: boolean, reason: string }}
   */
  classifyChange(change, { previousSignals = {}, currentSignals = {} }) {
    const shape = partShape(splitInputKey(change.key).part);
    if (change.change === 'relocated') return { reason: 'moved without changes', relevant: false };
    if (change.change === 'removed') return { reason: 'code no longer reached by the unit: an operation may have been removed', relevant: true };
    if (packageOfInputKey(change.key) !== undefined) return { reason: change.change === 'added' ? 'new package in the flow (data, cache or mutation primitives)' : 'package version changed', relevant: true };
    if (unresolvedSpecifierOfInputKey(change.key) !== undefined) return { reason: 'import that cannot be resolved: lifecycle impact unknown', relevant: true };
    if (shape.kind === 'file') return { reason: 'file tracked as a whole: lifecycle impact cannot be classified', relevant: true };
    if (shape.kind === 'member') {
      if (hasOperationSignals(currentSignals[change.key]) || hasOperationSignals(previousSignals[change.key])) return { reason: 'object member that performs I/O, timers or effects', relevant: true };
      if (LIFECYCLE_MEMBER_PATTERN.test(shape.member)) return { reason: `lifecycle configuration member (${shape.member})`, relevant: true };
      if (isPresentationMember(shape.owner, shape.member)) return { reason: 'copy or display member: no impact on the operation lifecycle', relevant: false };
      return { reason: 'unclassified object member: lifecycle impact unknown', relevant: true };
    }
    if (shape.kind === 'handler') return { reason: change.change === 'added' ? 'new action handler' : 'action handler changed', relevant: true };
    if (shape.kind === 'shell') return { reason: 'component state or render changed', relevant: true };
    return { reason: change.change === 'added' ? 'new code reached by the unit' : 'code reached by the unit changed', relevant: true };
  },

  /**
   * @param {string} mode
   * @returns {string[][]}
   */
  evidenceRequirements(mode) {
    if (mode === 'lightweight') return [['review'], ['test', 'browser']];
    return [['review'], ['test']];
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
      return [`whole unit ${unit.id}: inventory every read, mutation and long-running operation, classify each mutation (optimistic, pending-first or server-confirmed) and review its transitions, concurrency, rollback and reconciliation`];
    }
    return scopeByReviewFocus(relevantChanges, reviewFocus);
  },
};
