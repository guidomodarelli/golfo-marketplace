/**
 * The model of an RFC, validated on its own and checked against a real git repository built in a
 * temporary directory: the code the RFC proposes to change, committed on `main`, and the RFC text,
 * left uncommitted in the working tree as it usually is while it is being discussed.
 */
import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { after, before, describe, test } from 'node:test';

import { verifyModelAgainstRepository } from '../scripts/lib/check-evidence-in-repository.mjs';
import { readSections } from '../scripts/lib/check-rfc-in-repository.mjs';
import { validateFlowGraph } from '../scripts/lib/validate-flow-graph.mjs';
import {
  CLI_PATH,
  EXAMPLE_RFC_CODE_FILES,
  EXAMPLE_RFC_DOCUMENT_PATH,
  loadExampleModel,
  loadExampleRfcModel,
} from './support/example-model.mjs';

const CODE_REF = 'main';
const errorsOf = (model) => validateFlowGraph(model).filter((finding) => finding.severity === 'error');
const nodeById = (model, nodeId) => model.nodes.find((node) => node.id === nodeId);
const edgeById = (model, edgeId) => model.edges.find((edge) => edge.id === edgeId);

describe('validateFlowGraph with an RFC', () => {
  test('accepts the example RFC model', () => {
    assert.deepEqual(validateFlowGraph(loadExampleRfcModel()), []);
  });

  test('rejects a model that has both a pull request and an RFC, or neither', () => {
    const both = loadExampleRfcModel();
    both.pullRequest = loadExampleModel().pullRequest;
    const neither = loadExampleRfcModel();
    delete neither.rfc;

    assert.ok(errorsOf(both).some((finding) => /both `pullRequest` and `rfc`/.test(finding.message)));
    assert.ok(errorsOf(neither).some((finding) => /`pullRequest` for a pull request, or `rfc`/.test(finding.message)));
  });

  test('requires the title, the document and the code ref of the RFC', () => {
    const model = loadExampleRfcModel();
    model.rfc = { title: '', document: '../outside.md' };

    assert.deepEqual(errorsOf(model).map((finding) => finding.location).sort(), ['rfc.codeRef', 'rfc.document', 'rfc.title']);
  });

  test('rejects an added element that points at code, because it does not exist yet', () => {
    const model = loadExampleRfcModel();
    nodeById(model, 'cancel-order').evidence.push({ path: 'src/orders/get-order.js', line: 3 });

    assert.ok(errorsOf(model).some((finding) => finding.location === 'nodes[2].evidence' && /does not exist in the code yet/.test(finding.message)));
  });

  test('rejects a modified element without its line of code, and a change without its RFC line', () => {
    const withoutCode = loadExampleRfcModel();
    nodeById(withoutCode, 'order-routes').evidence = [{ side: 'rfc', line: 12 }];
    const withoutRfc = loadExampleRfcModel();
    nodeById(withoutRfc, 'order-routes').evidence = [{ path: 'src/orders/order-routes.js', line: 4 }];

    assert.ok(errorsOf(withoutCode).some((finding) => /so it exists today: add the line of code/.test(finding.message)));
    assert.ok(errorsOf(withoutRfc).some((finding) => /none of its evidence is a line of the RFC/.test(finding.message)));
  });

  test('rejects a verified relationship of today that only points at the RFC', () => {
    const model = loadExampleRfcModel();
    edgeById(model, 'routes-call-get-order').evidence = [{ side: 'rfc', line: 7 }];

    assert.ok(errorsOf(model).some((finding) => /"verified" and "unchanged", so the code writes it today/.test(finding.message)));
  });

  test('accepts only the sides of its source', () => {
    const rfcWithBase = loadExampleRfcModel();
    nodeById(rfcWithBase, 'get-order').evidence[0].side = 'base';
    const pullRequestWithRfcLine = loadExampleModel();
    pullRequestWithRfcLine.nodes[0].evidence = [{ side: 'rfc', line: 3 }];

    assert.ok(errorsOf(rfcWithBase).some((finding) => /In an RFC, expected one of code, rfc; received "base"/.test(finding.message)));
    assert.ok(errorsOf(pullRequestWithRfcLine).some((finding) => /In a pull request, expected one of head, base; received "rfc"/.test(finding.message)));
  });

  test('leaves out sections of the RFC, not files', () => {
    const model = loadExampleRfcModel();
    model.outOfScope = [{ path: 'docs/', reason: 'Documentación.' }];

    assert.deepEqual(errorsOf(model).map((finding) => finding.location).sort(), ['outOfScope[0].path', 'outOfScope[0].section']);
  });
});

