import assert from 'node:assert/strict';
import { after, before, beforeEach, describe, test } from 'node:test';

import { MANAGEMENT_FILE, PERFORMANCE_SKILL, UI_SKILL, createFixture } from './helpers/fixture-project.mjs';

const PROVIDERS = 'academy.manage.providers.save';

describe('skill-specific policies', () => {
  let fixture;
  let verifiedHead;
  before(() => {
    fixture = createFixture();
    fixture.verifyUiUx(PROVIDERS);
    fixture.verifyPerformance(PROVIDERS);
    fixture.git('add', '-A');
    fixture.git('commit', '--quiet', '-m', 'record coverage');
    verifiedHead = fixture.git('rev-parse', 'HEAD');
  });
  beforeEach(() => {
    fixture.git('reset', '--quiet', '--hard', verifiedHead);
    fixture.git('clean', '--quiet', '-fd');
  });
  after(() => fixture.cleanup());

  test('a copy change invalidates UI/UX but not performance', () => {
    fixture.replace(MANAGEMENT_FILE, 'providersTitle: "Proveedores"', 'providersTitle: "Proveedores de verificación"');
    assert.equal(fixture.check(PROVIDERS, UI_SKILL).freshness, 'stale');
    const performance = fixture.check(PROVIDERS, PERFORMANCE_SKILL);
    assert.equal(performance.freshness, 'current');
    assert.equal(performance.decision, 'skip');
    assert.equal(performance.ignoredChanges[0].reason, 'same load (copy, style, types or refactor)');
  });

  test('a refactor that keeps the same calls does not trigger performance', () => {
    fixture.replace(MANAGEMENT_FILE, 'if (!result.ok) setError(result.message);', 'if (result.ok === false) {\n      setError(result.message);\n    }');
    assert.equal(fixture.check(PROVIDERS, PERFORMANCE_SKILL).decision, 'skip');
  });

  test('a new request in the flow triggers an incremental measurement of the whole flow', () => {
    fixture.replace(MANAGEMENT_FILE, 'const result = await saveProvider({ name: "x" });', 'await fetch("/api/providers/validate");\n    const result = await saveProvider({ name: "x" });');
    const check = fixture.check(PROVIDERS, PERFORMANCE_SKILL);
    assert.equal(check.freshness, 'stale');
    assert.equal(check.decision, 'incremental');
    assert.match(check.relevantChanges[0].reason, /^adds load: .*\+1 requests/);
    assert.match(check.relevantChanges[0].reason, /\+1 awaited steps/);
    assert.match(check.suggestedScope[0], /measure the complete flow .* before = revision [0-9a-f]{12}/);
  });

  test('a new package in the flow triggers performance', () => {
    fixture.replace('lib/http.ts', 'export async function request', 'import { compress } from "heavy-compressor";\n\nexport async function request');
    fixture.replace('lib/http.ts', 'body: JSON.stringify(body)', 'body: compress(JSON.stringify(body))');
    const check = fixture.check(PROVIDERS, PERFORMANCE_SKILL);
    assert.equal(check.decision, 'incremental');
    assert.ok(check.relevantChanges.some((change) => change.key === 'pkg:heavy-compressor' && change.reason.includes('new package')));
  });

  test('style files are outside the performance closure but inside the UI/UX one', () => {
    fixture.write('components/academy-management/styles.module.scss', '.Management { color: red; }\n');
    fixture.replace(MANAGEMENT_FILE, 'import { useState } from "react";', 'import { useState } from "react";\nimport styles from "./styles.module.scss";');
    fixture.replace(MANAGEMENT_FILE, '<h2>{COPY.providersTitle}</h2>', '<h2 className={styles.Management}>{COPY.providersTitle}</h2>');
    const uiInputs = fixture.run(['inputs', '--unit', PROVIDERS, '--skill', UI_SKILL]).json.inputs;
    const performanceInputs = fixture.run(['inputs', '--unit', PROVIDERS, '--skill', PERFORMANCE_SKILL]).json.inputs;
    assert.ok('components/academy-management/styles.module.scss#*' in uiInputs);
    assert.ok(!('components/academy-management/styles.module.scss#*' in performanceInputs));
  });

  test('a performance run needs before and after measured with the same tool', () => {
    const begin = fixture.run(['begin', '--unit', PROVIDERS, '--skill', PERFORMANCE_SKILL, '--mode', 'full', '--force-full']);
    const runId = begin.json.runId;
    fixture.run(['evidence', '--run', runId, '--kind', 'measurement', '--outcome', 'measured', '--summary', 'only after', '--metric', 'LCP', '--after', '1.9 s', '--tool', 'lighthouse', '--conditions', 'mobile throttling']);
    fixture.run(['evidence', '--run', runId, '--kind', 'test', '--exec', `"${process.execPath}" -e "0"`]);
    const record = fixture.run(['record', '--run', runId, '--result', 'verified']);
    assert.equal(record.json.result, 'partial');
    assert.ok(record.json.downgradeReasons.some((reason) => reason.includes('lacks before')));
  });

  test('a new flow can be accredited with an absolute measurement against a reference', () => {
    const begin = fixture.run(['begin', '--unit', PROVIDERS, '--skill', PERFORMANCE_SKILL, '--mode', 'full', '--force-full']);
    const runId = begin.json.runId;
    fixture.run(['evidence', '--run', runId, '--kind', 'measurement', '--outcome', 'measured', '--summary', 'new flow cost', '--metric', 'requests per save', '--after', '1', '--baseline-kind', 'new-flow', '--reference', 'same as the members flow', '--tool', 'playwright', '--conditions', 'production build']);
    fixture.run(['evidence', '--run', runId, '--kind', 'test', '--exec', `"${process.execPath}" -e "0"`]);
    assert.equal(fixture.run(['record', '--run', runId, '--result', 'verified']).json.result, 'verified');
  });

  test('a skill without a built-in policy uses the generic policy and config overrides', () => {
    fixture.writeSkill('semantic-html-a11y', '1.0.0');
    fixture.write('.golfo/skill-coverage/config.json', `${JSON.stringify({ schemaVersion: 1, skills: { 'semantic-html-a11y': { evidence: { full: [['accessibility']] }, label: 'A11y' } } }, null, 2)}\n`);
    const begin = fixture.run(['begin', '--unit', PROVIDERS, '--skill', 'semantic-html-a11y', '--mode', 'full']);
    fixture.run(['evidence', '--run', begin.json.runId, '--kind', 'review', '--outcome', 'pass', '--summary', 'semantics reviewed']);
    fixture.run(['evidence', '--run', begin.json.runId, '--kind', 'test', '--exec', `"${process.execPath}" -e "0"`]);
    const record = fixture.run(['record', '--run', begin.json.runId, '--result', 'verified']);
    assert.equal(record.json.result, 'partial');
    assert.ok(record.json.downgradeReasons.includes('missing passing evidence of kind accessibility'));
  });

  test('a unit can declare a skill not applicable', () => {
    const unit = JSON.parse(fixture.read('.golfo/skill-coverage/units/academy.manage.providers.save.json'));
    unit.skills = { [PERFORMANCE_SKILL]: { applicable: false, reason: 'static copy only' } };
    fixture.write('.golfo/skill-coverage/units/academy.manage.providers.save.json', JSON.stringify(unit));
    const check = fixture.check(PROVIDERS, PERFORMANCE_SKILL);
    assert.equal(check.state, 'not-applicable');
    assert.equal(check.decision, 'not-applicable');
    assert.equal(fixture.check(PROVIDERS, PERFORMANCE_SKILL, ['--force-full']).decision, 'full');
  });
});
