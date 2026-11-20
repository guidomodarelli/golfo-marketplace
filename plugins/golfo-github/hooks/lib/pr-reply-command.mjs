/**
 * Reconoce qué invocaciones de `gh` de un comando (Bash o PowerShell) publican o editan una
 * respuesta en un PR de GitHub y junta, para cada una, los textos donde puede estar su body: la
 * propia invocación, los archivos que lee y las variables que usa, si el comando las asigna.
 * El comando no se ejecuta ni se expande.
 */
import { readFileSync } from 'node:fs';
import { posix, win32 } from 'node:path';
import { SEGMENT_TYPE, SHELL, splitCommandSegments } from './shell-segments.mjs';

/** Qué tipo de escritura hace una invocación. */
export const COMMAND_KIND = {
  /** No publica nada en un PR, o publica algo que no responde a otro comentario. */
  none: 'none',
  /** Responde en un hilo de review: siempre es una respuesta. */
  threadReply: 'thread-reply',
  /** Crea o edita un comentario que responde a otro (comentario general, edición o review). */
  commentReply: 'comment-reply',
};

/** Tamaño máximo de un archivo de body que se lee, para no cargar un archivo enorme por error. */
export const MAX_BODY_FILE_BYTES = 1024 * 1024;

/** Largo máximo con que se muestra una invocación en el motivo del rechazo. */
export const INVOCATION_LABEL_MAX_LENGTH = 100;

