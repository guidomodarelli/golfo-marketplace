import assert from 'node:assert/strict';
import { after, before, beforeEach, describe, test } from 'node:test';

import { MANAGEMENT_FILE, createFixture } from './helpers/fixture-project.mjs';

const BADGES_FILE = 'components/status-badges.tsx';

const DONE = 'badges.status.done';
const WARNING = 'badges.status.warning';
const LOADING = 'badges.status.loading';
const PROVIDERS_SAVE = 'academy.manage.providers.save';
const REQUESTS_APPROVE = 'academy.manage.requests.approve';
const REQUESTS_REJECT = 'academy.manage.requests.reject';

const NAMED_IMPORT = 'import { Check as Icon } from "lucide-react";';
const NAMESPACE_IMPORT = 'import * as Icons from "lucide-react";';
const DEFAULT_IMPORT = 'import Spinner from "react-spinners/ClipLoader";';

const BADGES_SOURCE = `${NAMED_IMPORT}
${NAMESPACE_IMPORT}
${DEFAULT_IMPORT}

export function DoneBadge() {
  return <Icon />;
}

export function WarningBadge() {
  return <Icons.AlertTriangle />;
}

export function LoadingBadge() {
  return <Spinner />;
}
`;

const BADGE_UNITS = {
  [DONE]: { symbol: 'DoneBadge', subflow: 'Done' },
  [LOADING]: { symbol: 'LoadingBadge', subflow: 'Loading' },
  [WARNING]: { symbol: 'WarningBadge', subflow: 'Warning' },
};

const ALL_UNITS = [DONE, WARNING, LOADING, PROVIDERS_SAVE, REQUESTS_APPROVE, REQUESTS_REJECT];

describe('identity of consumed import bindings in fingerprints', () => {
  let fixture;
  let verifiedHead;
  before(() => {
    fixture = createFixture();
    fixture.write(BADGES_FILE, BADGES_SOURCE);
    for (const [unitId, { symbol, subflow }] of Object.entries(BADGE_UNITS)) {
      fixture.writeUnit(unitId, { entries: [{ path: BADGES_FILE, symbol }], hierarchy: { module: 'Badges', page: 'Status', section: 'Badges', subflow } });
    }
    for (const unitId of ALL_UNITS) fixture.verifyUiUx(unitId);
    fixture.git('add', '-A');
    fixture.git('commit', '--quiet', '-m', 'record coverage');
    verifiedHead = fixture.git('rev-parse', 'HEAD');
  });
  beforeEach(() => {
    fixture.git('reset', '--quiet', '--hard', verifiedHead);
    fixture.git('clean', '--quiet', '-fd');
  });
  after(() => fixture.cleanup());

  /**
   * Asserts that exactly `staleUnitId` is stale, through `relevantKey`,
   * and that every other unit stays current.
   *
   * @param {string} staleUnitId
   * @param {string} relevantKey Input key expected to explain the change.
   */
  const assertOnlyStale = (staleUnitId, relevantKey) => {
    const check = fixture.check(staleUnitId);
    assert.equal(check.freshness, 'stale');
    assert.deepEqual(check.relevantChanges.map((change) => change.key), [relevantKey]);
    for (const unitId of ALL_UNITS.filter((candidate) => candidate !== staleUnitId)) {
      assert.equal(fixture.check(unitId).freshness, 'current', `${unitId} does not use the changed binding`);
    }
  };

  test('another export of the same package behind the same alias invalidates only its consumer', () => {
    fixture.replace(BADGES_FILE, NAMED_IMPORT, 'import { X as Icon } from "lucide-react";');
    assertOnlyStale(DONE, `${BADGES_FILE}#DoneBadge`);
  });

  test('a hook replaced by another export with the same local name invalidates only the section that calls it', () => {
    fixture.replace(MANAGEMENT_FILE, 'import { useState } from "react";', 'import { useReducer as useState } from "react";');
    assertOnlyStale(PROVIDERS_SAVE, `${MANAGEMENT_FILE}#ProvidersSection~shell`);
  });

  test('a namespace import read as Name.member follows a change of package subpath', () => {
    fixture.replace(BADGES_FILE, NAMESPACE_IMPORT, 'import * as Icons from "lucide-react/icons";');
    assertOnlyStale(WARNING, `${BADGES_FILE}#WarningBadge`);
  });

  test('a default import follows a change of package subpath', () => {
    fixture.replace(BADGES_FILE, DEFAULT_IMPORT, 'import Spinner from "react-spinners/BeatLoader";');
    assertOnlyStale(LOADING, `${BADGES_FILE}#LoadingBadge`);
  });

  test('a project binding pointed at another implementation of the same export invalidates only its consumers', () => {
    fixture.write('lib/api-client-v2.ts', fixture.read('lib/api-client.ts').replace('/api/requests/', '/api/v2/requests/'));
    fixture.replace(MANAGEMENT_FILE, 'import { decideRequest, saveProvider } from "@/lib/api-client";', 'import { saveProvider } from "@/lib/api-client";\nimport { decideRequest } from "@/lib/api-client-v2";');
    for (const unitId of [REQUESTS_APPROVE, REQUESTS_REJECT]) {
      const check = fixture.check(unitId);
      assert.equal(check.freshness, 'stale');
      assert.ok(check.relevantChanges.some((change) => change.key === 'lib/api-client-v2.ts#decideRequest' && change.change === 'added'));
    }
    for (const unitId of [PROVIDERS_SAVE, DONE, WARNING, LOADING]) assert.equal(fixture.check(unitId).freshness, 'current', `${unitId} does not use decideRequest`);
  });

  test('reformatting and reordering imports without changing their identity keeps coverage current', () => {
    fixture.replace(BADGES_FILE, `${NAMED_IMPORT}\n${NAMESPACE_IMPORT}\n${DEFAULT_IMPORT}`, `import Spinner from 'react-spinners/ClipLoader'
import * as Icons from 'lucide-react'
import {
  Check as Icon,
} from 'lucide-react'`);
    fixture.replace(MANAGEMENT_FILE, 'import { useState } from "react";', "import {useState} from 'react'");
    for (const unitId of ALL_UNITS) assert.equal(fixture.check(unitId).freshness, 'current', `${unitId} keeps its coverage`);
  });
});
