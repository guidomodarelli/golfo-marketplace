/**
 * Shared vocabulary of the skill coverage engine: storage layout, schema
 * versions, coverage states and limits. Every module imports these values
 * instead of repeating literals, so the on-disk contract lives in one place.
 */

/** Version of every JSON document the engine writes (config, units, records, runs). */
export const SCHEMA_VERSION = 1;

/** Version of the symbol analysis algorithm; part of each fingerprint. */
export const ANALYZER_VERSION = 'babel-tokens/1';

/** Analyzer label used when a file is hashed as a whole (no parser or non-JS file). */
export const FILE_LEVEL_ANALYZER = 'file-level/1';

/** Directory, relative to the consumer repository root, that holds the coverage registry. */
export const COVERAGE_DIRECTORY = '.golfo/skill-coverage';

export const REGISTRY_PATHS = {
  config: 'config.json',
  gitignore: '.gitignore',
  pending: '.pending',
  records: 'records',
  runs: 'runs',
  units: 'units',
};

/** Results an execution can register. */
export const EXECUTION_RESULTS = ['verified', 'partial', 'blocked', 'not-applicable'];

/** Coverage states shown for a unit and a skill. */
export const COVERAGE_STATES = ['verified', 'partial', 'blocked', 'unreviewed', 'not-applicable', 'unknown'];

/** Freshness of a coverage attempt, computed on every read and never stored. */
export const FRESHNESS = { current: 'current', stale: 'stale', unknown: 'unknown' };

export const EXECUTION_MODES = ['full', 'incremental', 'lightweight'];

/** Decisions `check` can return before a skill runs. */
export const DECISIONS = { full: 'full', incremental: 'incremental', notApplicable: 'not-applicable', skip: 'skip' };

export const UNIT_KINDS = ['ui-flow', 'api', 'job', 'webhook', 'backend'];

export const ENTRY_ROLES = ['ui', 'server', 'contract'];

export const EVIDENCE_KINDS = ['review', 'test', 'browser', 'accessibility', 'measurement', 'command', 'other'];

export const EVIDENCE_OUTCOMES = ['pass', 'fail', 'measured', 'skipped'];

/** Prefixes of the input keys that do not name a project file: an npm package and an import nobody could resolve. */
export const INPUT_KEY_PREFIXES = { package: 'pkg:', unresolved: 'unresolved:' };

/** Extensions parsed as JavaScript or TypeScript modules. */
export const SOURCE_EXTENSIONS = ['.ts', '.tsx', '.mts', '.cts', '.js', '.jsx', '.mjs', '.cjs'];

/** Extensions probed, in order, when an import specifier has none. */
export const RESOLUTION_EXTENSIONS = ['.ts', '.tsx', '.mts', '.js', '.jsx', '.mjs', '.cjs', '.json'];

/**
 * Package metadata files, relative to the project root, that the module
 * resolver reads package versions from. A change to any of them can change
 * every `pkg:` input, so units with package inputs depend on all of them.
 */
export const PACKAGE_METADATA_FILES = { manifest: 'package.json', npmLockfile: 'package-lock.json', pnpmLockfile: 'pnpm-lock.yaml' };

/** Paths never read as inputs: the registry itself and generated or vendored trees. */
export const ALWAYS_IGNORED_PREFIXES = ['.golfo/', '.git/', 'node_modules/', '.next/', '.open-next/', '.wrangler/', 'coverage/', 'dist/', 'build/'];

/** Hex characters kept from each SHA-256 entry hash. */
export const ENTRY_HASH_LENGTH = 16;

/** Pending runs older than this are reported by `validate` and cleaned by `begin`. */
export const PENDING_RUN_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

export const LOCK_TIMEOUT_MS = 15_000;
export const LOCK_STALE_MS = 60_000;
export const LOCK_RETRY_MS = 40;
export const RENAME_RETRY_COUNT = 5;

/** Limits that keep a single unit's input closure bounded. */
export const MAX_UNIT_INPUT_ENTRIES = 6000;

/** Default timeout of a command executed by `evidence --exec`. */
export const EVIDENCE_COMMAND_TIMEOUT_MS = 20 * 60 * 1000;

/** Maximum characters kept from any free text stored in the registry. */
export const MAX_STORED_TEXT_LENGTH = 600;

/** Share of changed parts above which an incremental review becomes a full one. */
export const FULL_REVIEW_CHANGE_RATIO = 0.6;

export const EXIT_CODES = { failure: 1, ok: 0, refused: 3, usage: 2 };

/** Next.js App Router files that define what a route segment shows while loading or failing. */
export const ROUTE_BOUNDARY_FILES = ['loading', 'error', 'not-found', 'template'];

/**
 * Next.js App Router files of a segment that wrap, replace or complete what
 * the routes below it render: shared chrome, remount, loading, error,
 * missing or forbidden resources, and the fallback of a parallel route slot.
 */
export const NEXT_SEGMENT_FILES = ['layout', 'template', 'loading', 'error', 'not-found', 'forbidden', 'unauthorized', 'default'];

/** Next.js files that only apply at the root of the app directory. */
export const NEXT_ROOT_SEGMENT_FILES = ['global-error', 'global-not-found'];

/** Extensions a Next.js segment file can have. */
export const NEXT_SEGMENT_FILE_EXTENSIONS = ['.tsx', '.jsx', '.ts', '.js'];

/**
 * Project files that configure rendering, caching or navigation of every
 * route (`proxy` is the Next.js 16 name of `middleware`), with the
 * directories, relative to the project root, where Next.js looks for them.
 */
export const NEXT_PROJECT_FILES = [
  { directories: [''], extensions: ['.ts', '.mts', '.mjs', '.js', '.cjs'], name: 'next.config' },
  { directories: ['', 'src/'], extensions: ['.ts', '.js'], name: 'middleware' },
  { directories: ['', 'src/'], extensions: ['.ts', '.js'], name: 'proxy' },
];
