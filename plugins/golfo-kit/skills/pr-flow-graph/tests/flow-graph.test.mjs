import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { after, before, describe, test } from 'node:test';

import { checkLeanModel } from '../scripts/lib/check-lean-model.mjs';
import { buildGithubDiffUrl, renderFlowGraphHtml } from '../scripts/lib/render-html.mjs';
import { renderBusinessStateDiagram, renderChangeFlowchart, renderMermaidMarkdown } from '../scripts/lib/render-mermaid.mjs';
import { buildVerificationChecks, findOutputMismatches, renderReport } from '../scripts/lib/render-report.mjs';
import { hasBlockingFindings, validateFlowGraph } from '../scripts/lib/validate-flow-graph.mjs';
import { CLI_PATH, EXAMPLE_MODEL_PATH, FIXTURES_DIRECTORY, SKILL_DIRECTORY, loadExampleModel } from './support/example-model.mjs';

const EXAMPLE_LEAN_MODEL_PATH = path.join(SKILL_DIRECTORY, 'assets', 'example-flow-model.lean');
const isRealLeanInstalled = spawnSync('lean', ['--version'], { encoding: 'utf8' }).status === 0;
const REAL_LEAN_SKIP_REASON = isRealLeanInstalled ? false : 'lean is not installed (install it with elan to run this test)';
const FAKE_LEAN_OPTIONS = { command: process.execPath, commandArguments: [path.join(FIXTURES_DIRECTORY, 'fake-lean.mjs')] };

const errorsOf = (model) => validateFlowGraph(model).filter((finding) => finding.severity === 'error');
const warningsOf = (model) => validateFlowGraph(model).filter((finding) => finding.severity === 'warning');
const locationsOf = (findings) => findings.map((finding) => finding.location);

/** Reads the model a rendered page embeds, the same way the page does. */
const readEmbeddedModel = (html) => JSON.parse(html.match(/<script type="application\/json" id="flow-graph-model">(.*?)<\/script>/s)[1]);

