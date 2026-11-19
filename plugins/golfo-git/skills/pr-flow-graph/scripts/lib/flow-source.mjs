import { EVIDENCE_SIDES_BY_SOURCE, FLOW_SOURCE } from './flow-graph-constants.mjs';

/**
 * Tells what a model describes. A model carries `pullRequest` when it graphs a pull request and
 * `rfc` when it graphs the change an RFC proposes; the validator makes sure it carries one.
 *
 * @param {object} model A flow graph model.
 * @returns {'pull-request' | 'rfc'} One of `FLOW_SOURCE`.
 */
export function getFlowSource(model) {
  return model.rfc !== undefined && model.pullRequest === undefined ? FLOW_SOURCE.rfc : FLOW_SOURCE.pullRequest;
}

/**
 * @param {object} model A valid flow graph model.
 * @returns {string} Title of the pull request or of the RFC.
 */
export function getFlowTitle(model) {
  return getFlowSource(model) === FLOW_SOURCE.rfc ? model.rfc.title : model.pullRequest.title;
}

/**
 * @param {{ side?: string }} evidence An evidence line.
 * @param {'pull-request' | 'rfc'} source Source of the model the evidence belongs to.
 * @returns {string} Side of the evidence, with the default of its source when it names none.
 */
export function getEvidenceSide(evidence, source) {
  return evidence.side ?? EVIDENCE_SIDES_BY_SOURCE[source][0];
}
