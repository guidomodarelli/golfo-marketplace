import { BUSINESS_STATE_KIND, CHANGE_STATUS, CHANGE_STATUSES, CONFIDENCE, KIND_LABELS } from './flow-graph-constants.mjs';

const MERMAID_INDENT = '  ';
const VERIFIED_ARROW = '-->';
const INFERRED_ARROW = '-.->';
const UNGROUPED = Symbol('ungrouped');

/** Colors of each change status; unchanged elements keep the default theme of the viewer. */
const CHANGE_CLASS_STYLES = {
  [CHANGE_STATUS.added]: 'fill:#dcfce7,stroke:#15803d,color:#14532d',
  [CHANGE_STATUS.modified]: 'fill:#fef3c7,stroke:#b45309,color:#78350f',
  [CHANGE_STATUS.removed]: 'fill:#fee2e2,stroke:#b91c1c,color:#7f1d1d,stroke-dasharray:4 3',
};

const CHANGE_MARKERS = {
  [CHANGE_STATUS.added]: '+ ',
  [CHANGE_STATUS.modified]: '~ ',
  [CHANGE_STATUS.removed]: '- ',
  [CHANGE_STATUS.unchanged]: '',
};

/**
 * Renders the model as Markdown with Mermaid diagrams, ready to paste into a pull request
 * description, where GitHub draws them.
 *
 * @param {object} model A valid flow graph model.
 * @returns {string} Markdown document.
 */
export function renderMermaidMarkdown(model) {
  const sections = [
    `## Flujo de cambios — ${model.pullRequest.title}`,
    '',
    'Verde: agregado · Ámbar: modificado · Rojo punteado: eliminado · Flecha punteada: relación inferida',
    '',
    fence(renderChangeFlowchart(model)),
  ];
  if (model.businessFlow) {
    sections.push('', '## Flujo de negocio', '', fence(renderBusinessStateDiagram(model.businessFlow)));
  }
  return `${sections.join('\n')}\n`;
}

/**
 * @param {object} model A valid flow graph model.
 * @returns {string} Mermaid `flowchart` source of the change graph.
 */
export function renderChangeFlowchart(model) {
  const lines = ['flowchart LR'];
  const nodesByGroup = Map.groupBy(model.nodes, (node) => node.group ?? UNGROUPED);

  for (const group of model.groups ?? []) {
    const groupNodes = nodesByGroup.get(group.id) ?? [];
    if (groupNodes.length === 0) continue;
    lines.push(`${MERMAID_INDENT}subgraph ${toMermaidId(group.id)}["${escapeLabel(group.label)}"]`);
    for (const node of groupNodes) lines.push(`${MERMAID_INDENT.repeat(2)}${renderNode(node)}`);
    lines.push(`${MERMAID_INDENT}end`);
  }
  for (const node of nodesByGroup.get(UNGROUPED) ?? []) lines.push(`${MERMAID_INDENT}${renderNode(node)}`);

  for (const edge of model.edges ?? []) {
    const arrow = edge.confidence === CONFIDENCE.inferred ? INFERRED_ARROW : VERIFIED_ARROW;
    const label = escapeLabel(`${CHANGE_MARKERS[edge.change]}${edge.label ?? KIND_LABELS[edge.kind]}`);
    lines.push(`${MERMAID_INDENT}${toMermaidId(edge.source)} ${arrow}|"${label}"| ${toMermaidId(edge.target)}`);
  }

  lines.push(...renderChangeClasses(model.nodes));
  return lines.join('\n');
}

/**
 * @param {object} businessFlow The `businessFlow` of a valid model.
 * @returns {string} Mermaid `stateDiagram-v2` source.
 */
export function renderBusinessStateDiagram(businessFlow) {
  const lines = ['stateDiagram-v2'];
  for (const state of businessFlow.states) {
    lines.push(`${MERMAID_INDENT}state "${escapeLabel(state.label)}" as ${toMermaidId(state.id)}`);
  }
  for (const state of businessFlow.states) {
    if (state.kind === BUSINESS_STATE_KIND.initial && state.change !== CHANGE_STATUS.removed) {
      lines.push(`${MERMAID_INDENT}[*] --> ${toMermaidId(state.id)}`);
    }
  }
  for (const transition of businessFlow.transitions ?? []) {
    const guard = transition.guard ? ` [${transition.guard}]` : '';
    const inferredNote = transition.confidence === CONFIDENCE.inferred ? ' (inferida)' : '';
    const label = escapeTransitionLabel(`${CHANGE_MARKERS[transition.change]}${transition.trigger}${guard}${inferredNote}`);
    lines.push(`${MERMAID_INDENT}${toMermaidId(transition.source)} --> ${toMermaidId(transition.target)}: ${label}`);
  }
  for (const state of businessFlow.states) {
    if (state.kind === BUSINESS_STATE_KIND.terminal && state.change !== CHANGE_STATUS.removed) {
      lines.push(`${MERMAID_INDENT}${toMermaidId(state.id)} --> [*]`);
    }
  }
  lines.push(...renderChangeClasses(businessFlow.states));
  return lines.join('\n');
}

function renderNode(node) {
  return `${toMermaidId(node.id)}["${escapeLabel(node.label)}"]`;
}

function renderChangeClasses(elements) {
  const lines = [];
  for (const change of CHANGE_STATUSES) {
    const style = CHANGE_CLASS_STYLES[change];
    const elementIds = elements.filter((element) => element.change === change).map((element) => toMermaidId(element.id));
    if (!style || elementIds.length === 0) continue;
    lines.push(`${MERMAID_INDENT}classDef ${change} ${style}`);
    lines.push(`${MERMAID_INDENT}class ${elementIds.join(',')} ${change}`);
  }
  return lines;
}

/** Mermaid reads a hyphen in some identifiers as an arrow, so identifiers use underscores. */
function toMermaidId(identifier) {
  return identifier.replaceAll('-', '_');
}

function escapeLabel(text) {
  return String(text).replaceAll('"', '#quot;').replaceAll('\n', ' ');
}

/** A colon ends a transition label in a state diagram. */
function escapeTransitionLabel(text) {
  return escapeLabel(text).replaceAll(':', '#colon;');
}

function fence(source) {
  return `\`\`\`mermaid\n${source}\n\`\`\``;
}
