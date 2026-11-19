import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { BROWSER_LIBRARIES, EVIDENCE_SIDE, FLOW_SOURCE, KIND_LABELS, SOURCE_WORDING, TEMPLATE_PLACEHOLDER } from './flow-graph-constants.mjs';
import { getFlowSource, getFlowTitle } from './flow-source.mjs';

const TEMPLATE_PATH = fileURLToPath(new URL('../../assets/flow-graph-template.html', import.meta.url));
const GITHUB_DIFF_SIDE_MARKER = { [EVIDENCE_SIDE.base]: 'L', [EVIDENCE_SIDE.head]: 'R' };

/**
 * Renders the interactive page of a model.
 *
 * @param {object} model A valid flow graph model.
 * @param {object} [options]
 * @param {string} [options.leanSource] Lean model that already passed `checkLeanModel`.
 * @param {Map<string, string>} [options.inlinedLibraries] Library source by URL; a library found
 *   here is embedded in the page, so the page also opens without network.
 * @param {{ checks: import('./render-report.mjs').Check[] }} [options.verification] What was
 *   verified before rendering. Without it the page says the graph was not verified.
 * @returns {string} HTML document.
 */
export function renderFlowGraphHtml(model, { leanSource, inlinedLibraries = new Map(), verification } = {}) {
  // The page trusts these three properties, so they only ever come from this renderer: a
  // `formalModel` written in the input JSON would be shown as a model Lean compiled.
  const { formalModel: _ignoredFormalModel, verification: _ignoredVerification, kindLabels: _ignoredKindLabels, ...authoredModel } = model;
  const pageModel = {
    ...withEvidenceLinks(authoredModel),
    kindLabels: KIND_LABELS,
    ...(verification ? { verification } : {}),
    ...(leanSource ? { formalModel: { language: 'lean4', source: leanSource } } : {}),
  };
  const title = getFlowTitle(model);
  // Function replacers: the replacement text may contain `$`, which a string replacement expands.
  return readFileSync(TEMPLATE_PATH, 'utf8')
    .replaceAll(TEMPLATE_PLACEHOLDER.documentTitle, () => escapeHtml(`${SOURCE_WORDING[getFlowSource(model)].pageTitlePrefix} — ${title}`))
    .replaceAll(TEMPLATE_PLACEHOLDER.title, () => escapeHtml(title))
    .replace(TEMPLATE_PLACEHOLDER.libraries, () => renderLibraryTags(inlinedLibraries))
    .replace(TEMPLATE_PLACEHOLDER.model, () => serializeForScriptTag(pageModel));
}

/**
 * Builds the link of an evidence line into the "Files changed" tab of a GitHub pull request.
 *
 * @param {string} pullRequestUrl URL of the pull request.
 * @param {{ path: string, line: number, side?: 'base' | 'head' }} evidence Evidence line.
 * @returns {string} URL that opens the diff at that line.
 */
export function buildGithubDiffUrl(pullRequestUrl, evidence) {
  const fileAnchor = createHash('sha256').update(evidence.path).digest('hex');
  const sideMarker = GITHUB_DIFF_SIDE_MARKER[evidence.side ?? EVIDENCE_SIDE.head];
  return `${pullRequestUrl}/files#diff-${fileAnchor}${sideMarker}${evidence.line}`;
}

/** Links each evidence line to the diff of the pull request; an RFC has no diff to link to yet. */
function withEvidenceLinks(model) {
  if (getFlowSource(model) === FLOW_SOURCE.rfc) return model;
  const pullRequestUrl = model.pullRequest.url;
  if (!pullRequestUrl) return model;
  const linkEvidence = (element) => ({
    ...element,
    evidence: (element.evidence ?? []).map((evidence) => ({
      ...evidence,
      href: buildGithubDiffUrl(pullRequestUrl, evidence),
    })),
  });
  return {
    ...model,
    nodes: model.nodes.map(linkEvidence),
    edges: (model.edges ?? []).map(linkEvidence),
    ...(model.businessFlow
      ? {
          businessFlow: {
            ...model.businessFlow,
            states: model.businessFlow.states.map(linkEvidence),
            transitions: (model.businessFlow.transitions ?? []).map(linkEvidence),
          },
        }
      : {}),
  };
}

function renderLibraryTags(inlinedLibraries) {
  return BROWSER_LIBRARIES.map((library) => {
    const source = inlinedLibraries.get(library.url);
    if (source === undefined) return `<script src="${library.url}"></script>`;
    return `<script data-library="${library.name}@${library.version}">${source.replaceAll('</script', '<\\/script')}</script>`;
  }).join('\n');
}

/** JSON placed inside a script element must not be able to close it. */
function serializeForScriptTag(value) {
  return JSON.stringify(value).replaceAll('<', '\\u003c');
}

function escapeHtml(text) {
  return String(text)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}
