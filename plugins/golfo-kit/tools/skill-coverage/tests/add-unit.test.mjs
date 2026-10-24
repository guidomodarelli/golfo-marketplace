import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { afterEach, beforeEach, describe, test } from 'node:test';

import { PERFORMANCE_SKILL, UI_SKILL, createFixture } from './helpers/fixture-project.mjs';

const REGISTRY = '.golfo/skill-coverage';
const JOB_FILE = 'lib/jobs/sync-invoices.ts';
const JOB_UNIT = 'billing.invoices.sync';
const JOB_UNIT_ARGS = ['add-unit', '--id', JOB_UNIT, '--kind', 'job', '--module', 'Billing', '--subflow', 'Sync invoices', '--entry', `${JOB_FILE}:syncInvoices`];

describe('add-unit in a repository without registry', () => {
  let fixture;
  beforeEach(() => {
    fixture = createFixture({ withUnits: false });
    fixture.write(JOB_FILE, 'import { request } from "../http";\n\nexport async function syncInvoices() {\n  return request("/api/invoices/sync", {});\n}\n');
  });
  afterEach(() => fixture.cleanup());

  test('creates the registry with its .gitignore and a schema-valid unit that the protocol can record on', () => {
    assert.equal(fs.existsSync(path.join(fixture.root, REGISTRY)), false);
    assert.equal(fixture.run(['affected', '--paths', JOB_FILE]).json.affected.length, 0);

    const created = fixture.run(JOB_UNIT_ARGS);
    assert.equal(created.status, 0, created.stderr);
    assert.deepEqual(created.json.unit.hierarchy, { module: 'Billing', page: null, section: null, subflow: 'Sync invoices' });
    assert.match(fixture.read(`${REGISTRY}/.gitignore`), /\.pending\//);
    assert.equal(fixture.run(['validate']).json.errors.length, 0);

    const affected = fixture.run(['affected', '--paths', JOB_FILE, '--skill', UI_SKILL]).json.affected;
    assert.deepEqual(affected.map((item) => [item.unit, item.decision]), [[JOB_UNIT, 'full']]);
    assert.ok(fixture.run(['inputs', '--unit', JOB_UNIT, '--skill', UI_SKILL]).json.files['lib/http.ts'], 'the unit follows its imports');

    assert.equal(fixture.verifyUiUx(JOB_UNIT).result, 'verified');
    assert.equal(fixture.readRecord(UI_SKILL, JOB_UNIT).verified.result, 'verified');
    assert.equal(fixture.check(JOB_UNIT).decision, 'skip');
  });

  test('an entry without symbol covers the whole file and optional labels and routes are kept', () => {
    const created = fixture.run(['add-unit', '--id', 'billing.invoices.view', '--kind', 'ui-flow', '--module', 'Billing', '--page', 'Invoices', '--section', 'List', '--subflow', 'View', '--entry', JOB_FILE, '--route', '/billing', '--description', 'Invoice list']);
    assert.equal(created.status, 0, created.stderr);
    assert.deepEqual(created.json.unit.entries, [{ path: JOB_FILE, symbol: '*' }]);
    assert.deepEqual(created.json.unit.routes, ['/billing']);
    assert.equal(created.json.unit.hierarchy.section, 'List');
  });

  test('refuses an existing id without touching the saved unit', () => {
    assert.equal(fixture.run(JOB_UNIT_ARGS).status, 0);
    const before = fixture.read(`${REGISTRY}/units/${JOB_UNIT}.json`);
    const duplicate = fixture.run([...JOB_UNIT_ARGS.slice(0, -1), JOB_FILE]);
    assert.equal(duplicate.status, 1);
    assert.match(duplicate.stderr, /already exists/);
    assert.equal(fixture.read(`${REGISTRY}/units/${JOB_UNIT}.json`), before);
  });

  test('rejects invalid ids, kinds and missing entry files with a usage error and writes nothing', () => {
    const invalid = fixture.run(['add-unit', '--id', 'Billing_Sync', '--kind', 'cron', '--module', 'Billing', '--subflow', 'Sync', '--entry', 'lib/jobs/missing.ts:run']);
    assert.equal(invalid.status, 2);
    assert.match(invalid.stderr, /lowercase dotted kebab-case/);
    assert.match(invalid.stderr, /kind: must be one of/);
    assert.match(invalid.stderr, /not found in the repository: lib\/jobs\/missing\.ts/);
    assert.equal(fs.existsSync(path.join(fixture.root, REGISTRY)), false);

    const withoutEntry = fixture.run(['add-unit', '--id', JOB_UNIT, '--kind', 'job', '--module', 'Billing', '--subflow', 'Sync']);
    assert.equal(withoutEntry.status, 2);
    assert.match(withoutEntry.stderr, /--entry/);
  });

  test('a unit created for a backend job records performance coverage with a new-flow measurement', () => {
    assert.equal(fixture.run(JOB_UNIT_ARGS).status, 0);
    const runId = fixture.run(['begin', '--unit', JOB_UNIT, '--skill', PERFORMANCE_SKILL, '--mode', 'full']).json.runId;
    fixture.run(['evidence', '--run', runId, '--kind', 'measurement', '--outcome', 'measured', '--summary', 'requests per run', '--metric', 'requests per run', '--after', '1', '--tool', 'node', '--conditions', 'local fixture', '--baseline-kind', 'new-flow', '--reference', 'new job']);
    fixture.run(['evidence', '--run', runId, '--kind', 'test', '--exec', `"${process.execPath}" -e "process.exit(0)"`]);
    const recorded = fixture.run(['record', '--run', runId, '--result', 'verified']);
    assert.equal(recorded.status, 0, recorded.stderr);
    assert.equal(recorded.json.result, 'verified');
  });
});
