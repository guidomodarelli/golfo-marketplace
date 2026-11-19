'use strict';

/**
 * Shared logic for the agent compatibility report of the golfo plugins: status
 * derivation, consistency rules, Markdown rendering and Markdown/JSON sync.
 *
 * The JSON report is the data source; the Markdown report is rendered from it
 * and validated back against it, so both always describe the same skills,
 * statuses and incompatibility IDs.
 */

const AGENT_IDS = ['claude_code', 'codex', 'hermes'];
const SKILL_STATUSES = ['compatible', 'adapted', 'partial', 'incompatible', 'unverified'];
/** Test kinds that prove the feature ran in that agent. */
const EXECUTION_EVIDENCE_KINDS = new Set(['eval', 'real_run']);
/** Path of an audited skill: any plugin of the marketplace, `plugins/<plugin>/skills/<id>/SKILL.md`. */
const SKILL_PATH_PATTERN = /^plugins\/[a-z0-9-]+\/skills\/([a-z0-9-]+)\/SKILL\.md$/;
const MATRIX_HEADING = '## B. Matriz global';
const SKILLS_HEADING = '## C. Análisis por skill';
const ISSUES_HEADING = '## D. Registro de incompatibilidades';
const ACTIONS_HEADING = '## E. Plan de acciones pendientes';
const RENDER_COMMAND = 'pnpm compat:render';

/** Rule shown in the report and applied by {@link deriveAgentStatus}. */
const STATUS_DERIVATION_RULE = [
  'El estado de una skill en un agente se deriva de sus funcionalidades, en este orden:',
  '',
  '1. `unverified` si alguna funcionalidad **obligatoria** está `unverified`.',
  '2. `incompatible` si todas las obligatorias están `disabled` y ninguna funcionalidad (obligatoria u opcional) está `enabled` o `adapted`.',
  '3. `partial` si alguna funcionalidad (obligatoria u opcional) está `disabled`.',
  '4. `adapted` si alguna funcionalidad está `adapted`.',
  '5. `compatible` en otro caso (todas las obligatorias `enabled`).',
  '',
  'Las funcionalidades opcionales `unverified` no cambian el estado global, pero se listan como pendientes de verificar.',
  'Una funcionalidad solo puede estar `enabled` o `adapted` si la respalda al menos una prueba `eval` o `real_run` ejecutada **en ese agente** con resultado `passed`; las pruebas `simulated_eval` (otro agente simulando este), `bats` (scripts) y `static` (inspección) no alcanzan.',
  'Toda funcionalidad `disabled` tiene una entrada en el registro de incompatibilidades con ID `INC-<skill>--<agente>--<funcionalidad>`.',
  '',
  'La **resolución** de cada funcionalidad dice cómo se entrega en ese agente, independientemente de cuánto se verificó: `native` (la misma funcionalidad que el original), `alternative` (un mecanismo equivalente con otra implementación) o `disabled` (sin solución directa ni alternativa viable).',
  'Una funcionalidad `disabled` lista las alternativas investigadas y ninguna es viable; una `alternative` lista al menos una alternativa viable.',
].join('\n');

/**
 * Derives the resolution a feature must declare from its status and adaptation flag.
 *
 * @param {{status: string, adaptation: boolean}} feature Feature of a skill in an agent.
 * @returns {string} `native`, `alternative` or `disabled`.
 */
function deriveResolution(feature) {
  if (feature.status === 'disabled') return 'disabled';
  return feature.adaptation ? 'alternative' : 'native';
}

/**
 * Counts the reclassifications that took a feature out of `disabled`.
 *
 * @param {object} report Parsed compatibility report.
 * @returns {number} Features that were disabled in the previous revision and are not anymore.
 */
function countReclassifiedFromDisabled(report) {
  return report.revision.reclassified
    .filter((reclassification) => reclassification.from === 'disabled' && reclassification.to !== 'disabled')
    .length;
}

/**
 * Derives the status of one skill in one agent from its features.
 *
 * @param {{status: string, required: boolean}[]} features Features of the skill in the agent.
 * @returns {string} One of {@link SKILL_STATUSES}.
 */
