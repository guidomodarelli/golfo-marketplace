import assert from 'node:assert/strict';
import { after, before, beforeEach, describe, test } from 'node:test';

import { UI_SKILL, createFixture } from './helpers/fixture-project.mjs';

const HOST_FILE = 'components/lazy-host.tsx';
const PANEL_FILE = 'components/lazy-panel.tsx';
const TEMPLATE_PANEL_FILE = 'components/lazy-template-panel.ts';
const BOOT_FILE = 'components/lazy-boot.ts';
const POLYFILL_FILE = 'components/lazy-polyfill.ts';
const COMPUTED_FILE = 'components/lazy-computed.ts';
const LOCALE_FILE = 'components/locales/es.ts';

const OPEN_PANEL = 'lazy.panel.open';
const TEMPLATE_PANEL = 'lazy.panel.template';
const BOOT = 'lazy.boot.start';
const COMPUTED = 'lazy.locale.load';

const LAZY_FILES = {
  [BOOT_FILE]: 'import("./lazy-polyfill");\n\nexport function boot() {\n  return "booted";\n}\n',
  [COMPUTED_FILE]: 'export function loadLocale(locale) {\n  return import(`./locales/${locale}`);\n}\n',
  [HOST_FILE]: `import { useState } from "react";

export function LazyHost() {
  const [panel, setPanel] = useState(null);
  const open = async () => {
    const panelModule = await import("./lazy-panel");
    setPanel(panelModule.renderPanel());
  };
  return <button onClick={open}>{panel ?? "Abrir"}</button>;
}

export function loadTemplatePanel() {
  return import(\`./lazy-template-panel\`);
}
`,
  [LOCALE_FILE]: 'export const messages = { title: "Hola" };\n',
  [PANEL_FILE]: 'export function renderPanel() {\n  return <p>Panel</p>;\n}\n',
  [POLYFILL_FILE]: 'globalThis.lazyPolyfill = true;\n',
  [TEMPLATE_PANEL_FILE]: 'export const title = "Plantilla";\n',
};

const LAZY_UNITS = {
  [BOOT]: { entries: [{ path: BOOT_FILE, symbol: 'boot' }], subflow: 'Boot' },
  [COMPUTED]: { entries: [{ path: COMPUTED_FILE, symbol: 'loadLocale' }], subflow: 'Locale' },
  [OPEN_PANEL]: { entries: [{ path: HOST_FILE, symbol: 'LazyHost/open' }], subflow: 'Open' },
  [TEMPLATE_PANEL]: { entries: [{ path: HOST_FILE, symbol: 'loadTemplatePanel' }], subflow: 'Template' },
};

describe('literal dynamic imports in symbol analysis', () => {
  let fixture;
  let verifiedHead;
  before(() => {
    fixture = createFixture({ withUnits: false });
    for (const [relativePath, content] of Object.entries(LAZY_FILES)) fixture.write(relativePath, content);
    for (const [unitId, { entries, subflow }] of Object.entries(LAZY_UNITS)) {
      fixture.writeUnit(unitId, { entries, hierarchy: { module: 'Lazy', page: 'Loading', section: 'Dynamic imports', subflow } });
    }
    for (const unitId of [OPEN_PANEL, TEMPLATE_PANEL, BOOT]) fixture.verifyUiUx(unitId);
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

  test('a handler that loads a module with import() depends on that module', () => {
    const inputs = inputsOf(OPEN_PANEL);
    assert.ok(`${HOST_FILE}#LazyHost/open` in inputs.inputs, 'the unit is analyzed by symbol');
    assert.ok(PANEL_FILE in inputs.files);
    assert.ok(`${PANEL_FILE}#renderPanel` in inputs.inputs);
    assert.equal(inputs.via[`${PANEL_FILE}#<module>`], `${HOST_FILE}#LazyHost/open`);

    fixture.replace(PANEL_FILE, '<p>Panel</p>', '<p>Panel actualizado</p>');
    const check = fixture.check(OPEN_PANEL);
    assert.equal(check.freshness, 'stale');
    assert.deepEqual(check.relevantChanges.map((change) => change.key), [`${PANEL_FILE}#renderPanel`]);
  });

  test('a template literal without expressions is followed like a string specifier', () => {
    assert.ok(TEMPLATE_PANEL_FILE in inputsOf(TEMPLATE_PANEL).files);
    fixture.replace(TEMPLATE_PANEL_FILE, '"Plantilla"', '"Plantilla nueva"');
    assert.equal(fixture.check(TEMPLATE_PANEL).freshness, 'stale');
    assert.equal(fixture.check(OPEN_PANEL).freshness, 'current', 'a sibling handler does not depend on it');
  });

  test('a top-level import() in the module shell is followed from <module>', () => {
    const inputs = inputsOf(BOOT);
    assert.ok(POLYFILL_FILE in inputs.files);
    assert.equal(inputs.via[`${POLYFILL_FILE}#<module>`], `${BOOT_FILE}#<module>`);

    fixture.replace(POLYFILL_FILE, 'true', 'false');
    assert.equal(fixture.check(BOOT).freshness, 'stale');
  });

  test('an import() with a computed specifier is not followed', () => {
    const inputs = inputsOf(COMPUTED);
    assert.ok(`${COMPUTED_FILE}#loadLocale` in inputs.inputs);
    assert.ok(!(LOCALE_FILE in inputs.files));
    assert.deepEqual(inputs.unresolved, []);
  });
});
