#!/usr/bin/env node

'use strict';

/**
 * Decides which heavy areas of `.github/workflows/tests.yml` a change needs.
 *
 * There is one area today, `agent_ready`: the agent-ready-setup suites on Linux, Windows and
 * macOS, the bootstrap shards and the browser registration test. A pull request needs it when it
 * changes a path in AGENT_READY_TRIGGER_PATHS, or a golfo-kit manifest in anything other than its
 * `version` field (adding or removing a manifest file also counts). A pure version bump does not:
 * the suites never read the real version, and check-version-bump.js already validates it.
 *
 * Any event other than `pull_request` (a push to main, workflow_dispatch) runs every area. If the
 * detection itself fails, every area runs too: skipping a suite by mistake is worse than running it.
 *
 * Usage:
 *   node scripts/detect-test-areas.js [base-ref]   (default: origin/main)
 *
 * Reads GITHUB_EVENT_NAME and, when set, appends `agent_ready=true|false` to GITHUB_OUTPUT.
 * Prints the same line on stdout and the reason on stderr.
 */

const childProcess = require('child_process');
const fs = require('fs');

const DEFAULT_BASE_REFERENCE = 'origin/main';
const FILTERED_EVENT = 'pull_request';
const AGENT_READY_AREA = 'agent_ready';

/** Paths whose change needs the agent-ready-setup suites. A trailing slash matches a directory. */
const AGENT_READY_TRIGGER_PATHS = [
  'plugins/golfo-kit/skills/agent-ready-setup/',
  'package.json',
  'pnpm-lock.yaml',
  'pnpm-workspace.yaml',
  '.nvmrc',
  '.gitattributes',
  '.github/workflows/tests.yml',
  'scripts/detect-test-areas.js',
  'tests/detect-test-areas.bats',
];

/** golfo-kit manifests that agent-ready-setup reads or copies; a pure version bump does not count. */
const MANIFEST_PATHS = [
  'plugins/golfo-kit/plugin.json',
  'plugins/golfo-kit/.claude-plugin/',
  'plugins/golfo-kit/.codex-plugin/',
];
const IGNORED_MANIFEST_FIELD = 'version';
const MODIFIED_STATUS = 'M';
const JSON_EXTENSION = '.json';

/**
 * Executes a Git command from the current directory and returns stdout.
 *
 * @param {string[]} args Git command arguments.
 * @returns {string} Command stdout.
 */
function git(args) {
  return childProcess.execFileSync('git', args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
}

/**
 * Tells whether a repository path matches one of the patterns.
 *
 * @param {string} filePath Path relative to the repository root, with forward slashes.
 * @param {string[]} patterns Exact paths, or directories ending in `/`.
 * @returns {boolean} True when it matches.
 */
function matchesAny(filePath, patterns) {
  return patterns.some((pattern) => (pattern.endsWith('/') ? filePath.startsWith(pattern) : filePath === pattern));
}

/**
 * Lists the files a change touched, with their Git status letter.
 *
 * @param {string} mergeBase Commit to compare against.
 * @returns {{status: string, filePath: string}[]} One entry per changed file.
 */
function changedFiles(mergeBase) {
  return git(['diff', '--name-status', '--no-renames', mergeBase, 'HEAD'])
    .split('\n')
    .filter(Boolean)
    .map((line) => {
      const [status, filePath] = line.split('\t');
      return { status: status.charAt(0), filePath };
    });
}

/**
 * Returns a manifest without the field that a version bump changes, ready to compare.
 *
 * @param {string} contents Raw JSON of the manifest.
 * @returns {string} Canonical JSON without the ignored field.
 */
function withoutVersion(contents) {
  const manifest = JSON.parse(contents);
  delete manifest[IGNORED_MANIFEST_FIELD];
  return JSON.stringify(manifest);
}

/**
 * Tells whether a manifest change goes beyond a version bump.
 *
 * @param {string} mergeBase Commit to compare against.
 * @param {{status: string, filePath: string}} change The changed manifest file.
 * @returns {boolean} True when the agent-ready-setup suites have to run.
 */
function isManifestChangeRelevant(mergeBase, change) {
  if (change.status !== MODIFIED_STATUS || !change.filePath.endsWith(JSON_EXTENSION)) {
    return true; // added, removed or not JSON: the suites copy these folders as they are
  }
  const before = git(['show', `${mergeBase}:${change.filePath}`]);
  const after = git(['show', `HEAD:${change.filePath}`]);
  return withoutVersion(before) !== withoutVersion(after);
}

/**
 * Decides whether the change needs the agent-ready-setup suites.
 *
 * @param {string} eventName The GitHub event that started the workflow, or an empty string.
 * @param {string} baseReference Branch or commit the change is compared against.
 * @returns {{needed: boolean, reason: string}} The decision and why.
 */
function decideAgentReady(eventName, baseReference) {
  if (eventName && eventName !== FILTERED_EVENT) {
    return { needed: true, reason: `event ${eventName} runs every area` };
  }
  let mergeBase;
  let changes;
  try {
    mergeBase = git(['merge-base', baseReference, 'HEAD']).trim();
    changes = changedFiles(mergeBase);
  } catch (gitError) {
    const detail = (gitError.stderr || gitError.message || '').toString().trim();
    return { needed: true, reason: `could not compare against ${baseReference} (${detail}); every area runs` };
  }
  for (const change of changes) {
    if (matchesAny(change.filePath, AGENT_READY_TRIGGER_PATHS)) {
      return { needed: true, reason: `${change.filePath} changed` };
    }
    if (matchesAny(change.filePath, MANIFEST_PATHS)) {
      let isRelevant;
      try {
        isRelevant = isManifestChangeRelevant(mergeBase, change);
      } catch (manifestError) {
        return { needed: true, reason: `could not compare ${change.filePath} (${manifestError.message}); every area runs` };
      }
      if (isRelevant) {
        return { needed: true, reason: `${change.filePath} changed beyond its version` };
      }
    }
  }
  return { needed: false, reason: 'no change under the agent-ready-setup trigger paths' };
}

function main() {
  const baseReference = process.argv[2] || DEFAULT_BASE_REFERENCE;
  const decision = decideAgentReady(process.env.GITHUB_EVENT_NAME || '', baseReference);
  const line = `${AGENT_READY_AREA}=${decision.needed}`;
  console.error(`detect-test-areas: ${AGENT_READY_AREA} ${decision.needed ? 'runs' : 'is skipped'}: ${decision.reason}.`);
  console.log(line);
  if (process.env.GITHUB_OUTPUT) {
    fs.appendFileSync(process.env.GITHUB_OUTPUT, `${line}\n`);
  }
}

if (require.main === module) {
  main();
}

module.exports = { AGENT_READY_TRIGGER_PATHS, MANIFEST_PATHS, decideAgentReady, matchesAny, withoutVersion };
