/**
 * Policy registry. Skills with specific invalidation and evidence rules have
 * their own module; any other skill gets the generic policy, which the
 * consumer can tune in `config.json` (`skills.<name>`) without code changes.
 */
import { EVIDENCE_KINDS, EXECUTION_MODES } from '../constants.mjs';
import { CoverageError, matchesAnyGlob } from '../support.mjs';
import { DEFAULT_DEFINITION_FILES, describeInputKey } from './base-policy.mjs';
import { measuredPerformanceOptimizationPolicy } from './measured-performance-optimization.mjs';
import { nextjsRouteUiBoundariesPolicy } from './nextjs-route-ui-boundaries.mjs';
import { optimisticActionMutationsPolicy } from './optimistic-action-mutations.mjs';
import { uiUxFlowPatternsPolicy } from './ui-ux-flow-patterns.mjs';

const BUILT_IN_POLICIES = new Map([
  [uiUxFlowPatternsPolicy.skill, uiUxFlowPatternsPolicy],
  [measuredPerformanceOptimizationPolicy.skill, measuredPerformanceOptimizationPolicy],
  [optimisticActionMutationsPolicy.skill, optimisticActionMutationsPolicy],
  [nextjsRouteUiBoundariesPolicy.skill, nextjsRouteUiBoundariesPolicy],
]);

/**
 * @param {string} skill
 * @returns {any} Policy for a skill without specific rules: every change is relevant.
 */
function createGenericPolicy(skill) {
  return {
    definitionFiles: DEFAULT_DEFINITION_FILES,
    label: skill,
    maxDepthByRole: {},
    modes: EXECUTION_MODES,
    skill,
    tracksLoadSignals: false,
    excludesFile: () => false,
    classifyChange: (change) => (change.change === 'relocated' ? { reason: 'moved without changes', relevant: false } : { reason: `code ${change.change}`, relevant: true }),
    evidenceRequirements: () => [['review'], ['test']],
    validateEvidence: () => [],
    suggestScope: (decision, relevantChanges, { unit }) => (decision === 'full' ? [`whole unit ${unit.id}`] : relevantChanges.map((change) => describeInputKey(change.key))),
  };
}

/**
 * @param {unknown} groups
 * @param {string} label
 * @returns {string[][]}
 */
function checkEvidenceGroups(groups, label) {
  const valid = Array.isArray(groups) && groups.every((group) => Array.isArray(group) && group.length && group.every((kind) => EVIDENCE_KINDS.includes(kind)));
  if (!valid) throw new CoverageError(`policies: ${label} must be a list of evidence-kind groups (${EVIDENCE_KINDS.join(', ')})`);
  return groups;
}

/**
 * Resolves the policy of a skill, applying `config.skills.<skill>` overrides:
 * `label`, `excludeFiles` (globs) and `evidence` (`{ <mode>: [[kinds]] }`).
 * Overrides can add exclusions and evidence, never drop the built-in ones.
 *
 * @param {string} skill
 * @param {any} config
 * @returns {any}
 */
export function resolvePolicy(skill, config) {
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(skill ?? '')) throw new CoverageError(`policies: invalid skill name ${JSON.stringify(skill)}`);
  const base = BUILT_IN_POLICIES.get(skill) ?? createGenericPolicy(skill);
  const options = config.skills?.[skill];
  if (!options) return base;
  const extraExclusions = options.excludeFiles ?? [];
  const extraEvidence = options.evidence ?? {};
  for (const [mode, groups] of Object.entries(extraEvidence)) checkEvidenceGroups(groups, `config.skills.${skill}.evidence.${mode}`);
  return {
    ...base,
    label: options.label ?? base.label,
    excludesFile: (filePath) => base.excludesFile(filePath) || matchesAnyGlob(filePath, extraExclusions),
    evidenceRequirements: (mode) => [...base.evidenceRequirements(mode), ...(extraEvidence[mode] ?? [])],
  };
}

/** @returns {string[]} Skills with built-in policies. */
export function builtInPolicySkills() {
  return [...BUILT_IN_POLICIES.keys()];
}
