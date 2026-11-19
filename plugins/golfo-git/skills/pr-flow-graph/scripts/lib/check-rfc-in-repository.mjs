import { readFileSync } from 'node:fs';
import path from 'node:path';

import {
  CHANGE_STATUS,
  CONFIDENCE,
  EVIDENCE_SIDE,
  FINDING_SEVERITY,
  FLOW_SOURCE,
  GIT_REMOTE_REF_PREFIX,
  LISTED_FILES_LIMIT,
  MARKDOWN_FENCE_PATTERN,
  RFC_SECTION_HEADING_PATTERN,
} from './flow-graph-constants.mjs';
import { getEvidenceSide } from './flow-source.mjs';
import {
  SHORT_COMMIT_LENGTH,
  createFileReader,
  createGitRunner,
  isGitRepository,
  listElementsWithLocation,
  mentionsNode,
  readNearbyLines,
  resolveRef,
  splitLines,
} from './repository-reading.mjs';

/**
 * @typedef {object} RfcVerification
 * @property {import('./validate-flow-graph.mjs').Finding[]} findings Errors and warnings found.
 * @property {object} [statistics] What was checked; present when the code and the RFC could be read.
 * @property {number} statistics.evidenceCount Evidence lines opened, in the code and in the RFC.
 * @property {number} statistics.codeEvidenceCount Lines opened in the code.
 * @property {number} statistics.rfcEvidenceCount Lines opened in the RFC.
 * @property {number} statistics.changedElementCount Elements the RFC proposes to add, modify or remove.
 * @property {number} statistics.verifiedRelationshipCount Verified relationships whose line was read.
 * @property {number} statistics.sectionCount `##` sections of the RFC.
 * @property {number} statistics.outOfScopeSectionCount Sections the model declares out of the graph.
 * @property {string} statistics.codeCommit Short hash of the commit the code was read at.
 * @property {string} statistics.document Path of the RFC document.
 */

/**
 * Checks the model of an RFC against the code it proposes to change and against the RFC itself.
 * There is no diff yet, so what proves a change is the line of the RFC that proposes it, and what
 * proves that a piece exists today is its line in the code:
 *
 * 1. Every code line exists at `rfc.codeRef`, and every RFC line is a line of the document with
 *    text on it.
 * 2. Every verified relationship names its ends: one that exists today, in the code; one the RFC
 *    adds, in the RFC, which has to name both ends because no code writes it yet.
 * 3. Every `##` section of the RFC is in the graph (one of its lines is evidence) or declared out
 *    of it, with a reason.
 *
 * The validator already made sure that each proposed change points at the RFC and that what
 * exists today points at the code.
 *
 * @param {object} model A model of an RFC that already passed `validateFlowGraph`.
 * @param {string} repositoryPath Path of a clone that has `rfc.codeRef`; `rfc.document` is read
 *   from its working tree, so an RFC that is not committed yet can be checked too.
 * @returns {RfcVerification}
 */
export function verifyRfcAgainstRepository(model, repositoryPath) {
  const findings = [];
  const reportError = (location, message) => findings.push({ severity: FINDING_SEVERITY.error, location, message });
  const reportWarning = (location, message) => findings.push({ severity: FINDING_SEVERITY.warning, location, message });
  const runGit = createGitRunner(repositoryPath);

  if (!isGitRepository(runGit)) {
    reportError('--repo', `${repositoryPath} is not a git repository.`);
    return { findings };
  }
  const codeCommit = resolveRef(model.rfc.codeRef, runGit);
  if (!codeCommit) {
    reportError('rfc.codeRef', `The ref "${model.rfc.codeRef}" is not in ${repositoryPath} (tried it and ${GIT_REMOTE_REF_PREFIX}${model.rfc.codeRef}); fetch it so the code the RFC changes can be read.`);
  }
  const documentLines = readDocument(repositoryPath, model.rfc.document, reportError);
  if (!codeCommit || !documentLines) return { findings };

  const readFileLines = createFileReader(runGit);
  const elements = listElementsWithLocation(model);
  const evidenceCounts = checkEvidenceExists(elements, { codeCommit, codeRef: model.rfc.codeRef, documentLines }, readFileLines, reportError);
  // The next steps read the lines the evidence points at, so they need all of them to exist.
  if (findings.length > 0) return { findings };

  const verifiedRelationshipCount = checkRelationshipsNameTheirEnds(model, { codeCommit, documentLines }, readFileLines, reportError);
  const sections = readSections(documentLines);
  const outOfScopeSectionCount = checkSectionCoverage(model, elements, sections, reportError, reportWarning);

  return {
    findings,
    statistics: {
      evidenceCount: evidenceCounts.code + evidenceCounts.rfc,
      codeEvidenceCount: evidenceCounts.code,
      rfcEvidenceCount: evidenceCounts.rfc,
      changedElementCount: elements.filter(({ element }) => element.change !== CHANGE_STATUS.unchanged).length,
      verifiedRelationshipCount,
      sectionCount: sections.length,
      outOfScopeSectionCount,
      codeCommit: codeCommit.slice(0, SHORT_COMMIT_LENGTH),
      document: model.rfc.document,
    },
  };
}

