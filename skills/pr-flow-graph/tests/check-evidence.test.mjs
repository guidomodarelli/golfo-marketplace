/**
 * Evidence checked against a real git repository built in a temporary directory: a base branch
 * and a head branch that adds a file, edits one and deletes another.
 */
import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { after, before, describe, test } from 'node:test';

import { checkEvidenceInRepository } from '../scripts/lib/check-evidence-in-repository.mjs';
import { CLI_PATH } from './support/example-model.mjs';

const BASE_REF = 'main';
const HEAD_REF = 'feature/cart';
const STORE_PATH = 'src/cart/CartStore.kt';
const SCREEN_PATH = 'src/detail/DetailScreen.kt';
const LEGACY_PATH = 'src/legacy/LegacyCart.kt';

const buildModel = (overrides = {}) => ({
  schemaVersion: 1,
  pullRequest: { title: 'Add cart', baseRef: BASE_REF, headRef: HEAD_REF },
  nodes: [
    { id: 'detail-screen', label: 'DetailScreen', kind: 'view', change: 'modified', evidence: [{ path: SCREEN_PATH, line: 3 }] },
    { id: 'cart-store', label: 'CartStore', kind: 'store', change: 'added', evidence: [{ path: STORE_PATH, line: 2 }] },
    { id: 'legacy-cart', label: 'LegacyCart', kind: 'service', change: 'removed', evidence: [{ path: LEGACY_PATH, line: 1, side: 'base' }] },
  ],
  edges: [
    { id: 'screen-calls-store', source: 'detail-screen', target: 'cart-store', kind: 'calls', change: 'added', confidence: 'verified', evidence: [{ path: SCREEN_PATH, line: 3 }] },
    { id: 'screen-calls-legacy', source: 'detail-screen', target: 'legacy-cart', kind: 'calls', change: 'removed', confidence: 'verified', evidence: [{ path: SCREEN_PATH, line: 2, side: 'base' }] },
  ],
  ...overrides,
});

