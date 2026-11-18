import { spawnSync } from 'node:child_process';

import { EVIDENCE_SIDE, FINDING_SEVERITY, GIT_REMOTE_REF_PREFIX } from './flow-graph-constants.mjs';

const GIT_COMMAND = 'git';
const LINE_BREAK_PATTERN = /\r?\n/;

/**
 * Checks every evidence line of a model against the repository: the file has to exist in the
 * version the evidence names (`base` or `head`) and has to be at least that long.
 *
 * The validator can only tell that evidence is present. This is what tells that it is real: an
 * evidence line the agent made up points at a file or a line that is not there.
 *
 * @param {object} model A model that already passed `validateFlowGraph`.
 * @param {string} repositoryPath Path of a clone that has both refs of the pull request.
 * @returns {import('./validate-flow-graph.mjs').Finding[]} One error per evidence that does not hold.
 */
export function checkEvidenceInRepository(model, repositoryPath) {
  const findings = [];
  const reportError = (location, message) => findings.push({ severity: FINDING_SEVERITY.error, location, message });
  const runGit = (gitArguments) => spawnSync(GIT_COMMAND, ['-C', repositoryPath, ...gitArguments], { encoding: 'utf8', maxBuffer: Infinity });

  if (runGit(['rev-parse', '--git-dir']).status !== 0) {
    reportError('--repo', `${repositoryPath} is not a git repository.`);
    return findings;
  }

  const resolvedRefs = new Map();
  const resolveRef = (refName) => {
    if (!resolvedRefs.has(refName)) {
      const candidates = [refName, `${GIT_REMOTE_REF_PREFIX}${refName}`];
      const resolved = candidates.find((candidate) => runGit(['rev-parse', '--verify', '--quiet', `${candidate}^{commit}`]).status === 0);
      resolvedRefs.set(refName, resolved ?? null);
    }
    return resolvedRefs.get(refName);
  };

  const lineCounts = new Map();
  /** @returns {number | null} Lines of the file at that ref, or null when the file is not there. */
  const countLines = (ref, filePath) => {
    const cacheKey = `${ref}:${filePath}`;
    if (!lineCounts.has(cacheKey)) {
      const result = runGit(['show', cacheKey]);
      if (result.status !== 0) {
        lineCounts.set(cacheKey, null);
      } else {
        const lines = result.stdout.split(LINE_BREAK_PATTERN);
        // A file that ends with a line break has one empty element after its last line.
        lineCounts.set(cacheKey, lines.at(-1) === '' ? lines.length - 1 : lines.length);
      }
    }
    return lineCounts.get(cacheKey);
  };

  const refNameBySide = { [EVIDENCE_SIDE.base]: model.pullRequest.baseRef, [EVIDENCE_SIDE.head]: model.pullRequest.headRef };
  const unresolvedRefNames = new Set();

  for (const { element, location } of listElementsWithLocation(model)) {
    for (const [index, evidence] of (element.evidence ?? []).entries()) {
      const evidenceLocation = `${location}.evidence[${index}]`;
      const side = evidence.side ?? EVIDENCE_SIDE.head;
      const refName = refNameBySide[side];
      const ref = resolveRef(refName);
      if (!ref) {
        unresolvedRefNames.add(refName);
        continue;
      }
      const lineCount = countLines(ref, evidence.path);
      if (lineCount === null) {
        reportError(evidenceLocation, `${evidence.path} does not exist in ${ref} (${side} side). Check the path, or use "side": "${side === EVIDENCE_SIDE.head ? EVIDENCE_SIDE.base : EVIDENCE_SIDE.head}" if the file only exists on the other side.`);
      } else if (evidence.line > lineCount) {
        reportError(evidenceLocation, `${evidence.path}:${evidence.line} is past the end of the file in ${ref} (${lineCount} lines).`);
      }
    }
  }

  for (const refName of unresolvedRefNames) {
    reportError('pullRequest', `The ref "${refName}" is not in ${repositoryPath} (tried it and ${GIT_REMOTE_REF_PREFIX}${refName}); fetch it so its evidence can be checked.`);
  }
  return findings;
}

function listElementsWithLocation(model) {
  const withLocation = (elements, listLocation) => (elements ?? []).map((element, index) => ({ element, location: `${listLocation}[${index}]` }));
  return [
    ...withLocation(model.nodes, 'nodes'),
    ...withLocation(model.edges, 'edges'),
    ...withLocation(model.businessFlow?.states, 'businessFlow.states'),
    ...withLocation(model.businessFlow?.transitions, 'businessFlow.transitions'),
  ];
}