function readDocument(repositoryPath, documentPath, reportError) {
  try {
    return splitLines(readFileSync(path.resolve(repositoryPath, documentPath), 'utf8'));
  } catch (error) {
    reportError('rfc.document', `Cannot read the RFC ${documentPath} under ${repositoryPath} (${error.code ?? error.message}). Save the RFC text there, as plain Markdown, and point \`rfc.document\` at it.`);
    return null;
  }
}

function checkEvidenceExists(elements, { codeCommit, codeRef, documentLines }, readFileLines, reportError) {
  const counts = { code: 0, rfc: 0 };
  for (const { element, location } of elements) {
    for (const [index, evidence] of (element.evidence ?? []).entries()) {
      const evidenceLocation = `${location}.evidence[${index}]`;
      if (getEvidenceSide(evidence, FLOW_SOURCE.rfc) === EVIDENCE_SIDE.rfc) {
        counts.rfc += 1;
        if (evidence.line > documentLines.length) {
          reportError(evidenceLocation, `RFC line ${evidence.line} is past the end of the document (${documentLines.length} lines).`);
        } else if (documentLines[evidence.line - 1].trim() === '') {
          reportError(evidenceLocation, `RFC line ${evidence.line} is blank. Point at the line that proposes this element.`);
        }
        continue;
      }
      counts.code += 1;
      const lines = readFileLines(codeCommit, evidence.path);
      if (lines === null) {
        reportError(evidenceLocation, `${evidence.path} does not exist in ${codeRef}. Code evidence points at what exists today; something the RFC adds points only at the RFC ("side": "rfc").`);
      } else if (evidence.line > lines.length) {
        reportError(evidenceLocation, `${evidence.path}:${evidence.line} is past the end of the file in ${codeRef} (${lines.length} lines).`);
      }
    }
  }
  return counts;
}

/**
 * A relationship that exists today is written in the code, so its code line has to name the end
 * that lives elsewhere, as in a pull request. One that the RFC adds is written nowhere yet: the
 * only proof is a line of the RFC that names both ends.
 */
function checkRelationshipsNameTheirEnds(model, { codeCommit, documentLines }, readFileLines, reportError) {
  const nodesById = new Map(model.nodes.map((node) => [node.id, node]));
  const ownsFile = (node, filePath) => (node.evidence ?? []).some((evidence) => evidence.path === filePath);
  let verifiedRelationshipCount = 0;

  (model.edges ?? []).forEach((edge, index) => {
    if (edge.confidence !== CONFIDENCE.verified) return;
    verifiedRelationshipCount += 1;
    const ends = [nodesById.get(edge.source), nodesById.get(edge.target)];
    const names = ends.map((node) => `"${node.symbol ?? node.label}"`).join(' and ');

    if (edge.change === CHANGE_STATUS.added) {
      const rfcEvidence = edge.evidence.filter((evidence) => getEvidenceSide(evidence, FLOW_SOURCE.rfc) === EVIDENCE_SIDE.rfc);
      const namesBothEnds = rfcEvidence.some((evidence) => {
        const nearbyText = readNearbyLines(documentLines, evidence.line);
        return ends.every((node) => mentionsNode(nearbyText, node));
      });
      if (!namesBothEnds) {
        reportError(
          `edges[${index}].evidence`,
          `Marked "verified", but no RFC line of it names both ends (${names}) as the code calls them. Point at the line of the RFC that describes this relationship, set \`symbol\` on a node if the RFC calls it differently, or mark it "inferred" with a \`reason\`.`,
        );
      }
      return;
    }

    const codeEvidence = edge.evidence.filter((evidence) => getEvidenceSide(evidence, FLOW_SOURCE.rfc) === EVIDENCE_SIDE.code);
    const namesAnEnd = codeEvidence.some((evidence) => {
      const nearbyCode = readNearbyLines(readFileLines(codeCommit, evidence.path), evidence.line);
      const endsElsewhere = ends.filter((node) => !ownsFile(node, evidence.path));
      // In a file that belongs to both ends, or to neither, naming either one is enough.
      const endsToName = endsElsewhere.length === 1 ? endsElsewhere : ends;
      return endsToName.some((node) => mentionsNode(nearbyCode, node));
    });
    if (!namesAnEnd) {
      reportError(
        `edges[${index}].evidence`,
        `Marked "verified", but the code around its evidence does not name the other end (${ends.map((node) => `"${node.symbol ?? node.label}"`).join(' or ')}). It exists today, so point at the line of code that writes it, or mark it "inferred" with a \`reason\`.`,
      );
    }
  });
  return verifiedRelationshipCount;
}

