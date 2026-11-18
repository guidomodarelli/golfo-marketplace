import assert from 'node:assert/strict';
import { after, before, beforeEach, describe, test } from 'node:test';

import { MANAGEMENT_FILE, UI_SKILL, createFixture } from './helpers/fixture-project.mjs';

const OPTIMISTIC_SKILL = 'optimistic-action-mutations';
const PROVIDERS = 'academy.manage.providers.save';
const APPROVE = 'academy.manage.requests.approve';
const REJECT = 'academy.manage.requests.reject';
const PROVIDERS_ROUTE = 'app/api/providers/route.ts';
const PASSING_TEST = `"${process.execPath}" -e "process.exit(0)"`;

/**
 * Accredited run of the optimistic policy: review of the operations and a
 * witnessed behavior test.
 *
 * @param {ReturnType<typeof createFixture>} fixture
 * @param {string} unitId
 */
function verifyOptimistic(fixture, unitId) {
  const begin = fixture.run(['begin', '--unit', unitId, '--skill', OPTIMISTIC_SKILL, '--mode', 'full']);
  if (begin.status !== 0) throw new Error(`begin failed: ${begin.stderr}`);
  const runId = begin.json.runId;
  fixture.run(['evidence', '--run', runId, '--kind', 'review', '--outcome', 'pass', '--summary', 'save classified pending-first; double submit and stale responses reviewed']);
  fixture.run(['evidence', '--run', runId, '--kind', 'test', '--exec', PASSING_TEST]);
  const record = fixture.run(['record', '--run', runId, '--result', 'verified']);
  if (record.status !== 0) throw new Error(`record failed: ${record.stderr}`);
  return record.json;
}

