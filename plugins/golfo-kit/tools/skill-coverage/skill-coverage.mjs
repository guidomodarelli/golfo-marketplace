#!/usr/bin/env node
/**
 * skill-coverage — traceability and incremental execution of golfo-kit skills.
 *
 * Agent-independent CLI over the coverage registry of the repository that
 * contains the current directory (`.golfo/skill-coverage/`). Run with
 * `help` for usage; the protocol skills follow is documented in
 * `plugins/golfo-kit/references/skill-coverage.md`.
 */
import { parseArgs } from 'node:util';

import { EXIT_CODES } from './lib/constants.mjs';
import { abortRun, addEvidence, beginRun, recordRun } from './lib/evaluation/run-lifecycle.mjs';
import { openProjectContext } from './lib/evaluation/project-context.mjs';
import { discoverUnits, writeDiscoveredUnits } from './lib/discovery/next-app-router.mjs';
import { snapshotPaths, splitInputKey } from './lib/impact/input-diff.mjs';
import { dependencyChain } from './lib/impact/unit-inputs.mjs';
import { describeInputKey } from './lib/policies/base-policy.mjs';
import { buildUnitDefinition } from './lib/persistence/unit-definition.mjs';
import { builtInPolicySkills } from './lib/policies/index.mjs';
import { validateRegistry } from './lib/report/registry-validation.mjs';
import { buildStatus, displayStatus, renderStatus } from './lib/report/status-report.mjs';
import { CoverageError, usageError } from './lib/support.mjs';

const USAGE = `skill-coverage <command> [options]

Registry: .golfo/skill-coverage/ in the repository of the current directory (or --root).

Commands
  init                                   Create the registry layout and default config.
  add-unit --id <id> --kind <ui-flow|api|job|webhook|backend> --module <m> --subflow <s>
           [--page <p>] [--section <s>] --entry <path[:symbol]>... [--route <r>]... [--description <text>]
                                         Create one unit in any repository (initializes the registry);
                                         validated against the schema, never coverage.
  discover [--scope <dir>] [--include-api] [--write]
                                         Propose functional units from Next.js App Router pages
                                         (and API routes); --write saves new ones, never coverage.
  status [--module <m>] [--page <p>] [--unit <id-prefix>] [--skill <s>] [--details]
                                         Coverage tree with aggregated counts per page and section.
  check --unit <id> --skill <s> [--force-full]
                                         Decide skip / incremental / full before running a skill.
  diff --unit <id> --skill <s> [--patch] Relevant changes since the last run, with commits and patch.
  inputs --unit <id> --skill <s> [--why <text>]
                                         Code (files, symbols, packages) the unit depends on;
                                         --why shows how the unit reaches the matching inputs.
  affected (--changed | --paths <p>...) [--skill <s>]
                                         Units whose inputs include changed or given files.
  begin --unit <id> --skill <s> --mode <full|incremental|lightweight> [--force-full]
                                         Snapshot the final code before verifying; prints a run id.
  evidence --run <id> --kind <kind> (--exec "<command>" | --outcome <pass|fail|measured|skipped> --summary "<text>")
           [--tool <t>] [--metric <m>] [--before <v>] [--after <v>] [--conditions <c>]
           [--baseline-kind <previous-revision|new-flow>] [--reference <r>] [--artifact <path>]
                                         Attach a verification. --exec runs and witnesses a command.
  record --run <id> --result <verified|partial|blocked|not-applicable>
         [--limitation <text>]... [--pending <text>]... [--summary <text>] [--report <ref>]
                                         Accredit the run; refuses if the code changed since begin and
                                         downgrades to partial when required evidence is missing.
  abort --run <id>                       Discard a pending run.
  validate [--informative]               Check registry integrity (exit 1 on errors unless informative).

Global options: --root <repo>, --skills-dir <dir>, --json`;

