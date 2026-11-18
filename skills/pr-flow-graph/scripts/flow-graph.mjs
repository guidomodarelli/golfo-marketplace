#!/usr/bin/env node

/**
 * CLI of the pr-flow-graph skill: validates a flow graph model and renders it.
 *
 * Usage:
 *   node flow-graph.mjs validate <model.json> [--repo <dir>]
 *   node flow-graph.mjs render <model.json> [--repo <dir>] [--out <dir>] [--lean <file.lean>] [--inline-libraries]
 */

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { parseArgs } from 'node:util';

import { checkEvidenceInRepository } from './lib/check-evidence-in-repository.mjs';
import { checkLeanModel } from './lib/check-lean-model.mjs';
import {
  BROWSER_LIBRARIES,
  CHANGE_STATUS,
  CONFIDENCE,
  EXIT_CODE,
  FINDING_SEVERITY,
  LEAN_STATUS,
  OUTPUT_FILE_NAMES,
} from './lib/flow-graph-constants.mjs';
import { renderFlowGraphHtml } from './lib/render-html.mjs';
import { renderMermaidMarkdown } from './lib/render-mermaid.mjs';
import { createTerminalUi } from './lib/terminal-ui.mjs';
import { hasBlockingFindings, validateFlowGraph } from './lib/validate-flow-graph.mjs';

const COMMAND = { validate: 'validate', render: 'render' };
const RENDER_STEP_COUNT = 3;
const USAGE = `pr-flow-graph — valida y dibuja el modelo de flujo de un pull request

Uso:
  node flow-graph.mjs validate <model.json> [--repo <dir>]
  node flow-graph.mjs render <model.json> [opciones]

Opciones:
  --repo <dir>         Clon del repo: comprueba que cada evidencia exista en base o head
  --out <dir>          Carpeta de salida (por defecto, la del modelo)
  --lean <file.lean>   Modelo Lean 4; se incluye solo si compila y no usa sorry
  --inline-libraries   Embebe las librerías en el HTML para abrirlo sin red
  -h, --help           Muestra esta ayuda

Códigos de salida: 0 correcto · 1 modelo inválido · 2 uso incorrecto`;

/** Error of a wrong invocation or an unreadable input; carries the exit code to use. */
class CommandLineError extends Error {
  constructor(message, { exitCode = EXIT_CODE.usage, cause } = {}) {
    super(message, { cause });
    this.exitCode = exitCode;
  }
}

async function main(commandLineArguments) {
  const { values: options, positionals } = parseCommandLine(commandLineArguments);
  if (options.help || positionals.length === 0) {
    process.stdout.write(`${USAGE}\n`);
    return EXIT_CODE.success;
  }

  const [command, modelPath] = positionals;
  if (!Object.values(COMMAND).includes(command)) {
    throw new CommandLineError(`Comando desconocido "${command}". Usá validate o render.`);
  }
  if (!modelPath) throw new CommandLineError(`Falta la ruta del modelo: flow-graph.mjs ${command} <model.json>`);

  const ui = createTerminalUi(process.stderr);
  const model = readModel(modelPath);

  if (command === COMMAND.validate) {
    ui.banner('pr-flow-graph · validate');
    return reportFindings(ui, collectFindings(model, options.repo), modelPath) ? EXIT_CODE.success : EXIT_CODE.invalidModel;
  }
  return render(ui, model, modelPath, options);
}

async function render(ui, model, modelPath, options) {
  ui.banner('pr-flow-graph · render');

  ui.step(1, RENDER_STEP_COUNT, 'Validar el modelo');
  if (!reportFindings(ui, collectFindings(model, options.repo), modelPath)) return EXIT_CODE.invalidModel;
  if (!options.repo) ui.warning('Evidencia sin comprobar contra el repo: pasá --repo <dir> para verificar que cada archivo y línea existan.');

  ui.step(2, RENDER_STEP_COUNT, 'Verificar el modelo formal');
  const leanSource = resolveLeanSource(ui, options.lean);

  ui.step(3, RENDER_STEP_COUNT, 'Generar el grafo');
  const inlinedLibraries = options['inline-libraries']
    ? await ui.withSpinner('Descargando librerías', downloadBrowserLibraries)
    : new Map();
  const outputDirectory = path.resolve(options.out ?? path.dirname(modelPath));
  mkdirSync(outputDirectory, { recursive: true });
  const htmlPath = path.join(outputDirectory, OUTPUT_FILE_NAMES.html);
  const mermaidPath = path.join(outputDirectory, OUTPUT_FILE_NAMES.mermaid);
  writeFileSync(htmlPath, renderFlowGraphHtml(model, { leanSource, inlinedLibraries }));
  writeFileSync(mermaidPath, renderMermaidMarkdown(model));
  ui.done(`Grafo interactivo: ${htmlPath}`);
  ui.done(`Mermaid para el PR: ${mermaidPath}`);

  ui.summary(buildSummaryLines(model, Boolean(leanSource)));
  // stdout carries only the machine-readable result, so another program can read it.
  process.stdout.write(`${JSON.stringify({ html: htmlPath, mermaid: mermaidPath, lean: Boolean(leanSource) })}\n`);
  return EXIT_CODE.success;
}