describe('validateFlowGraph', () => {
  test('accepts the example model without findings', () => {
    assert.deepEqual(validateFlowGraph(loadExampleModel()), []);
  });

  test('rejects a changed node without evidence', () => {
    const model = loadExampleModel();
    delete model.nodes[1].evidence;

    const errors = errorsOf(model);

    assert.deepEqual(locationsOf(errors), ['nodes[1].evidence']);
    assert.match(errors[0].message, /added/);
  });

  test('accepts an unchanged node without evidence', () => {
    const model = loadExampleModel();
    const unchangedNode = model.nodes.find((node) => node.change === 'unchanged');

    assert.equal(unchangedNode.evidence, undefined);
    assert.deepEqual(errorsOf(model), []);
  });

  test('rejects a verified relationship without evidence even when it did not change', () => {
    const model = loadExampleModel();
    const transition = model.businessFlow.transitions.find((candidate) => candidate.id === 'untap-favorite');
    transition.evidence = [];

    assert.deepEqual(locationsOf(errorsOf(model)), ['businessFlow.transitions[4].evidence']);
  });

  test('rejects an inferred relationship that does not say why', () => {
    const model = loadExampleModel();
    delete model.edges[2].reason;

    assert.deepEqual(locationsOf(errorsOf(model)), ['edges[2].reason']);
  });

  test('rejects an edge that points at a node that does not exist', () => {
    const model = loadExampleModel();
    model.edges[0].target = 'missing-node';

    assert.deepEqual(locationsOf(errorsOf(model)), ['edges[0].target']);
  });

  test('rejects duplicated identifiers', () => {
    const model = loadExampleModel();
    model.nodes[1].id = model.nodes[0].id;

    assert.ok(locationsOf(errorsOf(model)).includes('nodes[1].id'));
  });

  test('rejects a relationship that shares its id with one of the things its view shows', () => {
    const model = loadExampleModel();
    model.edges[0].id = model.nodes[0].id;
    model.businessFlow.transitions[0].id = model.businessFlow.states[0].id;

    const errors = errorsOf(model);

    assert.deepEqual(locationsOf(errors), ['edges[0].id', 'businessFlow.transitions[0].id']);
    assert.match(errors[0].message, /also the id of a node/);
    assert.match(errors[1].message, /also the id of a business state/);
  });

  test('rejects a changed business state without evidence and accepts an unchanged one', () => {
    const model = loadExampleModel();
    const changedIndex = model.businessFlow.states.findIndex((state) => state.change !== 'unchanged');
    delete model.businessFlow.states[changedIndex].evidence;

    assert.deepEqual(locationsOf(errorsOf(model)), [`businessFlow.states[${changedIndex}].evidence`]);
  });

  test('rejects malformed evidence on a business state', () => {
    const model = loadExampleModel();
    model.businessFlow.states[1].evidence = [{ path: '/etc/passwd', line: 0 }];

    assert.deepEqual(locationsOf(errorsOf(model)), ['businessFlow.states[1].evidence[0].path', 'businessFlow.states[1].evidence[0].line']);
  });

  test('rejects absolute evidence paths and non-positive lines', () => {
    const model = loadExampleModel();
    model.nodes[0].evidence = [{ path: 'C:\\repo\\File.kt', line: 0 }];

    assert.deepEqual(locationsOf(errorsOf(model)), ['nodes[0].evidence[0].path', 'nodes[0].evidence[0].line']);
  });

  test('rejects a model where the pull request changed nothing', () => {
    const model = loadExampleModel();
    delete model.businessFlow;
    for (const element of [...model.nodes, ...model.edges]) element.change = 'unchanged';

    assert.ok(errorsOf(model).some((finding) => /does not show what the pull request changed/.test(finding.message)));
  });

  test('requires exactly one initial business state', () => {
    const model = loadExampleModel();
    model.businessFlow.states[1].kind = 'initial';

    assert.ok(errorsOf(model).some((finding) => finding.location === 'businessFlow.states' && /found 2/.test(finding.message)));
  });

  test('warns about a business state that cannot be reached and still allows the render', () => {
    const model = loadExampleModel();
    model.businessFlow.transitions = model.businessFlow.transitions.filter((transition) => transition.target !== 'save-failed');

    const findings = validateFlowGraph(model);

    assert.ok(warningsOf(model).some((finding) => /"save-failed" cannot be reached/.test(finding.message)));
    assert.equal(hasBlockingFindings(findings), false);
  });

  test('warns about a node that no relationship touches', () => {
    const model = loadExampleModel();
    model.nodes.push({ id: 'orphan-helper', label: 'OrphanHelper', kind: 'other', change: 'unchanged' });

    assert.deepEqual(locationsOf(warningsOf(model)), ['nodes[7]']);
  });

  test('rejects a relationship that outlives one of its ends', () => {
    const model = loadExampleModel();
    model.edges[0].change = 'modified';
    model.edges[6].change = 'unchanged';

    const errors = errorsOf(model);

    assert.deepEqual(locationsOf(errors), ['edges[0].change', 'edges[6].change']);
    assert.match(errors[0].message, /Must be "added" because the node "toggle-favorite-action" is added/);
    assert.match(errors[1].message, /Must be "removed" because the node "legacy-wishlist-client" is removed/);
  });

  test('rejects two relationships that say the same thing', () => {
    const model = loadExampleModel();
    model.edges.push({ ...model.edges[0], id: 'screen-dispatches-toggle-again' });
    model.businessFlow.transitions.push({ ...model.businessFlow.transitions[0], id: 'tap-favorite-again', target: 'favorite' });

    const errors = errorsOf(model);

    assert.deepEqual(locationsOf(errors), ['edges[7]', 'businessFlow.transitions[5]']);
    assert.match(errors[0].message, /Repeats edges\[0\]/);
    assert.match(errors[1].message, /Repeats businessFlow\.transitions\[0\].*would not know which one to follow/);
  });

  test('requires the business flow to say in one sentence what changes for the user', () => {
    const model = loadExampleModel();
    delete model.businessFlow.summary;

    assert.deepEqual(locationsOf(errorsOf(model)), ['businessFlow.summary']);
  });

  test('requires a path and a reason for each file left out of the graph', () => {
    const model = loadExampleModel();
    model.outOfScope = [{ path: 'docs/', reason: 'Documentación.' }, { path: 'gradle/libs.versions.toml' }, 'README.md'];

    assert.deepEqual(locationsOf(errorsOf(model)), ['outOfScope[1].reason', 'outOfScope[2]']);
  });

  test('reports a model that is not an object instead of throwing', () => {
    assert.deepEqual(locationsOf(validateFlowGraph(null)), ['(root)']);
  });
});

