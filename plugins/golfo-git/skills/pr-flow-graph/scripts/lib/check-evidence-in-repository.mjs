import {
  CHANGE_STATUS,
  CONFIDENCE,
  EVIDENCE_SIDE,
  FINDING_SEVERITY,
  FLOW_SOURCE,
  GIT_REMOTE_REF_PREFIX,
  LISTED_FILES_LIMIT,
} from './flow-graph-constants.mjs';
import { verifyRfcAgainstRepository } from './check-rfc-in-repository.mjs';
import { getFlowSource } from './flow-source.mjs';
import {
  SHORT_COMMIT_LENGTH,
  createFileReader,
  createGitRunner,
  isGitRepository,
  listElementsWithLocation,
  mentionsNode,
  readNearbyLines,
  resolveRef,
} from './repository-reading.mjs';

const LINE_BREAK_PATTERN = /\r?\n/;
const HUNK_HEADER_PATTERN = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/;
const OLD_FILE_HEADER_PREFIX = '--- ';
const NEW_FILE_HEADER_PREFIX = '+++ ';
const DIFF_PATH_PREFIX_LENGTH = 2;
const NO_FILE_MARKER = '/dev/null';
const GLOB_ANY_FOLDERS = '**/';
const GLOB_ANY_DEPTH = '**';
const GLOB_ONE_SEGMENT = '*';
const FOLDER_SUFFIX = '/';

/**
 * @typedef {object} RepositoryVerification
 * @property {import('./validate-flow-graph.mjs').Finding[]} findings Errors and warnings found.
 * @property {object} [statistics] What was checked; present when the diff could be read.
 * @property {number} statistics.evidenceCount Evidence lines opened in the repository.
 * @property {number} statistics.changedElementCount Changed elements matched against the diff.
 * @property {number} statistics.verifiedRelationshipCount Verified relationships whose line was read.
 * @property {number} statistics.changedFileCount Files the pull request changed.
 * @property {number} statistics.outOfScopeFileCount Changed files the model declares out of the graph.
 * @property {string} statistics.baseCommit Short hash of the commit the base side was read from.
 * @property {string} statistics.headCommit Short hash of the commit the head side was read from.
 */

/**
 * Checks a model against the repository it describes. The shape validator can only tell that a
 * claim is present; this tells whether it is true, in four steps that each need the one before:
 *
 * 1. Every evidence line exists in the version it names.
 * 2. Every change matches the diff: an added element points at an added line, a removed one at a
 *    removed line, a modified one at a file the pull request touched.
 * 3. Every verified relationship points at code that names its other end.
 * 4. Every file the pull request changed is in the graph or declared out of it, with a reason.
 *
 * The base side is read at the merge base of the two refs, the same commit the pull request diff
 * starts from, so a base branch that kept moving does not shift the line numbers.
 *
 * A model of an RFC has no diff to compare with: `check-rfc-in-repository.mjs` checks it instead.
 *
 * @param {object} model A model that already passed `validateFlowGraph`.
 * @param {string} repositoryPath Path of a clone that has both refs of the pull request.
 * @returns {RepositoryVerification}
 */