function deriveAgentStatus(features) {
  const requiredFeatures = features.filter((feature) => feature.required);
  const isWorking = (feature) => feature.status === 'enabled' || feature.status === 'adapted';
  if (requiredFeatures.some((feature) => feature.status === 'unverified')) return 'unverified';
  if (requiredFeatures.length > 0
    && requiredFeatures.every((feature) => feature.status === 'disabled')
    && !features.some(isWorking)) return 'incompatible';
  if (features.some((feature) => feature.status === 'disabled')) return 'partial';
  if (features.some((feature) => feature.status === 'adapted')) return 'adapted';
  return 'compatible';
}

/**
 * Builds the stable incompatibility ID of a disabled feature.
 *
 * @param {string} skillId Skill identifier.
 * @param {string} agentId Agent identifier.
 * @param {string} featureId Feature identifier.
 * @returns {string} Issue identifier.
 */
function buildIssueId(skillId, agentId, featureId) {
  return `INC-${skillId}--${agentId}--${featureId}`;
}

/**
 * Computes the summary block that the report must declare.
 *
 * @param {object} report Parsed compatibility report.
 * @returns {object} Expected `summary` value.
 */
function computeSummary(report) {
  const byAgent = Object.fromEntries(AGENT_IDS.map((agentId) => [
    agentId, Object.fromEntries(SKILL_STATUSES.map((status) => [status, 0])),
  ]));
  let disabledFeatures = 0;
  let implementedAdaptations = 0;
  let verifiedAdaptations = 0;
  for (const skill of report.skills) {
    for (const agentId of AGENT_IDS) {
      const compatibility = skill.agents[agentId];
      byAgent[agentId][compatibility.status] += 1;
      for (const feature of compatibility.features) {
        if (feature.status === 'disabled') disabledFeatures += 1;
        if (feature.adaptation && feature.status !== 'disabled') implementedAdaptations += 1;
        if (feature.adaptation && feature.status === 'adapted') verifiedAdaptations += 1;
      }
    }
  }
  const criticalPending = report.skills
    .flatMap((skill) => skill.issues)
    .filter((issue) => issue.severity === 'critical' && issue.status === 'pending')
    .map((issue) => issue.id)
    .sort();
  return {
    total_skills: report.skills.length,
    agents: [...AGENT_IDS],
    by_agent: byAgent,
    disabled_features: disabledFeatures,
    adaptations: { implemented: implementedAdaptations, verified: verifiedAdaptations },
    critical_pending: criticalPending,
    reclassified_from_disabled: countReclassifiedFromDisabled(report),
  };
}

/**
 * Applies the consistency rules that a JSON Schema cannot express.
 *
 * @param {object} report Report that already passed schema validation.
 * @param {{skillIdsOnDisk?: string[]}} [options] Skill directories that must all be covered.
 * @returns {string[]} Violations; empty when consistent.
 */