/**
 * Splits the RFC into its `##` sections. What comes before the first one (title, authors, status)
 * is not a section: it proposes nothing. A `##` inside a fenced block is code, not a heading.
 *
 * @param {string[]} documentLines Lines of the RFC.
 * @returns {{ title: string, startLine: number, endLine: number }[]} Sections, with their lines from 1.
 */
export function readSections(documentLines) {
  const sections = [];
  let insideFence = false;
  documentLines.forEach((line, index) => {
    if (MARKDOWN_FENCE_PATTERN.test(line)) insideFence = !insideFence;
    const heading = insideFence ? null : RFC_SECTION_HEADING_PATTERN.exec(line);
    if (!heading) return;
    if (sections.length > 0) sections.at(-1).endLine = index;
    sections.push({ title: heading[1], startLine: index + 1, endLine: documentLines.length });
  });
  return sections;
}

const normalizeSectionTitle = (title) => title.trim().toLowerCase();

/** @returns {number} Sections the model declares out of the graph. */
function checkSectionCoverage(model, elements, sections, reportError, reportWarning) {
  if (sections.length === 0) {
    reportWarning('rfc.document', 'The RFC has no `##` sections, so its coverage could not be checked section by section.');
  }
  const rfcLines = elements.flatMap(({ element }) =>
    (element.evidence ?? []).filter((evidence) => getEvidenceSide(evidence, FLOW_SOURCE.rfc) === EVIDENCE_SIDE.rfc).map((evidence) => evidence.line),
  );
  const outOfScope = (model.outOfScope ?? []).map((entry) => ({ title: normalizeSectionTitle(entry.section), matchCount: 0 }));
  const unaccountedSections = [];
  let outOfScopeSectionCount = 0;

  for (const section of sections) {
    const matchingEntries = outOfScope.filter((entry) => entry.title === normalizeSectionTitle(section.title));
    for (const entry of matchingEntries) entry.matchCount += 1;
    if (rfcLines.some((line) => line >= section.startLine && line <= section.endLine)) continue;
    if (matchingEntries.length > 0) outOfScopeSectionCount += 1;
    else unaccountedSections.push(`"${section.title}" (line ${section.startLine})`);
  }

  if (unaccountedSections.length > 0) {
    const listed = unaccountedSections.slice(0, LISTED_FILES_LIMIT).join(', ');
    const rest = unaccountedSections.length > LISTED_FILES_LIMIT ? ` and ${unaccountedSections.length - LISTED_FILES_LIMIT} more` : '';
    reportError(
      'outOfScope',
      `The RFC has ${unaccountedSections.length} section(s) that the model does not account for: ${listed}${rest}. Point the evidence of an element at a line of each, or list it in \`outOfScope\` as { "section": "<its title>", "reason": "…" }.`,
    );
  }
  outOfScope.forEach((entry, index) => {
    if (entry.matchCount === 0) reportWarning(`outOfScope[${index}].section`, 'Matches no `##` section of the RFC; remove it or copy the title as the RFC writes it.');
  });
  return outOfScopeSectionCount;
}
