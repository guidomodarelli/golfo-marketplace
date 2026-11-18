#!/usr/bin/env node

/**
 * CLI of the pr-flow-graph skill: validates a flow graph model, of a pull request or of an RFC,
 * and renders it.
 *
 * Usage:
 *   node flow-graph.mjs validate <model.json> [--repo <dir>]
 *   node flow-graph.mjs render <model.json> --repo <dir> [--out <dir>] [--lean <file.lean>] [--inline-libraries]
 */

import { mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { parseArgs } from 'node:util';

import { verifyModelAgainstRepository } from './lib/check-evidence-in-repository.mjs';
import { checkLeanModel } from './lib/check-lean-model.mjs';
import {
  BROWSER_LIBRARIES,
  CHANGE_STATUS,
  CHECK_STATUS,
  EXIT_CODE,
  FINDING_SEVERITY,
  FLOW_SOURCE,
  LEAN_STATUS,
  OUTPUT_FILE_NAMES,
} from './lib/flow-graph-constants.mjs';
import { getFlowSource } from './lib/flow-source.mjs';
import { renderFlowGraphHtml } from './lib/render-html.mjs';
import { renderMermaidMarkdown } from './lib/render-mermaid.mjs';
import { buildVerificationChecks, findOutputMismatches, renderReport } from './lib/render-report.mjs';
import { createTerminalUi } from './lib/terminal-ui.mjs';
import { hasBlockingFindings, validateFlowGraph } from './lib/validate-flow-graph.mjs';

const COMMAND = { validate: 'validate', render: 'render' };
const CHECK_SUMMARY_MARKS = { [CHECK_STATUS.passed]: '✓', [CHECK_STATUS.skipped]: '–', [CHECK_STATUS.warning]: '!' };
const RENDER_STEP_COUNT = 4;
const USAGE = `pr-flow-graph — valida y dibuja el modelo de flujo de un pull request o de un RFC

Uso:
  node flow-graph.mjs validate <model.json> [--repo <dir>]
  node flow-graph.mjs render <model.json> --repo <dir> [opciones]

Opciones:
  --repo <dir>         Clon del repo: comprueba el modelo contra el código y el diff del PR,
                       o contra el código y el texto del RFC
                       (obligatorio en render, salvo con --skip-repo-check)
  --skip-repo-check    Genera sin comprobar contra el repo; el grafo y el reporte lo avisan
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
    return reportFindings(ui, verifyModel(model, options.repo).findings, modelPath) ? EXIT_CODE.success : EXIT_CODE.invalidModel;
  }
  if (!options.repo && !options['skip-repo-check']) {
    throw new CommandLineError('render necesita --repo <dir> para comprobar el modelo contra el código. Desde la raíz del repo analizado: --repo . (o --skip-repo-check para generar sin comprobar).');
  }
  return render(ui, model, modelPath, options);
}

async function render(ui, model, modelPath, options) {
  ui.banner('pr-flow-graph · render');

  ui.step(1, RENDER_STEP_COUNT, 'Validar el modelo');
  const { findings, repositoryStatistics } = verifyModel(model, options.repo);
  if (!reportFindings(ui, findings, modelPath)) return EXIT_CODE.invalidModel;

  ui.step(2, RENDER_STEP_COUNT, 'Comprobar contra el repo');
  if (repositoryStatistics && getFlowSource(model) === FLOW_SOURCE.rfc) {
    ui.done(`${repositoryStatistics.codeEvidenceCount} líneas de código (${repositoryStatistics.codeCommit}), ${repositoryStatistics.rfcEvidenceCount} del RFC y ${repositoryStatistics.sectionCount} secciones comprobadas.`);
  } else if (repositoryStatistics) {
    ui.done(`${repositoryStatistics.evidenceCount} evidencias y ${repositoryStatistics.changedFileCount} archivos del diff comprobados (${repositoryStatistics.baseCommit} → ${repositoryStatistics.headCommit}).`);
  } else {
    ui.warning('Evidencia sin comprobar contra el repo: el grafo y el reporte lo avisan. Pasá --repo <dir> para verificarla.');
  }

  ui.step(3, RENDER_STEP_COUNT, 'Verificar el modelo formal');
  const leanOutcome = resolveLeanOutcome(ui, options.lean, model);

  ui.step(4, RENDER_STEP_COUNT, 'Generar el grafo');
  const inlinedLibraries = options['inline-libraries']
    ? await ui.withSpinner('Descargando librerías', downloadBrowserLibraries)
    : new Map();
  const checks = buildVerificationChecks({ model, repositoryStatistics, leanOutcome });
  const outputDirectory = path.resolve(options.out ?? path.dirname(modelPath));
  const paths = {
    html: path.join(outputDirectory, OUTPUT_FILE_NAMES.html),
    mermaid: path.join(outputDirectory, OUTPUT_FILE_NAMES.mermaid),
    report: path.join(outputDirectory, OUTPUT_FILE_NAMES.report),
  };
  const html = renderFlowGraphHtml(model, { leanSource: leanOutcome.source, inlinedLibraries, verification: { checks } });
  const mermaidMarkdown = renderMermaidMarkdown(model);
  const report = renderReport({ model, paths, checks, leanOutcome });
  mkdirSync(outputDirectory, { recursive: true });
  writeFileSync(paths.html, html);
  writeFileSync(paths.mermaid, mermaidMarkdown);
  writeFileSync(paths.report, report);

  // Read back what was written: the check is on the files a person will open, not on the strings in memory.
  const mismatches = findOutputMismatches(model, readFileSync(paths.html, 'utf8'), readFileSync(paths.mermaid, 'utf8'));
  if (mismatches.length > 0) {
    for (const outputPath of Object.values(paths)) rmSync(outputPath, { force: true });
    for (const mismatch of mismatches) ui.error(mismatch);
    ui.error('Las salidas no coinciden con el modelo y se borraron. Es un error del generador, no del modelo: reportalo.');
    return EXIT_CODE.invalidModel;
  }
  ui.done(`Grafo interactivo: ${paths.html}`);
  ui.done(`Mermaid para el PR: ${paths.mermaid}`);
  ui.done(`Reporte para copiar: ${paths.report}`);

  ui.summary(checks.map((check) => `${CHECK_SUMMARY_MARKS[check.status]} ${check.label}`));
  // stdout carries only the machine-readable result, so another program can read it.
  process.stdout.write(`${JSON.stringify({ ...paths, lean: leanOutcome.included, repositoryChecked: Boolean(repositoryStatistics), checks })}\n`);
  return EXIT_CODE.success;
}

/**
 * Validates the shape of the model and, with a repository, checks it against the code. The
 * repository check needs a well-formed model, so it runs only when the shape has no errors.
 *
 * @returns {{ findings: object[], repositoryStatistics?: object }}
 */
function verifyModel(model, repositoryPath) {
  const shapeFindings = validateFlowGraph(model);
  if (!repositoryPath || hasBlockingFindings(shapeFindings)) return { findings: shapeFindings };
  const repositoryVerification = verifyModelAgainstRepository(model, repositoryPath);
  const findings = [...repositoryVerification.findings, ...shapeFindings];
  return { findings, repositoryStatistics: hasBlockingFindings(findings) ? undefined : repositoryVerification.statistics };
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

/**
 * @returns {import('./lib/render-report.mjs').LeanOutcome & { source?: string }} Outcome of the
 *   Lean gate, with the source only when it may be shown.
 */
function resolveLeanOutcome(ui, leanFilePath, model) {
  if (!leanFilePath) {
    ui.skipped('Sin modelo Lean (--lean no indicado).');
    return { requested: false, included: false, detail: 'No se pidió un modelo formal.' };
  }
  if (!model.businessFlow) {
    throw new CommandLineError('--lean necesita que el modelo tenga `businessFlow`: el modelo formal se escribe a partir de él.');
  }
  const expectedStateIds = model.businessFlow.states.filter((state) => state.change !== CHANGE_STATUS.removed).map((state) => state.id);
  let leanCheck;
  try {
    leanCheck = checkLeanModel(leanFilePath, { expectedStateIds });
  } catch (error) {
    throw new CommandLineError(`No se pudo leer el modelo Lean ${leanFilePath}: ${error.message}`, { cause: error });
  }
  if (leanCheck.status === LEAN_STATUS.compiled) {
    ui.done(`${leanFilePath} compila y se incluye en el grafo.`);
    return { requested: true, included: true, detail: 'Lean lo compiló sin errores ni pruebas pendientes, y nombra todos los estados del flujo.', source: leanCheck.source };
  }
  ui.warning(`El modelo Lean queda fuera del grafo. ${leanCheck.detail}`);
  return { requested: true, included: false, detail: leanCheck.detail };
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

function parseCommandLine(commandLineArguments) {
  try {
    return parseArgs({
      args: commandLineArguments,
      allowPositionals: true,
      options: {
        out: { type: 'string' },
        repo: { type: 'string' },
        'skip-repo-check': { type: 'boolean', default: false },
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
