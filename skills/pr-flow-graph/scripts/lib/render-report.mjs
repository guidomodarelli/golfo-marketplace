import { CHANGE_STATUS, CHECK_ID, CHECK_STATUS, CONFIDENCE, KIND_LABELS } from './flow-graph-constants.mjs';

const CHECK_STATUS_MARKS = {
  [CHECK_STATUS.passed]: '✓',
  [CHECK_STATUS.skipped]: '–',
  [CHECK_STATUS.warning]: '!',
};
const MODEL_ID_PATTERN = /<script type="application\/json" id="flow-graph-model">(.*?)<\/script>/s;

/**
 * @typedef {object} Check
 * @property {string} id One of `CHECK_ID`.
 * @property {string} label What was checked, for a reader of the graph.
 * @property {'passed' | 'skipped' | 'warning'} status Outcome; a failed check never gets here, because it stops the render.
 * @property {string} detail What the check covered, or why it did not run.
 */

/**
 * @typedef {object} LeanOutcome
 * @property {boolean} requested Whether a Lean model was passed.
 * @property {boolean} included Whether it passed the gate and is shown.
 * @property {string} detail One line on the outcome.
 */

/**
 * Lists what `render` verified before writing the graph. The page and the report show it, so a
 * reader knows which claims were checked against the code and which were not.
 *
 * @param {object} input
 * @param {object} input.model A valid flow graph model.
 * @param {object} [input.repositoryStatistics] Statistics of `verifyModelAgainstRepository`; absent when the repository check was skipped.
 * @param {LeanOutcome} input.leanOutcome Outcome of the Lean gate.
 * @returns {Check[]}
 */
export function buildVerificationChecks({ model, repositoryStatistics, leanOutcome }) {
  const skippedDetail = 'No se comprobó: se generó con --skip-repo-check.';
  const repositoryCheck = (id, label, describe) => ({
    id,
    label,
    status: repositoryStatistics ? CHECK_STATUS.passed : CHECK_STATUS.skipped,
    detail: repositoryStatistics ? describe(repositoryStatistics) : skippedDetail,
  });
  const leanStatus = leanOutcome.included ? CHECK_STATUS.passed : leanOutcome.requested ? CHECK_STATUS.warning : CHECK_STATUS.skipped;

  return [
    {
      id: CHECK_ID.modelShape,
      label: 'Estructura del modelo',
      status: CHECK_STATUS.passed,
      detail: `${model.nodes.length} piezas, ${(model.edges ?? []).length} relaciones, ${model.businessFlow?.states.length ?? 0} estados de negocio.`,
    },
    repositoryCheck(CHECK_ID.evidenceExists, 'Cada evidencia existe en el código', (statistics) =>
      `${statistics.evidenceCount} líneas abiertas entre ${statistics.baseCommit} (antes) y ${statistics.headCommit} (después).`),
    repositoryCheck(CHECK_ID.changeMatchesDiff, 'Cada cambio coincide con el diff', (statistics) =>
      `${statistics.changedElementCount} elementos: lo agregado apunta a una línea agregada y lo eliminado a una eliminada.`),
    repositoryCheck(CHECK_ID.relationshipNamesEndpoint, 'Cada relación verificada nombra a su otro extremo', (statistics) =>
      `${statistics.verifiedRelationshipCount} relaciones leídas en el código.`),
    repositoryCheck(CHECK_ID.diffCoverage, 'Ningún archivo del PR quedó sin explicar', (statistics) =>
      `${statistics.changedFileCount} archivos cambiados: ${statistics.changedFileCount - statistics.outOfScopeFileCount} en el grafo y ${statistics.outOfScopeFileCount} declarados fuera.`),
    { id: CHECK_ID.formalModel, label: 'Modelo formal compilado por Lean', status: leanStatus, detail: leanOutcome.detail },
    {
      id: CHECK_ID.outputs,
      label: 'Las salidas coinciden con el modelo',
      status: CHECK_STATUS.passed,
      detail: 'La página y el Mermaid contienen todas las piezas y relaciones del modelo.',
    },
  ];
}

/**
 * Checks that what was rendered carries the whole model: a page or a diagram that silently lost
 * an element would show a flow nobody validated.
 *
 * @param {object} model The model that was rendered.
 * @param {string} html Content of the generated page.
 * @param {string} mermaidMarkdown Content of the generated Mermaid file.
 * @returns {string[]} Problems found; empty when the outputs match the model.
 */