export function verifyModelAgainstRepository(model, repositoryPath) {
  if (getFlowSource(model) === FLOW_SOURCE.rfc) return verifyRfcAgainstRepository(model, repositoryPath);
  const findings = [];
  const reportError = (location, message) => findings.push({ severity: FINDING_SEVERITY.error, location, message });
  const reportWarning = (location, message) => findings.push({ severity: FINDING_SEVERITY.warning, location, message });
  const runGit = createGitRunner(repositoryPath);

  if (!isGitRepository(runGit)) {
    reportError('--repo', `${repositoryPath} is not a git repository.`);
    return { findings };
  }

  const commits = resolveCommits(model.pullRequest, runGit);
  for (const refName of commits.unresolvedRefNames) {
    reportError('pullRequest', `The ref "${refName}" is not in ${repositoryPath} (tried it and ${GIT_REMOTE_REF_PREFIX}${refName}); fetch it so its evidence can be checked.`);
  }
  if (commits.unresolvedRefNames.length > 0) return { findings };
  if (!commits.mergeBase) {
    reportError('pullRequest', `"${model.pullRequest.baseRef}" and "${model.pullRequest.headRef}" share no history in ${repositoryPath}, so the diff of the pull request cannot be read. Fetch the full history (git fetch --unshallow) or check the refs.`);
    return { findings };
  }

  const sides = {
    [EVIDENCE_SIDE.base]: { commit: commits.mergeBase, refName: model.pullRequest.baseRef },
    [EVIDENCE_SIDE.head]: { commit: commits.head, refName: model.pullRequest.headRef },
  };
  const readFileLines = createFileReader(runGit);
  const elements = listElementsWithLocation(model);

  const evidenceCount = checkEvidenceExists(elements, sides, readFileLines, reportError);
  // The next steps read the lines the evidence points at, so they need all of them to exist.
  if (findings.length > 0) return { findings };

  const diff = readDiff(commits.mergeBase, commits.head, runGit);
  const changedElementCount = checkChangesMatchDiff(elements, diff, reportError);
  const verifiedRelationshipCount = checkRelationshipsNameTheirEnds(model, sides, readFileLines, reportError);
  const outOfScopeFileCount = checkDiffCoverage(model, elements, diff, reportError, reportWarning);

  return {
    findings,
    statistics: {
      evidenceCount,
      changedElementCount,
      verifiedRelationshipCount,
      changedFileCount: diff.changedFiles.size,
      outOfScopeFileCount,
      baseCommit: commits.mergeBase.slice(0, SHORT_COMMIT_LENGTH),
      headCommit: commits.head.slice(0, SHORT_COMMIT_LENGTH),
    },
  };
}

/**
 * @param {object} model A model that already passed `validateFlowGraph`.
 * @param {string} repositoryPath Path of a clone that has both refs of the pull request.
 * @returns {import('./validate-flow-graph.mjs').Finding[]} Findings of `verifyModelAgainstRepository`.
 */
export function checkEvidenceInRepository(model, repositoryPath) {
  return verifyModelAgainstRepository(model, repositoryPath).findings;
}

function resolveCommits(pullRequest, runGit) {
  const base = resolveRef(pullRequest.baseRef, runGit);
  const head = resolveRef(pullRequest.headRef, runGit);
  const unresolvedRefNames = [...new Set([[pullRequest.baseRef, base], [pullRequest.headRef, head]].filter(([, commit]) => !commit).map(([refName]) => refName))];
  if (unresolvedRefNames.length > 0) return { unresolvedRefNames };
  const mergeBaseResult = runGit(['merge-base', base, head]);
  return { unresolvedRefNames, head, mergeBase: mergeBaseResult.status === 0 ? mergeBaseResult.stdout.trim() : null };
}

const sideOf = (evidence) => evidence.side ?? EVIDENCE_SIDE.head;
const otherSideOf = (side) => (side === EVIDENCE_SIDE.head ? EVIDENCE_SIDE.base : EVIDENCE_SIDE.head);

function checkEvidenceExists(elements, sides, readFileLines, reportError) {
  let evidenceCount = 0;
  for (const { element, location } of elements) {
    for (const [index, evidence] of (element.evidence ?? []).entries()) {
      evidenceCount += 1;
      const evidenceLocation = `${location}.evidence[${index}]`;
      const side = sideOf(evidence);
      const { commit, refName } = sides[side];
      const lines = readFileLines(commit, evidence.path);
      if (lines === null) {
        reportError(evidenceLocation, `${evidence.path} does not exist in ${refName} (${side} side). Check the path, or use "side": "${otherSideOf(side)}" if the file only exists on the other side.`);
      } else if (evidence.line > lines.length) {
        reportError(evidenceLocation, `${evidence.path}:${evidence.line} is past the end of the file in ${refName} (${lines.length} lines).`);
      }
    }
  }
  return evidenceCount;
}

/**
 * Reads which files the pull request changed and which lines it added (numbered as in head) and
 * removed (numbered as in base).
 */
