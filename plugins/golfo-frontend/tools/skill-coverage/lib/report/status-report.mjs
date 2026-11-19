/**
 * Project coverage status: evaluates every unit for every skill and renders
 * it as a module → page → section → subflow tree. Aggregated lines count
 * their children, so a page never looks covered while one subflow is
 * pending, and every non-current subflow explains why and what to run next.
 */
import { describeInputKey } from '../policies/base-policy.mjs';
import { builtInPolicySkills } from '../policies/index.mjs';

const MAX_LISTED_CHANGES = 6;
const MAX_LISTED_SCOPE = 4;
const NO_SECTION = '';

/**
 * Short label combining result and freshness.
 *
 * @param {string} state
 * @param {string} freshness
 * @returns {string}
 */
export function displayStatus(state, freshness) {
  if (state === 'unreviewed') return 'UNREVIEWED';
  if (state === 'not-applicable') return freshness === 'stale' ? 'N/A · RE-EVALUATE' : 'N/A';
  if (state === 'unknown') return 'UNKNOWN';
  if (state === 'verified') return freshness.toUpperCase();
  return freshness === 'current' ? state.toUpperCase() : `${state.toUpperCase()} · ${freshness.toUpperCase()}`;
}

/**
 * @param {{ state: string, freshness: string }} status
 * @returns {boolean} Whether nothing is pending for the skill on the unit.
 */
function isSettled(status) {
  return (status.state === 'verified' || status.state === 'not-applicable') && status.freshness === 'current';
}

/**
 * @param {string} text
 * @param {string[]} filters
 * @returns {boolean}
 */
function matchesFilter(text, filters) {
  return !filters.length || filters.some((filter) => (text ?? '').toLowerCase().includes(filter.toLowerCase()));
}

/**
 * Evaluates the coverage of the project.
 *
 * @param {any} context
 * @param {{ skills?: string[], modules?: string[], pages?: string[], units?: string[] }} [options]
 */
export function buildStatus(context, options = {}) {
  const { units, errors } = context.registry.loadUnits();
  const recordedSkills = context.registry.listRecordFiles().map((file) => file.skill);
  const extraSkills = [...Object.keys(context.config.skills ?? {}), ...recordedSkills].sort();
  const skills = options.skills?.length ? options.skills : [...new Set([...builtInPolicySkills(), ...extraSkills])];
  const selected = units.filter((unit) => matchesFilter(unit.hierarchy.module, options.modules ?? [])
    && matchesFilter(unit.hierarchy.page ?? '', options.pages ?? [])
    && (!(options.units ?? []).length || options.units.some((filter) => unit.id === filter || unit.id.startsWith(`${filter}.`))));

  const rows = [];
  for (const unit of selected.sort((left, right) => left.id.localeCompare(right.id))) {
    const row = { hierarchy: unit.hierarchy, id: unit.id, skills: {} };
    for (const skill of skills) {
      try {
        const { coverage, current, decision, policy } = context.evaluate(unit, skill);
        const attempt = coverage.attempt;
        row.skills[skill] = {
          baseline: attempt ? {
            commit: attempt.baseline.commit,
            mode: attempt.mode,
            recordedAt: attempt.recordedAt,
            uncommittedFiles: attempt.baseline.uncommittedFiles ?? [],
            version: attempt.skill.version,
          } : null,
          changes: (coverage.evaluation?.relevantChanges ?? []).map((change) => ({ change: change.change, description: describeInputKey(change.key), key: change.key, reason: change.reason })),
          decision: decision.decision,
          evidence: attempt ? attempt.evidence.map((item) => ({ kind: item.kind, outcome: item.outcome, source: item.source, summary: item.summary })) : [],
          freshness: coverage.freshness,
          history: coverage.evaluation?.history ?? null,
          label: policy.label,
          limitations: attempt?.limitations ?? [],
          pendingChecks: attempt?.pendingChecks ?? [],
          reasons: decision.reasons,
          report: attempt?.report ?? null,
          state: coverage.state,
          suggestedScope: decision.suggestedScope,
          warnings: current.warnings,
        };
      } catch (error) {
        row.skills[skill] = { decision: 'full', freshness: 'unknown', label: skill, reasons: [error.message], state: 'unknown' };
      }
    }
    rows.push(row);
  }

  const summary = {};
  for (const skill of skills) {
    const counts = { blocked: 0, current: 0, 'not-applicable': 0, partial: 0, stale: 0, unknown: 0, unreviewed: 0 };
    for (const row of rows) {
      const status = row.skills[skill];
      if (status.state === 'verified') counts[status.freshness === 'current' ? 'current' : status.freshness === 'stale' ? 'stale' : 'unknown'] += 1;
      else counts[status.state] = (counts[status.state] ?? 0) + 1;
    }
    summary[skill] = { counts, label: rows[0]?.skills[skill]?.label ?? context.policy(skill).label, total: rows.length };
  }

  return {
    errors,
    generatedAt: new Date().toISOString(),
    head: context.git.head() ?? null,
    parser: context.index.parserName,
    project: context.config.project ?? null,
    skills,
    summary,
    units: rows,
  };
}

/**
 * @param {any[]} rows
 * @param {string[]} skills
 * @param {Record<string, any>} summary
 * @returns {string} `UI/UX 2/3 · Performance 0/3` style aggregate.
 */