describe('evidence checked against the repository', () => {
  let workDirectory;
  let repositoryPath;
  const git = (...gitArguments) => execFileSync('git', ['-C', repositoryPath, ...gitArguments], { encoding: 'utf8' });
  const writeRepositoryFile = (filePath, content) => {
    const absolutePath = path.join(repositoryPath, filePath);
    mkdirSync(path.dirname(absolutePath), { recursive: true });
    writeFileSync(absolutePath, content);
  };
  const locationsOf = (findings) => findings.map((finding) => finding.location);

  before(() => {
    workDirectory = mkdtempSync(path.join(tmpdir(), 'pr-flow-graph-evidence-'));
    repositoryPath = path.join(workDirectory, 'repository');
    mkdirSync(repositoryPath);
    git('init', '--quiet', `--initial-branch=${BASE_REF}`);
    git('config', 'user.email', 'tests@example.com');
    git('config', 'user.name', 'Tests');
    git('config', 'commit.gpgsign', 'false');
    writeRepositoryFile(SCREEN_PATH, 'class DetailScreen {\n  val cart = LegacyCart()\n}\n');
    writeRepositoryFile(LEGACY_PATH, 'class LegacyCart\n');
    git('add', '.');
    git('commit', '--quiet', '-m', 'base');
    git('switch', '--quiet', '-c', HEAD_REF);
    writeRepositoryFile(STORE_PATH, 'class CartStore {\n  fun add(id: String) {}\n}\n');
    writeRepositoryFile(SCREEN_PATH, 'class DetailScreen {\n  val store = CartStore()\n  fun onTap() = store.add("1")\n  // four lines now\n}\n');
    git('rm', '--quiet', LEGACY_PATH);
    git('add', '.');
    git('commit', '--quiet', '-m', 'head');
    // The check reads the refs, not the working tree: leaving the base branch checked out proves it.
    git('switch', '--quiet', BASE_REF);
  });

  after(() => {
    rmSync(workDirectory, { recursive: true, force: true });
  });

  test('accepts evidence that exists on the side it names', () => {
    assert.deepEqual(checkEvidenceInRepository(buildModel(), repositoryPath), []);
  });

  test('rejects a file that does not exist in the head of the pull request', () => {
    const model = buildModel();
    model.nodes[1].evidence = [{ path: 'src/cart/InventedStore.kt', line: 1 }];

    const findings = checkEvidenceInRepository(model, repositoryPath);

    assert.deepEqual(locationsOf(findings), ['nodes[1].evidence[0]']);
    assert.match(findings[0].message, /InventedStore\.kt does not exist in feature\/cart \(head side\)/);
  });

  test('rejects a line past the end of the file', () => {
    const model = buildModel();
    model.nodes[1].evidence = [{ path: STORE_PATH, line: 4 }];

    const findings = checkEvidenceInRepository(model, repositoryPath);

    assert.deepEqual(locationsOf(findings), ['nodes[1].evidence[0]']);
    assert.match(findings[0].message, /CartStore\.kt:4 is past the end of the file in feature\/cart \(3 lines\)/);
  });

  test('accepts the last line of a file and rejects the one after it', () => {
    const lastLine = buildModel();
    lastLine.nodes[0].evidence = [{ path: SCREEN_PATH, line: 5 }];
    const pastLastLine = buildModel();
    pastLastLine.nodes[0].evidence = [{ path: SCREEN_PATH, line: 6 }];

    assert.deepEqual(checkEvidenceInRepository(lastLine, repositoryPath), []);
    assert.deepEqual(locationsOf(checkEvidenceInRepository(pastLastLine, repositoryPath)), ['nodes[0].evidence[0]']);
  });

  test('reads each side from its own ref: a deleted file needs the base side', () => {
    const model = buildModel();
    delete model.nodes[2].evidence[0].side;

    const findings = checkEvidenceInRepository(model, repositoryPath);

    assert.deepEqual(locationsOf(findings), ['nodes[2].evidence[0]']);
    assert.match(findings[0].message, /use "side": "base"/);
  });

  test('counts the lines of the base version for base evidence', () => {
    const model = buildModel();
    // The screen has five lines in head and three in base.
    model.edges[1].evidence = [{ path: SCREEN_PATH, line: 5, side: 'base' }];

    const findings = checkEvidenceInRepository(model, repositoryPath);

    assert.match(findings[0].message, /DetailScreen\.kt:5 is past the end of the file in main \(3 lines\)/);
  });

  test('checks business flow evidence too', () => {
    const model = buildModel({
      businessFlow: {
        states: [{ id: 'empty-cart', label: 'Carrito vacío', kind: 'initial', change: 'added', evidence: [{ path: 'src/cart/Missing.kt', line: 1 }] }],
        transitions: [],
      },
    });

    assert.deepEqual(locationsOf(checkEvidenceInRepository(model, repositoryPath)), ['businessFlow.states[0].evidence[0]']);
  });

  test('reports once a ref that the clone does not have', () => {
    const model = buildModel();
    model.pullRequest.headRef = 'feature/not-fetched';

    const findings = checkEvidenceInRepository(model, repositoryPath);

    assert.deepEqual(locationsOf(findings), ['pullRequest']);
    assert.match(findings[0].message, /"feature\/not-fetched" is not in .*origin\/feature\/not-fetched.*fetch it/);
  });

  test('reports a directory that is not a git repository', () => {
    const findings = checkEvidenceInRepository(buildModel(), tmpdir());

    assert.deepEqual(locationsOf(findings), ['--repo']);
  });

  test('the CLI refuses to render a model with invented evidence when --repo is given', () => {
    const model = buildModel();
    model.edges[0].evidence = [{ path: SCREEN_PATH, line: 40 }];
    const modelPath = path.join(workDirectory, 'invented.json');
    writeFileSync(modelPath, JSON.stringify(model));
    const runCli = (...extraArguments) => spawnSync(process.execPath, [CLI_PATH, 'render', modelPath, '--out', path.join(workDirectory, 'out'), ...extraArguments], {
      encoding: 'utf8',
      env: { ...process.env, NO_COLOR: '1' },
    });

    const checked = runCli('--repo', repositoryPath);
    const unchecked = runCli();

    assert.equal(checked.status, 1);
    assert.match(checked.stderr, /edges\[0\]\.evidence\[0\]: src\/detail\/DetailScreen\.kt:40 is past the end/);
    assert.equal(checked.stdout, '');
    assert.equal(unchecked.status, 0, 'without --repo the shape is valid, so it renders');
    assert.match(unchecked.stderr, /Evidencia sin comprobar contra el repo/);
  });
});
