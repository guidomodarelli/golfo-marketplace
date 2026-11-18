import {
  BUSINESS_STATE_KIND,
  BUSINESS_STATE_KINDS,
  CHANGE_STATUS,
  CHANGE_STATUSES,
  CONFIDENCE,
  CONFIDENCE_LEVELS,
  EDGE_KINDS,
  EVIDENCE_SIDE,
  EVIDENCE_SIDES_BY_SOURCE,
  FINDING_SEVERITY,
  FLOW_GRAPH_SCHEMA_VERSION,
  FLOW_SOURCE,
  GITHUB_PULL_REQUEST_URL_PATTERN,
  HTTPS_URL_PATTERN,
  IDENTIFIER_PATTERN,
  NODE_KINDS,
} from './flow-graph-constants.mjs';
import { getEvidenceSide } from './flow-source.mjs';

const ABSOLUTE_PATH_PATTERN = /^([a-zA-Z]:)?[\\/]/;
const PATH_SEPARATOR_PATTERN = /[\\/]/;
const PARENT_FOLDER_SEGMENT = '..';

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
 * code that proves it, and every relationship the agent deduced says so and says why. A model of an
 * RFC follows the same rules, with the RFC as the proof of what it proposes (`validateRfcEvidence`).
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

  const source = validateSource(model, error);
  const context = { source, rfcDocument: model.rfc?.document };

  const groupIds = validateGroups(model.groups, error);
  const nodeIds = validateNodes(model.nodes, groupIds, context, error);
  validateEdges(model.edges, model.nodes, nodeIds, context, error);
  validateBusinessFlow(model.businessFlow, nodeIds, context, error, warning);
  validateOutOfScope(model.outOfScope, source, error);
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

/**
 * A model describes either a pull request or an RFC, never both: the two read their evidence from
 * different places.
 *
 * @returns {'pull-request' | 'rfc'} Source the rest of the model is validated against.
 */
function validateSource(model, error) {
  const hasPullRequest = model.pullRequest !== undefined;
  const hasRfc = model.rfc !== undefined;
  if (hasPullRequest && hasRfc) {
    error('(root)', 'Has both `pullRequest` and `rfc`. A model graphs one pull request or one RFC: keep the one it describes.');
  } else if (!hasPullRequest && !hasRfc) {
    error('(root)', 'Required: `pullRequest` for a pull request, or `rfc` for the change an RFC proposes.');
    return FLOW_SOURCE.pullRequest;
  }
  if (hasPullRequest) {
    validatePullRequest(model.pullRequest, error);
    return FLOW_SOURCE.pullRequest;
  }
  validateRfc(model.rfc, error);
  return FLOW_SOURCE.rfc;
}

function validateRfc(rfc, error) {
  if (!isPlainObject(rfc)) {
    error('rfc', 'Required object with `title`, `document` and `codeRef`.');
    return;
  }
  for (const field of ['title', 'codeRef']) {
    if (!isNonEmptyString(rfc[field])) error(`rfc.${field}`, 'Required non-empty string.');
  }
  if (!isRelativePath(rfc.document)) {
    error('rfc.document', 'Required: path of the RFC text, relative to the repository root, with forward slashes and no `..`.');
  }
  if (rfc.url !== undefined && !HTTPS_URL_PATTERN.test(String(rfc.url))) {
    error('rfc.url', 'Must be an https:// URL where people read the RFC, or be omitted.');
  }
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

function validateNodes(nodes, groupIds, context, error) {
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
    if (node.symbol !== undefined && !isNonEmptyString(node.symbol)) {
      error(`${location}.symbol`, 'Must be the name the code uses for this piece, or be omitted.');
    }
    requireEnumValue(node.kind, NODE_KINDS, `${location}.kind`, error);
    requireEnumValue(node.change, CHANGE_STATUSES, `${location}.change`, error);
    if (node.group !== undefined && !groupIds.has(node.group)) {
      error(`${location}.group`, `Unknown group ${JSON.stringify(node.group)}; declare it in \`groups\`.`);
    }
    validateEvidence(node, location, context, error);
  });
  return nodeIds;
}

