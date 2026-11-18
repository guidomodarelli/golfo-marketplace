import {
  BUSINESS_STATE_KIND,
  BUSINESS_STATE_KINDS,
  CHANGE_STATUS,
  CHANGE_STATUSES,
  CONFIDENCE,
  CONFIDENCE_LEVELS,
  EDGE_KINDS,
  EVIDENCE_SIDES,
  FINDING_SEVERITY,
  FLOW_GRAPH_SCHEMA_VERSION,
  GITHUB_PULL_REQUEST_URL_PATTERN,
  IDENTIFIER_PATTERN,
  NODE_KINDS,
} from './flow-graph-constants.mjs';

/**
 * @typedef {object} Finding
 * @property {'error' | 'warning'} severity Errors block the render; warnings are reported.
 * @property {string} location Path of the element inside the model, e.g. `edges[2].source`.
 * @property {string} message What is wrong and how to fix it.
 */

/**
 * Validates a flow graph model against the contract of `references/flow-graph-schema.md`.
 *
 * The rules exist to keep the graph honest: every element the pull request changed points at the
 * code that proves it, and every relationship the agent deduced says so and says why.
 *
 * @param {unknown} model Parsed content of the model file.
 * @returns {Finding[]} Findings, errors first. Empty when the model is valid.
 */
export function validateFlowGraph(model) {
  const findings = [];
  const report = (severity, location, message) => findings.push({ severity, location, message });
  const error = (location, message) => report(FINDING_SEVERITY.error, location, message);
  const warning = (location, message) => report(FINDING_SEVERITY.warning, location, message);

  if (!isPlainObject(model)) {
    error('(root)', 'The model must be a JSON object.');
    return findings;
  }

  if (model.schemaVersion !== FLOW_GRAPH_SCHEMA_VERSION) {
    error('schemaVersion', `Expected ${FLOW_GRAPH_SCHEMA_VERSION}, received ${JSON.stringify(model.schemaVersion)}.`);
  }

  validatePullRequest(model.pullRequest, error);

  const groupIds = validateGroups(model.groups, error);
  const nodeIds = validateNodes(model.nodes, groupIds, error);
  validateEdges(model.edges, nodeIds, error);
  validateBusinessFlow(model.businessFlow, nodeIds, error, warning);
  validateChangePresence(model, error);
  warnAboutIsolatedNodes(model, warning);

  return findings.sort(compareBySeverity);
}

/**
 * @param {Finding[]} findings Findings of a validation.
 * @returns {boolean} Whether at least one finding blocks the render.
 */
export function hasBlockingFindings(findings) {
  return findings.some((finding) => finding.severity === FINDING_SEVERITY.error);
}

function validatePullRequest(pullRequest, error) {
  if (!isPlainObject(pullRequest)) {
    error('pullRequest', 'Required object with `title`, `baseRef` and `headRef`.');
    return;
  }
  for (const field of ['title', 'baseRef', 'headRef']) {
    if (!isNonEmptyString(pullRequest[field])) {
      error(`pullRequest.${field}`, 'Required non-empty string.');
    }
  }
  if (pullRequest.url !== undefined && !GITHUB_PULL_REQUEST_URL_PATTERN.test(String(pullRequest.url))) {
    error('pullRequest.url', 'Must look like https://github.com/<owner>/<repo>/pull/<number>, or be omitted.');
  }
}

function validateGroups(groups, error) {
  const groupIds = new Set();
  if (groups === undefined) return groupIds;
  if (!Array.isArray(groups)) {
    error('groups', 'Must be an array when present.');
    return groupIds;
  }
  groups.forEach((group, index) => {
    const location = `groups[${index}]`;
    if (!isPlainObject(group)) {
      error(location, 'Must be an object with `id` and `label`.');
      return;
    }
    registerIdentifier(group.id, groupIds, location, error);
    if (!isNonEmptyString(group.label)) error(`${location}.label`, 'Required non-empty string.');
  });
  return groupIds;
}

function validateNodes(nodes, groupIds, error) {
  const nodeIds = new Set();
  if (!Array.isArray(nodes) || nodes.length === 0) {
    error('nodes', 'Required non-empty array.');
    return nodeIds;
  }
  nodes.forEach((node, index) => {
    const location = `nodes[${index}]`;
    if (!isPlainObject(node)) {
      error(location, 'Must be an object.');
      return;
    }
    registerIdentifier(node.id, nodeIds, location, error);
    if (!isNonEmptyString(node.label)) error(`${location}.label`, 'Required non-empty string.');
    requireEnumValue(node.kind, NODE_KINDS, `${location}.kind`, error);
    requireEnumValue(node.change, CHANGE_STATUSES, `${location}.change`, error);
    if (node.group !== undefined && !groupIds.has(node.group)) {
      error(`${location}.group`, `Unknown group ${JSON.stringify(node.group)}; declare it in \`groups\`.`);
    }
    validateEvidence(node, location, error);
  });
  return nodeIds;
}