describe('readSections', () => {
  test('splits the RFC at its ## headings and skips a heading inside a code block', () => {
    const lines = readFileSync(EXAMPLE_RFC_DOCUMENT_PATH, 'utf8').split('\n');
    lines.pop();

    assert.deepEqual(readSections(lines), [
      { title: 'Contexto', startLine: 5, endLine: 8 },
      { title: 'Propuesta', startLine: 9, endLine: 14 },
      { title: 'Alternativas descartadas', startLine: 15, endLine: 21 },
    ]);
  });
});

describe('an RFC checked against the repository', () => {
  let workDirectory;
  let repositoryPath;
  const git = (...gitArguments) => execFileSync('git', ['-C', repositoryPath, ...gitArguments], { encoding: 'utf8' });
  const writeRepositoryFile = (filePath, content) => {
    const absolutePath = path.join(repositoryPath, filePath);
    mkdirSync(path.dirname(absolutePath), { recursive: true });
    writeFileSync(absolutePath, `${content}\n`);
  };
  const verify = (model) => verifyModelAgainstRepository(model, repositoryPath);
  const findingsOf = (model) => verify(model).findings.map((finding) => [finding.severity, finding.location]);

  before(() => {
    workDirectory = mkdtempSync(path.join(tmpdir(), 'pr-flow-graph-rfc-'));
    repositoryPath = path.join(workDirectory, 'repository');
    mkdirSync(repositoryPath);
    git('init', '--quiet', `--initial-branch=${CODE_REF}`);
    git('config', 'user.email', 'tests@example.com');
    git('config', 'user.name', 'Tests');
    git('config', 'commit.gpgsign', 'false');
    for (const [filePath, content] of Object.entries(EXAMPLE_RFC_CODE_FILES)) writeRepositoryFile(filePath, content);
    git('add', '.');
    git('commit', '--quiet', '-m', 'orders');
    const documentPath = path.join(repositoryPath, loadExampleRfcModel().rfc.document);
    mkdirSync(path.dirname(documentPath), { recursive: true });
    copyFileSync(EXAMPLE_RFC_DOCUMENT_PATH, documentPath);
  });

  after(() => {
    rmSync(workDirectory, { recursive: true, force: true });
  });

  test('accepts the example model and counts what it checked', () => {
    const { findings, statistics } = verify(loadExampleRfcModel());

    assert.deepEqual(findings, []);
    assert.deepEqual(
      { ...statistics, codeCommit: undefined },
      {
        evidenceCount: 12,
        codeEvidenceCount: 5,
        rfcEvidenceCount: 7,
        changedElementCount: 6,
        verifiedRelationshipCount: 4,
        sectionCount: 3,
        outOfScopeSectionCount: 1,
        codeCommit: undefined,
        document: 'docs/rfcs/0042-cancel-order.md',
      },
    );
  });

  test('reads the code at the code ref, not in the working tree', () => {
    writeRepositoryFile('src/orders/draft.js', 'only in the working tree');
    const model = loadExampleRfcModel();
    nodeById(model, 'get-order').evidence[0] = { path: 'src/orders/draft.js', line: 1 };

    assert.deepEqual(findingsOf(model), [['error', 'nodes[1].evidence[0]']]);
    assert.match(verify(model).findings[0].message, /draft\.js does not exist in main/);
  });

  test('rejects an RFC line past the end of the document, and a blank one', () => {
    const pastTheEnd = loadExampleRfcModel();
    nodeById(pastTheEnd, 'cancel-order').evidence = [{ side: 'rfc', line: 99 }];
    const blank = loadExampleRfcModel();
    nodeById(blank, 'cancel-order').evidence = [{ side: 'rfc', line: 10 }];

    assert.match(verify(pastTheEnd).findings[0].message, /RFC line 99 is past the end of the document \(21 lines\)/);
    assert.match(verify(blank).findings[0].message, /RFC line 10 is blank/);
  });

  test('rejects a relationship the RFC adds when its line does not name both ends', () => {
    const model = loadExampleRfcModel();
    // Line 17, and the two lines around it, discuss a discarded option: they name neither end.
    edgeById(model, 'routes-call-cancel-order').evidence = [{ side: 'rfc', line: 17 }];

    const { findings } = verify(model);

    assert.deepEqual(findings.map((finding) => finding.location), ['edges[2].evidence']);
    assert.match(findings[0].message, /no RFC line of it names both ends \("orderRoutes" and "cancelOrder"\)/);
  });

  test('accepts the same relationship marked inferred, with its reason', () => {
    const model = loadExampleRfcModel();
    Object.assign(edgeById(model, 'routes-call-cancel-order'), {
      confidence: 'inferred',
      reason: 'El RFC dice que la ruta nueva cancela el pedido.',
      evidence: [{ side: 'rfc', line: 13 }],
    });

    assert.deepEqual(findingsOf(model), []);
  });

  test('rejects a relationship of today whose code does not name its other end', () => {
    const model = loadExampleRfcModel();
    // The end of the repository file names neither the routes nor getOrder.
    edgeById(model, 'routes-call-get-order').evidence = [{ path: 'src/orders/order-repository.js', line: 6 }];

    assert.deepEqual(findingsOf(model), [['error', 'edges[0].evidence']]);
  });

  test('rejects a section of the RFC that the model does not account for', () => {
    const model = loadExampleRfcModel();
    model.outOfScope = [];

    const { findings } = verify(model);

    assert.deepEqual(findings.map((finding) => finding.location), ['outOfScope']);
    assert.match(findings[0].message, /1 section\(s\) that the model does not account for: "Alternativas descartadas" \(line 15\)/);
  });

  test('warns about an out-of-scope section that is not in the RFC', () => {
    const model = loadExampleRfcModel();
    model.outOfScope.push({ section: 'Riesgos', reason: 'No aplica.' });

    assert.deepEqual(findingsOf(model), [['warning', 'outOfScope[1].section']]);
  });

  test('names what is missing when the code ref or the document is not there', () => {
    const model = loadExampleRfcModel();
    model.rfc.codeRef = 'feature/missing';
    model.rfc.document = 'docs/rfcs/missing.md';

    assert.deepEqual(findingsOf(model), [['error', 'rfc.codeRef'], ['error', 'rfc.document']]);
  });

  test('the CLI renders the RFC graph and writes its report', () => {
    const outputDirectory = path.join(workDirectory, 'rfc-graph');
    const modelPath = path.join(workDirectory, 'rfc-flow-graph.json');
    writeFileSync(modelPath, JSON.stringify(loadExampleRfcModel()));

    const result = spawnSync(process.execPath, [CLI_PATH, 'render', modelPath, '--out', outputDirectory, '--repo', repositoryPath], {
      encoding: 'utf8',
      env: { ...process.env, NO_COLOR: '1' },
    });

    assert.equal(result.status, 0, result.stderr);
    const output = JSON.parse(result.stdout);
    assert.equal(output.repositoryChecked, true);
    assert.ok(output.checks.every((check) => check.status !== 'warning'));
    const report = readFileSync(output.report, 'utf8');
    assert.match(report, /\*\*Mermaid para el RFC:\*\*/);
    assert.match(report, /- \*\*Cambios:\*\* 3 agregados, 1 modificado, 0 eliminados/);
    assert.match(report, /sección «Alternativas descartadas»: Opción que el RFC no adopta/);
    assert.match(report, /✓ Ninguna sección del RFC quedó sin explicar\. 3 secciones: 2 en el grafo y 1 declaradas fuera\./);
    assert.match(readFileSync(output.mermaid, 'utf8'), /^## Flujo de cambios — RFC 0042: Cancelar un pedido antes del envío$/m);
    assert.match(readFileSync(output.html, 'utf8'), /<title>Flujo del RFC — RFC 0042: Cancelar un pedido antes del envío<\/title>/);
  });
});