function checkConsistency(report, options = {}) {
  const errors = [];
  const declaredAgentIds = report.agents.map((agent) => agent.id).sort();
  if (JSON.stringify(declaredAgentIds) !== JSON.stringify([...AGENT_IDS].sort())) {
    errors.push(`agents: expected exactly ${AGENT_IDS.join(', ')}, got ${declaredAgentIds.join(', ')}`);
  }

  const skillIds = report.skills.map((skill) => skill.id);
  const duplicatedSkillIds = skillIds.filter((skillId, index) => skillIds.indexOf(skillId) !== index);
  if (duplicatedSkillIds.length) errors.push(`skills: duplicated ids ${[...new Set(duplicatedSkillIds)].join(', ')}`);
  if (options.skillPathsOnDisk) {
    const skillIdsOnDisk = Object.keys(options.skillPathsOnDisk);
    const missingSkills = skillIdsOnDisk.filter((skillId) => !skillIds.includes(skillId));
    const unknownSkills = skillIds.filter((skillId) => !skillIdsOnDisk.includes(skillId));
    if (missingSkills.length) errors.push(`skills: not audited: ${missingSkills.join(', ')}`);
    if (unknownSkills.length) errors.push(`skills: not present on disk: ${unknownSkills.join(', ')}`);
  }

  const seenIssueIds = new Set();
  for (const skill of report.skills) {
    const where = `skill ${skill.id}`;
    const pathOnDisk = options.skillPathsOnDisk?.[skill.id];
    if (pathOnDisk && skill.path !== pathOnDisk) errors.push(`${where}: path must be ${pathOnDisk}`);
    if (!pathOnDisk && SKILL_PATH_PATTERN.exec(skill.path)?.[1] !== skill.id) errors.push(`${where}: path must be plugins/<plugin>/skills/${skill.id}/SKILL.md`);

    const testsById = new Map();
    for (const test of skill.tests) {
      if (testsById.has(test.id)) errors.push(`${where}: duplicated test id ${test.id}`);
      testsById.set(test.id, test);
    }

    const issuesById = new Map();
    for (const issue of skill.issues) {
      if (seenIssueIds.has(issue.id)) errors.push(`${where}: duplicated issue id ${issue.id}`);
      seenIssueIds.add(issue.id);
      issuesById.set(issue.id, issue);
      if (issue.skill !== skill.id) errors.push(`${where}: issue ${issue.id} belongs to skill ${issue.skill}`);
      if (issue.id !== buildIssueId(issue.skill, issue.agent, issue.feature)) {
        errors.push(`${where}: issue ${issue.id} must be ${buildIssueId(issue.skill, issue.agent, issue.feature)}`);
      }
      const owningFeature = skill.agents[issue.agent].features.find((feature) => feature.id === issue.feature);
      if (!owningFeature) errors.push(`${where}: issue ${issue.id} references unknown feature ${issue.feature} for ${issue.agent}`);
      if (issue.status === 'resolved' && owningFeature && owningFeature.status === 'disabled') {
        errors.push(`${where}: issue ${issue.id} is resolved but its feature is still disabled`);
      }
    }

    for (const agentId of AGENT_IDS) {
      const compatibility = skill.agents[agentId];
      const agentWhere = `${where} / ${agentId}`;
      const expectedStatus = deriveAgentStatus(compatibility.features);
      if (compatibility.status !== expectedStatus) {
        errors.push(`${agentWhere}: status is ${compatibility.status} but its features derive ${expectedStatus}`);
      }
      const featureIds = new Set();
      for (const feature of compatibility.features) {
        const featureWhere = `${agentWhere} / ${feature.id}`;
        if (featureIds.has(feature.id)) errors.push(`${featureWhere}: duplicated feature id`);
        featureIds.add(feature.id);
        for (const testId of feature.tests) {
          if (!testsById.has(testId)) errors.push(`${featureWhere}: unknown test ${testId}`);
        }
        if (feature.status === 'adapted' && !feature.adaptation) errors.push(`${featureWhere}: adapted features must set adaptation: true`);
        if (feature.status === 'enabled' && feature.adaptation) errors.push(`${featureWhere}: enabled features run the original implementation; set adaptation: false or status adapted`);
        if (feature.status === 'enabled' || feature.status === 'adapted') {
          const provingTests = feature.tests
            .map((testId) => testsById.get(testId))
            .filter((test) => test && test.agent === agentId && EXECUTION_EVIDENCE_KINDS.has(test.kind) && test.result === 'passed');
          if (!provingTests.length) {
            errors.push(`${featureWhere}: ${feature.status} requires a passed eval or real_run test executed in ${agentId}`);
          }
          if (!feature.evidence.length) errors.push(`${featureWhere}: ${feature.status} requires evidence`);
        }
        if (feature.status === 'disabled') {
          const issueId = buildIssueId(skill.id, agentId, feature.id);
          if (!issuesById.has(issueId)) errors.push(`${featureWhere}: disabled feature needs issue ${issueId}`);
        }
        const expectedResolution = deriveResolution(feature);
        if (feature.resolution !== expectedResolution) {
          errors.push(`${featureWhere}: resolution is ${feature.resolution} but status ${feature.status} with adaptation ${feature.adaptation} means ${expectedResolution}`);
        }
        const viableAlternatives = feature.alternatives_investigated.filter((alternative) => alternative.viable);
        if (feature.resolution === 'disabled' && (!feature.alternatives_investigated.length || viableAlternatives.length)) {
          errors.push(`${featureWhere}: disabled features must list the alternatives investigated, none of them viable`);
        }
        if (feature.resolution === 'alternative' && !viableAlternatives.length) {
          errors.push(`${featureWhere}: alternative resolution needs at least one viable investigated alternative`);
        }
      }
    }
  }

  const seenReclassifications = new Set();
  for (const reclassification of report.revision.reclassified) {
    const key = `${reclassification.skill} / ${reclassification.agent} / ${reclassification.feature}`;
    const where = `revision.reclassified ${key}`;
    if (seenReclassifications.has(key)) errors.push(`${where}: duplicated`);
    seenReclassifications.add(key);
    const skill = report.skills.find((candidate) => candidate.id === reclassification.skill);
    const feature = skill && skill.agents[reclassification.agent].features.find((candidate) => candidate.id === reclassification.feature);
    if (!feature) {
      errors.push(`${where}: unknown feature`);
      continue;
    }
    if (reclassification.from === reclassification.to && feature.resolution === reclassification.resolution) {
      errors.push(`${where}: from and to are equal; only list features that changed`);
    }
    if (feature.status !== reclassification.to) errors.push(`${where}: to is ${reclassification.to} but the feature is ${feature.status}`);
    if (feature.resolution !== reclassification.resolution) errors.push(`${where}: resolution is ${reclassification.resolution} but the feature declares ${feature.resolution}`);
  }

  const expectedSummary = computeSummary(report);
  for (const key of Object.keys(expectedSummary)) {
    if (JSON.stringify(report.summary[key]) !== JSON.stringify(expectedSummary[key])) {
      errors.push(`summary.${key}: declared ${JSON.stringify(report.summary[key])}, computed ${JSON.stringify(expectedSummary[key])}`);
    }
  }

  const priorities = report.pending_actions.map((action) => action.priority);
  if (JSON.stringify(priorities) !== JSON.stringify(priorities.map((_, index) => index + 1))) {
    errors.push('pending_actions: priorities must be 1..N in list order');
  }
  for (const action of report.pending_actions) {
    for (const issueId of action.related_issues) {
      if (!seenIssueIds.has(issueId)) errors.push(`pending_actions ${action.id}: unknown issue ${issueId}`);
    }
  }
  return errors;
}

