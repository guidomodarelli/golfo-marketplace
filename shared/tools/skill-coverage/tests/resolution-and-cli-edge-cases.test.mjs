import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, test } from 'node:test';

import { MANAGEMENT_FILE, PERFORMANCE_SKILL, UI_SKILL, createFixture } from './helpers/fixture-project.mjs';

const PROVIDERS = 'academy.manage.providers.save';
const APPROVE = 'academy.manage.requests.approve';
const REJECT = 'academy.manage.requests.reject';
const CHILD_FILE = 'components/child/index.tsx';
const HIERARCHY = { module: 'Academy', page: 'Wrappers', section: null, subflow: 'Wrapper' };

describe('resolution and CLI edge cases', () => {
  let fixture;
  beforeEach(() => {
    fixture = createFixture();
  });
  afterEach(() => fixture.cleanup());

  test('an imported component re-exported under a local alias is followed to its module', () => {
    fixture.write(CHILD_FILE, 'export default function Child() {\n  return <p>Hola</p>;\n}\n');
    fixture.write('components/default-wrapper.tsx', 'import Child from "./child";\n\nexport default Child;\n');
    fixture.write('components/named-wrapper.tsx', 'import Child from "./child";\n\nexport { Child as View };\n');
    fixture.writeUnit('wrappers.default', { entries: [{ path: 'components/default-wrapper.tsx', symbol: 'default' }], hierarchy: HIERARCHY });
    fixture.writeUnit('wrappers.named', { entries: [{ path: 'components/named-wrapper.tsx', symbol: 'View' }], hierarchy: HIERARCHY });

    for (const unitId of ['wrappers.default', 'wrappers.named']) {
      const inputs = fixture.run(['inputs', '--unit', unitId, '--skill', UI_SKILL]).json;
      assert.ok(`${CHILD_FILE}#Child` in inputs.inputs, `${unitId} reaches the child component`);
      assert.deepEqual(inputs.warnings, []);
      fixture.verifyUiUx(unitId);
    }

    fixture.replace(CHILD_FILE, '<p>Hola</p>', '<p>Chau</p>');
    for (const unitId of ['wrappers.default', 'wrappers.named']) {
      const check = fixture.check(unitId);
      assert.equal(check.freshness, 'stale', `${unitId} sees the change in the child`);
      assert.ok(check.relevantChanges.some((change) => change.key === `${CHILD_FILE}#Child`));
    }
  });

  test('a top-level initializer that does work on import belongs to the module shell', () => {
    fixture.verifyUiUx(PROVIDERS);
    fixture.verifyPerformance(PROVIDERS);

    fixture.replace(MANAGEMENT_FILE, 'export function AcademyManagement', 'const refreshTimer = setInterval(() => {}, 1000);\n\nexport function AcademyManagement');
    const performance = fixture.check(PROVIDERS, 'measured-performance-optimization');
    assert.equal(performance.freshness, 'stale');
    assert.ok(performance.relevantChanges.some((change) => change.key === `${MANAGEMENT_FILE}#<module>` && /timers/.test(change.reason)));
    assert.equal(fixture.check(PROVIDERS).freshness, 'stale');
  });

  test('a pure top-level initializer that nobody uses does not invalidate the units of the file', () => {
    fixture.verifyUiUx(PROVIDERS);
    fixture.replace(MANAGEMENT_FILE, 'export function AcademyManagement', 'const COPY_KEYS = Object.keys(COPY);\nconst lazyLoad = () => fetch("/api/later");\n\nexport function AcademyManagement');
    assert.equal(fixture.check(PROVIDERS).freshness, 'current');
  });

  test('with baseUrl and no paths, bare project imports resolve to files, not packages', () => {
    fixture.write('tsconfig.json', '{ "compilerOptions": { "baseUrl": "." } }\n');
    fixture.write('components/bare/index.tsx', 'import { request } from "lib/http";\n\nexport function Bare() {\n  return request("/api/bare", {});\n}\n');
    fixture.writeUnit('bare.view', { entries: [{ path: 'components/bare/index.tsx', symbol: 'Bare' }], hierarchy: HIERARCHY });

    const inputs = fixture.run(['inputs', '--unit', 'bare.view', '--skill', UI_SKILL]).json.inputs;
    assert.ok('lib/http.ts#request' in inputs);
    assert.ok(!('pkg:lib' in inputs));

    fixture.verifyUiUx('bare.view');
    fixture.replace('lib/http.ts', 'method: "POST"', 'method: "PUT"');
    assert.equal(fixture.check('bare.view').freshness, 'stale');
  });

  test('affected keeps every path given after --paths and other commands reject stray operands', () => {
    const affected = fixture.run(['affected', '--paths', 'unrelated.txt', 'lib/http.ts', '--skill', UI_SKILL]).json;
    assert.deepEqual(affected.paths, ['lib/http.ts', 'unrelated.txt']);
    assert.deepEqual(affected.affected.map((item) => item.unit).sort(), [PROVIDERS, APPROVE, REJECT]);

    const stray = fixture.run(['check', '--unit', PROVIDERS, '--skill', UI_SKILL, 'extra.txt']);
    assert.equal(stray.status, 2);
    assert.match(stray.stderr, /does not take extra arguments: extra\.txt/);
  });

  test('a performance baseline recorded over uncommitted code is not offered as the measured revision', () => {
    const previousHead = fixture.git('rev-parse', 'HEAD');
    fixture.replace('lib/http.ts', 'method: "POST"', 'method: "POST", keepalive: true');
    fixture.verifyPerformance(PROVIDERS);
    fixture.git('add', '-A');
    fixture.git('commit', '--quiet', '-m', 'measured flow');

    fixture.replace(MANAGEMENT_FILE, 'const result = await saveProvider({ name: "x" });', 'await fetch("/api/providers/validate");\n    const result = await saveProvider({ name: "x" });');
    const check = fixture.check(PROVIDERS, PERFORMANCE_SKILL);
    assert.equal(check.decision, 'incremental');
    assert.doesNotMatch(check.suggestedScope[0], new RegExp(`revision ${previousHead.slice(0, 12)} \\(last measured\\)`));
    assert.match(check.suggestedScope[0], /recorded over uncommitted changes/);
  });
});