function readDiff(baseCommit, headCommit, runGit) {
  const changedFiles = new Set(
    runGit(['diff', '--name-only', '--no-renames', '-z', baseCommit, headCommit]).stdout.split('\0').filter(Boolean),
  );
  const lineRanges = { [EVIDENCE_SIDE.base]: new Map(), [EVIDENCE_SIDE.head]: new Map() };
  const addRange = (side, filePath, start, length) => {
    if (!filePath || length === 0) return;
    if (!lineRanges[side].has(filePath)) lineRanges[side].set(filePath, []);
    lineRanges[side].get(filePath).push({ start, end: start + length - 1 });
  };
  const readPath = (headerLine, prefix) => {
    const filePath = headerLine.slice(prefix.length).trim();
    return filePath === NO_FILE_MARKER ? null : filePath.slice(DIFF_PATH_PREFIX_LENGTH);
  };

  let basePath = null;
  let headPath = null;
  const patch = runGit(['diff', '--unified=0', '--no-renames', '--no-color', baseCommit, headCommit]).stdout;
  for (const line of patch.split(LINE_BREAK_PATTERN)) {
    if (line.startsWith(OLD_FILE_HEADER_PREFIX)) basePath = readPath(line, OLD_FILE_HEADER_PREFIX);
    else if (line.startsWith(NEW_FILE_HEADER_PREFIX)) headPath = readPath(line, NEW_FILE_HEADER_PREFIX);
    else {
      const hunk = HUNK_HEADER_PATTERN.exec(line);
      if (!hunk) continue;
      // A hunk header without a length means one line.
      addRange(EVIDENCE_SIDE.base, basePath, Number(hunk[1]), Number(hunk[2] ?? 1));
      addRange(EVIDENCE_SIDE.head, headPath, Number(hunk[3]), Number(hunk[4] ?? 1));
    }
  }
  return {
    changedFiles,
    isChangedLine: (side, filePath, lineNumber) =>
      (lineRanges[side].get(filePath) ?? []).some((range) => lineNumber >= range.start && lineNumber <= range.end),
  };
}

function checkChangesMatchDiff(elements, diff, reportError) {
  let changedElementCount = 0;
  for (const { element, location } of elements) {
    const evidence = element.evidence ?? [];
    // A business state may carry no evidence; then there is nothing to match against the diff.
    if (element.change === CHANGE_STATUS.unchanged || evidence.length === 0) continue;
    changedElementCount += 1;

    if (element.change === CHANGE_STATUS.modified) {
      if (!evidence.some((item) => diff.changedFiles.has(item.path))) {
        reportError(`${location}.evidence`, `Marked "modified", but none of its evidence is in a file the pull request changed. Point at a changed file, or mark it "unchanged".`);
      }
      continue;
    }
    const side = element.change === CHANGE_STATUS.added ? EVIDENCE_SIDE.head : EVIDENCE_SIDE.base;
    const verb = element.change === CHANGE_STATUS.added ? 'added' : 'removed';
    if (!evidence.some((item) => sideOf(item) === side && diff.isChangedLine(side, item.path, item.line))) {
      reportError(
        `${location}.evidence`,
        `Marked "${element.change}", but none of its evidence is a line the pull request ${verb} (${side} side). Point at a line the diff shows as ${verb}, or change \`change\` to "modified" or "unchanged".`,
      );
    }
  }
  return changedElementCount;
}

/**
 * A verified relationship claims that a line of code writes it. The check reads that line and its
 * neighbours and looks for the name of the end the file does not belong to: the call, dispatch or
 * subscription has to name what it reaches.
 */