describe('Mermaid output', () => {
  test('draws inferred relationships dashed and verified ones solid', () => {
    const flowchart = renderChangeFlowchart(loadExampleModel());

    assert.match(flowchart, /dispatcher -\.->\|"\+ actualiza"\| favorites_store/);
    assert.match(flowchart, /favorites_store -->\|"\+ llama"\| favorites_repository/);
  });

  test('groups nodes in subgraphs and classifies them by change', () => {
    const flowchart = renderChangeFlowchart(loadExampleModel());

    assert.match(flowchart, /subgraph flux\["Flux"\]\n {4}toggle_favorite_action\["ToggleFavoriteAction"\]/);
    assert.match(flowchart, /class legacy_wishlist_client removed/);
    assert.match(flowchart, /class product_detail_screen modified/);
  });

  test('starts the state diagram at the initial state and marks inferred transitions', () => {
    const diagram = renderBusinessStateDiagram(loadExampleModel().businessFlow);

    assert.match(diagram, /\[\*\] --> not_favorite/);
    assert.match(diagram, /save_failed --> saving: \+ Reintentar \(inferida\)/);
    assert.match(diagram, /saving --> save_failed: \+ La API falla \[sin red o 5xx\]/);
  });

  test('escapes the characters that would break a label', () => {
    const model = loadExampleModel();
    model.nodes[0].label = 'Say "hi"';
    model.businessFlow.transitions[0].trigger = 'Status: ok';

    assert.match(renderChangeFlowchart(model), /product_detail_screen\["Say #quot;hi#quot;"\]/);
    assert.match(renderBusinessStateDiagram(model.businessFlow), /not_favorite --> saving: \+ Status#colon; ok/);
  });

  test('omits the business section when the model has no business flow', () => {
    const model = loadExampleModel();
    delete model.businessFlow;

    const markdown = renderMermaidMarkdown(model);

    assert.match(markdown, /```mermaid\nflowchart LR/);
    assert.doesNotMatch(markdown, /stateDiagram-v2/);
  });
});

describe('HTML output', () => {
  test('links each evidence line to its side of the GitHub diff', () => {
    const pullRequestUrl = 'https://github.com/example-org/shop-android/pull/128';

    const headUrl = buildGithubDiffUrl(pullRequestUrl, { path: 'README.md', line: 7 });
    const baseUrl = buildGithubDiffUrl(pullRequestUrl, { path: 'README.md', line: 7, side: 'base' });

    // sha256("README.md"): the anchor GitHub gives that file in "Files changed".
    const readmeAnchor = 'b335630551682c19a781afebcf4d07bf978fb1f8ac04c6bf87428ed5106870f5';
    assert.equal(headUrl, `${pullRequestUrl}/files#diff-${readmeAnchor}R7`);
    assert.equal(baseUrl, `${pullRequestUrl}/files#diff-${readmeAnchor}L7`);
  });

  test('embeds the model with evidence links and leaves no placeholder behind', () => {
    const html = renderFlowGraphHtml(loadExampleModel());
    const embeddedModel = readEmbeddedModel(html);

    assert.doesNotMatch(html, /__FLOW_GRAPH_/);
    assert.match(embeddedModel.nodes[0].evidence[0].href, /^https:\/\/github\.com\/example-org\/shop-android\/pull\/128\/files#diff-[0-9a-f]{64}R74$/);
    assert.match(embeddedModel.nodes[6].evidence[0].href, /L1$/);
    assert.equal(embeddedModel.formalModel, undefined);
  });

  test('leaves evidence without links when the pull request has no URL', () => {
    const model = loadExampleModel();
    delete model.pullRequest.url;

    assert.equal(readEmbeddedModel(renderFlowGraphHtml(model)).nodes[0].evidence[0].href, undefined);
  });

  test('keeps text from the model from closing the script or injecting markup', () => {
    const model = loadExampleModel();
    model.pullRequest.title = 'Fix </script><img src=x onerror=alert(1)> & $& more';

    const html = renderFlowGraphHtml(model);

    assert.doesNotMatch(html, /<img src=x/);
    assert.equal(readEmbeddedModel(html).pullRequest.title, model.pullRequest.title);
    assert.match(html, /<h1 id="title">Fix &lt;\/script&gt;&lt;img src=x onerror=alert\(1\)&gt; &amp; \$&amp; more<\/h1>/);
  });

  test('loads the library from the CDN by default and embeds it when its source is given', () => {
    const model = loadExampleModel();
    const libraryUrl = 'https://cdn.jsdelivr.net/npm/elkjs@0.12.1/lib/elk.bundled.js';

    const linkedHtml = renderFlowGraphHtml(model);
    const inlinedHtml = renderFlowGraphHtml(model, { inlinedLibraries: new Map([[libraryUrl, 'window.ELK = function () {}; // </script>']]) });

    assert.match(linkedHtml, new RegExp(`<script src="${libraryUrl}"></script>`));
    assert.doesNotMatch(inlinedHtml, /<script src=/);
    assert.match(inlinedHtml, /<script data-library="elkjs@0\.12\.1">window\.ELK = function \(\) \{\}; \/\/ <\\\/script><\/script>/);
  });

  test('carries the verification record only when render passes one', () => {
    const checks = [{ id: 'model-shape', label: 'Estructura del modelo', status: 'passed', detail: '7 piezas.' }];

    assert.deepEqual(readEmbeddedModel(renderFlowGraphHtml(loadExampleModel(), { verification: { checks } })).verification, { checks });
    assert.equal(readEmbeddedModel(renderFlowGraphHtml(loadExampleModel())).verification, undefined);
  });

  test('drops a formal model, a verification record or labels written in the input model', () => {
    const model = {
      ...loadExampleModel(),
      formalModel: { language: 'lean4', source: 'theorem never_checked : False := sorry' },
      verification: { checks: [{ id: 'model-shape', label: 'Inventado', status: 'passed', detail: '' }] },
      kindLabels: { view: 'Inventado' },
    };

    const embeddedModel = readEmbeddedModel(renderFlowGraphHtml(model));
    const embeddedWithLean = readEmbeddedModel(renderFlowGraphHtml(model, { leanSource: 'theorem ok : True := trivial' }));

    assert.equal(embeddedModel.formalModel, undefined);
    assert.equal(embeddedModel.verification, undefined);
    assert.notEqual(embeddedModel.kindLabels.view, 'Inventado');
    assert.equal(embeddedWithLean.formalModel.source, 'theorem ok : True := trivial');
  });

  test('includes the Lean source only when it is passed', () => {
    const html = renderFlowGraphHtml(loadExampleModel(), { leanSource: 'theorem ok : True := trivial' });

    assert.deepEqual(readEmbeddedModel(html).formalModel, { language: 'lean4', source: 'theorem ok : True := trivial' });
  });
});

describe('report and output checks', () => {
  const NOT_REQUESTED = { requested: false, included: false, detail: 'No se pidió un modelo formal.' };
  const REPOSITORY_STATISTICS = {
    evidenceCount: 13, changedElementCount: 11, verifiedRelationshipCount: 6, changedFileCount: 9, outOfScopeFileCount: 2, baseCommit: 'aaaaaaa', headCommit: 'bbbbbbb',
  };
  const statusesOf = (checks) => Object.fromEntries(checks.map((check) => [check.id, check.status]));

  test('marks the repository checks as skipped when the repository was not read', () => {
    const checks = buildVerificationChecks({ model: loadExampleModel(), leanOutcome: NOT_REQUESTED });

    assert.deepEqual(statusesOf(checks), {
      'model-shape': 'passed', 'evidence-exists': 'skipped', 'change-matches-diff': 'skipped', 'relationship-names-endpoint': 'skipped',
      'diff-coverage': 'skipped', 'formal-model': 'skipped', outputs: 'passed',
    });
  });

  test('marks them as passed with what was counted, and a rejected Lean model as a warning', () => {
    const leanOutcome = { requested: true, included: false, detail: '`lean` rejected the Lean model: unsolved goals' };

    const checks = buildVerificationChecks({ model: loadExampleModel(), repositoryStatistics: REPOSITORY_STATISTICS, leanOutcome });

    assert.equal(statusesOf(checks)['evidence-exists'], 'passed');
    assert.equal(statusesOf(checks)['formal-model'], 'warning');
    assert.match(checks.find((check) => check.id === 'diff-coverage').detail, /9 archivos cambiados: 7 en el grafo y 2 declarados fuera/);
  });

  test('writes the report from the model: counts, the business sentence, each inferred relationship and each check', () => {
    const model = loadExampleModel();
    model.outOfScope = [{ path: 'docs/', reason: 'Documentación.' }];
    const checks = buildVerificationChecks({ model, repositoryStatistics: REPOSITORY_STATISTICS, leanOutcome: NOT_REQUESTED });

    const report = renderReport({ model, paths: { html: 'out/pr-flow-graph.html', mermaid: 'out/pr-flow-graph.md' }, checks, leanOutcome: NOT_REQUESTED });

    assert.match(report, /^\*\*Grafo:\*\* out\/pr-flow-graph\.html\n\*\*Mermaid para el PR:\*\* out\/pr-flow-graph\.md\n/);
    assert.match(report, /- \*\*Cambios:\*\* 9 agregados, 1 modificado, 2 eliminados \(piezas y relaciones\) en flux-unidirectional/);
    assert.match(report, /- \*\*Flujo de negocio:\*\* Desde el detalle de un producto/);
    assert.match(report, /- \*\*Relaciones inferidas:\*\* 2, conviene que una persona las confirme\n  - Dispatcher → FavoritesStore \(actualiza\): /);
    assert.match(report, /  - No se pudo guardar → Guardando \(Reintentar\): /);
    assert.match(report, /- \*\*Fuera del grafo:\*\*\n  - `docs\/`: Documentación\./);
    assert.match(report, /- \*\*Modelo formal:\*\* no pedido/);
    assert.match(report, /  - ✓ Cada evidencia existe en el código\. 13 líneas abiertas entre aaaaaaa \(antes\) y bbbbbbb \(después\)\./);
  });

  test('says so when the pull request changes nothing observable and nothing is inferred or left out', () => {
    const model = loadExampleModel();
    delete model.businessFlow;
    model.edges = model.edges.filter((edge) => edge.confidence === 'verified');
    const checks = buildVerificationChecks({ model, leanOutcome: NOT_REQUESTED });

    const report = renderReport({ model, paths: { html: 'a.html', mermaid: 'a.md' }, checks, leanOutcome: NOT_REQUESTED });

    assert.match(report, /- \*\*Flujo de negocio:\*\* sin cambios observables/);
    assert.match(report, /- \*\*Relaciones inferidas:\*\* ninguna/);
    assert.match(report, /- \*\*Fuera del grafo:\*\* nada declarado/);
    assert.match(report, /– Cada evidencia existe en el código\. No se comprobó/);
  });

  test('finds a page or a diagram that lost part of the model', () => {
    const model = loadExampleModel();
    const html = renderFlowGraphHtml(model);
    const mermaid = renderMermaidMarkdown(model);
    const shorterModel = loadExampleModel();
    shorterModel.edges.pop();

    assert.deepEqual(findOutputMismatches(model, html, mermaid), []);
    assert.deepEqual(findOutputMismatches(model, renderFlowGraphHtml(shorterModel), mermaid), ['The generated page does not carry the same `edges` as the model.']);
    assert.deepEqual(findOutputMismatches(model, html, mermaid.replaceAll('favorites_store', 'store')), ['The Mermaid file does not draw "favorites-store".']);
    assert.deepEqual(findOutputMismatches(model, '<html></html>', mermaid), ['The generated page does not embed the model.']);
  });
});

describe('Lean gate and CLI', () => {
  let workDirectory;
  const writeWorkFile = (name, content) => {
    const filePath = path.join(workDirectory, name);
    writeFileSync(filePath, content);
    return filePath;
  };
  const runCli = (...commandArguments) => spawnSync(process.execPath, [CLI_PATH, ...commandArguments], { encoding: 'utf8', env: { ...process.env, NO_COLOR: '1' } });

  before(() => {
    workDirectory = mkdtempSync(path.join(tmpdir(), 'pr-flow-graph-'));
  });
  after(() => {
    rmSync(workDirectory, { recursive: true, force: true });
  });

  test('accepts a Lean model the checker compiles and returns its source', () => {
    const leanPath = writeWorkFile('Accepted.lean', 'theorem ok : True := trivial\n');

    const leanCheck = checkLeanModel(leanPath, FAKE_LEAN_OPTIONS);

    assert.equal(leanCheck.status, 'compiled');
    assert.equal(leanCheck.source, 'theorem ok : True := trivial\n');
  });

  test('rejects a Lean model the checker does not compile and reports its first error', () => {
    const leanPath = writeWorkFile('Rejected.lean', '-- REJECT_THIS_MODEL\ntheorem broken : False := by simp\n');

    const leanCheck = checkLeanModel(leanPath, FAKE_LEAN_OPTIONS);

    assert.equal(leanCheck.status, 'failed');
    assert.match(leanCheck.detail, /unsolved goals/);
    assert.equal(leanCheck.source, undefined);
  });

  test('rejects a Lean model that uses sorry without running the checker', () => {
    const leanPath = writeWorkFile('Unproven.lean', 'theorem pending : 1 = 2 := by\n  sorry\n');

    const leanCheck = checkLeanModel(leanPath, FAKE_LEAN_OPTIONS);

    assert.equal(leanCheck.status, 'unproven');
    assert.match(leanCheck.detail, /`sorry`/);
  });

  test('does not treat sorry inside a comment as an unproven theorem', () => {
    const leanPath = writeWorkFile('Commented.lean', '/- no sorry here -/\n-- sorry is not used\ntheorem ok : True := trivial\n');

    assert.equal(checkLeanModel(leanPath, FAKE_LEAN_OPTIONS).status, 'compiled');
  });

  test('rejects a Lean model that leaves out a business state or states no theorem, without running the checker', () => {
    const leanPath = writeWorkFile('Partial.lean', 'inductive State where\n  | notFavorite | saving\ntheorem ok : True := trivial\n');
    const definitionsOnlyPath = writeWorkFile('Definitions.lean', 'inductive State where\n  | notFavorite\n');

    const partial = checkLeanModel(leanPath, { ...FAKE_LEAN_OPTIONS, expectedStateIds: ['not-favorite', 'saving', 'save-failed'] });
    const complete = checkLeanModel(leanPath, { ...FAKE_LEAN_OPTIONS, expectedStateIds: ['not-favorite', 'saving'] });
    const definitionsOnly = checkLeanModel(definitionsOnlyPath, FAKE_LEAN_OPTIONS);

    assert.equal(partial.status, 'incomplete');
    assert.match(partial.detail, /does not name these business states: saveFailed/);
    assert.equal(complete.status, 'compiled');
    assert.equal(definitionsOnly.status, 'incomplete');
    assert.match(definitionsOnly.detail, /states no `theorem`/);
  });

  test('reports that Lean is not installed when the executable is missing', () => {
    const leanPath = writeWorkFile('Unchecked.lean', 'theorem ok : True := trivial\n');

    const leanCheck = checkLeanModel(leanPath, { command: 'pr-flow-graph-missing-lean-executable' });

    assert.equal(leanCheck.status, 'not-installed');
  });

  test('the real Lean compiler accepts the example model and rejects it once a transition breaks a theorem', { skip: REAL_LEAN_SKIP_REASON }, () => {
    const brokenSource = readFileSync(EXAMPLE_LEAN_MODEL_PATH, 'utf8').replace('| .saving, .saveFailed => .saveFailed', '| .saving, .saveFailed => .favorite');
    const brokenPath = writeWorkFile('Broken.lean', brokenSource);

    const accepted = checkLeanModel(EXAMPLE_LEAN_MODEL_PATH);
    const rejected = checkLeanModel(brokenPath);

    assert.equal(accepted.status, 'compiled', accepted.detail);
    assert.equal(rejected.status, 'failed');
    assert.match(rejected.detail, /unsolved goals/);
  });

  test('render writes the page, the Mermaid file and the report, and prints their paths and checks as JSON on stdout', () => {
    const outputDirectory = path.join(workDirectory, 'rendered');

    const result = runCli('render', EXAMPLE_MODEL_PATH, '--skip-repo-check', '--out', outputDirectory);

    assert.equal(result.status, 0, result.stderr);
    const { checks, ...output } = JSON.parse(result.stdout);
    assert.deepEqual(output, {
      html: path.join(outputDirectory, 'pr-flow-graph.html'),
      mermaid: path.join(outputDirectory, 'pr-flow-graph.md'),
      report: path.join(outputDirectory, 'pr-flow-graph-report.md'),
      lean: false,
      repositoryChecked: false,
    });
    assert.equal(checks.length, 7);
    assert.deepEqual(readEmbeddedModel(readFileSync(output.html, 'utf8')).verification, { checks });
    assert.match(readFileSync(output.mermaid, 'utf8'), /stateDiagram-v2/);
    assert.match(readFileSync(output.report, 'utf8'), /\*\*Grafo:\*\* .*pr-flow-graph\.html/);
    assert.doesNotMatch(result.stderr, /\u001b\[/, 'NO_COLOR output must not carry ANSI escapes');
  });

  test('render refuses an invalid model, names each error and writes nothing', () => {
    const model = loadExampleModel();
    delete model.edges[2].reason;
    const modelPath = writeWorkFile('invalid.json', JSON.stringify(model));
    const outputDirectory = path.join(workDirectory, 'not-rendered');

    const result = runCli('render', modelPath, '--skip-repo-check', '--out', outputDirectory);

    assert.equal(result.status, 1);
    assert.match(result.stderr, /edges\[2\]\.reason/);
    assert.equal(result.stdout, '');
    assert.equal(existsSync(outputDirectory), false);
  });

  test('validate exits 0 for a valid model and 1 for a file that is not JSON', () => {
    const brokenPath = writeWorkFile('broken.json', '{ not json');

    assert.equal(runCli('validate', EXAMPLE_MODEL_PATH).status, 0);
    const brokenResult = runCli('validate', brokenPath);
    assert.equal(brokenResult.status, 1);
    assert.match(brokenResult.stderr, /no es JSON válido/);
  });

  test('exits 2 on a wrong invocation', () => {
    assert.equal(runCli('draw', EXAMPLE_MODEL_PATH).status, 2);
    assert.equal(runCli('render').status, 2);
    assert.equal(runCli('validate', path.join(workDirectory, 'does-not-exist.json')).status, 2);
    assert.equal(runCli('render', EXAMPLE_MODEL_PATH, '--unknown-flag').status, 2);
    assert.equal(runCli('render', EXAMPLE_MODEL_PATH).status, 2, 'render needs --repo or --skip-repo-check');
  });

  test('prints the usage with --help', () => {
    const result = runCli('--help');

    assert.equal(result.status, 0);
    assert.match(result.stdout, /flow-graph\.mjs render <model\.json>/);
  });
});
