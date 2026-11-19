/**
 * Read-only Git queries used to anchor coverage to history: HEAD, dirty
 * paths (staged, unstaged and untracked), reachability of an old baseline
 * commit and the commits that touched a set of paths. Nothing here fetches
 * or needs network access; without Git the engine still works on content
 * fingerprints and reports the missing history.
 */
import { execFileSync } from 'node:child_process';

/**
 * @param {string} cwd
 * @param {string[]} args
 * @returns {{ ok: boolean, stdout: string }}
 */
function runGit(cwd, args) {
  try {
    const stdout = execFileSync('git', ['-C', cwd, ...args], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024, stdio: ['ignore', 'pipe', 'pipe'] });
    return { ok: true, stdout };
  } catch {
    return { ok: false, stdout: '' };
  }
}

/**
 * Finds the repository root that contains `directory`.
 *
 * @param {string} directory
 * @returns {string | undefined}
 */
export function findRepositoryRoot(directory) {
  const result = runGit(directory, ['rev-parse', '--show-toplevel']);
  return result.ok ? result.stdout.trim() : undefined;
}

/**
 * Opens the Git view of a project. Every method degrades to `undefined` or
 * an empty result outside a repository.
 *
 * @param {string} projectRoot
 */
export function openGitRepository(projectRoot) {
  const isRepository = runGit(projectRoot, ['rev-parse', '--git-dir']).ok;
  let dirtyPathsCache;

  return {
    isRepository,

    /** @returns {string | undefined} Full SHA of HEAD (undefined before the first commit). */
    head() {
      const result = runGit(projectRoot, ['rev-parse', '--verify', '--quiet', 'HEAD']);
      return result.ok ? result.stdout.trim() : undefined;
    },

    /** @returns {string | undefined} Current branch name, undefined when detached. */
    branch() {
      const result = runGit(projectRoot, ['symbolic-ref', '--quiet', '--short', 'HEAD']);
      return result.ok ? result.stdout.trim() : undefined;
    },

    /**
     * Tracked and untracked (not ignored) files, so new files that were never
     * staged are visible to discovery and resolution.
     *
     * @returns {string[] | undefined} POSIX paths, or undefined outside Git.
     */
    listFiles() {
      if (!isRepository) return undefined;
      const result = runGit(projectRoot, ['ls-files', '-z', '--cached', '--others', '--exclude-standard']);
      return result.ok ? [...new Set(result.stdout.split('\0').filter(Boolean))] : undefined;
    },

    /**
     * Paths whose working-tree content differs from HEAD: staged, unstaged,
     * untracked, deleted and both sides of a rename.
     *
     * @param {{ refresh?: boolean }} [options]
     * @returns {Set<string>}
     */
    dirtyPaths(options = {}) {
      if (dirtyPathsCache && !options.refresh) return dirtyPathsCache;
      const dirty = new Set();
      if (isRepository) {
        const result = runGit(projectRoot, ['status', '--porcelain=v1', '-z', '--untracked-files=all', '--no-renames']);
        for (const record of result.stdout.split('\0')) {
          if (record.length > 3) dirty.add(record.slice(3));
        }
      }
      dirtyPathsCache = dirty;
      return dirty;
    },

    /**
     * Describes how an old baseline commit relates to HEAD.
     *
     * @param {string | undefined} commit
     * @returns {'same' | 'ancestor' | 'diverged' | 'unreachable' | 'unknown'}
     */
    relationToHead(commit) {
      if (!isRepository || !commit) return 'unknown';
      if (!runGit(projectRoot, ['cat-file', '-e', `${commit}^{commit}`]).ok) return 'unreachable';
      const head = this.head();
      if (!head) return 'unknown';
      if (head === commit) return 'same';
      return runGit(projectRoot, ['merge-base', '--is-ancestor', commit, head]).ok ? 'ancestor' : 'diverged';
    },

    /**
     * Commits after `commit` that touched any of `paths` (one line each).
     *
     * @param {string} commit
     * @param {string[]} paths
     * @returns {string[]}
     */
    commitsTouching(commit, paths) {
      if (!paths.length) return [];
      const result = runGit(projectRoot, ['log', '--oneline', '--no-decorate', `${commit}..HEAD`, '--', ...paths]);
      return result.ok ? result.stdout.split('\n').filter(Boolean) : [];
    },

    /**
     * Patch between a commit and the working tree for the given paths.
     *
     * @param {string} commit
     * @param {string[]} paths
     * @returns {string}
     */
    patchSince(commit, paths) {
      if (!paths.length) return '';
      return runGit(projectRoot, ['diff', commit, '--', ...paths]).stdout;
    },
  };
}