function validateEdges(edges, nodeIds, error) {
  if (edges === undefined) return;
  if (!Array.isArray(edges)) {
    error('edges', 'Must be an array when present.');
    return;
  }
  const edgeIds = new Set();
  edges.forEach((edge, index) => {
    const location = `edges[${index}]`;
    if (!isPlainObject(edge)) {
      error(location, 'Must be an object.');
      return;
    }
    registerIdentifier(edge.id, edgeIds, location, error);
    requireEnumValue(edge.kind, EDGE_KINDS, `${location}.kind`, error);
    requireEnumValue(edge.change, CHANGE_STATUSES, `${location}.change`, error);
    requireKnownEndpoint(edge.source, nodeIds, `${location}.source`, 'node', error);
    requireKnownEndpoint(edge.target, nodeIds, `${location}.target`, 'node', error);
    validateConfidence(edge, location, error);
    validateEvidence(edge, location, error);
  });
}

function validateBusinessFlow(businessFlow, nodeIds, error, warning) {
  if (businessFlow === undefined) return;
  if (!isPlainObject(businessFlow)) {
    error('businessFlow', 'Must be an object with `states` and `transitions` when present.');
    return;
  }
  const stateIds = new Set();
  const states = Array.isArray(businessFlow.states) ? businessFlow.states : [];
  if (states.length === 0) error('businessFlow.states', 'Required non-empty array.');

  states.forEach((state, index) => {
    const location = `businessFlow.states[${index}]`;
    if (!isPlainObject(state)) {
      error(location, 'Must be an object.');
      return;
    }
    registerIdentifier(state.id, stateIds, location, error);
    if (!isNonEmptyString(state.label)) error(`${location}.label`, 'Required non-empty string.');
    requireEnumValue(state.kind, BUSINESS_STATE_KINDS, `${location}.kind`, error);
    requireEnumValue(state.change, CHANGE_STATUSES, `${location}.change`, error);
    for (const [nodeIndex, nodeId] of (state.nodeIds ?? []).entries()) {
      requireKnownEndpoint(nodeId, nodeIds, `${location}.nodeIds[${nodeIndex}]`, 'node', error);
    }
  });

  const initialStates = states.filter(
    (state) => isPlainObject(state) && state.kind === BUSINESS_STATE_KIND.initial && state.change !== CHANGE_STATUS.removed,
  );
  if (states.length > 0 && initialStates.length !== 1) {
    error('businessFlow.states', `Exactly one state of kind "initial" must exist after the pull request; found ${initialStates.length}.`);
  }

  const transitions = Array.isArray(businessFlow.transitions) ? businessFlow.transitions : [];
  const transitionIds = new Set();
  transitions.forEach((transition, index) => {
    const location = `businessFlow.transitions[${index}]`;
    if (!isPlainObject(transition)) {
      error(location, 'Must be an object.');
      return;
    }
    registerIdentifier(transition.id, transitionIds, location, error);
    if (!isNonEmptyString(transition.trigger)) {
      error(`${location}.trigger`, 'Required: the user action or event that fires the transition.');
    }
    requireEnumValue(transition.change, CHANGE_STATUSES, `${location}.change`, error);
    requireKnownEndpoint(transition.source, stateIds, `${location}.source`, 'business state', error);
    requireKnownEndpoint(transition.target, stateIds, `${location}.target`, 'business state', error);
    validateConfidence(transition, location, error);
    validateEvidence(transition, location, error);
  });

  if (initialStates.length === 1) {
    for (const unreachableId of findUnreachableStates(initialStates[0].id, states, transitions)) {
      warning('businessFlow.states', `State "${unreachableId}" cannot be reached from the initial state; add the missing transition or remove it.`);
    }
  }
}

/** A graph of a pull request with no changed element describes the app, not the pull request. */
function validateChangePresence(model, error) {
  const elements = [
    ...(Array.isArray(model.nodes) ? model.nodes : []),
    ...(Array.isArray(model.edges) ? model.edges : []),
    ...(Array.isArray(model.businessFlow?.states) ? model.businessFlow.states : []),
    ...(Array.isArray(model.businessFlow?.transitions) ? model.businessFlow.transitions : []),
  ];
  const hasChange = elements.some((element) => isPlainObject(element) && element.change !== CHANGE_STATUS.unchanged);
  if (elements.length > 0 && !hasChange) {
    error('nodes', 'No element is marked added, modified or removed, so the graph does not show what the pull request changed.');
  }
}

