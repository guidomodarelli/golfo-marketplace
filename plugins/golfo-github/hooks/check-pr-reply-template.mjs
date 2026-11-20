#!/usr/bin/env node
/**
 * Hook PreToolUse de Claude Code del plugin golfo-github.
 *
 * Frena un comando que publica o edita una respuesta en un PR de GitHub cuando el body no usa
 * ninguno de los templates de `codex-comment-closeout` o `inline-thread-autofix`. Lee el evento
 * del hook por stdin y, si hay que frenar, escribe en stdout la decisión `deny` con el motivo que
 * lee el agente. Cualquier otro comando sigue sin cambios.
 */
import { homedir } from 'node:os';
import { pathToFileURL } from 'node:url';
import { COMMAND_KIND, analyzeCommand } from './lib/pr-reply-command.mjs';
import { FOOTER_MARK, loadReplyTemplates, normalizeForComparison } from './lib/reply-templates.mjs';

/** Variable de entorno de Claude Code que apaga el chequeo; solo la puede definir la persona. */
export const DISABLE_ENVIRONMENT_VARIABLE = 'GOLFO_PR_REPLY_TEMPLATE_CHECK';
const DISABLED_VALUE = 'off';
const HOOK_EVENT_NAME = 'PreToolUse';
const CHECKED_TOOLS = new Set(['Bash', 'PowerShell']);
const LOG_PREFIX = 'golfo-github (hook de respuestas de PR)';

const KIND_DESCRIPTIONS = {
  [COMMAND_KIND.threadReply]: 'Esta respuesta a un hilo de review',
  [COMMAND_KIND.commentReply]: 'Este comentario de PR, que responde a otro,',
};

/**
 * Busca los templates cuyo encabezado aparece en alguno de los textos del comando.
 *
 * @param {{ signature: string, requiresFooter: boolean }[]} templates Firmas cargadas.
 * @param {string} normalizedText Textos del comando, ya normalizados y unidos.
 * @returns {{ signature: string, requiresFooter: boolean }[]} Los templates encontrados.
 */
function findMatchingTemplates(templates, normalizedText) {
  return templates.filter((template) => normalizedText.includes(normalizeForComparison(template.signature)));
}

/**
 * Arma el motivo que lee el agente cuando el hook frena el comando.
 *
 * @param {object} details Datos del rechazo.
 * @param {string} details.kind Tipo de escritura detectada.
 * @param {string[]} details.signatures Encabezados aceptados.
 * @param {string | undefined} details.headerWithoutFooter Encabezado encontrado sin su pie.
 * @param {string[]} details.unreadablePaths Rutas de body que no se pudieron leer.
 * @returns {string} Motivo en español, con los pasos para corregirlo.
 */
function buildDenyReason({ kind, signatures, headerWithoutFooter, unreadablePaths }) {
  const problem = headerWithoutFooter
    ? `${KIND_DESCRIPTIONS[kind]} tiene el encabezado «${headerWithoutFooter}» pero le falta el pie ${FOOTER_MARK} …</sub> de su template.`
    : `${KIND_DESCRIPTIONS[kind]} no usa ninguno de los templates de respuesta.`;
  const lines = [
    `${LOG_PREFIX}: ${problem}`,
    'Antes de publicar, cargá la skill `codex-comment-closeout` si el comentario es de Codex o de Claude (chatgpt-codex-connector[bot], claude[bot]), o `inline-thread-autofix` si es de una persona, y armá el body con su variante.',
    `El body tiene que llevar uno de estos encabezados y, salvo «Closeout realizado sin reply», el pie ${FOOTER_MARK} …</sub>:`,
    ...signatures.map((signature) => `- ${signature}`),
  ];
  if (unreadablePaths.length > 0) {
    lines.push(`No pude leer el body de: ${unreadablePaths.join(', ')}. Escribilo en un archivo con ruta literal y pasalo con \`-F body=@<ruta>\` o \`--body-file <ruta>\`, sin variables en la ruta.`);
  }
  lines.push(
    'Si ya publicaste una respuesta libre, editala con PATCH en lugar de publicar otra.',
    `Si la persona pidió a propósito un texto libre, avisale: puede apagar este chequeo con ${DISABLE_ENVIRONMENT_VARIABLE}=${DISABLED_VALUE} en el env de Claude Code.`,
  );
  return lines.join('\n');
}

