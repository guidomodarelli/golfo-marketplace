/**
 * Lifecycle of an execution: `begin` snapshots the unit inputs once the code
 * is final, `evidence` attaches verifications (commands are executed and
 * witnessed by the tool), and `record` accredits the run only if the inputs
 * are still the snapshotted ones and the policy's evidence is complete.
 * Anything short of that is stored as partial or blocked, never verified.
 */
import { spawnSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';

import { EVIDENCE_COMMAND_TIMEOUT_MS, EVIDENCE_KINDS, EVIDENCE_OUTCOMES, EXECUTION_RESULTS, EXIT_CODES, SCHEMA_VERSION } from '../constants.mjs';
import { diffInputs } from '../impact/input-diff.mjs';
import { missingEvidence } from '../policies/base-policy.mjs';
import { CoverageError, sanitizeText, sha256, usageError } from '../support.mjs';

/**
 * @returns {string} Sortable unique run id.
 */
function createRunId() {
  return `${new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d+Z$/, 'Z')}-${randomBytes(3).toString('hex')}`;
}

/**
 * @param {any} current Unit inputs.
 * @returns {any} The part of the inputs stored as baseline.
 */
function snapshotOf(current) {
  return {
    analyzer: current.analyzer,
    files: current.files,
    fingerprint: current.fingerprint,
    inputs: current.inputs,
    signals: current.signals,
    unresolved: current.unresolved,
    warnings: current.warnings,
  };
}

/**
 * Starts a run on a unit.
 *
 * @param {any} context Project context.
 * @param {{ unitId: string, skill: string, mode: string, forceFull?: boolean }} options
 */
export function beginRun(context, { unitId, skill, mode, forceFull = false }) {
  const policy = context.policy(skill);
  if (!policy.modes.includes(mode)) throw usageError(`begin: ${skill} supports modes ${policy.modes.join(', ')}, not ${mode}`);
  const unit = context.registry.loadUnit(unitId);
  const evaluation = context.evaluate(unit, skill, { forceFull });
  if (!evaluation.definition.available) {
    throw new CoverageError(`begin: the definition of ${skill} is not installed next to the tool nor in a golfo plugin beside it; install the plugin that carries ${skill} or set GOLFO_COVERAGE_SKILLS_DIR to its skills directory`);
  }
  for (const { expired, run } of context.registry.listPendingRuns()) if (expired) context.registry.deletePendingRun(run.runId);

  const run = {
    basedOn: evaluation.record?.verified ? { fingerprint: evaluation.record.verified.baseline.fingerprint, recordedAt: evaluation.record.verified.recordedAt } : null,
    definition: { definitionFiles: evaluation.definition.files, definitionHash: evaluation.definition.hash, version: evaluation.definition.version },
    evidence: [],
    head: context.git.head() ?? null,
    mode,
    plan: {
      decision: evaluation.decision.decision,
      reasons: evaluation.decision.reasons,
      relevantChanges: evaluation.decision.relevantChanges.map((change) => ({ change: change.change, key: change.key, reason: change.reason })),
      suggestedScope: evaluation.decision.suggestedScope,
    },
    runId: createRunId(),
    schemaVersion: SCHEMA_VERSION,
    skill,
    snapshot: snapshotOf(evaluation.current),
    startedAt: new Date().toISOString(),
    unitId,
  };
  context.registry.savePendingRun(run);
  return { coverage: evaluation.coverage, decision: evaluation.decision, run };
}

/**
 * Attaches one piece of evidence to a pending run.
 *
 * With `exec`, the command runs in the project root and the tool stores its
 * exit code, duration and a hash of its output (never the output itself).
 * Without it, the evidence is attested by the agent: kind, outcome and a
 * sanitized summary, plus the measurement fields when they apply.
 *
 * @param {any} context
 * @param {any} options
 */
export function addEvidence(context, options) {
  if (!EVIDENCE_KINDS.includes(options.kind)) throw usageError(`evidence: --kind must be one of ${EVIDENCE_KINDS.join(', ')}`);
  context.registry.loadPendingRun(options.runId);
  let evidence;
  if (options.exec) {
    const startedAt = Date.now();
    const execution = spawnSync(options.exec, {
      cwd: context.projectRoot,
      encoding: 'utf8',
      maxBuffer: 256 * 1024 * 1024,
      shell: true,
      timeout: options.timeoutMs ?? EVIDENCE_COMMAND_TIMEOUT_MS,
    });
    const output = `${execution.stdout ?? ''}${execution.stderr ?? ''}`;
    const timedOut = execution.error?.code === 'ETIMEDOUT' || execution.signal === 'SIGTERM';
    evidence = {
      command: sanitizeText(options.exec),
      durationMs: Date.now() - startedAt,
      exitCode: execution.status,
      kind: options.kind,
      outcome: execution.status === 0 && !timedOut ? 'pass' : 'fail',
      outputSha256: sha256(output),
      recordedAt: new Date().toISOString(),
      source: 'witnessed',
      summary: sanitizeText(options.summary ?? (timedOut ? 'command timed out' : `exit code ${execution.status}`)),
    };
    evidence.output = output;
  } else {
    if (!EVIDENCE_OUTCOMES.includes(options.outcome)) throw usageError(`evidence: attested evidence needs --outcome ${EVIDENCE_OUTCOMES.join('|')}`);
    if (!options.summary) throw usageError('evidence: attested evidence needs --summary describing what was verified and how');
    evidence = {
      kind: options.kind,
      outcome: options.outcome,
      recordedAt: new Date().toISOString(),
      source: 'attested',
      summary: sanitizeText(options.summary),
    };
    for (const field of ['tool', 'metric', 'before', 'after', 'conditions', 'reference', 'artifact']) {
      if (options[field] !== undefined) evidence[field] = sanitizeText(options[field]);
    }
    if (options.baselineKind !== undefined) {
      if (!['previous-revision', 'new-flow'].includes(options.baselineKind)) throw usageError('evidence: --baseline-kind must be previous-revision or new-flow');
      evidence.baselineKind = options.baselineKind;
    }
  }
  const { output, ...stored } = evidence;
  context.registry.updatePendingRun(options.runId, (run) => ({ ...run, evidence: [...run.evidence, stored] }));
  return { evidence: stored, output };
}

/**
 * Accredits a pending run and writes the coverage record.
 *
 * @param {any} context
 * @param {{ runId: string, result: string, limitations?: string[], pendingChecks?: string[], summary?: string, report?: string }} options
 */
export function recordRun(context, options) {
  if (!EXECUTION_RESULTS.includes(options.result)) throw usageError(`record: --result must be one of ${EXECUTION_RESULTS.join(', ')}`);
  const run = context.registry.loadPendingRun(options.runId);
  const limitations = (options.limitations ?? []).map(sanitizeText).filter(Boolean);
  const pendingChecks = (options.pendingChecks ?? []).map(sanitizeText).filter(Boolean);
  const summary = options.summary ? sanitizeText(options.summary) : undefined;
  if (options.result === 'partial' && !pendingChecks.length && !limitations.length) throw usageError('record: a partial result needs --pending or --limitation saying what is missing');
  if (options.result === 'blocked' && !limitations.length) throw usageError('record: a blocked result needs --limitation with the real blocker');
  if (options.result === 'not-applicable' && !summary) throw usageError('record: not-applicable needs --summary with the reason');

  context.refresh();
  const unit = context.registry.loadUnit(run.unitId);
  const policy = context.policy(run.skill);
  const definition = context.definition(run.skill);
  const current = context.inputs(unit, run.skill);

  if (current.fingerprint !== run.snapshot.fingerprint) {
    const changes = diffInputs(run.snapshot.inputs, current.inputs).map((change) => `${change.change} ${change.key}`);
    throw new CoverageError(
      `record: the unit inputs changed after begin (${changes.slice(0, 8).join('; ')}${changes.length > 8 ? '; …' : ''}). Nothing was recorded: run \`abort --run ${run.runId}\`, then \`begin\` again on the final code and repeat the verifications`,
      { details: changes, exitCode: EXIT_CODES.refused },
    );
  }
  if (definition.hash !== run.definition.definitionHash) {
    throw new CoverageError(`record: the definition of ${run.skill} changed during the run; nothing was recorded. Abort and run the skill again`, { exitCode: EXIT_CODES.refused });
  }

  let result = options.result;
  const downgradeReasons = [];
  if (result === 'verified') {
    downgradeReasons.push(...missingEvidence(run.evidence, policy.evidenceRequirements(run.mode), policy.validateEvidence));
    const previous = context.registry.loadRecord(run.skill, run.unitId);
    if (run.mode !== 'full' && !previous?.verified) downgradeReasons.push(`a ${run.mode} run only covers part of the unit and there is no previous verified coverage: run a full analysis`);
    if (pendingChecks.length) downgradeReasons.push('pending checks were declared');
    if (current.truncated) downgradeReasons.push('the input closure was truncated');
    if (downgradeReasons.length) result = 'partial';
  }

  const dirty = context.git.dirtyPaths({ refresh: true });
  const attempt = {
    baseline: {
      analyzer: current.analyzer,
      branch: context.git.branch() ?? null,
      commit: context.git.head() ?? null,
      files: current.files,
      fingerprint: current.fingerprint,
      inputs: current.inputs,
      ...(policy.tracksLoadSignals ? { signals: current.signals } : {}),
      uncommittedFiles: Object.keys(current.files).filter((filePath) => dirty.has(filePath)).sort(),
    },
    evidence: run.evidence,
    limitations,
    mode: run.mode,
    pendingChecks: [...pendingChecks, ...downgradeReasons.filter((reason) => reason !== 'pending checks were declared')],
    recordedAt: new Date().toISOString(),
    result,
    runId: run.runId,
    scope: { decision: run.plan.decision, reasons: run.plan.reasons, relevantChangesAtBegin: run.plan.relevantChanges, suggestedScope: run.plan.suggestedScope },
    skill: { definitionFiles: definition.files, definitionHash: definition.hash, name: run.skill, version: definition.version },
    ...(summary ? { summary } : {}),
  };
  const { inputs, files, signals, ...baselineSummary } = attempt.baseline;
  attempt.report = context.registry.saveRunReport(run.runId, {
    ...attempt,
    baseline: { ...baselineSummary, fileCount: Object.keys(files).length, inputCount: Object.keys(inputs).length },
    externalReport: options.report ? sanitizeText(options.report) : undefined,
    schemaVersion: SCHEMA_VERSION,
    startedAt: run.startedAt,
    unitId: run.unitId,
  });

  context.registry.updateRecord(run.skill, run.unitId, (existing) => {
    const record = existing ?? { latest: null, schemaVersion: SCHEMA_VERSION, skill: run.skill, unitId: run.unitId, verified: null };
    return result === 'verified' ? { ...record, latest: null, verified: attempt } : { ...record, latest: attempt };
  });
  context.registry.deletePendingRun(run.runId);
  return { attempt, downgraded: result !== options.result, downgradeReasons, result };
}

/**
 * Discards a pending run without recording anything.
 *
 * @param {any} context
 * @param {string} runId
 */
export function abortRun(context, runId) {
  context.registry.loadPendingRun(runId);
  context.registry.deletePendingRun(runId);
}
