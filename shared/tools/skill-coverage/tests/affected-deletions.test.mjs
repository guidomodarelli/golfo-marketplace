import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { afterEach, beforeEach, describe, test } from 'node:test';

import { MANAGEMENT_FILE, UI_SKILL, createFixture } from './helpers/fixture-project.mjs';

const PROVIDERS = 'academy.manage.providers.save';
const APPROVE = 'academy.manage.requests.approve';
const REJECT = 'academy.manage.requests.reject';
const ALL_UNITS = [PROVIDERS, APPROVE, REJECT];
const HTTP_HELPER = 'lib/http.ts';

/**
 * @param {any} fixture
 * @param {string[]} args Selection arguments for `affected`.
 * @returns {{ affected: any[], paths: string[] }}
 */
function affected(fixture, args) {
  const result = fixture.run(['affected', ...args, '--skill', UI_SKILL]);
  assert.equal(result.status, 0, result.stderr);
  return result.json;
}

describe('affected selects units through deleted dependencies', () => {
  let fixture;
  beforeEach(() => {
    fixture = createFixture();
  });
  afterEach(() => fixture.cleanup());

  test('a dependency deleted from the working tree selects the units that used it', () => {
    for (const unitId of ALL_UNITS) fixture.verifyUiUx(unitId);
    fixture.git('add', '-A');
    fixture.git('commit', '--quiet', '-m', 'record coverage');

    fs.rmSync(path.join(fixture.root, HTTP_HELPER));

    const result = affected(fixture, ['--changed']);
    assert.ok(result.paths.includes(HTTP_HELPER));
    assert.deepEqual(result.affected.map((item) => item.unit).sort(), [...ALL_UNITS].sort());
    for (const item of result.affected) assert.deepEqual(item.files, [HTTP_HELPER]);
  });

  test('a dependency removed with git rm still selects its units after the deletion is committed', () => {
    for (const unitId of ALL_UNITS) fixture.verifyUiUx(unitId);
    fixture.git('add', '-A');
    fixture.git('commit', '--quiet', '-m', 'record coverage');

    fixture.git('rm', '--quiet', HTTP_HELPER);
    assert.deepEqual(affected(fixture, ['--changed']).affected.map((item) => item.unit).sort(), [...ALL_UNITS].sort());

    fixture.git('commit', '--quiet', '-m', 'remove http helper');
    const byPath = affected(fixture, ['--paths', HTTP_HELPER]);
    assert.deepEqual(byPath.affected.map((item) => item.unit).sort(), [...ALL_UNITS].sort());
  });

  test('a deleted entry file selects its units even without recorded coverage', () => {
    fs.rmSync(path.join(fixture.root, MANAGEMENT_FILE));

    const result = affected(fixture, ['--changed']);
    assert.deepEqual(result.affected.map((item) => item.unit).sort(), [...ALL_UNITS].sort());
    for (const item of result.affected) {
      assert.deepEqual(item.files, [MANAGEMENT_FILE]);
      assert.equal(item.state, 'unreviewed');
    }
  });

  test('a deleted file outside every unit selects nothing', () => {
    for (const unitId of ALL_UNITS) fixture.verifyUiUx(unitId);
    fs.rmSync(path.join(fixture.root, 'lib/academy-server.ts'));

    assert.deepEqual(affected(fixture, ['--changed']).affected, []);
  });
});