/**
 * Evalúa un evento PreToolUse y devuelve la salida JSON del hook, o `null` para dejar pasar.
 *
 * @param {unknown} hookInput Evento recibido por stdin, ya parseado.
 * @param {object} [options] Dependencias de entorno, para poder probarlo.
 * @param {NodeJS.ProcessEnv} [options.environment] Variables de entorno de Claude Code.
 * @param {string} [options.platform] Plataforma (`win32`, `linux`, `darwin`).
 * @param {string} [options.homeDirectory] Home de la persona.
 * @param {string} [options.pluginRoot] Raíz del plugin con los templates.
 * @returns {object | null} Salida del hook.
 */
export function evaluateHookInput(hookInput, {
  environment = process.env,
  platform = process.platform,
  homeDirectory = homedir(),
  pluginRoot,
} = {}) {
  if (environment[DISABLE_ENVIRONMENT_VARIABLE]?.toLowerCase() === DISABLED_VALUE) {
    return null;
  }
  const command = hookInput?.tool_input?.command;
  if (!CHECKED_TOOLS.has(hookInput?.tool_name) || typeof command !== 'string') {
    return null;
  }
  const cwd = typeof hookInput.cwd === 'string' ? hookInput.cwd : process.cwd();
  const analysis = analyzeCommand(command, { cwd, platform, homeDirectory });
  if (analysis.kind === COMMAND_KIND.none) {
    return null;
  }
  const { templates, errors } = loadReplyTemplates(pluginRoot);
  if (templates.length === 0) {
    return {
      systemMessage: `${LOG_PREFIX}: no pude leer los templates de respuesta (${errors.join('; ')}), así que no revisé esta respuesta de PR.`,
    };
  }
  const normalizedText = normalizeForComparison(analysis.texts.join('\n'));
  const matchingTemplates = findMatchingTemplates(templates, normalizedText);
  const hasFooter = normalizedText.includes(normalizeForComparison(FOOTER_MARK));
  if (matchingTemplates.some((template) => !template.requiresFooter || hasFooter)) {
    return null;
  }
  return {
    hookSpecificOutput: {
      hookEventName: HOOK_EVENT_NAME,
      permissionDecision: 'deny',
      permissionDecisionReason: buildDenyReason({
        kind: analysis.kind,
        signatures: templates.map((template) => template.signature),
        headerWithoutFooter: matchingTemplates[0]?.signature,
        unreadablePaths: analysis.unreadablePaths,
      }),
    },
  };
}

/**
 * Lee todo stdin como texto UTF-8.
 *
 * @returns {Promise<string>} Contenido de stdin.
 */
async function readStandardInput() {
  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString('utf8');
}

/**
 * Punto de entrada: nunca falla con exit distinto de 0, para no trabar un comando por un error
 * del propio hook; ese error se le muestra a la persona como aviso.
 *
 * @returns {Promise<void>}
 */
async function main() {
  let output;
  try {
    const rawInput = await readStandardInput();
    let hookInput;
    try {
      hookInput = JSON.parse(rawInput);
    } catch (parseError) {
      output = { systemMessage: `${LOG_PREFIX}: la entrada del hook no es JSON válido (${parseError.message}); no revisé el comando.` };
    }
    output ??= evaluateHookInput(hookInput);
  } catch (unexpectedError) {
    output = { systemMessage: `${LOG_PREFIX}: falló al revisar el comando (${unexpectedError.message}); lo dejé pasar.` };
  }
  if (output) {
    process.stdout.write(`${JSON.stringify(output)}\n`);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