/**
 * Validates the shape of the model and, with a repository, that its evidence exists there. The
 * repository check needs a well-formed model, so it runs only when the shape has no errors.
 */
function collectFindings(model, repositoryPath) {
  const findings = validateFlowGraph(model);
  if (!repositoryPath || hasBlockingFindings(findings)) return findings;
  return [...checkEvidenceInRepository(model, repositoryPath), ...findings];
}

/** @returns {boolean} Whether the model can be rendered. */
function reportFindings(ui, findings, modelPath) {
  for (const finding of findings) {
    const write = finding.severity === FINDING_SEVERITY.error ? ui.error : ui.warning;
    write(`${finding.location}: ${finding.message}`);
  }
  if (hasBlockingFindings(findings)) {
    const errorCount = findings.filter((finding) => finding.severity === FINDING_SEVERITY.error).length;
    ui.error(`${modelPath} tiene ${errorCount} error(es); corregilos y volvé a correr.`);
    return false;
  }
  ui.done(`${modelPath} es válido${findings.length > 0 ? ` (${findings.length} aviso(s))` : ''}.`);
  return true;
}

/** @returns {string | undefined} The Lean source when it may be shown. */
function resolveLeanSource(ui, leanFilePath) {
  if (!leanFilePath) {
    ui.skipped('Sin modelo Lean (--lean no indicado).');
    return undefined;
  }
  let leanCheck;
  try {
    leanCheck = checkLeanModel(leanFilePath);
  } catch (error) {
    throw new CommandLineError(`No se pudo leer el modelo Lean ${leanFilePath}: ${error.message}`, { cause: error });
  }
  if (leanCheck.status === LEAN_STATUS.compiled) {
    ui.done(`${leanFilePath} compila y se incluye en el grafo.`);
    return leanCheck.source;
  }
  ui.warning(`El modelo Lean queda fuera del grafo. ${leanCheck.detail}`);
  return undefined;
}

async function downloadBrowserLibraries() {
  const inlinedLibraries = new Map();
  for (const library of BROWSER_LIBRARIES) {
    let response;
    try {
      response = await fetch(library.url);
    } catch (error) {
      throw new CommandLineError(`No se pudo descargar ${library.name}@${library.version} (GET ${library.url}): ${error.message}`, {
        exitCode: EXIT_CODE.invalidModel,
        cause: error,
      });
    }
    if (!response.ok) {
      throw new CommandLineError(`No se pudo descargar ${library.name}@${library.version} (GET ${library.url}): HTTP ${response.status}`, {
        exitCode: EXIT_CODE.invalidModel,
      });
    }
    inlinedLibraries.set(library.url, await response.text());
  }
  return inlinedLibraries;
}

function buildSummaryLines(model, hasLeanModel) {
  const relationships = [...(model.edges ?? []), ...(model.businessFlow?.transitions ?? [])];
  const elements = [...model.nodes, ...relationships, ...(model.businessFlow?.states ?? [])];
  const countByChange = (change) => elements.filter((element) => element.change === change).length;
  const inferredCount = relationships.filter((relationship) => relationship.confidence === CONFIDENCE.inferred).length;
  return [
    `${model.nodes.length} nodos, ${(model.edges ?? []).length} relaciones, ${model.businessFlow?.states.length ?? 0} estados de negocio`,
    `Agregados ${countByChange(CHANGE_STATUS.added)} · modificados ${countByChange(CHANGE_STATUS.modified)} · eliminados ${countByChange(CHANGE_STATUS.removed)}`,
    `Relaciones inferidas: ${inferredCount} · modelo Lean: ${hasLeanModel ? 'incluido' : 'no incluido'}`,
  ];
}

function parseCommandLine(commandLineArguments) {
  try {
    return parseArgs({
      args: commandLineArguments,
      allowPositionals: true,
      options: {
        out: { type: 'string' },
        repo: { type: 'string' },
        lean: { type: 'string' },
        'inline-libraries': { type: 'boolean', default: false },
        help: { type: 'boolean', short: 'h', default: false },
      },
    });
  } catch (error) {
    throw new CommandLineError(`${error.message}\n\n${USAGE}`, { cause: error });
  }
}

function readModel(modelPath) {
  let content;
  try {
    content = readFileSync(modelPath, 'utf8');
  } catch (error) {
    throw new CommandLineError(`No se pudo leer el modelo ${modelPath}: ${error.message}`, { cause: error });
  }
  try {
    return JSON.parse(content);
  } catch (error) {
    throw new CommandLineError(`${modelPath} no es JSON válido: ${error.message}`, {
      exitCode: EXIT_CODE.invalidModel,
      cause: error,
    });
  }
}

main(process.argv.slice(2)).then(
  (exitCode) => {
    process.exitCode = exitCode;
  },
  (error) => {
    createTerminalUi(process.stderr).error(error.message);
    process.exitCode = error.exitCode ?? EXIT_CODE.invalidModel;
  },
);