describe('optimistic-action-mutations policy', () => {
  let fixture;
  let verifiedHead;
  before(() => {
    fixture = createFixture();
    fixture.writeSkill(OPTIMISTIC_SKILL, '1.1.0');
    // A lifecycle setting next to the copy, a setting object whose member names
    // say nothing about the lifecycle, and a route handler that the client
    // reaches by URL, declared as a dependency the analyzer cannot follow.
    fixture.replace(MANAGEMENT_FILE, 'queueTitle: "Solicitudes",', 'queueTitle: "Solicitudes",\n  saveRetryLimit: 2,');
    fixture.replace(MANAGEMENT_FILE, 'if (!result.ok) setError(result.message);', 'if (!result.ok && COPY.saveRetryLimit > 0) setError(result.message);');
    fixture.replace(MANAGEMENT_FILE, 'export function AcademyManagement', 'export const SAVE_SETTINGS = {\n  optimistic: true,\n} as const;\n\nexport function AcademyManagement');
    fixture.replace(MANAGEMENT_FILE, 'const handleSubmit = async () => {', 'const handleSubmit = async () => {\n    if (!SAVE_SETTINGS.optimistic) setError(null);');
    fixture.write(PROVIDERS_ROUTE, 'export async function POST(request) {\n  const body = await request.json();\n  return Response.json({ id: "p1", name: body.name });\n}\n');
    const unitPath = `.golfo/skill-coverage/units/${PROVIDERS}.json`;
    const unit = JSON.parse(fixture.read(unitPath));
    unit.dependsOn = [{ path: PROVIDERS_ROUTE, reason: 'saveProvider posts to /api/providers by URL', symbol: '*' }];
    fixture.write(unitPath, `${JSON.stringify(unit, null, 2)}\n`);
    fixture.git('add', '-A');
    fixture.git('commit', '--quiet', '-m', 'lifecycle setting and route');
    for (const unitId of [PROVIDERS, APPROVE, REJECT]) verifyOptimistic(fixture, unitId);
    fixture.verifyUiUx(PROVIDERS);
    fixture.git('add', '-A');
    fixture.git('commit', '--quiet', '-m', 'record coverage');
    verifiedHead = fixture.git('rev-parse', 'HEAD');
  });
  beforeEach(() => {
    fixture.git('reset', '--quiet', '--hard', verifiedHead);
    fixture.git('clean', '--quiet', '-fd');
  });
  after(() => fixture.cleanup());

  test('verified coverage stays current while nothing relevant changes', () => {
    const check = fixture.check(PROVIDERS, OPTIMISTIC_SKILL);
    assert.equal(check.state, 'verified');
    assert.equal(check.freshness, 'current');
    assert.equal(check.decision, 'skip');
    assert.equal(fixture.check(PROVIDERS, OPTIMISTIC_SKILL, ['--force-full']).decision, 'full');
  });

  test('a copy change leaves the optimistic coverage current but invalidates UI/UX', () => {
    fixture.replace(MANAGEMENT_FILE, 'providersTitle: "Proveedores"', 'providersTitle: "Proveedores de verificación"');
    const check = fixture.check(PROVIDERS, OPTIMISTIC_SKILL);
    assert.equal(check.freshness, 'current');
    assert.equal(check.decision, 'skip');
    assert.ok(check.ignoredChanges.some((change) => change.reason === 'copy or display member: no impact on the operation lifecycle'));
    assert.equal(fixture.check(PROVIDERS, UI_SKILL).freshness, 'stale');
  });

  test('a lifecycle setting change is relevant even though it lives next to the copy', () => {
    fixture.replace(MANAGEMENT_FILE, 'saveRetryLimit: 2,', 'saveRetryLimit: 3,');
    const check = fixture.check(PROVIDERS, OPTIMISTIC_SKILL);
    assert.equal(check.freshness, 'stale');
    assert.equal(check.decision, 'incremental');
    assert.ok(check.relevantChanges.some((change) => change.reason === 'lifecycle configuration member (saveRetryLimit)'));
    assert.ok(check.suggestedScope.some((scope) => scope.includes('lifecycle configuration read from this member')));
  });

  test('a change in an unclassified object member is relevant because its lifecycle impact is unknown', () => {
    fixture.replace(MANAGEMENT_FILE, 'optimistic: true,', 'optimistic: false,');
    const check = fixture.check(PROVIDERS, OPTIMISTIC_SKILL);
    assert.equal(check.freshness, 'stale');
    assert.notEqual(check.decision, 'skip');
    assert.ok(check.relevantChanges.some((change) => change.key.endsWith('SAVE_SETTINGS.optimistic') && change.reason === 'unclassified object member: lifecycle impact unknown'));
  });

  test('a handler change scopes the next run to that action', () => {
    fixture.replace(MANAGEMENT_FILE, 'const result = await saveProvider({ name: "x" });', 'const result = await saveProvider({ name: "x", retry: true });');
    const check = fixture.check(PROVIDERS, OPTIMISTIC_SKILL);
    assert.equal(check.decision, 'incremental');
    assert.ok(check.relevantChanges.some((change) => change.reason === 'action handler changed'));
    assert.ok(check.suggestedScope.some((scope) => scope.includes('handleSubmit') && scope.includes('double submit, stale responses, rollback, unknown outcome')));
  });

  test('a change in one subflow keeps the coverage of the untouched subflows', () => {
    fixture.replace(MANAGEMENT_FILE, 'await decideRequest(id, "approved");', 'await decideRequest(id, "approved", { idempotencyKey: id });');
    assert.equal(fixture.check(APPROVE, OPTIMISTIC_SKILL).decision, 'incremental');
    assert.equal(fixture.check(REJECT, OPTIMISTIC_SKILL).decision, 'skip');
    assert.equal(fixture.check(PROVIDERS, OPTIMISTIC_SKILL).decision, 'skip');
  });

  test('a shared helper change invalidates every operation that reaches it', () => {
    fixture.replace('lib/http.ts', 'method: "POST"', 'method: "POST", keepalive: true');
    for (const unitId of [PROVIDERS, APPROVE, REJECT]) {
      const check = fixture.check(unitId, OPTIMISTIC_SKILL);
      assert.equal(check.freshness, 'stale', unitId);
      assert.ok(check.relevantChanges.some((change) => change.key.startsWith('lib/http.ts#')), unitId);
    }
  });

  test('a backend change reached only by URL is detected through dependsOn with a server-contract focus', () => {
    fixture.replace(PROVIDERS_ROUTE, 'return Response.json({ id: "p1", name: body.name });', 'return Response.json({ id: "p1", name: body.name, version: 1 });');
    const check = fixture.check(PROVIDERS, OPTIMISTIC_SKILL);
    assert.equal(check.decision, 'incremental');
    assert.ok(check.suggestedScope.some((scope) => scope.startsWith(PROVIDERS_ROUTE) && scope.includes('server contract of the operation')));
    assert.equal(fixture.check(APPROVE, OPTIMISTIC_SKILL).decision, 'skip');
  });

  test('a new package in the flow is relevant', () => {
    fixture.replace('lib/http.ts', 'export async function request', 'import { retry } from "fetch-retry-lib";\n\nexport async function request');
    fixture.replace('lib/http.ts', 'const response = await fetch(', 'const response = await retry(fetch)(');
    const check = fixture.check(PROVIDERS, OPTIMISTIC_SKILL);
    assert.ok(check.relevantChanges.some((change) => change.key === 'pkg:fetch-retry-lib' && change.reason.includes('new package')));
  });

  test('style files stay outside the optimistic closure', () => {
    fixture.write('components/academy-management/styles.module.scss', '.Saving { opacity: 0.6; }\n');
    fixture.replace(MANAGEMENT_FILE, 'import { useState } from "react";', 'import { useState } from "react";\nimport styles from "./styles.module.scss";');
    const inputs = fixture.run(['inputs', '--unit', PROVIDERS, '--skill', OPTIMISTIC_SKILL]).json.inputs;
    assert.ok(!('components/academy-management/styles.module.scss#*' in inputs));
  });

  test('a recorded not-applicable decision is re-evaluated when the operation changes', () => {
    const begin = fixture.run(['begin', '--unit', REJECT, '--skill', OPTIMISTIC_SKILL, '--mode', 'full', '--force-full']);
    fixture.run(['evidence', '--run', begin.json.runId, '--kind', 'review', '--outcome', 'pass', '--summary', 'reject is server-confirmed and has no optimistic state']);
    const record = fixture.run(['record', '--run', begin.json.runId, '--result', 'not-applicable', '--summary', 'server-confirmed decision without optimistic state']);
    assert.equal(record.json.result, 'not-applicable');
    assert.equal(fixture.check(REJECT, OPTIMISTIC_SKILL).decision, 'not-applicable');
    fixture.replace(MANAGEMENT_FILE, 'await decideRequest(id, "rejected");', 'setRejected(id);\n    await decideRequest(id, "rejected");');
    const check = fixture.check(REJECT, OPTIMISTIC_SKILL);
    assert.equal(check.decision, 'incremental');
    assert.ok(check.reasons.some((reason) => reason.includes('re-evaluate applicability')));
  });

  test('verified needs a review and a witnessed behavior test', () => {
    const begin = fixture.run(['begin', '--unit', PROVIDERS, '--skill', OPTIMISTIC_SKILL, '--mode', 'full', '--force-full']);
    fixture.run(['evidence', '--run', begin.json.runId, '--kind', 'review', '--outcome', 'pass', '--summary', 'operations reviewed, no tests run']);
    const record = fixture.run(['record', '--run', begin.json.runId, '--result', 'verified', '--limitation', 'no test runner in this environment']);
    assert.equal(record.json.result, 'partial');
    assert.ok(record.json.downgradeReasons.includes('missing passing evidence of kind test'));
  });

  test('a failing behavior test prevents verified', () => {
    const begin = fixture.run(['begin', '--unit', PROVIDERS, '--skill', OPTIMISTIC_SKILL, '--mode', 'full', '--force-full']);
    fixture.run(['evidence', '--run', begin.json.runId, '--kind', 'review', '--outcome', 'pass', '--summary', 'operations reviewed']);
    fixture.run(['evidence', '--run', begin.json.runId, '--kind', 'test', '--exec', `"${process.execPath}" -e "process.exit(1)"`]);
    const record = fixture.run(['record', '--run', begin.json.runId, '--result', 'verified']);
    assert.equal(record.json.result, 'partial');
    assert.ok(record.json.downgradeReasons.some((reason) => reason.startsWith('test evidence failed')));
  });

  test('a lightweight run accredits with a browser walk-through on top of verified coverage', () => {
    fixture.replace(MANAGEMENT_FILE, 'const result = await saveProvider({ name: "x" });', 'const result = await saveProvider({ name: "x", retry: true });');
    const begin = fixture.run(['begin', '--unit', PROVIDERS, '--skill', OPTIMISTIC_SKILL, '--mode', 'lightweight']);
    fixture.run(['evidence', '--run', begin.json.runId, '--kind', 'review', '--outcome', 'pass', '--summary', 'changed handler reviewed: still pending-first, guard against double submit']);
    fixture.run(['evidence', '--run', begin.json.runId, '--kind', 'browser', '--outcome', 'pass', '--summary', 'double click sends one request (Playwright)']);
    assert.equal(fixture.run(['record', '--run', begin.json.runId, '--result', 'verified']).json.result, 'verified');
  });

  test('changing the skill rules asks for a review against them, and a major version for a full one', () => {
    try {
      fixture.writeSkill(OPTIMISTIC_SKILL, '1.2.0', 'Rules of the skill, now with offline queues.');
      const minor = fixture.check(PROVIDERS, OPTIMISTIC_SKILL);
      assert.equal(minor.freshness, 'stale');
      assert.equal(minor.decision, 'incremental');
      fixture.writeSkill(OPTIMISTIC_SKILL, '2.0.0', 'Rules of the skill, rewritten for every operation type.');
      assert.equal(fixture.check(PROVIDERS, OPTIMISTIC_SKILL).decision, 'full');
      // A version bump alone does not change the definition hash.
      fixture.writeSkill(OPTIMISTIC_SKILL, '1.1.1');
      assert.equal(fixture.check(PROVIDERS, OPTIMISTIC_SKILL).decision, 'skip');
    } finally {
      fixture.writeSkill(OPTIMISTIC_SKILL, '1.1.0');
    }
    assert.equal(fixture.check(PROVIDERS, OPTIMISTIC_SKILL).decision, 'skip');
  });
});
