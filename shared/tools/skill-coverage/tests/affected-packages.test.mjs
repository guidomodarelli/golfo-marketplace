import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, test } from 'node:test';

import { UI_SKILL, createFixture } from './helpers/fixture-project.mjs';

/** The only fixture unit whose code uses React (`useState`). */
const REACT_UNIT = 'academy.manage.providers.save';
const ALL_UNITS = [REACT_UNIT, 'academy.manage.requests.approve', 'academy.manage.requests.reject'];
const PACKAGE_MANIFEST = 'package.json';

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

describe('affected selects units through package metadata changes', () => {
  let fixture;
  beforeEach(() => {
    fixture = createFixture();
    for (const unitId of ALL_UNITS) fixture.verifyUiUx(unitId);
    fixture.git('add', '-A');
    fixture.git('commit', '--quiet', '-m', 'record coverage');
  });
  afterEach(() => fixture.cleanup());

  test('a dependency upgrade in package.json selects the units that import the package', () => {
    fixture.replace(PACKAGE_MANIFEST, '"react": "19.0.0"', '"react": "19.1.0"');

    assert.equal(fixture.check(REACT_UNIT).freshness, 'stale');
    const result = affected(fixture, ['--changed']);
    assert.deepEqual(result.paths, [PACKAGE_MANIFEST]);
    assert.deepEqual(result.affected.map((item) => item.unit), [REACT_UNIT]);
    assert.deepEqual(result.affected[0].files, [PACKAGE_MANIFEST]);
    assert.equal(result.affected[0].freshness, 'stale');
  });

  test('a lockfile change selects the units that import a package', () => {
    for (const lockfile of ['pnpm-lock.yaml', 'package-lock.json']) {
      const result = affected(fixture, ['--paths', lockfile]);
      assert.deepEqual(result.affected.map((item) => item.unit), [REACT_UNIT], lockfile);
      assert.deepEqual(result.affected[0].files, [lockfile]);
    }
  });

  test('a change to a file outside every unit selects nothing', () => {
    fixture.write('README.md', '# Fixture app\n');

    assert.deepEqual(affected(fixture, ['--changed']).affected, []);
  });
});