function validateEdges(edges, nodes, nodeIds, context, error) {
  if (edges === undefined) return;
  if (!Array.isArray(edges)) {
    error('edges', 'Must be an array when present.');
    return;
  }
  const edgeIds = new Set();
  const seenRelationships = new Map();
  const changeByNodeId = readChangeById(nodes);
  edges.forEach((edge, index) => {
    const location = `edges[${index}]`;
    if (!isPlainObject(edge)) {
      error(location, 'Must be an object.');
      return;
    }
    registerIdentifier(edge.id, edgeIds, location, error);
    requireIdentifierNotSharedWith(edge.id, nodeIds, location, 'node', error);
    requireEnumValue(edge.kind, EDGE_KINDS, `${location}.kind`, error);
    requireEnumValue(edge.change, CHANGE_STATUSES, `${location}.change`, error);
    requireKnownEndpoint(edge.source, nodeIds, `${location}.source`, 'node', error);
    requireKnownEndpoint(edge.target, nodeIds, `${location}.target`, 'node', error);
    validateConfidence(edge, location, error);
    validateEvidence(edge, location, context, error);
    requireUniqueRelationship([edge.source, edge.target, edge.kind], seenRelationships, location, 'source, target and kind', error);
    requireChangeConsistentWithEndpoints(edge, changeByNodeId, location, 'node', error);
  });
}

function validateBusinessFlow(businessFlow, nodeIds, context, error, warning) {
  if (businessFlow === undefined) return;
  if (!isPlainObject(businessFlow)) {
    error('businessFlow', 'Must be an object with `states` and `transitions` when present.');
    return;
  }
  const stateIds = new Set();
  const states = Array.isArray(businessFlow.states) ? businessFlow.states : [];
  if (states.length === 0) error('businessFlow.states', 'Required non-empty array.');
  if (!isNonEmptyString(businessFlow.summary)) {
    error('businessFlow.summary', 'Required: one sentence, in product words, on what changes for the user. The final report quotes it.');
  }

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
    validateEvidence(state, location, context, error);
    for (const [nodeIndex, nodeId] of (state.nodeIds ?? []).entries()) {
      requireKnownEndpoint(nodeId, nodeIds, `${location}.nodeIds[${nodeIndex}]`, 'node', error);
    }
  });

  const initialStates = states.filter(
    (state) => isPlainObject(state) && state.kind === BUSINESS_STATE_KIND.initial && state.change !== CHANGE_STATUS.removed,
  );
  if (states.length > 0 && initialStates.length !== 1) {
    error('businessFlow.states', `Exactly one state of kind "initial" must exist after the change; found ${initialStates.length}.`);
  }

  const transitions = Array.isArray(businessFlow.transitions) ? businessFlow.transitions : [];
  const transitionIds = new Set();
  const seenTransitions = new Map();
  const changeByStateId = readChangeById(states);
  transitions.forEach((transition, index) => {
    const location = `businessFlow.transitions[${index}]`;
    if (!isPlainObject(transition)) {
      error(location, 'Must be an object.');
      return;
    }
    registerIdentifier(transition.id, transitionIds, location, error);
    requireIdentifierNotSharedWith(transition.id, stateIds, location, 'business state', error);
    if (!isNonEmptyString(transition.trigger)) {
      error(`${location}.trigger`, 'Required: the user action or event that fires the transition.');
    }
    requireEnumValue(transition.change, CHANGE_STATUSES, `${location}.change`, error);
    requireKnownEndpoint(transition.source, stateIds, `${location}.source`, 'business state', error);
    requireKnownEndpoint(transition.target, stateIds, `${location}.target`, 'business state', error);
    validateConfidence(transition, location, error);
    validateEvidence(transition, location, context, error);
    requireUniqueRelationship(
      [transition.source, transition.trigger, transition.guard ?? ''],
      seenTransitions,
      location,
      'source, trigger and guard, so the flow would not know which one to follow',
      error,
    );
    requireChangeConsistentWithEndpoints(transition, changeByStateId, location, 'business state', error);
  });

  if (initialStates.length === 1) {
    for (const unreachableId of findUnreachableStates(initialStates[0].id, states, transitions)) {
      warning('businessFlow.states', `State "${unreachableId}" cannot be reached from the initial state; add the missing transition or remove it.`);
    }
  }
}

