import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { afterEach, beforeEach, describe, test } from 'node:test';

import { MANAGEMENT_FILE, UI_SKILL, createFixture } from './helpers/fixture-project.mjs';

const PROVIDERS = 'academy.manage.providers.save';

describe('run lifecycle', () => {
  let fixture;
  beforeEach(() => {
    fixture = createFixture();
  });
  afterEach(() => fixture.cleanup());

  test('a unit without coverage is unreviewed and needs a full analysis', () => {
    const check = fixture.check(PROVIDERS);
    assert.equal(check.state, 'unreviewed');
    assert.equal(check.decision, 'full');
    assert.equal(check.mode, 'full');
    assert.ok(check.suggestedScope[0].includes(PROVIDERS));
  });

  test('a verified run is skipped the second time when nothing changed', () => {
    const recorded = fixture.verifyUiUx(PROVIDERS);
    assert.equal(recorded.result, 'verified');
    assert.equal(recorded.downgraded, false);

    const check = fixture.check(PROVIDERS);
    assert.equal(check.state, 'verified');
    assert.equal(check.freshness, 'current');
    assert.equal(check.decision, 'skip');
    assert.equal(check.baseline.commit, fixture.git('rev-parse', 'HEAD'));

    const record = fixture.readRecord(UI_SKILL, PROVIDERS);
    assert.equal(record.verified.skill.version, '1.0.0');
    assert.match(record.verified.baseline.fingerprint, /^sha256:/);
    assert.ok(Object.keys(record.verified.baseline.inputs).some((key) => key.endsWith('#ProvidersSection/handleSubmit')));
    assert.equal(record.verified.evidence.find((item) => item.kind === 'test').source, 'witnessed');
    assert.ok(fs.existsSync(path.join(fixture.root, '.golfo/skill-coverage', record.verified.report)));
  });

  test('a forced full audit ignores current coverage', () => {
    fixture.verifyUiUx(PROVIDERS);
    const check = fixture.check(PROVIDERS, UI_SKILL, ['--force-full']);
    assert.equal(check.decision, 'full');
    assert.match(check.reasons[0], /full audit requested/);
  });

  test('a run without every required verification is recorded as partial, never verified', () => {
    const begin = fixture.run(['begin', '--unit', PROVIDERS, '--skill', UI_SKILL, '--mode', 'full']);
    fixture.run(['evidence', '--run', begin.json.runId, '--kind', 'review', '--outcome', 'pass', '--summary', 'reviewed']);
    const record = fixture.run(['record', '--run', begin.json.runId, '--result', 'verified']);

    assert.equal(record.status, 0);
    assert.equal(record.json.result, 'partial');
    assert.equal(record.json.downgraded, true);
    assert.ok(record.json.downgradeReasons.some((reason) => reason.includes('test')));
    assert.ok(record.json.downgradeReasons.some((reason) => reason.includes('browser')));

    const stored = fixture.readRecord(UI_SKILL, PROVIDERS);
    assert.equal(stored.verified, null);
    assert.equal(stored.latest.result, 'partial');

    const check = fixture.check(PROVIDERS);
    assert.equal(check.state, 'partial');
    // Without verified coverage only a full run can accredit the unit.
    assert.equal(check.decision, 'full');
    assert.ok(check.suggestedScope.some((scope) => scope.startsWith('pending from the previous run')));
  });

  test('a failing verification command keeps the run from being verified', () => {
    const begin = fixture.run(['begin', '--unit', PROVIDERS, '--skill', UI_SKILL, '--mode', 'full']);
    const runId = begin.json.runId;
    fixture.run(['evidence', '--run', runId, '--kind', 'review', '--outcome', 'pass', '--summary', 'reviewed']);
    const failing = fixture.run(['evidence', '--run', runId, '--kind', 'test', '--exec', `"${process.execPath}" -e "process.exit(3)"`]);
    assert.equal(failing.status, 1);
    assert.equal(failing.json.exitCode, 3);
    assert.equal(failing.json.outcome, 'fail');
    fixture.run(['evidence', '--run', runId, '--kind', 'browser', '--outcome', 'pass', '--summary', 'walked states']);

    const record = fixture.run(['record', '--run', runId, '--result', 'verified']);
    assert.equal(record.json.result, 'partial');
    assert.ok(record.json.downgradeReasons.some((reason) => reason.startsWith('test evidence failed')));
    assert.equal(fixture.readRecord(UI_SKILL, PROVIDERS).verified, null);
  });

  test('a partial run never replaces the last verified evidence', () => {
    fixture.verifyUiUx(PROVIDERS);
    const verifiedRunId = fixture.readRecord(UI_SKILL, PROVIDERS).verified.runId;
    const begin = fixture.run(['begin', '--unit', PROVIDERS, '--skill', UI_SKILL, '--mode', 'full']);
    fixture.run(['record', '--run', begin.json.runId, '--result', 'blocked', '--limitation', 'no browser available in the session']);

    const record = fixture.readRecord(UI_SKILL, PROVIDERS);
    assert.equal(record.verified.runId, verifiedRunId);
    assert.equal(record.latest.result, 'blocked');
    assert.equal(fixture.check(PROVIDERS).state, 'blocked');
  });

  test('the record is refused when the code changes between begin and record', () => {
    const begin = fixture.run(['begin', '--unit', PROVIDERS, '--skill', UI_SKILL, '--mode', 'full']);
    const runId = begin.json.runId;
    fixture.run(['evidence', '--run', runId, '--kind', 'review', '--outcome', 'pass', '--summary', 'reviewed']);
    fixture.replace(MANAGEMENT_FILE, 'if (!result.ok) setError(result.message);', 'if (!result.ok) setError(result.message ?? "Error");');

    const record = fixture.run(['record', '--run', runId, '--result', 'verified']);
    assert.equal(record.status, 3);
    assert.match(record.stderr, /inputs changed after begin/);
    assert.match(record.stderr, /ProvidersSection\/handleSubmit/);
    assert.equal(fixture.readRecord(UI_SKILL, PROVIDERS), undefined);

    const abort = fixture.run(['abort', '--run', runId]);
    assert.equal(abort.status, 0);
    assert.equal(fixture.run(['record', '--run', runId, '--result', 'partial', '--pending', 'x']).status, 1);
  });

  test('incremental and lightweight runs cannot accredit a unit that was never verified', () => {
    const begin = fixture.run(['begin', '--unit', PROVIDERS, '--skill', UI_SKILL, '--mode', 'lightweight']);
    const runId = begin.json.runId;
    fixture.run(['evidence', '--run', runId, '--kind', 'review', '--outcome', 'pass', '--summary', 'checklist']);
    fixture.run(['evidence', '--run', runId, '--kind', 'test', '--exec', `"${process.execPath}" -e "0"`]);
    const record = fixture.run(['record', '--run', runId, '--result', 'verified']);
    assert.equal(record.json.result, 'partial');
    assert.ok(record.json.downgradeReasons.some((reason) => reason.includes('no previous verified coverage')));
  });

  test('evidence text is sanitized before it is stored', () => {
    const begin = fixture.run(['begin', '--unit', PROVIDERS, '--skill', UI_SKILL, '--mode', 'full']);
    const evidence = fixture.run(['evidence', '--run', begin.json.runId, '--kind', 'review', '--outcome', 'pass', '--summary', 'logged in as ana@example.com with token=abc123secret and Bearer abcdefghijklmnop']);
    assert.doesNotMatch(evidence.json.summary, /ana@example\.com|abc123secret|abcdefghijklmnop/);
    assert.match(evidence.json.summary, /\[redacted\]/);
  });

  test('usage errors exit with code 2 and an actionable message', () => {
    const missing = fixture.run(['check', '--skill', UI_SKILL]);
    assert.equal(missing.status, 2);
    assert.match(missing.stderr, /--unit is required/);
    const unknownUnit = fixture.run(['check', '--unit', 'academy.nope', '--skill', UI_SKILL]);
    assert.equal(unknownUnit.status, 1);
    assert.match(unknownUnit.stderr, /unit academy.nope does not exist/);
    const badMode = fixture.run(['begin', '--unit', PROVIDERS, '--skill', 'measured-performance-optimization', '--mode', 'lightweight']);
    assert.equal(badMode.status, 2);
  });
});
