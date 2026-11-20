/**
 * Reconoce si un comando de shell (Bash o PowerShell) publica o edita una respuesta en un PR de
 * GitHub y junta los textos donde puede estar el body: el propio comando y los archivos que lee.
 * El comando no se ejecuta ni se expande: un body que depende de una variable no se puede leer.
 */
import { readFileSync } from 'node:fs';
import { posix, win32 } from 'node:path';

/** Qué tipo de escritura hace el comando. */
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

const PATH_SEGMENT = String.raw`[^/\s"'\x60]+`;
const GH_COMMAND_PATTERN = /(^|[\s;&|(`'"])gh(\.exe)?\s/;
const WRITE_FLAG_PATTERN = /(^|\s)(-f|-F|--field|--raw-field|--input)(\s|=)|(-X\s*|--method[=\s]+)(POST|PATCH|PUT)\b/i;

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
const GH_COMMENT_SUBCOMMAND_PATTERN = /\bgh(\.exe)?\s+(pr|issue)\s+comment\b/;
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

const PATH_TOKEN = String.raw`("[^"]+"|'[^']+'|[^\s"'\x60;|&()]+)`;
const BODY_FILE_PATTERNS = [
  new RegExp(String.raw`[A-Za-z_]+=@${PATH_TOKEN}`, 'g'),
  new RegExp(String.raw`--input(?:=|\s+)${PATH_TOKEN}`, 'g'),
  new RegExp(String.raw`--body-file(?:=|\s+)${PATH_TOKEN}`, 'g'),
  new RegExp(String.raw`\$\(\s*(?:cat\s+|<\s*)${PATH_TOKEN}\s*\)`, 'g'),
  new RegExp(String.raw`\b(?:Get-Content|gc)\s+(?:-(?:Raw|Path|LiteralPath|Encoding\s+\S+)\s+)*${PATH_TOKEN}`, 'gi'),
  new RegExp(String.raw`ReadAllText\(\s*${PATH_TOKEN}`, 'g'),
];
const GH_COMMENT_BODY_FILE_PATTERN = new RegExp(String.raw`\s-F\s+${PATH_TOKEN}`, 'g');
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
 * Lista las rutas de archivo de donde el comando lee el body.
 *
 * @param {string} command Comando completo.
 * @returns {string[]} Rutas sin resolver, sin repetir.
 */
export function findBodyFilePaths(command) {
  const patterns = GH_COMMENT_SUBCOMMAND_PATTERN.test(command)
    ? [...BODY_FILE_PATTERNS, GH_COMMENT_BODY_FILE_PATTERN]
    : BODY_FILE_PATTERNS;
  const paths = patterns.flatMap((pattern) => [...command.matchAll(pattern)].map((match) => unquote(match[1])));
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
 * Decide qué tipo de escritura hace el texto del comando, ya sumados los archivos que lee.
 *
 * @param {string} command Comando original.
 * @param {string} combinedText Comando más el contenido de los archivos de body.
 * @returns {string} Un valor de {@link COMMAND_KIND}.
 */
function classify(command, combinedText) {
  if (!GH_COMMAND_PATTERN.test(command)) {
    return COMMAND_KIND.none;
  }
  const writes = WRITE_FLAG_PATTERN.test(command) || GH_COMMENT_SUBCOMMAND_PATTERN.test(command);
  const isGraphqlMutation = /\bmutation\b/.test(combinedText);
  const createsThreadReply = THREAD_REPLY_PATTERNS.some((pattern) => pattern.test(combinedText))
    || ((REVIEW_COMMENT_CREATE_PATTERN.test(combinedText) || REVIEW_COMMENT_GRAPHQL_PATTERN.test(combinedText))
      && IN_REPLY_TO_PATTERN.test(combinedText));
  if (createsThreadReply && (writes || isGraphqlMutation)) {
    return COMMAND_KIND.threadReply;
  }
  const writesComment = (writes && COMMENT_WRITE_PATTERNS.some((pattern) => pattern.test(combinedText)))
    || GH_COMMENT_SUBCOMMAND_PATTERN.test(command)
    || (isGraphqlMutation && COMMENT_GRAPHQL_PATTERN.test(combinedText));
  if (writesComment && REPLY_SIGNAL_PATTERNS.some((pattern) => pattern.test(combinedText))) {
    return COMMAND_KIND.commentReply;
  }
  return COMMAND_KIND.none;
}

/**
 * Analiza un comando antes de que se ejecute.
 *
 * @param {string} command Comando del tool Bash o PowerShell.
 * @param {{ cwd: string, platform: string, homeDirectory: string }} context Directorio, plataforma y home.
 * @returns {{ kind: string, texts: string[], unreadablePaths: string[] }} Tipo de escritura, textos donde
 *   buscar el body y las rutas de body que no se pudieron leer.
 */
export function analyzeCommand(command, context) {
  const texts = [command];
  const unreadablePaths = [];
  for (const rawPath of findBodyFilePaths(command)) {
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
  return { kind: classify(command, texts.join('\n')), texts, unreadablePaths };
}