const OPTIONS = {
  after: { type: 'string' },
  artifact: { type: 'string' },
  before: { type: 'string' },
  'baseline-kind': { type: 'string' },
  changed: { type: 'boolean' },
  conditions: { type: 'string' },
  description: { type: 'string' },
  details: { type: 'boolean' },
  entry: { multiple: true, type: 'string' },
  exec: { type: 'string' },
  'force-full': { type: 'boolean' },
  help: { short: 'h', type: 'boolean' },
  id: { type: 'string' },
  'include-api': { type: 'boolean' },
  informative: { type: 'boolean' },
  json: { type: 'boolean' },
  kind: { type: 'string' },
  limitation: { multiple: true, type: 'string' },
  metric: { type: 'string' },
  mode: { type: 'string' },
  module: { multiple: true, type: 'string' },
  outcome: { type: 'string' },
  page: { multiple: true, type: 'string' },
  patch: { type: 'boolean' },
  paths: { multiple: true, type: 'string' },
  pending: { multiple: true, type: 'string' },
  reference: { type: 'string' },
  report: { type: 'string' },
  result: { type: 'string' },
  root: { type: 'string' },
  route: { multiple: true, type: 'string' },
  run: { type: 'string' },
  scope: { type: 'string' },
  section: { type: 'string' },
  skill: { multiple: true, type: 'string' },
  'skills-dir': { type: 'string' },
  subflow: { type: 'string' },
  summary: { type: 'string' },
  'timeout-ms': { type: 'string' },
  tool: { type: 'string' },
  unit: { multiple: true, type: 'string' },
  why: { type: 'string' },
  write: { type: 'boolean' },
};

/**
 * @param {Record<string, any>} values
 * @param {string} name
 * @returns {string}
 */
function requireSingle(values, name) {
  const value = Array.isArray(values[name]) ? values[name] : values[name] === undefined ? [] : [values[name]];
  if (value.length !== 1 || !value[0]) throw usageError(`--${name} is required once`);
  return value[0];
}

/**
 * @param {any} value
 * @param {boolean} asJson
 * @param {() => string} renderText
 */
function output(value, asJson, renderText) {
  process.stdout.write(`${asJson ? JSON.stringify(value, null, 2) : renderText()}\n`);
}

/**
 * @param {any} evaluation Result of `context.evaluate`.
 * @param {any} unit
 * @param {string} skill
 */
function checkPayload(evaluation, unit, skill) {
  const { coverage, decision, current } = evaluation;
  const attempt = coverage.attempt;
  return {
    analyzer: current.analyzer,
    baseline: attempt ? {
      commit: attempt.baseline.commit,
      history: coverage.evaluation?.history,
      mode: attempt.mode,
      recordedAt: attempt.recordedAt,
      result: attempt.result,
      uncommittedFiles: attempt.baseline.uncommittedFiles ?? [],
      version: attempt.skill.version,
    } : null,
    decision: decision.decision,
    definition: { status: coverage.evaluation?.definitionStatus ?? null, version: evaluation.definition.version },
    fileLevelFiles: current.fileLevelFiles,
    freshness: coverage.freshness,
    ignoredChanges: decision.ignoredChanges.map((change) => ({ change: change.change, key: change.key, reason: change.reason })),
    mode: decision.mode,
    reasons: decision.reasons,
    relevantChanges: decision.relevantChanges.map((change) => ({
      change: change.change,
      key: change.key,
      reason: change.reason,
      ...(change.from ? { from: change.from } : {}),
      ...(change.key in current.inputs ? { via: dependencyChain(current.via, change.key).slice(1) } : {}),
    })),
    skill,
    state: coverage.state,
    suggestedScope: decision.suggestedScope,
    unit: unit.id,
    unresolved: current.unresolved,
    warnings: current.warnings,
  };
}

/**
 * @param {ReturnType<typeof checkPayload>} payload
 * @returns {string}
 */