const MAX_VARIABLE_DEPTH = 5;
const PATH_SEGMENT = String.raw`[^/\s"'\x60]+`;
const WRITE_FLAG_PATTERN = /(^|\s)["']?(-f|-F|--field|--raw-field|--input)(\s|=)|(-X\s*|--method[=\s]+)(POST|PATCH|PUT)\b/i;

const THREAD_REPLY_PATTERNS = [
  new RegExp(String.raw`pulls/${PATH_SEGMENT}/comments/${PATH_SEGMENT}/replies\b`),
  /\baddPullRequestReviewThreadReply\b/,
];
const REVIEW_COMMENT_CREATE_PATTERN = new RegExp(String.raw`pulls/${PATH_SEGMENT}/comments(?![/\w])`);
const IN_REPLY_TO_PATTERN = /\bin_reply_to\b|\binReplyTo\b/;
const REVIEW_COMMENT_GRAPHQL_PATTERN = /\baddPullRequestReviewComment\b/;

const COMMENT_WRITE_PATTERNS = [
  new RegExp(String.raw`pulls/comments/${PATH_SEGMENT}`),
  new RegExp(String.raw`issues/${PATH_SEGMENT}/comments(?![/\w])`),
  new RegExp(String.raw`issues/comments/${PATH_SEGMENT}`),
  new RegExp(String.raw`pulls/${PATH_SEGMENT}/reviews/${PATH_SEGMENT}(?![/\w])`),
];
/** Flags de `gh` (con o sin valor) que pueden ir antes o entre los subcomandos, como `--repo o/r`. */
const GH_FLAGS = String.raw`(?:\s+--?[\w-]+(?:=\S+|\s+(?!-)[^\s;&|]+)?)*`;
const GH_COMMENT_SUBCOMMAND_PATTERN = new RegExp(String.raw`^gh(?:\.exe)?${GH_FLAGS}\s+(?:pr|issue)${GH_FLAGS}\s+comment\b`);
const COMMENT_GRAPHQL_PATTERN = /\b(updatePullRequestReviewComment|addComment|updateIssueComment|updatePullRequestReview)\b/;

/**
 * Señales de que un comentario responde a otro: la línea que pide el Auto-fix de la app de
 * escritorio, un link a un comentario, review o hilo, o el id del comentario respondido.
 */
const REPLY_SIGNAL_PATTERNS = [
  /addressed by \[claude code\]/i,
  /#discussion_r\d+|#issuecomment-\d+|#pullrequestreview-\d+/,
  IN_REPLY_TO_PATTERN,
];

const PATH_TOKEN = String.raw`(?<path>"[^"]+"|'[^']+'|[^\s"'\x60;|&()]+)`;
const BODY_FILE_PATTERNS = [
  // Campo citado entero: -F "body=@/tmp/reply body.md".
  /(?<quote>["'])[A-Za-z_]+=@(?<path>(?:(?!\k<quote>)[^\n])+)\k<quote>/g,
  new RegExp(String.raw`(?<!["'\w])[A-Za-z_]+=@${PATH_TOKEN}`, 'g'),
  new RegExp(String.raw`--input(?:=|\s+)${PATH_TOKEN}`, 'g'),
  new RegExp(String.raw`--body-file(?:=|\s+)${PATH_TOKEN}`, 'g'),
  new RegExp(String.raw`\$\(\s*(?:cat\s+|<\s*)${PATH_TOKEN}\s*\)`, 'g'),
  new RegExp(String.raw`\b(?:Get-Content|gc)\s+(?:-(?:Raw|Path|LiteralPath|Encoding\s+\S+)\s+)*${PATH_TOKEN}`, 'gi'),
  new RegExp(String.raw`ReadAllText\(\s*${PATH_TOKEN}`, 'g'),
];
const GH_COMMENT_BODY_FILE_PATTERN = new RegExp(String.raw`\s-F\s+${PATH_TOKEN}`, 'g');
const VARIABLE_REFERENCE_PATTERN = /\$\{?([A-Za-z_]\w*)\}?/g;
const BODY_VARIABLE_PATTERN = /(?:body=@?|--body(?:-file)?(?:=|\s+)|(?:^|\s)-b\s+)["']?[^\s"']*?\$\{?([A-Za-z_]\w*)/g;
const STDIN_PATH = '-';
const UNRESOLVED_EXPANSION_PATTERN = /[$`%]/;
const GIT_BASH_DRIVE_PATTERN = /^\/([a-zA-Z])\//;
const HOME_PREFIX_PATTERN = /^(~|\$HOME|\$\{HOME\}|\$env:USERPROFILE|\$env:HOME)(?=[/\\]|$)/i;

/**
 * Quita las comillas que envuelven un token de ruta.
 *
 * @param {string} token Token tal como aparece en el comando.
 * @returns {string} Ruta sin comillas.
 */
function unquote(token) {
  const quoted = (token.startsWith('"') && token.endsWith('"')) || (token.startsWith("'") && token.endsWith("'"));
  return quoted ? token.slice(1, -1) : token;
}

/**
 * Lista las rutas de archivo de donde un texto de comando lee el body.
 *
 * @param {string} command Invocación o asignación.
 * @returns {string[]} Rutas sin resolver, sin repetir.
 */
export function findBodyFilePaths(command) {
  const patterns = GH_COMMENT_SUBCOMMAND_PATTERN.test(command.trimStart())
    ? [...BODY_FILE_PATTERNS, GH_COMMENT_BODY_FILE_PATTERN]
    : BODY_FILE_PATTERNS;
  const paths = patterns.flatMap((pattern) => [...command.matchAll(pattern)].map((match) => unquote(match.groups.path)));
  // Un token con salto de línea es un here-string de PowerShell (`body=@'…'@`): el body va en el comando.
  return [...new Set(paths)].filter((path) => path !== STDIN_PATH && !path.includes('=') && !path.includes('\n'));
}

/**
 * Convierte una ruta del comando en una ruta del sistema de archivos.
 *
 * @param {string} rawPath Ruta tal como la escribió el comando.
 * @param {{ cwd: string, platform: string, homeDirectory: string }} context Directorio, plataforma y home.
 * @returns {string | null} Ruta resuelta, o `null` si depende de una variable que no se puede expandir.
 */
export function resolveBodyFilePath(rawPath, { cwd, platform, homeDirectory }) {
  let path = rawPath.replace(HOME_PREFIX_PATTERN, homeDirectory);
  if (UNRESOLVED_EXPANSION_PATTERN.test(path)) {
    return null;
  }
  const pathModule = platform === 'win32' ? win32 : posix;
  if (platform === 'win32') {
    path = path.replace(GIT_BASH_DRIVE_PATTERN, (_match, drive) => `${drive.toUpperCase()}:/`);
  }
  return pathModule.isAbsolute(path) ? path : pathModule.join(cwd, path);
}

/**
 * Junta todos los strings de un valor JSON, para leer el body de un `--input` con escapes `\uXXXX`.
 *
 * @param {unknown} value Valor JSON ya parseado.
 * @returns {string[]} Strings encontrados.
 */
function collectJsonStrings(value) {
  if (typeof value === 'string') {
    return [value];
  }
  if (Array.isArray(value)) {
    return value.flatMap(collectJsonStrings);
  }
  if (value !== null && typeof value === 'object') {
    return Object.values(value).flatMap(collectJsonStrings);
  }
  return [];
}

/**
 * Lee un archivo de body. Si es JSON, suma sus strings ya decodificados.
 *
 * @param {string} path Ruta resuelta.
 * @returns {string[]} Textos del archivo.
 */
function readBodyFile(path) {
  const content = readFileSync(path);
  if (content.length > MAX_BODY_FILE_BYTES) {
    throw new Error(`supera ${MAX_BODY_FILE_BYTES} bytes`);
  }
  const text = content.toString('utf8');
  try {
    return [text, ...collectJsonStrings(JSON.parse(text))];
  } catch {
    return [text];
  }
}

/**
 * Decide qué tipo de escritura hace una invocación de `gh`, ya sumados sus bodies.
 *
 * @param {string} invocation Texto de la invocación.
 * @param {string} combinedText Invocación más sus archivos y variables de body.
 * @returns {string} Un valor de {@link COMMAND_KIND}.
 */
function classify(invocation, combinedText) {
  const isCommentSubcommand = GH_COMMENT_SUBCOMMAND_PATTERN.test(invocation.trimStart());
  const writes = WRITE_FLAG_PATTERN.test(invocation) || isCommentSubcommand;
  const isGraphqlMutation = /\bmutation\b/.test(combinedText);
  const createsThreadReply = THREAD_REPLY_PATTERNS.some((pattern) => pattern.test(combinedText))
    || ((REVIEW_COMMENT_CREATE_PATTERN.test(combinedText) || REVIEW_COMMENT_GRAPHQL_PATTERN.test(combinedText))
      && IN_REPLY_TO_PATTERN.test(combinedText));
  if (createsThreadReply && (writes || isGraphqlMutation)) {
    return COMMAND_KIND.threadReply;
  }
  const writesComment = (writes && COMMENT_WRITE_PATTERNS.some((pattern) => pattern.test(combinedText)))
    || isCommentSubcommand
    || (isGraphqlMutation && COMMENT_GRAPHQL_PATTERN.test(combinedText));
  if (writesComment && REPLY_SIGNAL_PATTERNS.some((pattern) => pattern.test(combinedText))) {
    return COMMAND_KIND.commentReply;
  }
  return COMMAND_KIND.none;
}

/**
 * Junta los textos de un tramo: el propio texto, los archivos que lee y, de forma transitiva, lo
 * asignado a las variables que usa.
 *
 * @param {string} text Texto del tramo.
 * @param {Map<string, string[]>} assignments Textos asignados a cada variable del comando.
 * @param {object} context Directorio, plataforma y home.
 * @param {Set<string>} visitedVariables Variables ya sumadas, para no entrar en ciclos.
 * @param {number} depth Profundidad actual de variables anidadas.
 * @returns {{ texts: string[], unreadablePaths: string[] }} Textos y rutas que no se pudieron leer.
 */
function collectSegmentTexts(text, assignments, context, visitedVariables, depth) {
  const texts = [text];
  const unreadablePaths = [];
  for (const rawPath of findBodyFilePaths(text)) {
    const resolvedPath = resolveBodyFilePath(rawPath, context);
    if (resolvedPath === null) {
      unreadablePaths.push(rawPath);
      continue;
    }
    try {
      texts.push(...readBodyFile(resolvedPath));
    } catch {
      unreadablePaths.push(rawPath);
    }
  }
  if (depth >= MAX_VARIABLE_DEPTH) {
    return { texts, unreadablePaths };
  }
  for (const [, variableName] of text.matchAll(VARIABLE_REFERENCE_PATTERN)) {
    if (visitedVariables.has(variableName) || !assignments.has(variableName)) {
      continue;
    }
    visitedVariables.add(variableName);
    for (const assignedText of assignments.get(variableName)) {
      const nested = collectSegmentTexts(assignedText, assignments, context, visitedVariables, depth + 1);
      texts.push(...nested.texts);
      unreadablePaths.push(...nested.unreadablePaths);
    }
  }
  return { texts, unreadablePaths };
}

/**
 * Analiza un comando antes de que se ejecute y devuelve solo las invocaciones de `gh` que
 * publican o editan una respuesta, cada una con sus propios textos de body.
 *
 * @param {string} command Comando del tool Bash o PowerShell.
 * @param {{ cwd: string, platform: string, homeDirectory: string, shell?: string }} context Directorio,
 *   plataforma, home y shell (`bash` por defecto).
 * @returns {{ kind: string, label: string, texts: string[], unreadablePaths: string[] }[]} Una entrada por
 *   invocación que responde en un PR.
 */
export function analyzeCommand(command, context) {
  const segments = splitCommandSegments(command, context.shell ?? SHELL.bash);
  const assignments = new Map();
  for (const segment of segments.filter((candidate) => candidate.type === SEGMENT_TYPE.variableAssignment)) {
    assignments.set(segment.name, [...(assignments.get(segment.name) ?? []), segment.text]);
  }
  const replies = [];
  for (const segment of segments.filter((candidate) => candidate.type === SEGMENT_TYPE.ghInvocation)) {
    const { texts, unreadablePaths } = collectSegmentTexts(segment.text, assignments, context, new Set(), 0);
    const kind = classify(segment.text, texts.join('\n'));
    if (kind === COMMAND_KIND.none) {
      continue;
    }
    for (const [, variableName] of segment.text.matchAll(BODY_VARIABLE_PATTERN)) {
      if (!assignments.has(variableName)) {
        unreadablePaths.push(`$${variableName}`);
      }
    }
    const firstLine = segment.text.trim().split('\n')[0];
    const label = firstLine.length > INVOCATION_LABEL_MAX_LENGTH
      ? `${firstLine.slice(0, INVOCATION_LABEL_MAX_LENGTH)}…`
      : firstLine;
    replies.push({ kind, label, texts, unreadablePaths: [...new Set(unreadablePaths)] });
  }
  return replies;
}