export function findOutputMismatches(model, html, mermaidMarkdown) {
  const problems = [];
  const embeddedModelSource = MODEL_ID_PATTERN.exec(html)?.[1];
  if (!embeddedModelSource) return ['The generated page does not embed the model.'];
  const embeddedModel = JSON.parse(embeddedModelSource);
  const idsOf = (elements) => (elements ?? []).map((element) => element.id).join(',');
  const lists = [
    ['nodes', model.nodes, embeddedModel.nodes],
    ['edges', model.edges, embeddedModel.edges],
    ['businessFlow.states', model.businessFlow?.states, embeddedModel.businessFlow?.states],
    ['businessFlow.transitions', model.businessFlow?.transitions, embeddedModel.businessFlow?.transitions],
  ];
  for (const [name, expected, actual] of lists) {
    if (idsOf(expected) !== idsOf(actual)) problems.push(`The generated page does not carry the same \`${name}\` as the model.`);
  }
  for (const element of [...model.nodes, ...(model.businessFlow?.states ?? [])]) {
    if (!mermaidMarkdown.includes(element.id.replaceAll('-', '_'))) problems.push(`The Mermaid file does not draw "${element.id}".`);
  }
  return problems;
}

/**
 * Writes the closing report of the skill from the model and the checks, so every figure in it is
 * computed and none depends on whoever ran the skill counting right.
 *
 * @param {object} input
 * @param {object} input.model A valid flow graph model.
 * @param {{ html: string, mermaid: string }} input.paths Paths of the generated files.
 * @param {Check[]} input.checks Result of `buildVerificationChecks`.
 * @param {LeanOutcome} input.leanOutcome Outcome of the Lean gate.
 * @returns {string} Markdown report.
 */
export function renderReport({ model, paths, checks, leanOutcome }) {
  const codeElements = [...model.nodes, ...(model.edges ?? [])];
  const countByChange = (change) => codeElements.filter((element) => element.change === change).length;
  const labelById = new Map([...model.nodes, ...(model.businessFlow?.states ?? [])].map((element) => [element.id, element.label]));
  const describeRelationship = (relationship) =>
    `${labelById.get(relationship.source)} → ${labelById.get(relationship.target)} (${relationship.label ?? relationship.trigger ?? KIND_LABELS[relationship.kind]}): ${relationship.reason}`;
  const inferredRelationships = [...(model.edges ?? []), ...(model.businessFlow?.transitions ?? [])].filter(
    (relationship) => relationship.confidence === CONFIDENCE.inferred,
  );
  const outOfScope = model.outOfScope ?? [];
  const formalModel = leanOutcome.included ? 'incluido' : leanOutcome.requested ? `no incluido: ${leanOutcome.detail}` : 'no pedido';
  const nestedList = (items) => items.map((item) => `\n  - ${item}`).join('');

  const countOf = (change, singular) => {
    const count = countByChange(change);
    return `${count} ${singular}${count === 1 ? '' : 's'}`;
  };
  // A value that is a nested list starts on the next line, so the label is not followed by a space.
  const field = (label, value) => `- **${label}:**${value.startsWith('\n') ? '' : ' '}${value}`;

  const lines = [
    `**Grafo:** ${paths.html}`,
    `**Mermaid para el PR:** ${paths.mermaid}`,
    '',
    field('Cambios', `${countOf(CHANGE_STATUS.added, 'agregado')}, ${countOf(CHANGE_STATUS.modified, 'modificado')}, ${countOf(CHANGE_STATUS.removed, 'eliminado')} (piezas y relaciones)${model.architecture ? ` en ${model.architecture}` : ''}`),
    field('Flujo de negocio', model.businessFlow ? model.businessFlow.summary : 'sin cambios observables'),
    field('Relaciones inferidas', inferredRelationships.length === 0 ? 'ninguna' : `${inferredRelationships.length}, conviene que una persona las confirme${nestedList(inferredRelationships.map(describeRelationship))}`),
    field('Fuera del grafo', outOfScope.length === 0 ? 'nada declarado' : nestedList(outOfScope.map((entry) => `\`${entry.path}\`: ${entry.reason}`))),
    field('Modelo formal', formalModel),
    field('Verificación', nestedList(checks.map((check) => `${CHECK_STATUS_MARKS[check.status]} ${check.label}. ${check.detail}`))),
  ];
  return `${lines.join('\n')}\n`;
}