function aggregateLine(rows, skills, summary) {
  return skills.map((skill) => {
    const settled = rows.filter((row) => isSettled(row.skills[skill])).length;
    return `${summary[skill].label} ${settled}/${rows.length}`;
  }).join(' · ');
}

/**
 * Renders the status as an indented tree.
 *
 * @param {ReturnType<typeof buildStatus>} status
 * @param {{ details?: boolean }} [options]
 * @returns {string}
 */
export function renderStatus(status, options = {}) {
  const lines = [`${status.project ?? 'Project'} — Skill Coverage`, ''];
  if (!status.units.length) lines.push('No functional units match. Create them with `discover --write` or add files under .golfo/skill-coverage/units/.');
  const labelWidth = Math.max(...status.skills.map((skill) => status.summary[skill].label.length)) + 1;
  const modules = new Map();
  for (const row of status.units) {
    const { module, page, section } = row.hierarchy;
    if (!modules.has(module)) modules.set(module, new Map());
    const pages = modules.get(module);
    const pageKey = page ?? '(no page)';
    if (!pages.has(pageKey)) pages.set(pageKey, new Map());
    const sections = pages.get(pageKey);
    const sectionKey = section ?? NO_SECTION;
    if (!sections.has(sectionKey)) sections.set(sectionKey, []);
    sections.get(sectionKey).push(row);
  }

  const pushUnit = (row, indent) => {
    lines.push(`${indent}${row.hierarchy.subflow}  [${row.id}]`);
    for (const skill of status.skills) {
      const unitStatus = row.skills[skill];
      lines.push(`${indent}  ${`${unitStatus.label}:`.padEnd(labelWidth + 1)} ${displayStatus(unitStatus.state, unitStatus.freshness)}`);
      if (!options.details && isSettled(unitStatus)) continue;
      const detailIndent = `${indent}      `;
      const baseline = unitStatus.baseline;
      if (baseline && options.details) {
        const provisional = baseline.uncommittedFiles.length ? ` · recorded over ${baseline.uncommittedFiles.length} uncommitted file(s)` : '';
        lines.push(`${detailIndent}baseline: ${baseline.commit?.slice(0, 12) ?? 'no commit'} · skill ${baseline.version ?? '?'} · ${baseline.mode} · ${baseline.recordedAt}${provisional}`);
      }
      if (unitStatus.state === 'unreviewed') continue;
      for (const change of (unitStatus.changes ?? []).slice(0, MAX_LISTED_CHANGES)) lines.push(`${detailIndent}${change.change}: ${change.description} (${change.reason})`);
      if ((unitStatus.changes ?? []).length > MAX_LISTED_CHANGES) lines.push(`${detailIndent}… ${unitStatus.changes.length - MAX_LISTED_CHANGES} more change(s)`);
      for (const check of unitStatus.pendingChecks ?? []) lines.push(`${detailIndent}pending: ${check}`);
      for (const limitation of unitStatus.limitations ?? []) lines.push(`${detailIndent}limitation: ${limitation}`);
      if (!isSettled(unitStatus)) {
        lines.push(`${detailIndent}next: ${unitStatus.decision}${unitStatus.reasons?.length ? ` — ${unitStatus.reasons[unitStatus.reasons.length - 1]}` : ''}`);
        for (const scope of (unitStatus.suggestedScope ?? []).slice(0, MAX_LISTED_SCOPE)) lines.push(`${detailIndent}  scope: ${scope}`);
      }
      if (options.details && unitStatus.evidence?.length) {
        const witnessed = unitStatus.evidence.filter((item) => item.source === 'witnessed').length;
        lines.push(`${detailIndent}evidence: ${unitStatus.evidence.length} item(s), ${witnessed} witnessed · report ${unitStatus.report}`);
      }
    }
  };

  for (const [module, pages] of modules) {
    const moduleRows = [...pages.values()].flatMap((sections) => [...sections.values()].flat());
    lines.push(`${module}  (${aggregateLine(moduleRows, status.skills, status.summary)})`);
    for (const [page, sections] of pages) {
      const pageRows = [...sections.values()].flat();
      lines.push(`  ${page}  (${aggregateLine(pageRows, status.skills, status.summary)})`);
      for (const [section, rows] of sections) {
        if (section === NO_SECTION) {
          for (const row of rows) pushUnit(row, '    ');
        } else {
          lines.push(`    ${section}  (${aggregateLine(rows, status.skills, status.summary)})`);
          for (const row of rows) pushUnit(row, '      ');
        }
      }
    }
    lines.push('');
  }

  lines.push('Summary');
  for (const skill of status.skills) {
    const { counts, label, total } = status.summary[skill];
    const parts = Object.entries(counts).filter(([, count]) => count > 0).map(([name, count]) => `${count} ${name}`);
    lines.push(`  ${`${label}:`.padEnd(labelWidth + 1)} ${total} unit(s) — ${parts.join(', ') || 'none'}`);
  }
  if (!status.parser) lines.push('', 'Limitation: no Babel parser found in the project; files are compared as a whole (install dependencies for symbol-level impact).');
  if (status.errors.length) lines.push('', 'Invalid units (run `validate`):', ...status.errors.map((error) => `  ${error}`));
  return lines.join('\n');
}
