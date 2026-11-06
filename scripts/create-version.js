#!/usr/bin/env node

'use strict';

/**
 * Interactive plugin version bumper.
 *
 * Updates the `version` field in every provider manifest of a plugin
 * (`.claude-plugin/plugin.json`, `.codex-plugin/plugin.json` and, when present,
 * the portable root `plugin.json` used by Hermes), keeping them in sync, then
 * commits only those manifests and pushes the branch.
 *
 * Usage:
 *   pnpm create-version            -> interactive plugin menu
 *   pnpm create-version <plugin>   -> target a plugin directly by name
 *   pnpm create-version --dry-run | -n   -> preview without writing, committing or pushing
 *   pnpm create-version --bump <kind> | --set <version>   -> skip the version prompt
 *   pnpm create-version --help | -h   -> show usage
 */

const childProcess = require('child_process');
const fs = require('fs');
const path = require('path');
const readline = require('readline');
const { stripVTControlCharacters } = require('util');
const {
  SEMVER_PATTERN,
  discoverPlugins,
  listVersionedManifests,
  readManifest,
} = require('./lib/plugin-manifests');
const {
  fitToTerminal,
  paint,
  renderAlertBanner,
  renderPanel,
  stderrOutput,
  stdoutOutput,
  supportsLineEditing,
  visibleWidth,
} = require('./lib/terminal-output');

