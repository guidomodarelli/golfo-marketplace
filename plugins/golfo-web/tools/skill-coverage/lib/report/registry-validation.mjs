/**
 * Integrity check of a coverage registry: valid documents, unit entries that
 * still point to existing files and symbols, records that belong to known
 * units and run reports, and abandoned pending runs.
 */
import { FILE_LEVEL_ANALYZER } from '../constants.mjs';

/**
 * @param {any} analysis Module analysis.
 * @param {string} symbol Entry symbol.
 * @returns {string | undefined} Problem description, if the symbol is not there.
 */
function findSymbolProblem(analysis, symbol) {
  if (!symbol || symbol === '*' || analysis.analyzer === FILE_LEVEL_ANALYZER) return undefined;
  const match = /^([^/.~]+)(?:\/(.+)|\.(.+)|(~shell))?$/.exec(symbol);
  const [, name, inner, member, shellOnly] = match;
  const local = analysis.symbols.get(name) ?? analysis.symbols.get(analysis.localExports.get(name));
  if (!local) {
    if (analysis.reExports.has(name) || analysis.exportAllSources.length || analysis.imports.has(analysis.localExports.get(name))) return undefined;
    return `symbol ${name} not found`;
  }
  if (inner && !local.parts.has(`${local.name}/${inner}`)) return `inner function ${name}/${inner} not found`;
  if (shellOnly && local.layout !== 'container') return `${name} has no inner functions: use ${name} instead of ${name}~shell`;
  if (member && local.layout === 'object' && !local.parts.has(`${local.name}.${member}`)) return `member ${name}.${member} not found`;
  return undefined;
}

/**
 * @param {any} context
 * @returns {{ errors: string[], warnings: string[], unitCount: number, recordCount: number }}
 */
export function validateRegistry(context) {
  const errors = [];
  const warnings = [];
  if (!context.registry.exists()) {
    return { errors: [], recordCount: 0, unitCount: 0, warnings: ['no .golfo/skill-coverage registry in this repository (run `init` or `discover --write`)'] };
  }
  const { units, errors: unitErrors } = context.registry.loadUnits();
  errors.push(...unitErrors);
  const unitIds = new Set(units.map((unit) => unit.id));
  if (!context.index.parser) warnings.push('no Babel parser found: entry symbols cannot be checked and impact is computed per file');

  for (const unit of units) {
    for (const [field, entries] of [['entries', unit.entries], ['dependsOn', unit.dependsOn ?? []]]) {
      entries.forEach((entry, position) => {
        const label = `units/${unit.id}.json ${field}[${position}]`;
        if (!context.index.fileExists(entry.path)) {
          errors.push(`${label}: ${entry.path} does not exist (moved? run \`discover\` to find it and keep the unit id)`);
          return;
        }
        const analysis = context.index.analyze(entry.path);
        const problem = analysis && findSymbolProblem(analysis, entry.symbol);
        if (problem) errors.push(`${label}: ${problem} in ${entry.path}`);
      });
    }
  }

  let recordCount = 0;
  for (const { skill, unitId } of context.registry.listRecordFiles()) {
    recordCount += 1;
    let record;
    try {
      record = context.registry.loadRecord(skill, unitId);
    } catch (error) {
      errors.push(error.message);
      continue;
    }
    if (record.skill !== skill || record.unitId !== unitId) errors.push(`records/${skill}/${unitId}.json: declares ${record.skill}/${record.unitId}`);
    if (!unitIds.has(unitId)) errors.push(`records/${skill}/${unitId}.json: unit ${unitId} does not exist (renamed? keep the id stable or move the record)`);
    for (const attempt of [record.verified, record.latest].filter(Boolean)) {
      if (attempt.report && !context.registry.runReportExists(attempt.report)) warnings.push(`records/${skill}/${unitId}.json: run report ${attempt.report} is missing`);
    }
  }

  for (const { expired, run } of context.registry.listPendingRuns()) {
    if (expired) warnings.push(`pending run ${run.runId} (${run.skill} on ${run.unitId}) was never recorded; it is deleted by the next \`begin\``);
  }
  return { errors, recordCount, unitCount: units.length, warnings };
}
