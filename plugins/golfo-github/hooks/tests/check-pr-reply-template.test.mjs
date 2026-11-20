/**
 * Tests del hook PreToolUse que frena respuestas de PR sin template.
 * Corren el hook real como proceso (stdin → stdout, igual que Claude Code) contra los templates
 * reales del plugin; solo los archivos de body y la raíz del plugin rota son temporales.
 */
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { after, describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { DISABLE_ENVIRONMENT_VARIABLE, evaluateHookInput } from '../check-pr-reply-template.mjs';
import { resolveBodyFilePath } from '../lib/pr-reply-command.mjs';
import { PLUGIN_ROOT, TEMPLATE_SOURCES } from '../lib/reply-templates.mjs';

const HOOK_PATH = join(dirname(fileURLToPath(import.meta.url)), '..', 'check-pr-reply-template.mjs');
const REPLIES_ENDPOINT = 'repos/acme/widgets/pulls/7/comments/4637729127/replies';
const COMMIT_URL = 'https://github.com/acme/widgets/commit/07820ccc668bdb2bf22dbb5a1a9a5978db2044af';
const APP_ATTRIBUTION = '_🤖 Addressed by [Claude Code](https://claude.com/claude-code)_';
const RESOLVED_BODY = [
  `✅ **Resuelto** en [\`07820cc\`](${COMMIT_URL}).`,
  '',
  '**Qué cambió:** el menú conserva los flags globales al elegir el subcomando.',
  '',
  '<sub>🤖 Fix automático en respuesta a este comentario de Codex</sub>',
  '',
  APP_ATTRIBUTION,
].join('\n');
const FREE_FORM_BODY = `Corregido en 07820cc: el menú conserva los flags globales.\n\n${APP_ATTRIBUTION}`;

const temporaryDirectory = mkdtempSync(join(tmpdir(), 'pr-reply-hook-'));
after(() => rmSync(temporaryDirectory, { recursive: true, force: true }));

/**
 * Arma el evento PreToolUse que Claude Code le pasa al hook.
 *
 * @param {string} command Comando del tool.
 * @param {string} [toolName] Tool que lo ejecuta.
 * @returns {object} Evento del hook.
 */
function preToolUseEvent(command, toolName = 'Bash') {
  return { hook_event_name: 'PreToolUse', tool_name: toolName, tool_input: { command }, cwd: temporaryDirectory };
}

/**
 * Corre el hook como proceso, igual que Claude Code.
 *
 * @param {string} rawInput Lo que recibe por stdin.
 * @param {NodeJS.ProcessEnv} [extraEnvironment] Variables que se suman al entorno.
 * @returns {{ status: number, output: object | null }} Exit code y JSON de stdout (o `null` si no escribió nada).
 */
function runHook(rawInput, extraEnvironment = {}) {
  const environment = { ...process.env, ...extraEnvironment };
  if (!(DISABLE_ENVIRONMENT_VARIABLE in extraEnvironment)) {
    delete environment[DISABLE_ENVIRONMENT_VARIABLE];
  }
  const result = spawnSync(process.execPath, [HOOK_PATH], { input: rawInput, env: environment, encoding: 'utf8' });
  const stdout = result.stdout.trim();
  return { status: result.status, output: stdout === '' ? null : JSON.parse(stdout) };
}

/**
 * Corre el hook con un comando y devuelve su decisión.
 *
 * @param {string} command Comando del tool.
 * @param {object} [options] Tool y variables extra.
 * @param {string} [options.toolName] Tool que lo ejecuta.
 * @param {NodeJS.ProcessEnv} [options.environment] Variables que se suman al entorno.
 * @returns {{ decision: string, reason: string, output: object | null }} `deny` o `allow`, y el motivo.
 */
function decide(command, { toolName, environment } = {}) {
  const { status, output } = runHook(JSON.stringify(preToolUseEvent(command, toolName)), environment);
  assert.equal(status, 0, 'el hook nunca sale con error');
  const decision = output?.hookSpecificOutput?.permissionDecision ?? 'allow';
  return { decision, reason: output?.hookSpecificOutput?.permissionDecisionReason ?? '', output };
}

/**
 * Escribe un archivo temporal de body.
 *
 * @param {string} fileName Nombre del archivo.
 * @param {string} content Contenido.
 * @returns {string} Ruta del archivo.
 */
function writeBodyFile(fileName, content) {
  const path = join(temporaryDirectory, fileName);
  writeFileSync(path, content, 'utf8');
  return path;
}

/**
 * Pone comillas simples de shell a un texto.
 *
 * @param {string} text Texto.
 * @returns {string} Texto citado.
 */
function shellQuote(text) {
  return `'${text.replaceAll("'", String.raw`'\''`)}'`;
}

describe('respuestas a hilos de review', () => {
  test('frena una respuesta libre y dice qué skill cargar', () => {
    const { decision, reason } = decide(`gh api ${REPLIES_ENDPOINT} -f body=${shellQuote(FREE_FORM_BODY)}`);
    assert.equal(decision, 'deny');
    assert.match(reason, /codex-comment-closeout/);
    assert.match(reason, /inline-thread-autofix/);
    assert.match(reason, /✅ \*\*Resuelto\*\*/);
  });

  test('deja pasar una respuesta armada con el template de Codex', () => {
    assert.equal(decide(`gh api ${REPLIES_ENDPOINT} -f body=${shellQuote(RESOLVED_BODY)}`).decision, 'allow');
  });

  test('frena un encabezado de template sin su pie', () => {
    const bodyWithoutFooter = `✅ **Resuelto** en [\`07820cc\`](${COMMIT_URL}).\n\n**Qué cambió:** algo.`;
    const { decision, reason } = decide(`gh api ${REPLIES_ENDPOINT} -f body=${shellQuote(bodyWithoutFooter)}`);
    assert.equal(decision, 'deny');
    assert.match(reason, /le falta el pie/);
  });

  test('lee el body de un archivo pasado con -F body=@ruta', () => {
    const templatePath = writeBodyFile('reply-template.md', RESOLVED_BODY);
    const freeFormPath = writeBodyFile('reply-free.md', FREE_FORM_BODY);
    assert.equal(decide(`gh api -X POST ${REPLIES_ENDPOINT} -F body=@${templatePath}`).decision, 'allow');
    assert.equal(decide(`gh api -X POST ${REPLIES_ENDPOINT} -F "body=@${freeFormPath}"`).decision, 'deny');
  });

  test('lee un --input JSON aunque los emojis vengan escapados', () => {
    const escapedJson = JSON.stringify({ body: RESOLVED_BODY, in_reply_to: 4637729127 })
      .replace(/[\u0080-\uffff]/g, (character) => `\\u${character.charCodeAt(0).toString(16).padStart(4, '0')}`);
    const inputPath = writeBodyFile('reply-input.json', escapedJson);
    assert.equal(decide(`gh api repos/acme/widgets/pulls/7/comments --input ${inputPath}`).decision, 'allow');
  });

  test('acepta el emoji sin el selector de variación U+FE0F', () => {
    const noChangeBody = 'ℹ **Sin cambios.** Revisé la sugerencia pero no requería cambios de código.\n\n<sub>🤖 Auto-fix de Codex</sub>';
    assert.equal(decide(`gh api ${REPLIES_ENDPOINT} -f body=${shellQuote(noChangeBody)}`).decision, 'allow');
  });

  test('frena si el body está en una ruta con variables y lo dice', () => {
    const { decision, reason } = decide(`gh api ${REPLIES_ENDPOINT} -F body=@"$SCRATCH/reply.md"`);
    assert.equal(decision, 'deny');
    assert.match(reason, /No pude leer el body de: \$SCRATCH\/reply\.md/);
  });

  test('frena una respuesta libre por GraphQL', () => {
    const mutation = `mutation { addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: "PRRT_x", body: "Listo, corregido."}) { comment { id } } }`;
    assert.equal(decide(`gh api graphql -f query=${shellQuote(mutation)}`).decision, 'deny');
  });

  test('revisa igual un comando del tool PowerShell', () => {
    const command = `gh api ${REPLIES_ENDPOINT} -f body=@'\n${FREE_FORM_BODY}\n'@`;
    assert.equal(decide(command, { toolName: 'PowerShell' }).decision, 'deny');
  });
});

describe('comentarios generales y ediciones', () => {
  test('deja pasar un comentario que no responde a nadie, como pedir una review', () => {
    assert.equal(decide('gh pr comment 7 --body "@codex review"').decision, 'allow');
  });

  test('frena un comentario general libre con la línea del Auto-fix de la app', () => {
    assert.equal(decide(`gh api repos/acme/widgets/issues/7/comments -f body=${shellQuote(FREE_FORM_BODY)}`).decision, 'deny');
  });

  test('frena la edición libre de una respuesta ya publicada', () => {
    const command = `gh api -X PATCH repos/acme/widgets/pulls/comments/4637808675 -f body=${shellQuote(FREE_FORM_BODY)}`;
    assert.equal(decide(command).decision, 'deny');
  });

  test('deja pasar el back-link que se agrega al comentario original', () => {
    const backLinkBody = 'Texto original del autor.\n\n---\n↪️ Respondido en [este comentario](https://github.com/acme/widgets/pull/7#issuecomment-123).\n\n<!-- inline-thread-autofix: issuecomment-backlink:99 -->';
    const command = `gh api -X PATCH repos/acme/widgets/issues/comments/99 -f body=${shellQuote(backLinkBody)}`;
    assert.equal(decide(command).decision, 'allow');
  });

  test('lee el --body-file de gh pr comment', () => {
    const freeFormPath = writeBodyFile('general-free.md', `Respondo a https://github.com/acme/widgets/pull/7#issuecomment-55: ya está.`);
    assert.equal(decide(`gh pr comment 7 --body-file ${freeFormPath}`).decision, 'deny');
  });
});

describe('comandos que no publican', () => {
  test('deja pasar una lectura de comentarios', () => {
    assert.equal(decide("gh api repos/acme/widgets/pulls/7/comments --jq '.[].body'").decision, 'allow');
  });

  test('deja pasar un comando que no es gh', () => {
    assert.equal(decide(`echo ${REPLIES_ENDPOINT} -f body=hola`).decision, 'allow');
  });

  test('ignora otros tools', () => {
    const event = { tool_name: 'Write', tool_input: { file_path: 'x.md', content: FREE_FORM_BODY } };
    assert.equal(runHook(JSON.stringify(event)).output, null);
  });
});

describe('controles y fallas del hook', () => {
  test('la persona lo puede apagar desde el entorno de Claude Code', () => {
    const command = `gh api ${REPLIES_ENDPOINT} -f body=${shellQuote(FREE_FORM_BODY)}`;
    assert.equal(decide(command, { environment: { [DISABLE_ENVIRONMENT_VARIABLE]: 'off' } }).decision, 'allow');
  });

  test('con una entrada que no es JSON deja pasar y avisa', () => {
    const { status, output } = runHook('no es json');
    assert.equal(status, 0);
    assert.match(output.systemMessage, /no es JSON válido/);
  });

  test('sin templates deja pasar y avisa qué no pudo leer', () => {
    const missingPluginRoot = join(temporaryDirectory, 'plugin-sin-templates');
    const command = `gh api ${REPLIES_ENDPOINT} -f body=${shellQuote(FREE_FORM_BODY)}`;
    const output = evaluateHookInput(preToolUseEvent(command), { environment: {}, pluginRoot: missingPluginRoot });
    assert.match(output.systemMessage, /no pude leer los templates de respuesta/);
    assert.match(output.systemMessage, /codex-comment-closeout\/templates/);
  });
});

describe('rutas de body', () => {
  const windowsContext = { cwd: 'C:/repo', platform: 'win32', homeDirectory: 'C:/Users/persona' };
  const posixContext = { cwd: '/repo', platform: 'linux', homeDirectory: '/home/persona' };

  test('convierte rutas de Git Bash y relativas en Windows', () => {
    assert.equal(resolveBodyFilePath('/c/Temp/reply.md', windowsContext), 'C:/Temp/reply.md');
    assert.equal(resolveBodyFilePath('reply.md', windowsContext), 'C:\\repo\\reply.md');
  });

  test('expande el home y no adivina variables', () => {
    assert.equal(resolveBodyFilePath('~/reply.md', posixContext), '/home/persona/reply.md');
    assert.equal(resolveBodyFilePath('$TMPDIR/reply.md', posixContext), null);
  });
});

describe('paridad con los templates del plugin', () => {
  /**
   * Lee cada variante publicada de los templates, tal como la usa quien responde.
   *
   * @returns {{ origin: string, text: string }[]} Variantes con su origen.
   */
  function publishedVariants() {
    return TEMPLATE_SOURCES.flatMap((source) => {
      const sourcePath = join(PLUGIN_ROOT, source.path);
      if (source.format === 'directory') {
        return readdirSync(sourcePath).map((fileName) => ({
          origin: `${source.path}/${fileName}`,
          text: readFileSync(join(sourcePath, fileName), 'utf8'),
        }));
      }
      return [...readFileSync(sourcePath, 'utf8').matchAll(/```markdown\r?\n([\s\S]*?)\r?\n```/g)]
        .map((match, index) => ({ origin: `${source.path} (bloque ${index + 1})`, text: match[1] }));
    });
  }

  for (const variant of publishedVariants()) {
    const firstContentLine = variant.text.split('\n').map((line) => line.trim())
      .find((line) => line !== '' && line !== '---' && !line.startsWith('>'));
    const startsWithEmoji = firstContentLine.codePointAt(0) >= 128;
    test(`${variant.origin} ${startsWithEmoji ? 'pasa' : 'no tiene encabezado propio y queda afuera'}`, () => {
      const filledBody = variant.text.replace(/\{\{[^}]+\}\}/g, 'valor');
      const command = `gh api ${REPLIES_ENDPOINT} -f body=${shellQuote(filledBody)}`;
      assert.equal(decide(command).decision, startsWithEmoji ? 'allow' : 'deny');
    });
  }
});
