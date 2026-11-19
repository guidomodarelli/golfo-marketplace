import assert from 'node:assert/strict';
import { after, before, beforeEach, describe, test } from 'node:test';

import { MANAGEMENT_FILE, UI_SKILL, createFixture } from './helpers/fixture-project.mjs';

const PROVIDERS = 'academy.manage.providers.save';
const APPROVE = 'academy.manage.requests.approve';
const REJECT = 'academy.manage.requests.reject';
const PROVIDERS_VIEW = 'academy.manage.providers.view';

/**
 * @param {any} fixture
 * @returns {Record<string, string>} Freshness per unit.
 */
function freshnessOfAll(fixture) {
  return Object.fromEntries([PROVIDERS, APPROVE, REJECT].map((unitId) => [unitId, fixture.check(unitId).freshness]));
}

describe('granular impact detection', () => {
  let fixture;
  let verifiedHead;
  before(() => {
    fixture = createFixture();
    fixture.writeUnit(PROVIDERS_VIEW, {
      entries: [{ path: MANAGEMENT_FILE, symbol: "ProvidersSection~shell" }],
      hierarchy: { module: "Academy", page: "Management", section: "Verification Providers", subflow: "View" },
    });
    for (const unitId of [PROVIDERS, APPROVE, REJECT, PROVIDERS_VIEW]) fixture.verifyUiUx(unitId);
    fixture.git('add', '-A');
    fixture.git('commit', '--quiet', '-m', 'record coverage');
    verifiedHead = fixture.git('rev-parse', 'HEAD');
  });
  beforeEach(() => {
    fixture.git('reset', '--quiet', '--hard', verifiedHead);
    fixture.git('clean', '--quiet', '-fd');
  });
  after(() => fixture.cleanup());

  test('a change in one handler invalidates only the subflow that uses it', () => {
    fixture.replace(MANAGEMENT_FILE, 'await decideRequest(id, "rejected");', 'await decideRequest(id, "rejected");\n    console.info("rejected", id);');
    assert.deepEqual(freshnessOfAll(fixture), { [APPROVE]: 'current', [PROVIDERS]: 'current', [REJECT]: 'stale' });

    const check = fixture.check(REJECT);
    assert.equal(check.decision, 'incremental');
    assert.deepEqual(check.relevantChanges.map((change) => change.key), [`${MANAGEMENT_FILE}#ReviewQueueSection/reject`]);
    assert.match(check.suggestedScope[0], /ReviewQueueSection › reject/);
  });

  test('two sections in the same file keep independent coverage', () => {
    fixture.replace(MANAGEMENT_FILE, '<button onClick={handleSubmit}>Guardar</button>', '<button onClick={handleSubmit} type="button">Guardar proveedor</button>');
    assert.deepEqual(freshnessOfAll(fixture), { [APPROVE]: 'current', [PROVIDERS]: 'stale', [REJECT]: 'current' });
    assert.deepEqual(fixture.check(PROVIDERS).relevantChanges.map((change) => change.key), [`${MANAGEMENT_FILE}#ProvidersSection~shell`]);
  });

  test('a component body entry (Name~shell) ignores its handlers but not its markup', () => {
    fixture.replace(MANAGEMENT_FILE, 'if (!result.ok) setError(result.message);', 'if (!result.ok) setError(result.message ?? null);');
    assert.equal(fixture.check(PROVIDERS_VIEW).freshness, 'current');
    assert.equal(fixture.check(PROVIDERS).freshness, 'stale');
    fixture.replace(MANAGEMENT_FILE, '<button onClick={handleSubmit}>Guardar</button>', '<button onClick={handleSubmit}>Guardar ya</button>');
    assert.equal(fixture.check(PROVIDERS_VIEW).freshness, 'stale');
  });

  test('a change in the markup shared by two handlers invalidates both, not the other section', () => {
    fixture.replace(MANAGEMENT_FILE, '<h2>{COPY.queueTitle}</h2>', '<h2 id="queue">{COPY.queueTitle}</h2>');
    assert.deepEqual(freshnessOfAll(fixture), { [APPROVE]: 'stale', [PROVIDERS]: 'current', [REJECT]: 'stale' });
  });

  test('editing one message of a shared copy dictionary invalidates only its readers', () => {
    fixture.replace(MANAGEMENT_FILE, 'queueTitle: "Solicitudes"', 'queueTitle: "Solicitudes de verificación"');
    assert.deepEqual(freshnessOfAll(fixture), { [APPROVE]: 'stale', [PROVIDERS]: 'current', [REJECT]: 'stale' });
    assert.deepEqual(fixture.check(APPROVE).relevantChanges.map((change) => change.key), [`${MANAGEMENT_FILE}#COPY.queueTitle`]);

    fixture.replace(MANAGEMENT_FILE, 'approved: "Aprobada",', 'approved: "Aprobada",\n  rejected: "Rechazada",');
    assert.equal(fixture.check(PROVIDERS).freshness, 'current');
  });

  test('a change in a shared dependency invalidates every unit that reaches it', () => {
    fixture.replace('lib/http.ts', 'method: "POST"', 'method: "POST", credentials: "same-origin"');
    assert.deepEqual(freshnessOfAll(fixture), { [APPROVE]: 'stale', [PROVIDERS]: 'stale', [REJECT]: 'stale' });
    assert.deepEqual(fixture.check(PROVIDERS).relevantChanges.map((change) => change.key), ['lib/http.ts#request']);
  });

  test('a change in a helper used by some units invalidates only those', () => {
    fixture.replace('lib/api-client.ts', 'return request(`/api/requests/${id}`, { decision });', 'return request(`/api/requests/${encodeURIComponent(id)}`, { decision });');
    assert.deepEqual(freshnessOfAll(fixture), { [APPROVE]: 'stale', [PROVIDERS]: 'current', [REJECT]: 'stale' });
  });

  test('formatting and comments never invalidate coverage', () => {
    fixture.replace(MANAGEMENT_FILE, 'function ProvidersSection() {', '/** Lists and saves providers. */\nfunction   ProvidersSection()   {\n');
    assert.deepEqual(freshnessOfAll(fixture), { [APPROVE]: 'current', [PROVIDERS]: 'current', [REJECT]: 'current' });
  });

  test('staged, unstaged and untracked changes are all detected', () => {
    fixture.replace(MANAGEMENT_FILE, 'await decideRequest(id, "approved");', 'await decideRequest(id, "approved", { notify: true });');
    fixture.git('add', MANAGEMENT_FILE);
    assert.equal(fixture.check(APPROVE).freshness, 'stale', 'staged change');

    fixture.git('reset', '--quiet', '--hard', verifiedHead);
    fixture.replace('lib/api-client.ts', 'import { request } from "./http";', 'import { request } from "./http";\nimport { normalizeProvider } from "./provider-normalizer";');
    fixture.replace('lib/api-client.ts', 'return request("/api/providers", input);', 'return request("/api/providers", normalizeProvider(input));');
    fixture.write('lib/provider-normalizer.ts', 'export function normalizeProvider(input) {\n  return { ...input, name: input.name.trim() };\n}\n');
    const check = fixture.check(PROVIDERS);
    assert.equal(check.freshness, 'stale', 'unstaged edit plus untracked file');
    assert.ok(check.relevantChanges.some((change) => change.change === 'added' && change.key === 'lib/provider-normalizer.ts#normalizeProvider'));
    assert.equal(fixture.check(APPROVE).freshness, 'current');
  });

  test('deleting a dependency file is detected', () => {
    fixture.write('lib/http.ts', '');
    const check = fixture.check(PROVIDERS);
    assert.equal(check.freshness, 'stale');
    assert.ok(check.relevantChanges.some((change) => change.key === 'lib/http.ts#request' && change.change === 'removed'));
  });

  test('extracting a component to its own file keeps its coverage and unit id', () => {
    const source = fixture.read(MANAGEMENT_FILE);
    const start = source.indexOf('function ProvidersSection()');
    const end = source.indexOf('function ReviewQueueSection()');
    const providersSource = source.slice(start, end);
    fixture.write(MANAGEMENT_FILE, source.slice(0, start) + source.slice(end));
    fixture.replace(MANAGEMENT_FILE, 'import { decideRequest, saveProvider } from "@/lib/api-client";', 'import { decideRequest } from "@/lib/api-client";\nimport { ProvidersSection } from "@/components/providers-section";');
    fixture.write('components/providers-section/index.tsx', `"use client";\n\nimport { useState } from "react";\n\nimport { COPY } from "@/components/academy-management";\nimport { saveProvider } from "@/lib/api-client";\n\nexport ${providersSource}`);

    const moved = fixture.check(PROVIDERS);
    assert.equal(moved.decision, 'full', 'the unit entry points to the old file');
    assert.match(moved.reasons.join(' '), /no longer exists/);

    const discovery = fixture.run(['discover', '--write']);
    assert.ok(discovery.json.relocations.some((relocation) => relocation.unitId === PROVIDERS && relocation.to === 'components/providers-section/index.tsx'));
    assert.deepEqual(discovery.json.written.relocated, [PROVIDERS]);

    const check = fixture.check(PROVIDERS);
    assert.equal(check.freshness, 'current');
    assert.equal(check.decision, 'skip');
    assert.ok(check.relevantChanges.length === 0);
    assert.ok(check.ignoredChanges.some((change) => change.change === 'relocated'));
  });
});