const REPOSITORY_ROOT = path.join(__dirname, '..');
const PLUGINS_DIR = path.join(REPOSITORY_ROOT, 'plugins');
const REMOTE_NAME = 'origin';
const DEFAULT_BRANCHES = ['develop', 'master', 'main'];
const DRY_RUN_FLAGS = ['--dry-run', '-n'];
const HELP_FLAGS = ['--help', '-h'];
const BUMP_FLAG = '--bump';
const SET_FLAG = '--set';
const SUPPORTED_OPTIONS = [...DRY_RUN_FLAGS, ...HELP_FLAGS, BUMP_FLAG, SET_FLAG];
const DRY_RUN_BANNER_MESSAGE = '🧪 DRY RUN · nothing will be written, committed or pushed';
const DRY_RUN_COMPLETE_MESSAGE = '🧪 DRY RUN complete · run again without --dry-run to apply';
const VERSION_FIELD_PATTERN = /("version"\s*:\s*")([^"]+)(")/;
/** Matches manifest diff lines that touch the `version` key (POSIX regex for `git log -G`). */
const VERSION_KEY_DIFF_PATTERN = '"version"';

/** Bump kinds offered for semantic version increments. */
const BUMP_KINDS = {
  patch: 'patch',
  minor: 'minor',
  major: 'major',
};

const LINE_BREAK_PATTERN = /\r\n?|\n/;

/**
 * Formats a version transition such as `1.0.0 → 1.0.1`.
 *
 * @param {string} fromVersion Previous version.
 * @param {string} toVersion Next version.
 * @returns {string} Styled transition.
 */
function formatVersionTransition(fromVersion, toVersion) {
  return `${paint('dim', fromVersion)} ${paint('gray', '→')} ${paint('green', paint('bold', toVersion))}`;
}

/**
 * Formats a numbered menu option.
 *
 * @param {number} optionNumber Option number typed by the user.
 * @param {string} label Option label.
 * @returns {string} Styled option line.
 */
function formatMenuOption(optionNumber, label) {
  return `  ${paint('magenta', paint('bold', String(optionNumber).padStart(2)))}  ${label}`;
}

/**
 * Formats an interactive prompt query.
 *
 * @param {string} query Prompt text.
 * @returns {string} Styled prompt.
 */
function formatPrompt(query) {
  return `\n${fitToTerminal(`${paint('cyan', '❯')} ${paint('bold', query)}`)} `;
}

/**
 * Computes the next semantic version for the given bump kind.
 *
 * @param {string} currentVersion Current semver string (MAJOR.MINOR.PATCH).
 * @param {string} bumpKind One of BUMP_KINDS.
 * @returns {string} The next semver string.
 */
function bumpVersion(currentVersion, bumpKind) {
  const [major, minor, patch] = currentVersion.split('.').map(Number);
  switch (bumpKind) {
    case BUMP_KINDS.major:
      return `${major + 1}.0.0`;
    case BUMP_KINDS.minor:
      return `${major}.${minor + 1}.0`;
    case BUMP_KINDS.patch:
      return `${major}.${minor}.${patch + 1}`;
    default:
      throw new Error(`Unknown bump kind: ${bumpKind}`);
  }
}

/**
 * Executes a Git command from repository root and returns stdout.
 *
 * @param {string[]} args Git command arguments.
 * @returns {string} Command stdout.
 */
function runGit(args) {
  try {
    return childProcess.execFileSync('git', args, {
      cwd: REPOSITORY_ROOT,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    });
  } catch (error) {
    const stderr = error.stderr ? String(error.stderr).trim() : '';
    const detail = stderr || error.message;
    throw new Error(`Git command failed: ${detail}`, { cause: error });
  }
}

/**
 * Finds first supported remote base reference available in the repository.
 *
 * @returns {string} Remote base reference, or empty string when none exists.
 */
function getRemoteBaseReference() {
  const candidates = DEFAULT_BRANCHES.map((branchName) => `${REMOTE_NAME}/${branchName}`);

  for (const candidate of candidates) {
    try {
      runGit(['show-ref', '--verify', '--quiet', `refs/remotes/${candidate}`]);
      return candidate;
    } catch (error) {
      // Try next supported base reference.
    }
  }

  return '';
}

/**
 * Returns paths changed in the current branch and working tree, including untracked files.
 *
 * @returns {string[]} Changed repository-relative paths.
 */
function getChangedPaths() {
  const remoteBaseReference = getRemoteBaseReference();
  const committedPaths = remoteBaseReference
    ? runGit(['diff', '--name-only', `${remoteBaseReference}...HEAD`])
    : '';
  const trackedPaths = runGit(['diff', '--name-only', 'HEAD']);
  const untrackedPaths = runGit(['ls-files', '--others', '--exclude-standard']);

  return [
    ...new Set(`${committedPaths}\n${trackedPaths}\n${untrackedPaths}`.split('\n').filter(Boolean)),
  ];
}

/**
 * Converts an absolute path into the repository-relative, slash-separated form Git expects.
 *
 * @param {string} absolutePath Absolute path inside the repository.
 * @returns {string} Repository-relative path.
 */
function toRepositoryPath(absolutePath) {
  return path.relative(REPOSITORY_ROOT, absolutePath).split(path.sep).join('/');
}

/**
 * Finds the last commit that changed the plugin's `version` field.
 *
 * @param {{ claudePath: string }} plugin Plugin descriptor.
 * @returns {string} Commit hash, or empty string when the manifest has no committed version yet.
 */
function getLastVersionChangeCommit(plugin) {
  return runGit([
    'log', '-1', '--format=%H', `-G${VERSION_KEY_DIFF_PATTERN}`, '--', toRepositoryPath(plugin.claudePath),
  ]).trim();
}

/**
 * Detects plugins with committed changes after their last version change, so plugins
 * already merged into the default branch without a bump are still detected there.
 *
 * @param {Array<{ name: string, rootPath: string, claudePath: string }>} plugins Discovered plugins.
 * @returns {string[]} Names of plugins with unreleased commits.
 */
function detectPluginsChangedSinceLastVersion(plugins) {
  return plugins
    .filter((plugin) => {
      const lastVersionChangeCommit = getLastVersionChangeCommit(plugin);
      if (!lastVersionChangeCommit) {
        return false;
      }
      return runGit(['diff', '--name-only', lastVersionChangeCommit, 'HEAD', '--', toRepositoryPath(plugin.rootPath)]).trim() !== '';
    })
    .map((plugin) => plugin.name);
}

/**
 * Detects plugin names changed under `plugins/`, ignoring other paths: changes in the
 * current branch and working tree, plus commits made after each plugin's last version change.
 *
 * @param {Array<{ name: string, claudePath: string }>} plugins Discovered plugins.
 * @returns {string[]} Unique changed plugin names.
 */
function detectChangedPluginNames(plugins) {
  const branchChangedPluginNames = getChangedPaths()
    .map((changedPath) => changedPath.split('/'))
    .filter(([rootDirectory, pluginName]) => rootDirectory === 'plugins' && pluginName)
    .map(([, pluginName]) => pluginName);

  return [...new Set([...branchChangedPluginNames, ...detectPluginsChangedSinceLastVersion(plugins)])];
}

/**
 * Resolves the commit where the current branch forked from the remote base.
 *
 * @returns {string} Merge-base commit, or empty string when no shared history exists.
 */
function getBranchBaseCommit() {
  const remoteBaseReference = getRemoteBaseReference();
  if (!remoteBaseReference) {
    return '';
  }

  try {
    return runGit(['merge-base', remoteBaseReference, 'HEAD']).trim();
  } catch (error) {
    // Unrelated histories have no merge-base; treat every plugin as not bumped.
    return '';
  }
}

/**
 * Reads the Claude manifest version a plugin had at the given commit.
 *
 * @param {string} baseCommit Commit to read the manifest from.
 * @param {{ claudePath: string }} plugin Plugin descriptor.
 * @returns {string} Version at that commit, or empty string when the manifest did not exist there.
 */
function readBaseManifestVersion(baseCommit, plugin) {
  try {
    const parsed = JSON.parse(runGit(['show', `${baseCommit}:${toRepositoryPath(plugin.claudePath)}`]));
    return typeof parsed.version === 'string' ? parsed.version : '';
  } catch (error) {
    // New plugins have no manifest at the base commit, so there is no bump to detect.
    return '';
  }
}

/**
 * Detects changed plugins whose version already differs from the branch base,
 * either in branch commits or in the working tree.
 *
 * @param {Array<{ name: string, claudePath: string }>} plugins Discovered plugins.
 * @param {string[]} changedPluginNames Plugin names detected from branch and working-tree changes.
 * @returns {Map<string, { baseVersion: string, currentVersion: string }>} Bumped plugins by name.
 */
function detectBumpedPlugins(plugins, changedPluginNames) {
  const bumpedPlugins = new Map();
  const baseCommit = getBranchBaseCommit();
  if (!baseCommit) {
    return bumpedPlugins;
  }

  for (const plugin of plugins) {
    if (!changedPluginNames.includes(plugin.name)) {
      continue;
    }
    const baseVersion = readBaseManifestVersion(baseCommit, plugin);
    const currentVersion = readManifest(plugin.claudePath).version;
    if (baseVersion && baseVersion !== currentVersion) {
      bumpedPlugins.set(plugin.name, { baseVersion, currentVersion });
    }
  }

  return bumpedPlugins;
}

/**
 * Rewrites only the `version` field of a manifest, preserving all other
 * formatting (indentation, key order, inline arrays) to keep diffs minimal.
 *
 * @param {string} manifestPath Absolute path to the manifest file.
 * @param {string} rawContents Current raw file contents.
 * @param {string} newVersion Version to write.
 */
function writeManifestVersion(manifestPath, rawContents, newVersion) {
  if (!VERSION_FIELD_PATTERN.test(rawContents)) {
    throw new Error(`Could not locate a "version" field to update in ${manifestPath}`);
  }
  const updated = rawContents.replace(VERSION_FIELD_PATTERN, `$1${newVersion}$3`);
  fs.writeFileSync(manifestPath, updated);
}

/**
 * Builds the version bump commit subject.
 *
 * @param {string} pluginName Selected plugin name.
 * @param {string} currentVersion Previous plugin version.
 * @param {string} newVersion New plugin version.
 * @returns {string} Commit subject.
 */
function buildCommitSubject(pluginName, currentVersion, newVersion) {
  return (
    `Bump the version number from ${currentVersion} to ${newVersion} in all ` +
    `"plugin.json" files for the "${pluginName}" plugin`
  );
}

/**
 * Commits only the updated provider manifests, leaving any other staged or
 * unstaged working-tree changes untouched.
 *
 * @param {string} subject Commit subject.
 * @param {string[]} manifestPaths Absolute paths of the manifests to commit.
 * @returns {{ hash: string, subject: string }} Created commit metadata.
 */
function commitVersionBump(subject, manifestPaths) {
  const commitMessage = `${subject}\n\nCo-Authored-By: Claude Code <noreply@anthropic.com>`;
  const relativeManifestPaths = manifestPaths.map((manifestPath) =>
    path.relative(REPOSITORY_ROOT, manifestPath)
  );

  runGit(['commit', '--only', '-m', commitMessage, '--', ...relativeManifestPaths]);

  return {
    hash: runGit(['rev-parse', '--short', 'HEAD']).trim(),
    subject,
  };
}

/**
 * Checks whether the current branch already tracks an upstream branch.
 *
 * @returns {boolean} True when an upstream is configured.
 */
function hasUpstreamBranch() {
  try {
    runGit(['rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}']);
    return true;
  } catch (error) {
    return false;
  }
}

/**
 * Plans the push for the current branch, including default branches, setting upstream on first push.
 *
 * @returns {{ branchName: string, pushArguments: string[] }} Push plan.
 */
function planPush() {
  const branchName = runGit(['rev-parse', '--abbrev-ref', 'HEAD']).trim();

  return {
    branchName,
    pushArguments: hasUpstreamBranch() ? ['push'] : ['push', '-u', REMOTE_NAME, 'HEAD'],
  };
}

/**
 * Executes a push plan. Never force-pushes.
 *
 * @param {{ branchName: string, pushArguments: string[] }} pushPlan Plan from planPush.
 */
function pushVersionBump({ branchName, pushArguments }) {
  try {
    runGit(pushArguments);
  } catch (error) {
    throw new Error(
      `Version bump commit was created but "git ${pushArguments.join(' ')}" failed for branch ` +
        `"${branchName}". Resolve the issue and push manually. ${error.message}`,
      { cause: error }
    );
  }
}

/**
 * Splits `--flag=value` into its name and inline value.
 *
 * @param {string} cliArgument Raw CLI argument.
 * @returns {{ flagName: string, inlineValue: string | undefined }} Flag parts.
 */
function splitFlag(cliArgument) {
  const separatorIndex = cliArgument.indexOf('=');
  if (!cliArgument.startsWith('--') || separatorIndex === -1) {
    return { flagName: cliArgument, inlineValue: undefined };
  }
  return {
    flagName: cliArgument.slice(0, separatorIndex),
    inlineValue: cliArgument.slice(separatorIndex + 1),
  };
}

/**
 * Parses CLI arguments into a plugin name and supported flags.
 *
 * @param {string[]} cliArguments Arguments after the script path.
 * @returns {{
 *   pluginName: string | undefined,
 *   isDryRun: boolean,
 *   isHelp: boolean,
 *   bumpKind: string | undefined,
 *   exactVersion: string | undefined,
 * }} Parsed options.
 */
function parseCliArguments(cliArguments) {
  const options = {
    pluginName: undefined,
    isDryRun: false,
    isHelp: false,
    bumpKind: undefined,
    exactVersion: undefined,
  };

  for (let argumentIndex = 0; argumentIndex < cliArguments.length; argumentIndex++) {
    const cliArgument = cliArguments[argumentIndex];
    const { flagName, inlineValue } = splitFlag(cliArgument);
    const readFlagValue = () => {
      const flagValue = inlineValue ?? cliArguments[++argumentIndex];
      if (!flagValue || (inlineValue === undefined && flagValue.startsWith('-'))) {
        throw new Error(`Option "${flagName}" requires a value. Run with --help for usage.`);
      }
      return flagValue;
    };

    if (DRY_RUN_FLAGS.includes(flagName)) {
      options.isDryRun = true;
    } else if (HELP_FLAGS.includes(flagName)) {
      options.isHelp = true;
    } else if (flagName === BUMP_FLAG) {
      const bumpKind = readFlagValue();
      if (!Object.values(BUMP_KINDS).includes(bumpKind)) {
        throw new Error(
          `Invalid ${BUMP_FLAG} value "${bumpKind}". Expected one of: ${Object.values(BUMP_KINDS).join(', ')}`
        );
      }
      options.bumpKind = bumpKind;
    } else if (flagName === SET_FLAG) {
      const exactVersion = readFlagValue();
      if (!SEMVER_PATTERN.test(exactVersion)) {
        throw new Error(`Invalid ${SET_FLAG} value "${exactVersion}". Expected MAJOR.MINOR.PATCH.`);
      }
      options.exactVersion = exactVersion;
    } else if (cliArgument.startsWith('-')) {
      throw new Error(`Unknown option "${cliArgument}". Supported options: ${SUPPORTED_OPTIONS.join(', ')}`);
    } else if (options.pluginName) {
      throw new Error(
        `Unexpected argument "${cliArgument}": plugin "${options.pluginName}" was already provided.`
      );
    } else {
      options.pluginName = cliArgument;
    }
  }

  if (options.bumpKind && options.exactVersion) {
    throw new Error(`Options ${BUMP_FLAG} and ${SET_FLAG} cannot be used together.`);
  }

  return options;
}

/**
 * Renders CLI usage help.
 *
 * @returns {string} Rendered help.
 */
function renderHelp() {
  const command = (text) => paint('cyan', text);
  const flag = (text) => paint('magenta', paint('bold', text.padEnd(24)));
  const section = (text) => paint('bold', text);
  const examples = [
    ['pnpm create-version', 'interactive'],
    [`pnpm create-version golfo-kit ${BUMP_FLAG} minor`, 'no prompts'],
    [`pnpm create-version -n ${SET_FLAG} 2.0.0`, 'preview exact version'],
  ];
  const exampleColumnWidth = Math.max(...examples.map(([exampleCommand]) => exampleCommand.length));
  return renderPanel('🌱 create-version · help', [
    section('Usage'),
    `  ${command('pnpm create-version [plugin] [options]')}`,
    '',
    section('Options'),
    `  ${flag('-n, --dry-run')}Preview without writing, committing or pushing`,
    `  ${flag(`${BUMP_FLAG} <kind>`)}Bump without prompting: ${Object.values(BUMP_KINDS).join(' | ')}`,
    `  ${flag(`${SET_FLAG} <version>`)}Set an exact MAJOR.MINOR.PATCH version`,
    `  ${flag('-h, --help')}Show this help`,
    '',
    section('Examples'),
    ...examples.map(
      ([exampleCommand, description]) =>
        `  ${command(exampleCommand.padEnd(exampleColumnWidth))}  ${paint('gray', description)}`
    ),
  ]);
}

/**
 * Resolves the new version from CLI flags, falling back to the interactive menu.
 *
 * @param {(query: string) => Promise<string>} ask Prompt function.
 * @param {string} currentVersion Current synced version.
 * @param {{ bumpKind: string | undefined, exactVersion: string | undefined }} versionOptions CLI version options.
 * @returns {Promise<string>} The validated new version.
 */
async function resolveRequestedVersion(ask, currentVersion, { bumpKind, exactVersion }) {
  if (exactVersion) {
    console.log(fitToTerminal(`\n🎯 Using ${SET_FLAG}: ${formatVersionTransition(currentVersion, exactVersion)}`));
    return exactVersion;
  }
  if (bumpKind) {
    const bumpedVersion = bumpVersion(currentVersion, bumpKind);
    console.log(
      fitToTerminal(
        `\n🎚️  Using ${BUMP_FLAG} ${paint('bold', bumpKind)}: ${formatVersionTransition(currentVersion, bumpedVersion)}`
      )
    );
    return bumpedVersion;
  }
  return resolveNewVersion(ask, currentVersion);
}

/**
 * Builds a promise-based prompt function over a readline interface.
 *
 * Uses a buffered `line` event queue instead of `rl.question` so that
 * multiple sequential prompts work reliably both on an interactive TTY and
 * with redirected stdin (where `rl.question` can drop later answers at EOF).
 *
 * @param {readline.Interface} rl Active readline interface.
 * @returns {(query: string) => Promise<string>} Prompt function returning the trimmed answer.
 */
function createPrompter(rl) {
  const pendingResolvers = [];
  const bufferedLines = [];
  let inputClosed = false;

  rl.on('line', (line) => {
    const resolve = pendingResolvers.shift();
    if (resolve) {
      resolve(line);
    } else {
      bufferedLines.push(line);
    }
  });

  rl.on('close', () => {
    inputClosed = true;
    while (pendingResolvers.length > 0) {
      pendingResolvers.shift()(null);
    }
  });

  return function ask(query) {
    process.stdout.write(query);
    return new Promise((resolve) => {
      if (bufferedLines.length > 0) {
        resolve(bufferedLines.shift());
      } else if (inputClosed) {
        resolve(null);
      } else {
        pendingResolvers.push(resolve);
      }
    }).then((line) => {
      if (line === null) {
        throw new Error('Input ended before an answer was provided.');
      }
      return line.trim();
    });
  };
}

/**
 * Resolves the target plugin from a CLI argument, falling back to an
 * interactive numbered menu.
 *
 * @param {(query: string) => Promise<string>} ask Prompt function.
 * @param {Array} plugins Discovered plugins.
 * @param {string|undefined} requestedName Plugin name passed via CLI.
 * @param {string[]} changedPluginNames Plugin names detected from working-tree changes.
 * @param {Map<string, { baseVersion: string, currentVersion: string }>} bumpedPlugins Changed plugins
 *   whose version already differs from the branch base.
 * @returns {Promise<object>} The selected plugin descriptor.
 */
async function resolvePlugin(ask, plugins, requestedName, changedPluginNames, bumpedPlugins) {
  if (requestedName) {
    const match = plugins.find((plugin) => plugin.name === requestedName);
    if (!match) {
      const available = plugins.map((plugin) => plugin.name).join(', ');
      throw new Error(`Plugin "${requestedName}" not found. Available: ${available}`);
    }
    return match;
  }

  if (bumpedPlugins.size > 0) {
    const bumpedSummaries = [...bumpedPlugins].map(
      ([pluginName, { baseVersion, currentVersion }]) =>
        `${paint('cyan', pluginName)} (${formatVersionTransition(baseVersion, currentVersion)})`
    );
    console.log(fitToTerminal(`\n✅ Already bumped in this branch: ${bumpedSummaries.join(', ')}`));
  }

  const pendingPluginNames = changedPluginNames.filter((pluginName) => !bumpedPlugins.has(pluginName));

  if (pendingPluginNames.length === 1) {
    const [pendingPluginName] = pendingPluginNames;
    const match = plugins.find((plugin) => plugin.name === pendingPluginName);
    if (!match) {
      throw new Error(
        `Plugin "${pendingPluginName}" changed under plugins/ but does not expose both provider manifests.`
      );
    }
    console.log(fitToTerminal(`\n🔍 Detected changed plugin: ${paint('cyan', paint('bold', match.name))}`));
    return match;
  }

  if (plugins.length === 1) {
    const [onlyPlugin] = plugins;
    console.log(fitToTerminal(`\n🔍 Only plugin available: ${paint('cyan', paint('bold', onlyPlugin.name))}`));
    return onlyPlugin;
  }

  if (pendingPluginNames.length > 1) {
    console.log(fitToTerminal(`\n🔍 Detected changed plugins: ${paint('cyan', pendingPluginNames.join(', '))}`));
  }

  const changedMarker = paint('yellow', '● changed');
  const formatPluginLabel = (plugin) => {
    const bumpedPlugin = bumpedPlugins.get(plugin.name);
    if (bumpedPlugin) {
      const bumpedMarker = paint('green', '✔ bumped');
      return `${plugin.name}  ${bumpedMarker} ${formatVersionTransition(bumpedPlugin.baseVersion, bumpedPlugin.currentVersion)}`;
    }
    return changedPluginNames.includes(plugin.name) ? `${plugin.name}  ${changedMarker}` : plugin.name;
  };
  console.log(
    `\n${renderPanel(
      '🧩 Available plugins',
      plugins.map((plugin, index) => formatMenuOption(index + 1, formatPluginLabel(plugin)))
    )}`
  );

  const answer = await ask(formatPrompt('Select a plugin by number:'));
  const selectedIndex = Number(answer) - 1;
  if (!Number.isInteger(selectedIndex) || selectedIndex < 0 || selectedIndex >= plugins.length) {
    throw new Error(`Invalid selection: "${answer}"`);
  }
  return plugins[selectedIndex];
}

/**
 * Prompts for the new version, offering semver bumps or a custom value.
 *
 * @param {(query: string) => Promise<string>} ask Prompt function.
 * @param {string} currentVersion Current synced version.
 * @returns {Promise<string>} The validated new version.
 */
async function resolveNewVersion(ask, currentVersion) {
  const transitionColumnWidth = Math.max(
    ...Object.values(BUMP_KINDS).map((bumpKind) =>
      visibleWidth(formatVersionTransition(currentVersion, bumpVersion(currentVersion, bumpKind)))
    )
  );
  const bumpOption = (emoji, bumpKind, hint) => {
    const transition = formatVersionTransition(currentVersion, bumpVersion(currentVersion, bumpKind));
    const padding = ' '.repeat(transitionColumnWidth - visibleWidth(transition));
    return `${emoji} ${paint('bold', bumpKind.padEnd(8))}${transition}${padding}  ${paint('gray', hint)}`;
  };

  console.log(
    `\n${renderPanel('🎚️  How do you want to set the new version?', [
      formatMenuOption(1, bumpOption('🩹', BUMP_KINDS.patch, 'fixes')),
      formatMenuOption(2, bumpOption('✨', BUMP_KINDS.minor, 'new features')),
      formatMenuOption(3, bumpOption('💥', BUMP_KINDS.major, 'breaking changes')),
      formatMenuOption(4, `🎯 ${paint('bold', 'custom'.padEnd(8))}${paint('gray', 'type an exact version')}`),
    ])}`
  );

  const choice = await ask(formatPrompt('Select an option [1-4]:'));

  switch (choice) {
    case '1':
      return bumpVersion(currentVersion, BUMP_KINDS.patch);
    case '2':
      return bumpVersion(currentVersion, BUMP_KINDS.minor);
    case '3':
      return bumpVersion(currentVersion, BUMP_KINDS.major);
    case '4': {
      const custom = await ask(formatPrompt('Enter the exact version (MAJOR.MINOR.PATCH):'));
      if (!SEMVER_PATTERN.test(custom)) {
        throw new Error(`Invalid semver version: "${custom}"`);
      }
      return custom;
    }
    default:
      throw new Error(`Invalid option: "${choice}"`);
  }
}

/**
 * Renders a failure for stderr. Git output inside the message may carry its own escapes and
 * line breaks, so they are removed and every line gets its own style and panel prefix.
 *
 * @param {Error} error Failure to report.
 * @returns {string} Rendered panel.
 */
function renderFailurePanel(error) {
  const messageLines = stripVTControlCharacters(error.message)
    .split(LINE_BREAK_PATTERN)
    .map((messageLine) => paint('red', messageLine, stderrOutput));
  return renderPanel('❌ create-version failed', messageLines, 'red', stderrOutput);
}

async function main() {
  const cliOptions = parseCliArguments(process.argv.slice(2));
  const { pluginName: requestedName, isDryRun } = cliOptions;

  if (cliOptions.isHelp) {
    console.log(`\n${renderHelp()}\n`);
    return;
  }

  const plugins = discoverPlugins(PLUGINS_DIR);
  const changedPluginNames = detectChangedPluginNames(plugins);

  if (plugins.length === 0) {
    throw new Error('No plugins with both Claude and Codex manifests were found.');
  }

  console.log(
    fitToTerminal(
      `\n🌱 ${paint('green', paint('bold', 'create-version'))} ` +
        paint('gray', '· plugin version bumper for Claude + Codex')
    )
  );
  if (isDryRun) {
    console.log(`\n${renderAlertBanner(DRY_RUN_BANNER_MESSAGE)}`);
  }

  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: supportsLineEditing(stdoutOutput),
  });
  const ask = createPrompter(rl);

  try {
    const bumpedPlugins = requestedName ? new Map() : detectBumpedPlugins(plugins, changedPluginNames);
    const plugin = await resolvePlugin(ask, plugins, requestedName, changedPluginNames, bumpedPlugins);

    const versionedManifestPaths = listVersionedManifests(plugin);
    const manifests = versionedManifestPaths.map((manifestPath) => ({
      path: manifestPath,
      ...readManifest(manifestPath),
    }));
    const [claude] = manifests;
    const mismatchedManifests = manifests.filter((manifest) => manifest.version !== claude.version);

    if (mismatchedManifests.length > 0) {
      const versionSummary = manifests
        .map((manifest) => `${toRepositoryPath(manifest.path)} is ${manifest.version}`)
        .join(', ');
      throw new Error(
        `Version mismatch in "${plugin.name}": ${versionSummary}. Sync them manually before bumping.`
      );
    }

    const syncedBadge = paint(
      'green',
      plugin.portablePath ? '✔ Claude · ✔ Codex · ✔ Portable in sync' : '✔ Claude · ✔ Codex in sync'
    );
    console.log(
      `\n${renderPanel('📦 Plugin', [
        `${paint('gray', 'Name     ')} ${paint('cyan', paint('bold', plugin.name))}`,
        `${paint('gray', 'Version  ')} ${paint('bold', claude.version)}  ${syncedBadge}`,
      ])}`
    );

    const newVersion = await resolveRequestedVersion(ask, claude.version, cliOptions);

    if (newVersion === claude.version) {
      throw new Error(`New version "${newVersion}" matches the current version.`);
    }

    const subject = buildCommitSubject(plugin.name, claude.version, newVersion);
    const versionHeadline =
      `${paint('cyan', paint('bold', plugin.name))}  ${formatVersionTransition(claude.version, newVersion)}`;
    const manifestPaths = versionedManifestPaths.map((manifestPath) =>
      // Forward slashes keep the output identical on Windows, where path.sep is a backslash.
      paint('dim', path.relative(process.cwd(), manifestPath).split(path.sep).join('/'))
    );

    if (isDryRun) {
      const pushPlan = planPush();
      const pushLine =
        `🚀 Would push "${paint('cyan', pushPlan.branchName)}" to ${REMOTE_NAME} ` +
        paint('gray', `(git ${pushPlan.pushArguments.join(' ')})`);

      console.log(
        `\n${renderPanel(
          '🧪 Dry run · no changes were made',
          [
            versionHeadline,
            '',
            ...manifestPaths.map((manifestPath) => `📝 Would update ${manifestPath}`),
            `🔖 Would commit only the plugin manifests: ${subject}`,
            pushLine,
          ],
          'yellow'
        )}`
      );
      console.log(`\n${renderAlertBanner(DRY_RUN_COMPLETE_MESSAGE)}\n`);
      return;
    }

    manifests.forEach((manifest) => writeManifestVersion(manifest.path, manifest.raw, newVersion));

    const commit = commitVersionBump(subject, versionedManifestPaths);

    console.log(
      `\n${renderPanel(
        '✅ Version bumped',
        [
          versionHeadline,
          '',
          ...manifestPaths.map((manifestPath) => `📝 ${manifestPath}`),
          `🔖 Created commit ${paint('yellow', commit.hash)}: ${commit.subject}`,
        ],
        'green'
      )}`
    );

    const pushPlan = planPush();
    pushVersionBump(pushPlan);
    console.log(fitToTerminal(`\n🚀 Pushed "${paint('cyan', pushPlan.branchName)}" to ${REMOTE_NAME}\n`));
  } finally {
    rl.close();
  }
}

main().catch((error) => {
  console.error(`\n${renderFailurePanel(error)}\n`);
  process.exit(1);
});
