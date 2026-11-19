import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, test } from 'node:test';

import { UI_SKILL, createFixture } from './helpers/fixture-project.mjs';

const PROVIDERS = 'academy.manage.providers.save';

describe('decision continuations', () => {
  let fixture;
  beforeEach(() => {
    fixture = createFixture();
  });
  afterEach(() => fixture.cleanup());

  test('a partial first run without verified coverage is continued as a full analysis that can be verified', () => {
    const begin = fixture.run(['begin', '--unit', PROVIDERS, '--skill', UI_SKILL, '--mode', 'full']);
    const runId = begin.json.runId;
    fixture.run(['evidence', '--run', runId, '--kind', 'review', '--outcome', 'pass', '--summary', 'state matrix reviewed']);
    fixture.run(['evidence', '--run', runId, '--kind', 'test', '--exec', `"${process.execPath}" -e "process.exit(0)"`]);
    const partial = fixture.run(['record', '--run', runId, '--result', 'verified']);
    assert.equal(partial.json.result, 'partial');
    assert.ok(partial.json.downgradeReasons.some((reason) => reason.includes('browser')));

    const check = fixture.check(PROVIDERS);
    assert.equal(check.state, 'partial');
    assert.equal(check.decision, 'full');
    assert.equal(check.mode, 'full');
    assert.ok(check.reasons.some((reason) => reason.includes('no verified coverage')));
    assert.ok(check.suggestedScope.some((scope) => scope.startsWith('pending from the previous run')));
    assert.ok(check.suggestedScope.some((scope) => scope.includes(PROVIDERS)));

    const recorded = fixture.verifyUiUx(PROVIDERS, { mode: check.mode });
    assert.equal(recorded.result, 'verified');
    assert.equal(recorded.downgraded, false);
    assert.equal(fixture.check(PROVIDERS).decision, 'skip');
  });

  test('an incremental run after a rules change and a code change re-checks both', () => {
    fixture.verifyUiUx(PROVIDERS);
    fixture.writeSkill(UI_SKILL, '1.1.0', 'otras reglas');
    fixture.replace('lib/http.ts', 'method: "POST"', 'method: "PUT"');

    const check = fixture.check(PROVIDERS);
    assert.equal(check.decision, 'incremental');
    assert.ok(check.suggestedScope.includes(`re-check the unit against the rules changed in ${UI_SKILL}/SKILL.md`));
    assert.ok(check.suggestedScope.some((scope) => scope.includes('lib/http.ts')));
  });
});
