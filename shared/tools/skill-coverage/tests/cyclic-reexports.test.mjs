import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { after, before, beforeEach, describe, test } from 'node:test';

import { CLI_PATH, UI_SKILL, createFixture } from './helpers/fixture-project.mjs';

/** A circular barrel graph must resolve in well under this time. */
const CLI_TIMEOUT_MS = 30_000;
const TEST_TIMEOUT_MS = 120_000;

const BARREL_FILE = 'lib/pricing/index.ts';
const MIRROR_FILE = 'lib/pricing/mirror.ts';
const FORMAT_FILE = 'lib/pricing/format.ts';
const NAMESPACE_FILE = 'lib/catalog/index.ts';
const CATALOG_FILE = 'lib/catalog/products.ts';

const CYCLIC_FILES = {
  [BARREL_FILE]: 'export * from "./mirror";\nexport * from "./format";\nexport { formatPrice as price } from "./format";\n',
  [CATALOG_FILE]: 'export * from "./index";\nexport const catalogName = "Cursos";\n',
  [FORMAT_FILE]: 'export function formatPrice(value) {\n  return `$${value}`;\n}\n',
  [MIRROR_FILE]: 'export * from "./index";\n',
  [NAMESPACE_FILE]: 'export * as products from "./products";\n',
};

const SYMBOL_UNIT = 'pricing.format.symbol';
const WHOLE_BARREL_UNIT = 'pricing.format.barrel';
const NAMESPACE_UNIT = 'catalog.products.namespace';

const CYCLIC_UNITS = {
  [NAMESPACE_UNIT]: { entries: [{ path: NAMESPACE_FILE, symbol: '*' }], subflow: 'Namespace' },
  [SYMBOL_UNIT]: { entries: [{ path: BARREL_FILE, symbol: 'formatPrice' }], subflow: 'Symbol' },
  [WHOLE_BARREL_UNIT]: { entries: [{ path: BARREL_FILE, symbol: '*' }], subflow: 'Barrel' },
};

describe('circular re-exports in symbol analysis', { timeout: TEST_TIMEOUT_MS }, () => {
  let fixture;
  let verifiedHead;

  /**
   * Runs the real CLI with a hard timeout, so a traversal that never ends
   * fails the test instead of hanging the suite.
   *
   * @param {string[]} args
   * @returns {any} Parsed JSON output.
   */
  const runBounded = (args) => {
    const result = spawnSync(process.execPath, [CLI_PATH, ...args, '--root', fixture.root, '--skills-dir', fixture.skillsDirectory, '--json'], {
      encoding: 'utf8',
      killSignal: 'SIGKILL',
      timeout: CLI_TIMEOUT_MS,
    });
    assert.equal(result.error?.code, undefined, `skill-coverage ${args.join(' ')} did not finish within ${CLI_TIMEOUT_MS} ms`);
    assert.equal(result.status, 0, `skill-coverage ${args.join(' ')} failed: ${result.stderr}`);
    return JSON.parse(result.stdout);
  };

  /**
   * @param {string} unitId
   * @returns {any} `inputs` payload of the unit for the UI/UX skill.
   */
  const inputsOf = (unitId) => runBounded(['inputs', '--unit', unitId, '--skill', UI_SKILL]);

  /**
   * @param {string} unitId
   * @returns {any} `check` payload of the unit for the UI/UX skill.
   */
  const checkOf = (unitId) => runBounded(['check', '--unit', unitId, '--skill', UI_SKILL]);

  before(() => {
    fixture = createFixture({ withUnits: false });
    for (const [relativePath, content] of Object.entries(CYCLIC_FILES)) fixture.write(relativePath, content);
    for (const [unitId, { entries, subflow }] of Object.entries(CYCLIC_UNITS)) {
      fixture.writeUnit(unitId, { entries, hierarchy: { module: 'Pricing', page: 'Barrels', section: 'Circular re-exports', subflow } });
    }
    // Traverse every unit under the timeout first: the recording below runs
    // the CLI without one.
    for (const unitId of Object.keys(CYCLIC_UNITS)) inputsOf(unitId);
    for (const unitId of Object.keys(CYCLIC_UNITS)) fixture.verifyUiUx(unitId);
    fixture.git('add', '-A');
    fixture.git('commit', '--quiet', '-m', 'record coverage');
    verifiedHead = fixture.git('rev-parse', 'HEAD');
  });
  beforeEach(() => {
    fixture.git('reset', '--quiet', '--hard', verifiedHead);
    fixture.git('clean', '--quiet', '-fd');
  });
  after(() => fixture?.cleanup());

  test('a symbol reached through a cycle of export * barrels is found and tracked', () => {
    const inputs = inputsOf(SYMBOL_UNIT);
    assert.equal(inputs.truncated, false);
    assert.ok(`${FORMAT_FILE}#formatPrice` in inputs.inputs, 'the declaration in the leaf module is an input');
    assert.ok(MIRROR_FILE in inputs.files, 'the barrel that re-exports back is analyzed');

    fixture.replace(FORMAT_FILE, '`$${value}`', '`ARS ${value}`');
    const check = checkOf(SYMBOL_UNIT);
    assert.equal(check.freshness, 'stale');
    assert.deepEqual(check.relevantChanges.map((change) => change.key), [`${FORMAT_FILE}#formatPrice`]);
  });

  test('a whole barrel with export * and named re-exports in a cycle is tracked once', () => {
    const inputs = inputsOf(WHOLE_BARREL_UNIT);
    assert.equal(inputs.truncated, false);
    assert.ok(`${FORMAT_FILE}#formatPrice` in inputs.inputs);
    assert.ok(MIRROR_FILE in inputs.files);

    fixture.replace(FORMAT_FILE, '`$${value}`', '`ARS ${value}`');
    assert.equal(checkOf(WHOLE_BARREL_UNIT).freshness, 'stale');
  });

  test('an export * as namespace whose target re-exports the barrel back is tracked', () => {
    const inputs = inputsOf(NAMESPACE_UNIT);
    assert.equal(inputs.truncated, false);
    assert.ok(`${CATALOG_FILE}#catalogName` in inputs.inputs);

    fixture.replace(CATALOG_FILE, '"Cursos"', '"Cursos nuevos"');
    assert.equal(checkOf(NAMESPACE_UNIT).freshness, 'stale');
    assert.equal(checkOf(SYMBOL_UNIT).freshness, 'current', 'an unrelated barrel does not depend on it');
  });
});