/**
 * What the graph leaves out on purpose, each with the reason: files of a pull request, or `##`
 * sections of an RFC.
 */
function validateOutOfScope(outOfScope, source, error) {
  if (outOfScope === undefined) return;
  const field = source === FLOW_SOURCE.rfc ? 'section' : 'path';
  if (!Array.isArray(outOfScope)) {
    error('outOfScope', `Must be an array of \`{ ${field}, reason }\` when present.`);
    return;
  }
  outOfScope.forEach((entry, index) => {
    const location = `outOfScope[${index}]`;
    if (!isPlainObject(entry)) {
      error(location, `Must be an object with \`${field}\` and \`reason\`.`);
      return;
    }
    if (source === FLOW_SOURCE.rfc) {
      if (!isNonEmptyString(entry.section)) error(`${location}.section`, 'Required: the title of a `##` section of the RFC, as the RFC writes it.');
      if (entry.path !== undefined) error(`${location}.path`, 'An RFC leaves out sections, not files: use `section` with the title of the section.');
      if (!isNonEmptyString(entry.reason)) error(`${location}.reason`, 'Required: why this section is not part of the graph.');
      return;
    }
    if (!isNonEmptyString(entry.path)) error(`${location}.path`, 'Required: a file path, a folder ending in `/` or a pattern with `*`.');
    if (!isNonEmptyString(entry.reason)) error(`${location}.reason`, 'Required: why these files are not part of the graph.');
  });
}

function readChangeById(elements) {
  const changeById = new Map();
  for (const element of Array.isArray(elements) ? elements : []) {
    if (isPlainObject(element) && isNonEmptyString(element.id)) changeById.set(element.id, element.change);
  }
  return changeById;
}

/** Two relationships that say the same thing make the graph, and its counts, lie. */
function requireUniqueRelationship(keyParts, seenRelationships, location, description, error) {
  if (keyParts.some((part) => typeof part !== 'string')) return;
  const key = JSON.stringify(keyParts);
  if (seenRelationships.has(key)) {
    error(location, `Repeats ${seenRelationships.get(key)}: same ${description}. Keep one.`);
    return;
  }
  seenRelationships.set(key, location);
}

/**
 * A relationship cannot outlive its ends: one that touches something the pull request added did
 * not exist before, and one that touches something it removed does not exist after.
 */
function requireChangeConsistentWithEndpoints(relationship, changeById, location, elementName, error) {
  for (const endpointId of [relationship.source, relationship.target]) {
    const endpointChange = changeById.get(endpointId);
    const isForced = endpointChange === CHANGE_STATUS.added || endpointChange === CHANGE_STATUS.removed;
    if (isForced && relationship.change !== endpointChange) {
      error(
        `${location}.change`,
        `Must be "${endpointChange}" because the ${elementName} "${endpointId}" is ${endpointChange}; received ${JSON.stringify(relationship.change)}.`,
      );
      return;
    }
  }
}