function renderCheck(payload) {
  const lines = [
    `${payload.skill} on ${payload.unit}`,
    `  coverage: ${displayStatus(payload.state, payload.freshness)} (state ${payload.state}, freshness ${payload.freshness})`,
    `  decision: ${payload.decision.toUpperCase()}${payload.mode ? ` (mode ${payload.mode})` : ''}`,
  ];
  for (const reason of payload.reasons) lines.push(`    - ${reason}`);
  if (payload.baseline) {
    const provisional = payload.baseline.uncommittedFiles.length ? `, recorded over ${payload.baseline.uncommittedFiles.length} uncommitted file(s)` : '';
    lines.push(`  baseline: ${payload.baseline.result} ${payload.baseline.mode} at ${payload.baseline.commit?.slice(0, 12) ?? 'no commit'} (${payload.baseline.history}) · skill ${payload.baseline.version ?? '?'} · ${payload.baseline.recordedAt}${provisional}`);
  }
  if (payload.relevantChanges.length) {
    lines.push('  relevant changes:');
    for (const change of payload.relevantChanges) {
      lines.push(`    ${change.change}: ${describeInputKey(change.key)} — ${change.reason}`);
      if (change.via?.length > 1) lines.push(`      via ${change.via.map((key) => key.replace(/^(entry|context):/, '$1 ')).join(' ← ')}`);
    }
  }
  if (payload.ignoredChanges.length) {
    lines.push('  ignored changes:');
    for (const change of payload.ignoredChanges) lines.push(`    ${change.change}: ${describeInputKey(change.key)} — ${change.reason}`);
  }
  if (payload.suggestedScope.length) {
    lines.push('  suggested scope:');
    for (const scope of payload.suggestedScope) lines.push(`    - ${scope}`);
  }
  if (Object.keys(payload.fileLevelFiles).length) lines.push(`  limitation: compared as whole files: ${Object.entries(payload.fileLevelFiles).map(([file, reason]) => `${file} (${reason})`).join(', ')}`);
  if (payload.analyzer.startsWith('file-level')) lines.push('  limitation: no Babel parser in the project; impact is computed per file');
  for (const warning of payload.warnings) lines.push(`  warning: ${warning}`);
  for (const unresolved of payload.unresolved) lines.push(`  unresolved import: ${unresolved}`);
  return lines.join('\n');
}

/** Commands that accept positional operands after the command name. */
const COMMANDS_WITH_OPERANDS = new Set(['affected']);

