import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { afterEach, beforeEach, describe, test } from 'node:test';

import { withFileLock, writeJsonFileAtomic } from '../lib/persistence/json-store.mjs';
import { MANAGEMENT_FILE, PERFORMANCE_SKILL, UI_SKILL, createFixture } from './helpers/fixture-project.mjs';

const PROVIDERS = 'academy.manage.providers.save';
const APPROVE = 'academy.manage.requests.approve';
const REJECT = 'academy.manage.requests.reject';

describe('status, discovery and registry integrity', () => {
  let fixture;
  beforeEach(() => {
    fixture = createFixture();
  });
  afterEach(() => fixture.cleanup());

  test('status aggregates subflows into sections and pages without hiding pending ones', () => {
    fixture.verifyUiUx(PROVIDERS);
    fixture.verifyUiUx(APPROVE);
    fixture.verifyUiUx(REJECT);
    fixture.replace(MANAGEMENT_FILE, 'await decideRequest(id, "rejected");', 'await decideRequest(id, "rejected", { notify: true });');

    const status = fixture.run(['status']).json;
    assert.deepEqual(status.summary[UI_SKILL].counts, { blocked: 0, current: 2, 'not-applicable': 0, partial: 0, stale: 1, unknown: 0, unreviewed: 0 });
    assert.equal(status.summary[PERFORMANCE_SKILL].counts.unreviewed, 3);
    const reject = status.units.find((unit) => unit.id === REJECT).skills[UI_SKILL];
    assert.equal(reject.freshness, 'stale');
    assert.equal(reject.changes[0].key, `${MANAGEMENT_FILE}#ReviewQueueSection/reject`);

    const text = fixture.run(['status', '--details'], { json: false }).stdout;
    assert.match(text, /Academy {2}\(UI\/UX 2\/3 · Performance 0\/3 · Optimistic 0\/3 · Next\.js 0\/3\)/);
    assert.match(text, /Verification Requests {2}\(UI\/UX 1\/2 · Performance 0\/2 · Optimistic 0\/2 · Next\.js 0\/2\)/);
    assert.match(text, /Reject {2}\[academy\.manage\.requests\.reject\]\n\s+UI\/UX: +STALE/);
    assert.match(text, /modified: .*ReviewQueueSection › reject/);
    assert.match(text, /next: incremental/);
    assert.match(text, /Performance: +UNREVIEWED/);

    const filtered = fixture.run(['status', '--unit', 'academy.manage.requests', '--skill', UI_SKILL]).json;
    assert.deepEqual(filtered.units.map((unit) => unit.id), [APPROVE, REJECT]);
  });

  test('affected maps changed files to the units that depend on them', () => {
    fixture.replace('lib/api-client.ts', 'return request("/api/providers", input);', 'return request("/api/providers", { ...input });');
    const affected = fixture.run(['affected', '--changed', '--skill', UI_SKILL]).json;
    assert.deepEqual(affected.affected.map((item) => item.unit).sort(), [PROVIDERS, APPROVE, REJECT]);
    const byPath = fixture.run(['affected', '--paths', 'lib/academy-server.ts']).json;
    assert.deepEqual(byPath.affected, []);
  });

  test('discover proposes independent actions, reuses existing ids and records no coverage', () => {
    const discovery = fixture.run(['discover']).json;
    const byEntry = new Map(discovery.proposals.map((proposal) => [`${proposal.entries[0].path}#${proposal.entries[0].symbol}`, proposal]));
    assert.equal(byEntry.get(`${MANAGEMENT_FILE}#ReviewQueueSection/approve`).existingId, APPROVE);
    assert.equal(byEntry.get(`${MANAGEMENT_FILE}#ReviewQueueSection/reject`).existingId, REJECT);
    assert.equal(byEntry.get(`${MANAGEMENT_FILE}#ProvidersSection`).existingId, PROVIDERS);
    const view = discovery.proposals.find((proposal) => proposal.id === 'academy.manage.view');
    assert.ok(view.entries.some((entry) => entry.path === 'app/(platform)/academy/manage/loading.tsx'));

    const written = fixture.run(['discover', '--write']).json.written;
    assert.ok(written.created.includes('academy.manage.view'));
    assert.ok(!fs.existsSync(path.join(fixture.root, '.golfo/skill-coverage/records')) || fs.readdirSync(path.join(fixture.root, '.golfo/skill-coverage/records')).length === 0);
    assert.equal(fixture.check('academy.manage.view').state, 'unreviewed');
    assert.equal(fixture.run(['discover', '--write']).json.written.created.length, 0, 'a second run creates nothing new');
  });

  test('validate reports broken entries and records of unknown units', () => {
    fixture.verifyUiUx(PROVIDERS);
    fixture.writeUnit('academy.manage.broken', {
      entries: [{ path: MANAGEMENT_FILE, symbol: 'ReviewQueueSection/archive' }],
      hierarchy: { module: 'Academy', page: 'Management', subflow: 'Archive' },
    });
    fs.renameSync(fixture.recordPath(UI_SKILL, PROVIDERS), fixture.recordPath(UI_SKILL, 'academy.manage.gone'));

    const validation = fixture.run(['validate']);
    assert.equal(validation.status, 1);
    assert.ok(validation.json.errors.some((error) => error.includes('inner function ReviewQueueSection/archive not found')));
    assert.ok(validation.json.errors.some((error) => error.includes('declares ui-ux-flow-patterns/academy.manage.providers.save')));
    assert.equal(fixture.run(['validate', '--informative']).status, 0);
  });

  test('concurrent records of different units and skills never lose or corrupt files', async () => {
    const units = [PROVIDERS, APPROVE, REJECT];
    const runIds = [];
    for (const unitId of units) {
      for (const skill of [UI_SKILL, PERFORMANCE_SKILL]) {
        const begin = fixture.run(['begin', '--unit', unitId, '--skill', skill, '--mode', 'full']);
        runIds.push(begin.json.runId);
      }
    }
    const results = await Promise.all(runIds.map((runId) => fixture.runAsync(['record', '--run', runId, '--result', 'blocked', '--limitation', 'no browser'])));
    assert.deepEqual(results.map((result) => result.status), runIds.map(() => 0));
    for (const unitId of units) {
      for (const skill of [UI_SKILL, PERFORMANCE_SKILL]) {
        const record = fixture.readRecord(skill, unitId);
        assert.equal(record.latest.result, 'blocked');
      }
    }
    const leftovers = fs.readdirSync(path.join(fixture.root, '.golfo/skill-coverage'), { recursive: true }).filter((name) => /\.tmp$|\.lock$/.test(String(name)));
    assert.deepEqual(leftovers, []);
    assert.equal(fixture.run(['validate']).status, 0);
  });

  test('repeating a run on the same unit keeps a single valid record', () => {
    fixture.verifyUiUx(PROVIDERS);
    fixture.verifyUiUx(PROVIDERS, { mode: 'incremental' });
    const record = fixture.readRecord(UI_SKILL, PROVIDERS);
    assert.equal(record.verified.mode, 'incremental');
    assert.equal(record.latest, null);
    assert.equal(fs.readdirSync(path.dirname(fixture.recordPath(UI_SKILL, PROVIDERS))).length, 1);
  });

  test('locks left by a crashed process are taken over and writes are atomic', () => {
    const target = path.join(fixture.base, 'store', 'record.json');
    fs.mkdirSync(`${target}.lock`, { recursive: true });
    const old = new Date(Date.now() - 5 * 60 * 1000);
    fs.utimesSync(`${target}.lock`, old, old);
    withFileLock(target, () => writeJsonFileAtomic(target, { value: 1 }));
    assert.deepEqual(JSON.parse(fs.readFileSync(target, 'utf8')), { value: 1 });
    assert.equal(fs.existsSync(`${target}.lock`), false);
    assert.deepEqual(fs.readdirSync(path.dirname(target)), ['record.json']);
  });

  test('the registry, runs and reports never enter a fingerprint', () => {
    fixture.verifyUiUx(PROVIDERS);
    const inputs = fixture.run(['inputs', '--unit', PROVIDERS, '--skill', UI_SKILL]).json;
    assert.ok(Object.keys(inputs.files).every((filePath) => !filePath.startsWith('.golfo/')));
    fixture.write('.golfo/skill-coverage/runs/manual-note.json', '{}\n');
    assert.equal(fixture.check(PROVIDERS).decision, 'skip');
  });

  test('a change explains the dependency chain that brought it into the unit', () => {
    fixture.verifyUiUx(PROVIDERS);
    fixture.replace('lib/http.ts', 'method: "POST"', 'method: "PUT"');
    const change = fixture.check(PROVIDERS).relevantChanges[0];
    assert.equal(change.key, 'lib/http.ts#request');
    assert.deepEqual(change.via, [
      'lib/api-client.ts#saveProvider',
      `${MANAGEMENT_FILE}#ProvidersSection/handleSubmit`,
      `entry:${MANAGEMENT_FILE}#ProvidersSection`,
    ]);
    const why = fixture.run(['inputs', '--unit', PROVIDERS, '--skill', UI_SKILL, '--why', 'lib/http.ts#request']).json;
    assert.deepEqual(why.chains[0].chain.slice(0, 2), ['lib/http.ts#request', 'lib/api-client.ts#saveProvider']);
  });

  test('configured boundaries are hashed but their dependencies are not followed', () => {
    fixture.write('.golfo/skill-coverage/config.json', `${JSON.stringify({ boundaries: [{ path: 'lib/api-client.ts', reason: 'client of the API: the route is declared per unit', symbol: '*' }], schemaVersion: 1 }, null, 2)}\n`);
    const inputs = fixture.run(['inputs', '--unit', PROVIDERS, '--skill', UI_SKILL]).json.inputs;
    assert.ok('lib/api-client.ts#saveProvider' in inputs);
    assert.ok(!('lib/http.ts#request' in inputs));

    fixture.write('.golfo/skill-coverage/config.json', '{ "schemaVersion": 1, "boundaries": [{ "path": "lib/http.ts" }] }\n');
    const invalid = fixture.run(['status']);
    assert.equal(invalid.status, 1);
    assert.match(invalid.stderr, /boundaries\[0\]\.reason/);
  });

  test('evaluating a project stays fast', () => {
    const started = Date.now();
    assert.equal(fixture.run(['status']).status, 0);
    assert.ok(Date.now() - started < 10_000, `status took ${Date.now() - started} ms`);
  });
});
