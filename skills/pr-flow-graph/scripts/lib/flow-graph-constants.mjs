/**
 * Vocabulary of the flow graph model: the contract shared by the validator and the renderers.
 * `references/flow-graph-schema.md` documents each value for the agent that writes the model.
 */

export const FLOW_GRAPH_SCHEMA_VERSION = 1;

/** Role a node plays in the architecture. */
export const NODE_KINDS = [
  'view',
  'action',
  'dispatcher',
  'store',
  'state',
  'effect',
  'service',
  'external',
  'data',
  'other',
];

/** Relationship an edge represents between two nodes. */
export const EDGE_KINDS = [
  'calls',
  'dispatches',
  'updates',
  'observes',
  'navigates',
  'requests',
  'other',
];

/** Reader-facing name of each node kind, edge kind and business state kind. */
export const KIND_LABELS = {
  view: 'Vista',
  action: 'Acción',
  dispatcher: 'Dispatcher',
  store: 'Store',
  state: 'Estado',
  effect: 'Efecto',
  service: 'Servicio',
  external: 'Sistema externo',
  data: 'Datos',
  other: 'Otro',
  calls: 'llama',
  dispatches: 'despacha',
  updates: 'actualiza',
  observes: 'observa',
  navigates: 'navega',
  requests: 'consulta',
  initial: 'Estado inicial',
  normal: 'Estado',
  success: 'Éxito',
  error: 'Error',
  terminal: 'Estado final',
};

/** What the pull request did to an element. */
export const CHANGE_STATUS = {
  added: 'added',
  modified: 'modified',
  removed: 'removed',
  unchanged: 'unchanged',
};
export const CHANGE_STATUSES = Object.values(CHANGE_STATUS);

/** `verified`: the relationship is written in the code. `inferred`: the agent deduced it. */
export const CONFIDENCE = {
  verified: 'verified',
  inferred: 'inferred',
};
export const CONFIDENCE_LEVELS = Object.values(CONFIDENCE);

/** Role of a state in the business flow. */
export const BUSINESS_STATE_KIND = {
  initial: 'initial',
  normal: 'normal',
  success: 'success',
  error: 'error',
  terminal: 'terminal',
};
export const BUSINESS_STATE_KINDS = Object.values(BUSINESS_STATE_KIND);

/** Side of the diff an evidence line belongs to: `base` is before the pull request, `head` after. */
export const EVIDENCE_SIDE = {
  base: 'base',
  head: 'head',
};
export const EVIDENCE_SIDES = Object.values(EVIDENCE_SIDE);

/** Where a ref of the pull request is looked up when the clone has no local branch for it. */
export const GIT_REMOTE_REF_PREFIX = 'origin/';

/** Severity of a validation finding. Only errors block the render. */
export const FINDING_SEVERITY = {
  error: 'error',
  warning: 'warning',
};

export const IDENTIFIER_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

/** Process exit codes of the CLI. */
export const EXIT_CODE = {
  success: 0,
  invalidModel: 1,
  usage: 2,
};

/** Browser libraries the rendered page loads, pinned so a regenerated graph looks the same. */
export const BROWSER_LIBRARIES = [
  {
    name: 'elkjs',
    version: '0.12.1',
    url: 'https://cdn.jsdelivr.net/npm/elkjs@0.12.1/lib/elk.bundled.js',
  },
];

export const OUTPUT_FILE_NAMES = {
  html: 'pr-flow-graph.html',
  mermaid: 'pr-flow-graph.md',
  report: 'pr-flow-graph-report.md',
};

/** Outcome of one verification step; the page and the report show it next to the graph. */
export const CHECK_STATUS = {
  passed: 'passed',
  skipped: 'skipped',
  warning: 'warning',
};

/** Identifier of each verification step `render` records. */
export const CHECK_ID = {
  modelShape: 'model-shape',
  evidenceExists: 'evidence-exists',
  changeMatchesDiff: 'change-matches-diff',
  relationshipNamesEndpoint: 'relationship-names-endpoint',
  diffCoverage: 'diff-coverage',
  formalModel: 'formal-model',
  outputs: 'outputs',
};

/** Lines read above and below an evidence line when looking for the name of a piece of code. */
export const EVIDENCE_CONTEXT_LINE_COUNT = 2;
/** Shorter words of a label (`get`, `put`, `id`) appear in almost any line, so they prove nothing. */
export const NAME_TOKEN_MIN_LENGTH = 3;
/** From this length a word of a label also counts when it is part of a longer identifier. */
export const NAME_TOKEN_SUBSTRING_MIN_LENGTH = 5;
/** Files listed in one message before the rest is summarised as a count. */
export const LISTED_FILES_LIMIT = 15;

/** Placeholders of `assets/flow-graph-template.html` replaced at render time. */
export const TEMPLATE_PLACEHOLDER = {
  title: '__FLOW_GRAPH_TITLE__',
  model: '__FLOW_GRAPH_MODEL_JSON__',
  libraries: '<!-- __FLOW_GRAPH_LIBRARIES__ -->',
};

export const GITHUB_PULL_REQUEST_URL_PATTERN = /^https:\/\/github\.com\/[^/\s]+\/[^/\s]+\/pull\/\d+$/;

/** Words that make Lean accept a file without proving it; a model that uses them is not shown. */
export const LEAN_UNPROVEN_KEYWORDS = ['sorry', 'admit', 'axiom'];
export const LEAN_DEFAULT_COMMAND = 'lean';
export const LEAN_CHECK_TIMEOUT_MS = 120_000;

export const LEAN_STATUS = {
  compiled: 'compiled',
  incomplete: 'incomplete',
  notInstalled: 'not-installed',
  unproven: 'unproven',
  failed: 'failed',
};
