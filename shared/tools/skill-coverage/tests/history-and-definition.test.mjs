import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, test } from 'node:test';

import { MANAGEMENT_FILE, UI_SKILL, createFixture } from './helpers/fixture-project.mjs';

const PROVIDERS = 'academy.manage.providers.save';
const APPROVE = 'academy.manage.requests.approve';

describe('git history and skill definition', () => {
  let fixture;
  beforeEach(() => {
    fixture = createFixture();
  });
  afterEach(() => fixture.cleanup());

  test('coverage recorded over uncommitted code is provisional and stays current once committed', () => {
    fixture.replace(MANAGEMENT_FILE, '<button onClick={handleSubmit}>Guardar</button>', '<button onClick={handleSubmit}>Guardar proveedor</button>');
    fixture.verifyUiUx(PROVIDERS);
    const record = fixture.readRecord(UI_SKILL, PROVIDERS);
    assert.deepEqual(record.verified.baseline.uncommittedFiles, [MANAGEMENT_FILE]);
    const recordedCommit = record.verified.baseline.commit;

    fixture.git('add', '-A');
    fixture.git('commit', '--quiet', '-m', 'save provider copy');
    const check = fixture.check(PROVIDERS);
    assert.equal(check.freshness, 'current');
    assert.equal(check.decision, 'skip');
    assert.equal(check.baseline.history, 'ancestor');
    assert.equal(check.baseline.commit, recordedCommit);
  });

  test('a rewritten history with an unreachable baseline commit is compared by content', () => {
    fixture.write('README.md', 'notes\n');
    fixture.git('add', '-A');
    fixture.git('commit', '--quiet', '-m', 'notes');
    fixture.verifyUiUx(PROVIDERS);
    const baselineCommit = fixture.readRecord(UI_SKILL, PROVIDERS).verified.baseline.commit;

    // Squash everything into a new root commit and drop the old history.
    fixture.git('checkout', '--quiet', '--orphan', 'squashed');
    fixture.git('add', '-A');
    fixture.git('commit', '--quiet', '-m', 'squashed');
    fixture.git('branch', '-D', 'main');
    fixture.git('reflog', 'expire', '--expire=now', '--all');
    fixture.git('gc', '--quiet', '--prune=now');
    assert.throws(() => fixture.git('cat-file', '-e', `${baselineCommit}^{commit}`));

    const unchanged = fixture.check(PROVIDERS);
    assert.equal(unchanged.baseline.history, 'unreachable');
    assert.equal(unchanged.freshness, 'current');
    assert.ok(unchanged.reasons.some((reason) => reason.includes('no longer in history')));

    fixture.replace(MANAGEMENT_FILE, 'const result = await saveProvider({ name: "x" });', 'const result = await saveProvider({ name: "y" });');
    const changed = fixture.check(PROVIDERS);
    assert.equal(changed.freshness, 'stale');
    assert.equal(changed.decision, 'incremental');

    const diff = fixture.run(['diff', '--unit', PROVIDERS, '--skill', UI_SKILL]);
    assert.equal(diff.status, 0);
    assert.deepEqual(diff.json.commits, []);
  });

  test('diff lists the commits that touched the changed files since the baseline', () => {
    fixture.verifyUiUx(PROVIDERS);
    fixture.replace('lib/http.ts', 'method: "POST"', 'method: "PUT"');
    fixture.git('add', '-A');
    fixture.git('commit', '--quiet', '-m', 'switch to PUT');
    const diff = fixture.run(['diff', '--unit', PROVIDERS, '--skill', UI_SKILL, '--patch']);
    assert.equal(diff.json.commits.length, 1);
    assert.match(diff.json.commits[0], /switch to PUT/);
    assert.match(diff.json.patch, /method: "PUT"/);
  });

  test('a change in the skill rules makes coverage stale and scopes the review to the changed rules', () => {
    fixture.verifyUiUx(PROVIDERS);
    fixture.writeSkill(UI_SKILL, '1.1.0', 'Rules of the skill, now with a stale-error rule.');
    const check = fixture.check(PROVIDERS);
    assert.equal(check.freshness, 'stale');
    assert.equal(check.definition.status, 'changed');
    assert.equal(check.decision, 'incremental');
    assert.deepEqual(check.suggestedScope, [`re-check the unit against the rules changed in ${UI_SKILL}/SKILL.md`]);
  });

  test('a version bump without rule changes keeps coverage current', () => {
    fixture.verifyUiUx(PROVIDERS);
    fixture.writeSkill(UI_SKILL, '1.0.1');
    const check = fixture.check(PROVIDERS);
    assert.equal(check.freshness, 'current');
    assert.equal(check.decision, 'skip');
  });

  test('a major version of the skill requires a full analysis', () => {
    fixture.verifyUiUx(PROVIDERS);
    fixture.writeSkill(UI_SKILL, '2.0.0', 'Completely new rules.');
    const check = fixture.check(PROVIDERS);
    assert.equal(check.decision, 'full');
    assert.ok(check.reasons.some((reason) => reason.includes('major version')));
  });

  test('without a parser, impact falls back to whole files and stays conservative', () => {
    const env = { GOLFO_COVERAGE_PARSER: 'none' };
    const begin = fixture.run(['begin', '--unit', APPROVE, '--skill', UI_SKILL, '--mode', 'full'], { env });
    assert.equal(begin.status, 0);
    for (const args of [
      ['--kind', 'review', '--outcome', 'pass', '--summary', 'reviewed'],
      ['--kind', 'test', '--exec', `"${process.execPath}" -e "0"`],
      ['--kind', 'browser', '--outcome', 'pass', '--summary', 'walked states'],
    ]) fixture.run(['evidence', '--run', begin.json.runId, ...args], { env });
    assert.equal(fixture.run(['record', '--run', begin.json.runId, '--result', 'verified'], { env }).json.result, 'verified');

    const inputs = fixture.run(['inputs', '--unit', APPROVE, '--skill', UI_SKILL], { env }).json;
    assert.equal(inputs.analyzer, 'file-level/1');
    assert.ok(inputs.inputs[`${MANAGEMENT_FILE}#*`]);
    assert.ok(inputs.inputs['lib/http.ts#*'], 'imports are still followed by pattern');

    fixture.replace(MANAGEMENT_FILE, '<button onClick={handleSubmit}>Guardar</button>', '<button onClick={handleSubmit}>Guardar ya</button>');
    const fallbackCheck = fixture.check(APPROVE, UI_SKILL);
    assert.equal(fallbackCheck.freshness, 'unknown', 'parser available now: recorded per file, compared per file');
    assert.equal(fallbackCheck.decision, 'incremental');
    assert.ok(fallbackCheck.suggestedScope.some((scope) => scope.includes(MANAGEMENT_FILE)));

    const withoutParser = fixture.run(['check', '--unit', APPROVE, '--skill', UI_SKILL], { env }).json;
    assert.equal(withoutParser.freshness, 'stale', 'a change anywhere in the file invalidates every unit in it');
  });

  test('a record made with symbol analysis is still current when read without a parser if files did not change', () => {
    fixture.verifyUiUx(PROVIDERS);
    const check = fixture.run(['check', '--unit', PROVIDERS, '--skill', UI_SKILL], { env: { GOLFO_COVERAGE_PARSER: 'none' } }).json;
    assert.equal(check.freshness, 'current');
    assert.equal(check.decision, 'skip');
  });
});