/**
 * Escapes text for a single Markdown table cell.
 *
 * @param {unknown} text Cell content.
 * @returns {string} Cell-safe text.
 */
function cell(text) {
  const value = Array.isArray(text) ? text.join('; ') : String(text ?? '');
  return (value || '—').replace(/\|/g, '\\|').replace(/\r?\n/g, ' ');
}

/**
 * Renders a Markdown bullet list, or a dash when the list is empty.
 *
 * @param {string[]} items List items.
 * @returns {string} Markdown list.
 */
function bulletList(items) {
  return items.length ? items.map((item) => `- ${item}`).join('\n') : '- —';
}

/**
 * Renders the Markdown report from the JSON report.
 *
 * @param {object} report Compatibility report.
 * @returns {string} Markdown document ending with a newline.
 */
function renderMarkdown(report) {
  const agentsById = Object.fromEntries(report.agents.map((agent) => [agent.id, agent]));
  const allIssues = report.skills.flatMap((skill) => skill.issues);
  const lines = [];
  const push = (...newLines) => lines.push(...newLines);

  push('# Reporte de compatibilidad entre agentes: plugins golfo', '');
  push(`<!-- Generado desde compatibility-report.json con \`${RENDER_COMMAND}\`. No editar a mano: editá el JSON y regenerá. -->`, '');
  push('> Este reporte **describe** la compatibilidad verificada; no es la fuente de verdad para decidir qué ejecutar.',
    '> Cada skill verifica en runtime las herramientas realmente disponibles en la sesión, según [`agent-capabilities.md`](agent-capabilities.md).', '');

  push('## A. Resumen ejecutivo', '');
  push(`- **Fecha de auditoría:** ${report.audit_date} (generado ${report.generated_at}).`);
  push(`- **Total de skills analizadas:** ${report.summary.total_skills}.`);
  push(`- **Funcionalidades deshabilitadas:** ${report.summary.disabled_features}.`);
  push(`- **Adaptaciones implementadas:** ${report.summary.adaptations.implemented}; verificadas: ${report.summary.adaptations.verified}.`);
  push(`- **Problemas críticos pendientes:** ${report.summary.critical_pending.length ? report.summary.critical_pending.map((issueId) => `\`${issueId}\``).join(', ') : 'ninguno'}.`);
  push(`- **Funcionalidades que dejaron de estar deshabilitadas en esta revisión:** ${report.summary.reclassified_from_disabled} (respecto de \`${report.revision.previous_revision}\`).`, '');
  push('### Cambios de esta revisión', '', report.revision.summary, '');
  if (report.revision.reclassified.length) {
    push('| Skill | Agente | Funcionalidad | Antes | Ahora | Resolución | Motivo |', '|---|---|---|---|---|---|---|');
    for (const reclassification of report.revision.reclassified) {
      push(`| \`${reclassification.skill}\` | \`${reclassification.agent}\` | \`${reclassification.feature}\` | \`${reclassification.from}\` | \`${reclassification.to}\` | \`${reclassification.resolution}\` | ${cell(reclassification.reason)} |`);
    }
    push('');
  }
  push('### Agentes evaluados', '', '| Agente | Versión | Comando | Señales de detección |', '|---|---|---|---|');
  for (const agent of report.agents) {
    push(`| ${cell(agent.name)} (\`${agent.id}\`) | ${cell(agent.version)} | \`${cell(agent.version_command)}\` | ${cell(agent.detection_signals)} |`);
  }
  push('', '### Skills por estado y agente', '', `| Estado | ${AGENT_IDS.map((agentId) => `\`${agentId}\``).join(' | ')} |`, `|---|${AGENT_IDS.map(() => '---').join('|')}|`);
  for (const status of SKILL_STATUSES) {
    push(`| \`${status}\` | ${AGENT_IDS.map((agentId) => report.summary.by_agent[agentId][status]).join(' | ')} |`);
  }
  push('', '### Regla de derivación del estado', '', STATUS_DERIVATION_RULE, '');

  push(MATRIX_HEADING, '', `| Skill | ${AGENT_IDS.map((agentId) => `\`${agentId}\``).join(' | ')} |`, `|---|${AGENT_IDS.map(() => '---').join('|')}|`);
  for (const skill of report.skills) {
    push(`| \`${skill.id}\` | ${AGENT_IDS.map((agentId) => `\`${skill.agents[agentId].status}\``).join(' | ')} |`);
  }
  push('');

  push(SKILLS_HEADING, '');
  for (const skill of report.skills) {
    push(`### \`${skill.id}\``, '');
    push('**Identificación**', '');
    push(`- Nombre: ${skill.name}; versión: ${skill.version ?? 'sin versión declarada'}; SKILL.md: \`${skill.path}\`.`);
    push(`- Propósito: ${skill.purpose}`);
    push(`- Funcionalidades principales: ${skill.main_features.join('; ')}.`);
    push(`- Agentes soportados declarados: ${skill.declared_agents ? skill.declared_agents.map((agentId) => `\`${agentId}\``).join(', ') : 'no declara'}.`, '');
    push('**Dependencias**', '');
    if (skill.dependencies.length) {
      push('| Dependencia | Tipo | Obligatoria | Agentes que la tienen |', '|---|---|---|---|');
      for (const dependency of skill.dependencies) {
        push(`| ${cell(dependency.name)} | ${dependency.kind} | ${dependency.required ? 'sí' : 'no'} | ${cell(dependency.agents.map((agentId) => `\`${agentId}\``))} |`);
      }
    } else {
      push('Sin dependencias específicas de agente detectadas por inspección.');
    }
    push('', '**Compatibilidad por agente**', '');
    for (const agentId of AGENT_IDS) {
      const compatibility = skill.agents[agentId];
      push(`#### ${skill.id} / \`${agentId}\`: \`${compatibility.status}\``, '');
      push(compatibility.summary, '');
      push(`- Capacidades faltantes: ${compatibility.missing_capabilities.length ? compatibility.missing_capabilities.join('; ') : 'ninguna'}.`);
      push(`- Alternativas investigadas: ${compatibility.alternatives_investigated.length ? compatibility.alternatives_investigated.join('; ') : 'ninguna'}.`, '');
      push('| Funcionalidad | Obligatoria | Estado | Resolución | Implementación | Fallback | Justificación | Evidencia |', '|---|---|---|---|---|---|---|---|');
      for (const feature of compatibility.features) {
        const evidence = [...feature.evidence, ...feature.tests.map((testId) => `prueba \`${testId}\``)];
        push(`| \`${feature.id}\` | ${feature.required ? 'sí' : 'no'} | \`${feature.status}\` | \`${feature.resolution}\` | ${cell(feature.implementation)} | ${cell(feature.fallback)} | ${cell(feature.reason)} | ${cell(evidence)} |`);
      }
      push('');
      const featuresWithAlternatives = compatibility.features.filter((feature) => feature.alternatives_investigated.length);
      if (featuresWithAlternatives.length) {
        push('| Funcionalidad | Alternativa investigada | Fuente | Viable | Motivo |', '|---|---|---|---|---|');
        for (const feature of featuresWithAlternatives) {
          for (const alternative of feature.alternatives_investigated) {
            push(`| \`${feature.id}\` | ${cell(alternative.name)} | ${cell(alternative.source)} | ${alternative.viable ? 'sí' : 'no'} | ${cell(alternative.reason)} |`);
          }
        }
        push('');
      }
    }
    push('**Implementación**', '');
    push(`- Adaptaciones: ${skill.implementation.adaptations.length ? skill.implementation.adaptations.join('; ') : 'ninguna'}.`);
    push(`- Archivos modificados: ${skill.implementation.files_modified.length ? skill.implementation.files_modified.map((filePath) => `\`${filePath}\``).join(', ') : 'ninguno'}.`);
    push(`- Fallback: ${skill.implementation.fallback || 'ninguno'}.`);
    push(`- Cambios de comportamiento respecto del original: ${skill.implementation.behavior_changes || 'ninguno'}.`, '');
    push('**Verificación**', '');
    if (skill.tests.length) {
      push('| Prueba | Agente | Tipo | Comando | Resultado | Evidencia |', '|---|---|---|---|---|---|');
      for (const test of skill.tests) {
        push(`| \`${test.id}\` | \`${test.agent}\` | ${test.kind} | \`${cell(test.command)}\` | \`${test.result}\` | ${cell(test.evidence)} |`);
      }
    } else {
      push('Sin pruebas ejecutadas en esta auditoría.');
    }
    push('', 'Pendiente de verificar:', '', bulletList(skill.pending_verification), '');
  }

  push(ISSUES_HEADING, '');
  if (allIssues.length) {
    push('| ID | Skill | Agente | Funcionalidad | Dependencia faltante | Motivo técnico | Alternativas investigadas | Solución o bloqueo | Severidad | Estado |', '|---|---|---|---|---|---|---|---|---|---|');
    for (const issue of allIssues) {
      push(`| \`${issue.id}\` | \`${issue.skill}\` | \`${issue.agent}\` | \`${issue.feature}\` | ${cell(issue.missing_dependency)} | ${cell(issue.technical_reason)} | ${cell(issue.alternatives_investigated)} | ${cell(issue.resolution)} | \`${issue.severity}\` | \`${issue.status}\` |`);
    }
  } else {
    push('Sin incompatibilidades registradas.');
  }
  push('');

  push(ACTIONS_HEADING, '');
  if (report.pending_actions.length) {
    push('| Prioridad | ID | Impacto | Acción recomendada | Criterio de resolución | Incompatibilidades |', '|---|---|---|---|---|---|');
    for (const action of report.pending_actions) {
      push(`| ${action.priority} | \`${action.id}\` | \`${action.impact}\` | ${cell(action.action)} | ${cell(action.done_when)} | ${cell(action.related_issues.map((issueId) => `\`${issueId}\``))} |`);
    }
  } else {
    push('Sin acciones pendientes.');
  }
  return `${lines.join('\n')}\n`;
}

/**
 * Returns the lines of one `## ` section of a Markdown document.
 *
 * @param {string[]} lines Document lines.
 * @param {string} heading Exact section heading.
 * @returns {string[]|null} Section lines without the heading, or null when missing.
 */