function checkRelationshipsNameTheirEnds(model, sides, readFileLines, reportError) {
  const nodesById = new Map(model.nodes.map((node) => [node.id, node]));
  const ownsFile = (node, filePath) => (node.evidence ?? []).some((evidence) => evidence.path === filePath);
  let verifiedRelationshipCount = 0;

  (model.edges ?? []).forEach((edge, index) => {
    if (edge.confidence !== CONFIDENCE.verified) return;
    verifiedRelationshipCount += 1;
    const ends = [nodesById.get(edge.source), nodesById.get(edge.target)];
    const namesAnEnd = edge.evidence.some((evidence) => {
      const fileLines = readFileLines(sides[sideOf(evidence)].commit, evidence.path);
      const nearbyCode = readNearbyLines(fileLines, evidence.line);
      const endsElsewhere = ends.filter((node) => !ownsFile(node, evidence.path));
      // In a file that belongs to both ends, or to neither, naming either one is enough.
      const endsToName = endsElsewhere.length === 1 ? endsElsewhere : ends;
      return endsToName.some((node) => mentionsNode(nearbyCode, node));
    });
    if (!namesAnEnd) {
      const names = ends.map((node) => `"${node.symbol ?? node.label}"`).join(' or ');
      reportError(
        `edges[${index}].evidence`,
        `Marked "verified", but the code around its evidence does not name the other end (${names}). Point at the line that writes the relationship, set \`symbol\` on the node if the code calls it differently, or mark the relationship "inferred" with a \`reason\`.`,
      );
    }
  });
  return verifiedRelationshipCount;
}

/** @returns {number} Changed files the model declares out of the graph. */
function checkDiffCoverage(model, elements, diff, reportError, reportWarning) {
  const filesInGraph = new Set(elements.flatMap(({ element }) => (element.evidence ?? []).map((evidence) => evidence.path)));
  const outOfScope = (model.outOfScope ?? []).map((entry) => ({ matches: createPathMatcher(entry.path), matchCount: 0 }));
  const unaccountedFiles = [];
  let outOfScopeFileCount = 0;

  for (const filePath of diff.changedFiles) {
    const matchingEntries = outOfScope.filter((entry) => entry.matches(filePath));
    for (const entry of matchingEntries) entry.matchCount += 1;
    if (filesInGraph.has(filePath)) continue;
    if (matchingEntries.length > 0) outOfScopeFileCount += 1;
    else unaccountedFiles.push(filePath);
  }

  if (unaccountedFiles.length > 0) {
    const listed = unaccountedFiles.slice(0, LISTED_FILES_LIMIT).join(', ');
    const rest = unaccountedFiles.length > LISTED_FILES_LIMIT ? ` and ${unaccountedFiles.length - LISTED_FILES_LIMIT} more` : '';
    reportError(
      'outOfScope',
      `The pull request changed ${unaccountedFiles.length} file(s) that the model does not account for: ${listed}${rest}. Add each to the graph as evidence of an element, or list it in \`outOfScope\` with the reason it is left out.`,
    );
  }
  outOfScope.forEach((entry, index) => {
    if (entry.matchCount === 0) {
      reportWarning(`outOfScope[${index}].path`, `Matches no file the pull request changed; remove it or fix the path.`);
    }
  });
  return outOfScopeFileCount;
}

/**
 * @param {string} pattern A file path, a folder ending in `/`, or a pattern where `*` stands for
 *   part of a name and `**` for any number of folders (none included, so the pattern with two
 *   stars, a slash and `*.md` also matches a file at the root).
 * @returns {(filePath: string) => boolean}
 */
function createPathMatcher(pattern) {
  if (pattern.endsWith(FOLDER_SUFFIX)) return (filePath) => filePath.startsWith(pattern);
  if (!pattern.includes(GLOB_ONE_SEGMENT)) return (filePath) => filePath === pattern;
  const escapeForPattern = (text) => text.replace(/[.+?^${}()|[\]\\]/g, '\\$&');
  const withinOneSegment = (part) => part.split(GLOB_ONE_SEGMENT).map(escapeForPattern).join('[^/]*');
  const expression = pattern
    .split(GLOB_ANY_FOLDERS)
    .map((part) => part.split(GLOB_ANY_DEPTH).map(withinOneSegment).join('.*'))
    .join('(?:.*/)?');
  const matcher = new RegExp(`^${expression}$`);
  return (filePath) => matcher.test(filePath);
}
