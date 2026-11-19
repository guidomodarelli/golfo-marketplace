/**
 * Coverage evaluation: separates the *result* stored by an execution
 * (verified, partial, blocked, not-applicable) from its *freshness*, which
 * is computed on every read from the current inputs and skill definition
 * and is never written to disk.
 */
import { FRESHNESS, INPUT_KEY_PREFIXES } from '../constants.mjs';
import { diffFiles, diffInputs } from '../impact/input-diff.mjs';
import { missingEvidence } from '../policies/base-policy.mjs';
import { compareVersions } from '../support.mjs';

/** Input key prefixes whose value does not depend on the module analyzer (package versions, unresolved imports). */
const ANALYZER_INDEPENDENT_INPUT_PREFIXES = Object.values(INPUT_KEY_PREFIXES);

/**
 * Keeps the analyzer-independent inputs present in both maps. Each analyzer
 * follows imports at a different granularity, so only keys reached by both
 * closures are comparable; adding or removing an import changes a file,
 * which the file comparison already reports.
 *
 * @param {Record<string, string>} inputs
 * @param {Record<string, string>} otherInputs
 * @returns {Record<string, string>}
 */
function sharedAnalyzerIndependentInputs(inputs, otherInputs) {
  return Object.fromEntries(Object.entries(inputs)
    .filter(([key]) => key in otherInputs && ANALYZER_INDEPENDENT_INPUT_PREFIXES.some((prefix) => key.startsWith(prefix))));
}

/**
 * Compares one stored attempt with the present.
 *
 * @param {{ attempt: any, current: any, definition: any, policy: any, git: any }} input
 */
export function evaluateAttempt({ attempt, current, definition, policy, git }) {
  const baseline = attempt.baseline;
  const reasons = [];
  let codeFreshness;
  let changes = [];
  let relevantChanges = [];
  let ignoredChanges = [];
  let changedFiles = [];

  const analyzerChanged = baseline.analyzer !== current.analyzer;
  changes = analyzerChanged
    ? diffInputs(sharedAnalyzerIndependentInputs(baseline.inputs, current.inputs), sharedAnalyzerIndependentInputs(current.inputs, baseline.inputs))
    : diffInputs(baseline.inputs, current.inputs);
  const context = { currentSignals: current.signals ?? {}, currentImporters: current.importers ?? {}, previousSignals: baseline.signals ?? {}, signalsRecorded: baseline.signals !== undefined };
  for (const change of changes) {
    const classification = policy.classifyChange(change, context);
    const classified = { ...change, reason: classification.reason };
    (classification.relevant ? relevantChanges : ignoredChanges).push(classified);
  }
  changedFiles = diffFiles(baseline.files, current.files);
  if (analyzerChanged) {
    codeFreshness = relevantChanges.length ? FRESHNESS.stale : changedFiles.length ? FRESHNESS.unknown : FRESHNESS.current;
    reasons.push(`recorded with ${baseline.analyzer} and evaluated with ${current.analyzer}: compared file by file`);
    if (changedFiles.length) reasons.push(`files changed and symbol impact cannot be compared: ${changedFiles.join(', ')}`);
  } else {
    codeFreshness = relevantChanges.length ? FRESHNESS.stale : FRESHNESS.current;
  }

  // Evidence requirements can grow after a run (config.skills.<skill>.evidence):
  // a verified attempt stays accredited only while its evidence meets them.
  const evidenceGaps = attempt.result === 'verified'
    ? missingEvidence(attempt.evidence ?? [], policy.evidenceRequirements(attempt.mode), policy.validateEvidence)
    : [];
  if (evidenceGaps.length) reasons.push(`evidence requirements changed: ${evidenceGaps.join('; ')}`);

  let definitionStatus;
  let definitionChangedFiles = [];
  if (!definition.available) {
    definitionStatus = 'unknown';
    reasons.push(`skill ${policy.skill} is not installed next to the tool: its definition cannot be compared`);
  } else if (attempt.skill.definitionHash === definition.hash) {
    definitionStatus = 'same';
  } else {
    const versions = compareVersions(attempt.skill.version, definition.version);
    definitionStatus = versions.majorChanged ? 'major-change' : 'changed';
    const previousFiles = attempt.skill.definitionFiles ?? {};
    definitionChangedFiles = [...new Set([...Object.keys(previousFiles), ...Object.keys(definition.files)])]
      .filter((file) => previousFiles[file] !== definition.files[file]).sort();
    reasons.push(`skill definition changed (${attempt.skill.version ?? '?'} → ${definition.version ?? '?'}): ${definitionChangedFiles.join(', ') || 'content'}`);
  }

  let freshness;
  if (codeFreshness === FRESHNESS.stale || evidenceGaps.length || definitionStatus === 'changed' || definitionStatus === 'major-change') freshness = FRESHNESS.stale;
  else if (codeFreshness === FRESHNESS.unknown || definitionStatus === 'unknown') freshness = FRESHNESS.unknown;
  else freshness = FRESHNESS.current;

  if (current.truncated) {
    freshness = freshness === FRESHNESS.current ? FRESHNESS.unknown : freshness;
    reasons.push('the unit input closure was truncated: coverage cannot be confirmed');
  }

  return {
    changedFiles,
    changes,
    definitionChangedFiles,
    definitionStatus,
    evidenceGaps,
    freshness,
    history: git.relationToHead(baseline.commit),
    ignoredChanges,
    reasons,
    relevantChanges,
  };
}

/**
 * Derives the coverage state of a unit for a skill from its record.
 *
 * The attempt that represents the unit is the newest one whose inputs still
 * match; failing that, the verified one; failing that, the newest one.
 *
 * @param {{ unit: any, record: any, current: any, definition: any, policy: any, git: any }} input
 */
export function deriveCoverage({ unit, record, current, definition, policy, git }) {
  const declared = unit.skills?.[policy.skill];
  if (declared?.applicable === false) {
    return { attempt: null, evaluation: null, freshness: FRESHNESS.current, reasons: [`declared not applicable: ${declared.reason}`], state: 'not-applicable' };
  }
  if (!record) return { attempt: null, evaluation: null, freshness: FRESHNESS.unknown, reasons: ['no previous execution of this skill on the unit'], state: 'unreviewed' };

  const verifiedEvaluation = record.verified ? evaluateAttempt({ attempt: record.verified, current, definition, git, policy }) : null;
  const latestEvaluation = record.latest ? evaluateAttempt({ attempt: record.latest, current, definition, git, policy }) : null;
  const latestIsNewer = record.latest && (!record.verified || Date.parse(record.latest.recordedAt) >= Date.parse(record.verified.recordedAt));

  let attempt;
  let evaluation;
  if (latestIsNewer && (latestEvaluation.freshness === FRESHNESS.current || !(verifiedEvaluation?.freshness === FRESHNESS.current))) {
    attempt = record.latest;
    evaluation = latestEvaluation;
  } else if (record.verified) {
    attempt = record.verified;
    evaluation = verifiedEvaluation;
  } else {
    attempt = record.latest;
    evaluation = latestEvaluation;
  }
  return {
    attempt,
    evaluation,
    freshness: evaluation.freshness,
    reasons: evaluation.reasons,
    state: attempt.result,
    verifiedAttempt: record.verified,
    verifiedEvaluation,
  };
}