/** A graph with no changed element describes the app, not the pull request or the RFC. */
function validateChangePresence(model, error) {
  const elements = [
    ...(Array.isArray(model.nodes) ? model.nodes : []),
    ...(Array.isArray(model.edges) ? model.edges : []),
    ...(Array.isArray(model.businessFlow?.states) ? model.businessFlow.states : []),
    ...(Array.isArray(model.businessFlow?.transitions) ? model.businessFlow.transitions : []),
  ];
  const hasChange = elements.some((element) => isPlainObject(element) && element.change !== CHANGE_STATUS.unchanged);
  if (elements.length > 0 && !hasChange) {
    error('nodes', 'No element is marked added, modified or removed, so the graph does not show what changes.');
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
function validateEvidence(element, location, context, error) {
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
  const allowedSides = EVIDENCE_SIDES_BY_SOURCE[context.source];
  evidence.forEach((item, index) => {
    const itemLocation = `${location}.evidence[${index}]`;
    if (!isPlainObject(item)) {
      error(itemLocation, 'Must be an object with `path` and `line`.');
      return;
    }
    if (item.side !== undefined && !allowedSides.includes(item.side)) {
      const sourceName = context.source === FLOW_SOURCE.rfc ? 'an RFC' : 'a pull request';
      error(`${itemLocation}.side`, `In ${sourceName}, expected one of ${allowedSides.join(', ')}; received ${JSON.stringify(item.side)}.`);
    }
    const isRfcLine = context.source === FLOW_SOURCE.rfc && item.side === EVIDENCE_SIDE.rfc;
    if (isRfcLine) {
      if (item.path !== undefined && item.path !== context.rfcDocument) {
        error(`${itemLocation}.path`, 'An RFC line needs only `line`: omit `path`, or make it the same as `rfc.document`.');
      }
    } else if (!isRelativePath(item.path)) {
      error(`${itemLocation}.path`, 'Required path relative to the repository root, with forward slashes.');
    }
    if (!Number.isInteger(item.line) || item.line < 1) {
      error(`${itemLocation}.line`, 'Required line number, an integer starting at 1.');
    }
  });
  if (context.source === FLOW_SOURCE.rfc && evidence.every(isPlainObject)) validateRfcEvidence(element, evidence, location, error);
}

/**
 * In an RFC nothing is in the code yet, so a change is proved by the line of the RFC that proposes
 * it, and what exists today by its line in the code:
 *
 * - `added`: at least one RFC line, and no code line, because it does not exist yet.
 * - `modified` and `removed`: at least one RFC line and at least one code line.
 * - a `verified` relationship the RFC does not change: a code line, because the code writes it.
 */
function validateRfcEvidence(element, evidence, location, error) {
  const countBySide = (side) => evidence.filter((item) => getEvidenceSide(item, FLOW_SOURCE.rfc) === side).length;
  const rfcLineCount = countBySide(EVIDENCE_SIDE.rfc);
  const codeLineCount = countBySide(EVIDENCE_SIDE.code);
  const evidenceLocation = `${location}.evidence`;
  if (evidence.length === 0) return;

  if (element.change !== CHANGE_STATUS.unchanged && rfcLineCount === 0) {
    error(evidenceLocation, `Marked "${element.change}", but none of its evidence is a line of the RFC. Add { "side": "rfc", "line": N } pointing at the line that proposes it, or mark it "unchanged".`);
  }
  if (element.change === CHANGE_STATUS.added && codeLineCount > 0) {
    error(evidenceLocation, 'Marked "added", so it does not exist in the code yet: keep only its RFC lines. If it already exists, it is "modified" or "unchanged".');
  }
  const existsToday = element.change === CHANGE_STATUS.modified || element.change === CHANGE_STATUS.removed;
  if (existsToday && codeLineCount === 0) {
    error(evidenceLocation, `Marked "${element.change}", so it exists today: add the line of code where it is, besides the RFC line.`);
  }
  if (element.confidence === CONFIDENCE.verified && element.change === CHANGE_STATUS.unchanged && codeLineCount === 0) {
    error(evidenceLocation, 'Marked "verified" and "unchanged", so the code writes it today: point at that line of code, or mark it "inferred" with a `reason`.');
  }
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

/**
 * A view of the page selects, focuses and links its elements by id, so a relationship that
 * shares its id with one of the things it connects would replace it there.
 */
function requireIdentifierNotSharedWith(identifier, otherIds, location, otherElementName, error) {
  if (otherIds.has(identifier)) {
    error(`${location}.id`, `"${identifier}" is also the id of a ${otherElementName}. Rename one of them: the two are shown in the same view.`);
  }
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

function isRelativePath(value) {
  return isNonEmptyString(value) && !ABSOLUTE_PATH_PATTERN.test(value) && !value.split(PATH_SEPARATOR_PATTERN).includes(PARENT_FOLDER_SEGMENT);
}

function isNonEmptyString(value) {
  return typeof value === 'string' && value.trim().length > 0;
}