function warnAboutIsolatedNodes(model, warning) {
  if (!Array.isArray(model.nodes) || !Array.isArray(model.edges)) return;
  const connectedIds = new Set(model.edges.flatMap((edge) => (isPlainObject(edge) ? [edge.source, edge.target] : [])));
  model.nodes.forEach((node, index) => {
    if (isPlainObject(node) && !connectedIds.has(node.id)) {
      warning(`nodes[${index}]`, `Node "${node.id}" has no edges; connect it to the flow or remove it.`);
    }
  });
}

/**
 * A changed element without evidence is a claim nobody can check, and a verified relationship
 * without evidence is not verified.
 */
function validateEvidence(element, location, error) {
  const evidence = element.evidence ?? [];
  if (!Array.isArray(evidence)) {
    error(`${location}.evidence`, 'Must be an array of `{ path, line }`.');
    return;
  }
  const isChanged = element.change !== CHANGE_STATUS.unchanged;
  const isVerifiedRelationship = element.confidence === CONFIDENCE.verified;
  if (evidence.length === 0 && (isChanged || isVerifiedRelationship)) {
    const reason = isChanged ? `it is marked "${element.change}"` : 'it is marked "verified"';
    error(`${location}.evidence`, `At least one \`{ path, line }\` is required because ${reason}.`);
  }
  evidence.forEach((item, index) => {
    const itemLocation = `${location}.evidence[${index}]`;
    if (!isPlainObject(item)) {
      error(itemLocation, 'Must be an object with `path` and `line`.');
      return;
    }
    if (!isNonEmptyString(item.path) || /^([a-zA-Z]:)?[\\/]/.test(item.path)) {
      error(`${itemLocation}.path`, 'Required path relative to the repository root, with forward slashes.');
    }
    if (!Number.isInteger(item.line) || item.line < 1) {
      error(`${itemLocation}.line`, 'Required line number, an integer starting at 1.');
    }
    if (item.side !== undefined) requireEnumValue(item.side, EVIDENCE_SIDES, `${itemLocation}.side`, error);
  });
}

function validateConfidence(relationship, location, error) {
  requireEnumValue(relationship.confidence, CONFIDENCE_LEVELS, `${location}.confidence`, error);
  if (relationship.confidence === CONFIDENCE.inferred && !isNonEmptyString(relationship.reason)) {
    error(`${location}.reason`, 'Required for an inferred relationship: say what makes you think it exists.');
  }
}

function findUnreachableStates(initialStateId, states, transitions) {
  const reachableIds = new Set([initialStateId]);
  const pendingIds = [initialStateId];
  while (pendingIds.length > 0) {
    const currentId = pendingIds.pop();
    for (const transition of transitions) {
      if (isPlainObject(transition) && transition.source === currentId && !reachableIds.has(transition.target)) {
        reachableIds.add(transition.target);
        pendingIds.push(transition.target);
      }
    }
  }
  return states
    .filter((state) => isPlainObject(state) && isNonEmptyString(state.id) && !reachableIds.has(state.id))
    .map((state) => state.id);
}

function registerIdentifier(identifier, knownIds, location, error) {
  if (!isNonEmptyString(identifier) || !IDENTIFIER_PATTERN.test(identifier)) {
    error(`${location}.id`, 'Required kebab-case identifier (lowercase letters, digits and hyphens).');
    return;
  }
  if (knownIds.has(identifier)) {
    error(`${location}.id`, `Duplicated identifier "${identifier}".`);
    return;
  }
  knownIds.add(identifier);
}

function requireKnownEndpoint(identifier, knownIds, location, elementName, error) {
  if (!knownIds.has(identifier)) {
    error(location, `Unknown ${elementName} ${JSON.stringify(identifier)}.`);
  }
}

function requireEnumValue(value, allowedValues, location, error) {
  if (!allowedValues.includes(value)) {
    error(location, `Expected one of ${allowedValues.join(', ')}; received ${JSON.stringify(value)}.`);
  }
}

function compareBySeverity(first, second) {
  if (first.severity === second.severity) return 0;
  return first.severity === FINDING_SEVERITY.error ? -1 : 1;
}

function isPlainObject(value) {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isNonEmptyString(value) {
  return typeof value === 'string' && value.trim().length > 0;
}
