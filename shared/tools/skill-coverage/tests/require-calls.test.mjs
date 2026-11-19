import assert from 'node:assert/strict';
import { after, before, beforeEach, describe, test } from 'node:test';

import { UI_SKILL, createFixture } from './helpers/fixture-project.mjs';

const HANDLER_FILE = 'lib/save-handler.js';
const CHILD_FILE = 'lib/child.cjs';
const TEMPLATE_CHILD_FILE = 'lib/template-child.cjs';
const COMPUTED_FILE = 'lib/locale-loader.js';
const LOCALE_FILE = 'lib/locales/es.cjs';

const SAVE = 'require.handler.save';
const TEMPLATE = 'require.handler.template';
const COMPUTED = 'require.locale.load';

const REQUIRE_FILES = {
  [CHILD_FILE]: 'module.exports = {\n  save() {\n    return "v1";\n  },\n};\n',
  [COMPUTED_FILE]: `export function loadLocale(locale) {
  const name = \`./locales/\${locale}.cjs\`;
  return [require(\`./locales/\${locale}.cjs\`), require(name)];
}
`,
  [HANDLER_FILE]: `export function handleSave() {
  const child = require("./child.cjs");
  return child.save();
}

export function loadTemplateChild() {
  return require(\`./template-child.cjs\`);
}
`,
  [LOCALE_FILE]: 'module.exports = { title: "Hola" };\n',
  [TEMPLATE_CHILD_FILE]: 'module.exports = { title: "Plantilla" };\n',
};

const REQUIRE_UNITS = {
  [COMPUTED]: { entries: [{ path: COMPUTED_FILE, symbol: 'loadLocale' }], subflow: 'Locale' },
  [SAVE]: { entries: [{ path: HANDLER_FILE, symbol: 'handleSave' }], subflow: 'Save' },
  [TEMPLATE]: { entries: [{ path: HANDLER_FILE, symbol: 'loadTemplateChild' }], subflow: 'Template' },
};

describe('literal require calls in symbol analysis', () => {
  let fixture;
  let verifiedHead;
  before(() => {
    fixture = createFixture({ withUnits: false });
    for (const [relativePath, content] of Object.entries(REQUIRE_FILES)) fixture.write(relativePath, content);
    for (const [unitId, { entries, subflow }] of Object.entries(REQUIRE_UNITS)) {
      fixture.writeUnit(unitId, { entries, hierarchy: { module: 'Require', page: 'Loading', section: 'CommonJS', subflow } });
    }
    for (const unitId of [SAVE, TEMPLATE]) fixture.verifyUiUx(unitId);
    fixture.git('add', '-A');
    fixture.git('commit', '--quiet', '-m', 'record coverage');
    verifiedHead = fixture.git('rev-parse', 'HEAD');
  });
  beforeEach(() => {
    fixture.git('reset', '--quiet', '--hard', verifiedHead);
    fixture.git('clean', '--quiet', '-fd');
  });
  after(() => fixture.cleanup());

  /**
   * @param {string} unitId
   * @returns {any} `inputs` payload of the unit for the UI/UX skill.
   */
  const inputsOf = (unitId) => fixture.run(['inputs', '--unit', unitId, '--skill', UI_SKILL]).json;

  test('a handler that loads a module with require() depends on that module', () => {
    const inputs = inputsOf(SAVE);
    assert.ok(`${HANDLER_FILE}#handleSave` in inputs.inputs, 'the unit is analyzed by symbol');
    assert.ok(CHILD_FILE in inputs.files);
    assert.equal(inputs.via[`${CHILD_FILE}#<module>`], `${HANDLER_FILE}#handleSave`);

    fixture.replace(CHILD_FILE, '"v1"', '"v2"');
    const check = fixture.check(SAVE);
    assert.equal(check.freshness, 'stale');
    assert.deepEqual(check.relevantChanges.map((change) => change.key), [`${CHILD_FILE}#<module>`]);
    assert.equal(fixture.check(TEMPLATE).freshness, 'current', 'a sibling function does not depend on it');
  });

  test('a template literal without expressions is followed like a string specifier', () => {
    assert.ok(TEMPLATE_CHILD_FILE in inputsOf(TEMPLATE).files);
    fixture.replace(TEMPLATE_CHILD_FILE, '"Plantilla"', '"Plantilla nueva"');
    assert.equal(fixture.check(TEMPLATE).freshness, 'stale');
    assert.equal(fixture.check(SAVE).freshness, 'current');
  });

  test('a require() with a computed argument is not followed', () => {
    const inputs = inputsOf(COMPUTED);
    assert.ok(`${COMPUTED_FILE}#loadLocale` in inputs.inputs);
    assert.ok(!(LOCALE_FILE in inputs.files));
    assert.deepEqual(inputs.unresolved, []);
  });
});
