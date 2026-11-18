import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, test } from 'node:test';

import { UI_SKILL, createFixture } from './helpers/fixture-project.mjs';

const PROVIDERS = 'academy.manage.providers.save';
const WITHOUT_PARSER = { GOLFO_COVERAGE_PARSER: 'none' };
const CONFIG_PATH = '.golfo/skill-coverage/config.json';

describe('coverage freshness revalidation', () => {
  let fixture;
  beforeEach(() => {
    fixture = createFixture();
  });
  afterEach(() => fixture.cleanup());

  test('a package upgrade stays visible when coverage is read with another analyzer', () => {
    fixture.verifyUiUx(PROVIDERS);
    fixture.replace('package.json', '"react": "19.0.0"', '"react": "19.1.0"');

    const check = fixture.run(['check', '--unit', PROVIDERS, '--skill', UI_SKILL], { env: WITHOUT_PARSER }).json;
    assert.equal(check.analyzer, 'file-level/1');
    assert.notEqual(check.freshness, 'current');
    assert.notEqual(check.decision, 'skip');
    assert.ok(check.relevantChanges.some((change) => change.key === 'pkg:react' && change.change === 'modified'));
    assert.ok(check.suggestedScope.some((scope) => scope.includes('package react')));
  });

  test('verified coverage that lacks newly required evidence is no longer skipped', () => {
    fixture.verifyUiUx(PROVIDERS);
    assert.equal(fixture.check(PROVIDERS).decision, 'skip');

    fixture.write(CONFIG_PATH, `${JSON.stringify({ schemaVersion: 1, skills: { [UI_SKILL]: { evidence: { full: [['accessibility']] } } } }, null, 2)}\n`);
    const check = fixture.check(PROVIDERS);
    assert.equal(check.freshness, 'stale');
    assert.equal(check.decision, 'full');
    assert.ok(check.reasons.some((reason) => reason.includes('evidence requirements changed') && reason.includes('accessibility')));
    assert.ok(check.suggestedScope.some((scope) => scope.includes('accessibility')));
  });
});
