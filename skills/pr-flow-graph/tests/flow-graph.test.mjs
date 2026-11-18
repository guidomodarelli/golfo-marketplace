import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { after, before, describe, test } from 'node:test';

import { checkLeanModel } from '../scripts/lib/check-lean-model.mjs';
import { buildGithubDiffUrl, renderFlowGraphHtml } from '../scripts/lib/render-html.mjs';
import { renderBusinessStateDiagram, renderChangeFlowchart, renderMermaidMarkdown } from '../scripts/lib/render-mermaid.mjs';
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

  test('includes the Lean source only when it is passed', () => {
    const html = renderFlowGraphHtml(loadExampleModel(), { leanSource: 'theorem ok : True := trivial' });

    assert.deepEqual(readEmbeddedModel(html).formalModel, { language: 'lean4', source: 'theorem ok : True := trivial' });
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

  test('render writes the page and the Mermaid file and prints their paths as JSON on stdout', () => {
    const outputDirectory = path.join(workDirectory, 'rendered');

    const result = runCli('render', EXAMPLE_MODEL_PATH, '--out', outputDirectory);

    assert.equal(result.status, 0, result.stderr);
    const output = JSON.parse(result.stdout);
    assert.deepEqual(output, {
      html: path.join(outputDirectory, 'pr-flow-graph.html'),
      mermaid: path.join(outputDirectory, 'pr-flow-graph.md'),
      lean: false,
    });
    assert.ok(existsSync(output.html));
    assert.match(readFileSync(output.mermaid, 'utf8'), /stateDiagram-v2/);
    assert.doesNotMatch(result.stderr, /\u001b\[/, 'NO_COLOR output must not carry ANSI escapes');
  });

  test('render refuses an invalid model, names each error and writes nothing', () => {
    const model = loadExampleModel();
    delete model.edges[2].reason;
    const modelPath = writeWorkFile('invalid.json', JSON.stringify(model));
    const outputDirectory = path.join(workDirectory, 'not-rendered');

    const result = runCli('render', modelPath, '--out', outputDirectory);

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
  });

  test('prints the usage with --help', () => {
    const result = runCli('--help');

    assert.equal(result.status, 0);
    assert.match(result.stdout, /flow-graph\.mjs render <model\.json>/);
  });
});