const COMMANDS = {
  init(context, values) {
    context.registry.initialize();
    output({ registry: context.registry.root }, values.json, () => `Registry ready at ${context.registry.root}`);
  },

  'add-unit'(context, values) {
    if (!values.entry?.length) throw usageError('add-unit: pass at least one --entry <path[:symbol]>');
    const unit = buildUnitDefinition({
      description: values.description,
      entries: values.entry,
      id: requireSingle(values, 'id'),
      kind: requireSingle(values, 'kind'),
      module: requireSingle(values, 'module'),
      page: values.page?.length ? requireSingle(values, 'page') : undefined,
      routes: values.route,
      section: values.section,
      subflow: requireSingle(values, 'subflow'),
    }, context.projectRoot);
    context.registry.initialize();
    if (!context.registry.saveUnit(unit)) throw new CoverageError(`add-unit: unit ${unit.id} already exists; adjust units/${unit.id}.json or pick another id`);
    output({ unit }, values.json, () => `Created unit ${unit.id} (${unit.kind}) with ${unit.entries.length} entr${unit.entries.length === 1 ? 'y' : 'ies'}. No coverage was recorded.`);
  },

  discover(context, values) {
    const discovery = discoverUnits(context, { includeApi: values['include-api'], scope: values.scope });
    const written = values.write ? writeDiscoveredUnits(context, discovery) : null;
    output({ ...discovery, written }, values.json, () => {
      const lines = [`${discovery.proposals.length} proposal(s)${values.scope ? ` under ${values.scope}` : ''}`];
      for (const proposal of discovery.proposals) {
        const status = proposal.existingId ? `existing ${proposal.existingId}` : `new (${proposal.confidence})`;
        lines.push(`  ${proposal.id}  [${status}]`, `      ${proposal.entries.filter((entry) => entry.follow !== false).map((entry) => `${entry.path}#${entry.symbol}`).join(', ')} — ${proposal.signals.join('; ')}`);
      }
      for (const relocation of discovery.relocations) lines.push(`  moved: ${relocation.unitId} ${relocation.symbol} ${relocation.from} → ${relocation.to}`);
      for (const error of discovery.errors) lines.push(`  invalid unit: ${error}`);
      for (const skippedUnit of written?.skipped ?? []) lines.push(`  not saved: ${skippedUnit.id} (${skippedUnit.reason})`);
      if (written) lines.push(`Created ${written.created.length} unit(s); updated ${written.relocated.length} moved unit(s); skipped ${written.skipped.length}. No coverage was recorded.`);
      else lines.push('Nothing written: review the proposals and run with --write to save the new ones.');
      return lines.join('\n');
    });
  },

  status(context, values) {
    const status = buildStatus(context, { modules: values.module, pages: values.page, skills: values.skill, units: values.unit });
    output(status, values.json, () => renderStatus(status, { details: values.details }));
  },

  check(context, values) {
    const unit = context.registry.loadUnit(requireSingle(values, 'unit'));
    const skill = requireSingle(values, 'skill');
    const payload = checkPayload(context.evaluate(unit, skill, { forceFull: values['force-full'] }), unit, skill);
    output(payload, values.json, () => renderCheck(payload));
  },

  diff(context, values) {
    const unit = context.registry.loadUnit(requireSingle(values, 'unit'));
    const skill = requireSingle(values, 'skill');
    const evaluation = context.evaluate(unit, skill);
    const payload = checkPayload(evaluation, unit, skill);
    const attempt = evaluation.coverage.attempt;
    const changedPaths = [...new Set([...payload.relevantChanges, ...payload.ignoredChanges].map((change) => splitInputKey(change.key).path).filter(Boolean))].sort();
    const history = payload.baseline?.history;
    const commitsReachable = attempt?.baseline.commit && ['ancestor', 'same'].includes(history);
    payload.commits = commitsReachable ? context.git.commitsTouching(attempt.baseline.commit, changedPaths) : [];
    payload.changedFiles = evaluation.coverage.evaluation?.changedFiles ?? [];
    if (values.patch && attempt?.baseline.commit && history !== 'unreachable') payload.patch = context.git.patchSince(attempt.baseline.commit, changedPaths);
    output(payload, values.json, () => {
      const lines = [renderCheck(payload)];
      if (!attempt) lines.push('  no baseline: nothing to compare (the whole unit is new to this skill)');
      else if (!commitsReachable) lines.push(`  commits: baseline history is ${history}; changes come from content fingerprints only`);
      else lines.push(`  commits since baseline touching changed files: ${payload.commits.length ? '' : 'none (changes are uncommitted)'}`, ...payload.commits.map((commit) => `    ${commit}`));
      if (payload.patch) lines.push('', payload.patch);
      return lines.join('\n');
    });
  },

  inputs(context, values) {
    const unit = context.registry.loadUnit(requireSingle(values, 'unit'));
    const skill = requireSingle(values, 'skill');
    const current = context.inputs(unit, skill);
    if (values.why) {
      const matches = Object.keys(current.inputs).filter((key) => key.includes(values.why)).sort();
      const chains = matches.map((key) => ({ chain: dependencyChain(current.via, key), key }));
      output({ chains, unit: unit.id }, values.json, () => (chains.length
        ? chains.slice(0, 20).map(({ chain }) => chain.map((key, position) => `${'  '.repeat(position)}${position ? '← ' : ''}${key}`).join('\n')).join('\n\n')
        : `${unit.id} does not reach any input matching ${values.why}`));
      return;
    }
    output(current, values.json, () => [
      `${unit.id} for ${skill}: ${Object.keys(current.inputs).length} input(s) in ${Object.keys(current.files).length} file(s) · ${current.analyzer}`,
      ...Object.keys(current.inputs).sort().map((key) => `  ${describeInputKey(key)}`),
      ...current.warnings.map((warning) => `  warning: ${warning}`),
    ].join('\n'));
  },

  affected(context, values, operands) {
    // `--paths a b c` and repeated `--paths` flags both select files.
    const paths = new Set([...(values.paths ?? []), ...operands]);
    if (values.changed) for (const dirty of context.git.dirtyPaths()) paths.add(dirty);
    if (!paths.size) throw usageError('affected: pass --changed or --paths <file>...');
    const skills = values.skill?.length ? values.skill : builtInPolicySkills();
    const { units } = context.registry.loadUnits();
    const affected = [];
    for (const unit of units) {
      for (const skill of skills) {
        const evaluation = context.evaluate(unit, skill);
        // Recorded baselines keep the paths of dependencies that were deleted or
        // whose import no longer resolves, so their units are still selected.
        const recordedBaselines = [evaluation.record?.verified, evaluation.record?.latest].filter(Boolean).map((attempt) => attempt.baseline);
        const unitPaths = new Set([evaluation.current, ...recordedBaselines].flatMap(snapshotPaths));
        const matches = [...unitPaths].filter((filePath) => paths.has(filePath)).sort();
        if (matches.length) {
          affected.push({ decision: evaluation.decision.decision, files: matches, freshness: evaluation.coverage.freshness, skill, state: evaluation.coverage.state, unit: unit.id });
        }
      }
    }
    output({ affected, paths: [...paths].sort() }, values.json, () => (affected.length
      ? affected.map((item) => `${item.unit}  ${item.skill}: ${displayStatus(item.state, item.freshness)} → ${item.decision}  (${item.files.join(', ')})`).join('\n')
      : `No unit includes ${[...paths].join(', ')}. If the files belong to a functionality, create its unit (add-unit, or discover --scope <dir> --write in a Next.js App Router app) or adjust an existing one.`));
  },

  begin(context, values) {
    const { coverage, decision, run } = beginRun(context, {
      forceFull: values['force-full'],
      mode: requireSingle(values, 'mode'),
      skill: requireSingle(values, 'skill'),
      unitId: requireSingle(values, 'unit'),
    });
    const payload = { decision: decision.decision, fingerprint: run.snapshot.fingerprint, mode: run.mode, reasons: decision.reasons, runId: run.runId, state: coverage.state, suggestedScope: decision.suggestedScope };
    output(payload, values.json, () => [
      `run ${run.runId} started: ${run.skill} on ${run.unitId} (${run.mode})`,
      `  snapshot ${run.snapshot.fingerprint.slice(0, 19)}… of ${Object.keys(run.snapshot.inputs).length} input(s); do not edit the unit's code before \`record\``,
      `  plan: ${decision.decision} — ${decision.reasons.join('; ')}`,
    ].join('\n'));
  },

  evidence(context, values) {
    const timeoutMs = values['timeout-ms'] ? Number(values['timeout-ms']) : undefined;
    if (timeoutMs !== undefined && !(timeoutMs > 0)) throw usageError('evidence: --timeout-ms must be a positive number');
    const { evidence, output: commandOutput } = addEvidence(context, {
      after: values.after,
      artifact: values.artifact,
      baselineKind: values['baseline-kind'],
      before: values.before,
      conditions: values.conditions,
      exec: values.exec,
      kind: requireSingle(values, 'kind'),
      metric: values.metric,
      outcome: values.outcome,
      reference: values.reference,
      runId: requireSingle(values, 'run'),
      summary: values.summary,
      timeoutMs,
      tool: values.tool,
    });
    if (commandOutput) process.stderr.write(commandOutput.endsWith('\n') ? commandOutput : `${commandOutput}\n`);
    output(evidence, values.json, () => `${evidence.kind} evidence ${evidence.outcome} (${evidence.source})${evidence.exitCode !== undefined ? `, exit code ${evidence.exitCode}` : ''}`);
    if (evidence.outcome === 'fail') process.exitCode = EXIT_CODES.failure;
  },

  record(context, values) {
    const recorded = recordRun(context, {
      limitations: values.limitation,
      pendingChecks: values.pending,
      report: values.report,
      result: requireSingle(values, 'result'),
      runId: requireSingle(values, 'run'),
      summary: values.summary,
    });
    const payload = { downgraded: recorded.downgraded, downgradeReasons: recorded.downgradeReasons, report: recorded.attempt.report, result: recorded.result, runId: recorded.attempt.runId };
    output(payload, values.json, () => [
      `recorded ${recorded.result} (${recorded.attempt.mode}) at ${recorded.attempt.baseline.commit?.slice(0, 12) ?? 'no commit'}${recorded.attempt.baseline.uncommittedFiles.length ? ` + ${recorded.attempt.baseline.uncommittedFiles.length} uncommitted file(s)` : ''}`,
      ...(recorded.downgraded ? ['  downgraded to partial, not verified:', ...recorded.downgradeReasons.map((reason) => `    - ${reason}`)] : []),
      `  report: ${recorded.attempt.report}`,
    ].join('\n'));
  },

  abort(context, values) {
    const runId = requireSingle(values, 'run');
    abortRun(context, runId);
    output({ aborted: runId }, values.json, () => `run ${runId} discarded; nothing was recorded`);
  },

  validate(context, values) {
    const validation = validateRegistry(context);
    output(validation, values.json, () => [
      `${validation.unitCount} unit(s), ${validation.recordCount} record(s): ${validation.errors.length} error(s), ${validation.warnings.length} warning(s)`,
      ...validation.errors.map((error) => `  error: ${error}`),
      ...validation.warnings.map((warning) => `  warning: ${warning}`),
    ].join('\n'));
    if (validation.errors.length && !values.informative) process.exitCode = EXIT_CODES.failure;
  },
};

/**
 * @param {string[]} argv
 */
export function main(argv) {
  let parsed;
  try {
    parsed = parseArgs({ allowPositionals: true, args: argv, options: OPTIONS, strict: true });
  } catch (error) {
    process.stderr.write(`skill-coverage: ${error.message}\n\n${USAGE}\n`);
    return EXIT_CODES.usage;
  }
  const [command, ...operands] = parsed.positionals;
  if (!command || command === 'help' || parsed.values.help) {
    process.stdout.write(`${USAGE}\n`);
    return command || parsed.values.help ? EXIT_CODES.ok : EXIT_CODES.usage;
  }
  const handler = COMMANDS[command];
  if (!handler) {
    process.stderr.write(`skill-coverage: unknown command ${command}\n\n${USAGE}\n`);
    return EXIT_CODES.usage;
  }
  // Only `affected` takes operands (the files after --paths); anything else would be silently ignored.
  if (operands.length && !COMMANDS_WITH_OPERANDS.has(command)) {
    process.stderr.write(`skill-coverage: ${command} does not take extra arguments: ${operands.join(' ')}\n\n${USAGE}\n`);
    return EXIT_CODES.usage;
  }
  try {
    const context = openProjectContext({ root: parsed.values.root, skillsDirectory: parsed.values['skills-dir'] });
    handler(context, parsed.values, operands);
    return process.exitCode ?? EXIT_CODES.ok;
  } catch (error) {
    if (error instanceof CoverageError) {
      process.stderr.write(`skill-coverage: ${error.message}\n`);
      return error.exitCode;
    }
    process.stderr.write(`skill-coverage: unexpected failure in ${command}: ${error.stack ?? error}\n`);
    return EXIT_CODES.failure;
  }
}

process.exitCode = main(process.argv.slice(2));