function sectionLines(lines, heading) {
  const start = lines.indexOf(heading);
  if (start === -1) return null;
  const end = lines.findIndex((line, index) => index > start && line.startsWith('## '));
  return lines.slice(start + 1, end === -1 ? lines.length : end);
}

/**
 * Extracts the facts the sync check compares from a Markdown report.
 *
 * @param {string} markdown Markdown report.
 * @returns {{matrix: Map<string, string[]>|null, skillSections: Map<string, Map<string, string>>|null, issueIds: string[]|null}} Parsed facts.
 */
function parseMarkdown(markdown) {
  const lines = markdown.split(/\r?\n/);
  const matrixLines = sectionLines(lines, MATRIX_HEADING);
  const skillLines = sectionLines(lines, SKILLS_HEADING);
  const issueLines = sectionLines(lines, ISSUES_HEADING);
  const backtickCells = (line) => line.split('|').slice(1, -1).map((part) => part.trim().replace(/^`|`$/g, ''));

  let matrix = null;
  if (matrixLines) {
    matrix = new Map();
    for (const line of matrixLines.filter((row) => /^\| `[a-z0-9-]+` \|/.test(row))) {
      const [skillId, ...statuses] = backtickCells(line);
      matrix.set(skillId, statuses);
    }
  }
  let skillSections = null;
  if (skillLines) {
    skillSections = new Map();
    for (const line of skillLines) {
      const headingMatch = /^#### ([a-z0-9-]+) \/ `([a-z_]+)`: `([a-z]+)`$/.exec(line);
      if (headingMatch) {
        const [, skillId, agentId, status] = headingMatch;
        if (!skillSections.has(skillId)) skillSections.set(skillId, new Map());
        skillSections.get(skillId).set(agentId, status);
      }
    }
  }
  const issueIds = issueLines
    ? issueLines.filter((row) => /^\| `INC-/.test(row)).map((row) => backtickCells(row)[0])
    : null;
  return { matrix, skillSections, issueIds };
}

/**
 * Checks that a Markdown report describes the same skills, statuses and
 * incompatibility IDs as the JSON report, and that it matches the rendering.
 *
 * @param {object} report Compatibility report.
 * @param {string} markdown Markdown report.
 * @returns {string[]} Violations; empty when in sync.
 */
function checkMarkdownSync(report, markdown) {
  const errors = [];
  const { matrix, skillSections, issueIds } = parseMarkdown(markdown);
  if (!matrix) errors.push(`markdown: missing section '${MATRIX_HEADING}'`);
  if (!skillSections) errors.push(`markdown: missing section '${SKILLS_HEADING}'`);
  if (!issueIds) errors.push(`markdown: missing section '${ISSUES_HEADING}'`);
  if (errors.length) return errors;

  const jsonSkillIds = report.skills.map((skill) => skill.id);
  const compareLists = (label, expected, actual) => {
    const missing = expected.filter((item) => !actual.includes(item));
    const extra = actual.filter((item) => !expected.includes(item));
    if (missing.length) errors.push(`markdown ${label}: missing ${missing.join(', ')}`);
    if (extra.length) errors.push(`markdown ${label}: not in JSON ${extra.join(', ')}`);
  };
  compareLists('matrix skills', jsonSkillIds, [...matrix.keys()]);
  compareLists('skill sections', jsonSkillIds, [...skillSections.keys()]);
  compareLists('incompatibility IDs', report.skills.flatMap((skill) => skill.issues.map((issue) => issue.id)), issueIds);

  for (const skill of report.skills) {
    const expectedStatuses = AGENT_IDS.map((agentId) => skill.agents[agentId].status);
    const matrixStatuses = matrix.get(skill.id);
    if (matrixStatuses && JSON.stringify(matrixStatuses) !== JSON.stringify(expectedStatuses)) {
      errors.push(`markdown matrix ${skill.id}: ${matrixStatuses.join('/')} but JSON says ${expectedStatuses.join('/')}`);
    }
    const sectionStatuses = skillSections.get(skill.id);
    for (const agentId of AGENT_IDS) {
      if (sectionStatuses && sectionStatuses.get(agentId) !== skill.agents[agentId].status) {
        errors.push(`markdown section ${skill.id} / ${agentId}: ${sectionStatuses.get(agentId) ?? 'missing'} but JSON says ${skill.agents[agentId].status}`);
      }
    }
  }
  if (!errors.length && markdown.replace(/\r\n/g, '\n') !== renderMarkdown(report)) {
    errors.push(`markdown: content differs from the JSON rendering; run ${RENDER_COMMAND}`);
  }
  return errors;
}

module.exports = {
  AGENT_IDS,
  RENDER_COMMAND,
  STATUS_DERIVATION_RULE,
  buildIssueId,
  checkConsistency,
  checkMarkdownSync,
  computeSummary,
  deriveAgentStatus,
  deriveResolution,
  renderMarkdown,
};
