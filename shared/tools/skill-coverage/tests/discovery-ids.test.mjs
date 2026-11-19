import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, test } from 'node:test';

import { createFixture } from './helpers/fixture-project.mjs';

const SHOP_PAGE = 'app/shop/page.tsx';
const PRODUCT_PAGE = 'app/shop/[id]/page.tsx';
const SHOP_SERVER = 'lib/shop-server.ts';
const VIEW_UNIT = 'shop.view';

const SHOP_LOADING_PAGE = `import { loadShop } from "@/lib/shop-server";

export default async function ShopPage() {
  const shop = await loadShop();
  return <h1>{shop.title}</h1>;
}
`;

const PRODUCT_LOADING_PAGE = `import { loadProduct } from "@/lib/shop-server";

export default async function ProductPage({ params }) {
  const product = await loadProduct(params.id);
  return <h1>{product.name}</h1>;
}
`;

const SHOP_SERVER_SOURCE = `export async function loadShop() {
  return { title: "Shop" };
}

export async function loadProduct(id) {
  return { name: \`Product \${id}\` };
}
`;

/**
 * @param {any} discovery `discover --json` output.
 * @param {string} pagePath
 */
function proposalForPage(discovery, pagePath) {
  return discovery.proposals.find((proposal) => proposal.entries[0].path === pagePath && proposal.entries[0].symbol === 'default');
}

describe('discovery reserves registered unit ids for new proposals', () => {
  let fixture;
  beforeEach(() => {
    fixture = createFixture({ withUnits: false });
    fixture.write(SHOP_SERVER, SHOP_SERVER_SOURCE);
    fixture.write(SHOP_PAGE, SHOP_LOADING_PAGE);
    fixture.git('add', '-A');
    fixture.git('commit', '--quiet', '-m', 'shop page');
  });
  afterEach(() => fixture.cleanup());

  test('a new route whose id collides with a registered unit is saved under a free id and the existing unit keeps its id', () => {
    const firstWritten = fixture.run(['discover', '--write', '--scope', 'app/shop']).json.written;
    assert.deepEqual(firstWritten.created, [VIEW_UNIT]);

    fixture.write(PRODUCT_PAGE, PRODUCT_LOADING_PAGE);
    const discovery = fixture.run(['discover', '--write', '--scope', 'app/shop']).json;

    const existing = proposalForPage(discovery, SHOP_PAGE);
    assert.equal(existing.existingId, VIEW_UNIT);
    assert.equal(existing.id, VIEW_UNIT, 'the proposal matching a registered unit keeps its id');

    const product = proposalForPage(discovery, PRODUCT_PAGE);
    assert.equal(product.existingId, null);
    assert.notEqual(product.id, VIEW_UNIT, 'the new page never takes a registered id');
    assert.deepEqual(discovery.written.created, [product.id]);
    assert.deepEqual(discovery.written.skipped, []);

    const savedUnit = JSON.parse(fixture.read(`.golfo/skill-coverage/units/${product.id}.json`));
    assert.equal(savedUnit.entries[0].path, PRODUCT_PAGE, 'the dynamic page is registered as its own unit');
    assert.equal(JSON.parse(fixture.read(`.golfo/skill-coverage/units/${VIEW_UNIT}.json`)).entries[0].path, SHOP_PAGE);

    const repeated = fixture.run(['discover', '--write', '--scope', 'app/shop']).json;
    assert.deepEqual(repeated.written.created, [], 'a repeated discovery creates nothing new');
    assert.equal(proposalForPage(repeated, PRODUCT_PAGE).existingId, product.id);
    assert.equal(proposalForPage(repeated, SHOP_PAGE).existingId, VIEW_UNIT);
  });

  test('a unit file that cannot be saved is reported instead of being skipped silently', () => {
    fixture.write(`.golfo/skill-coverage/units/${VIEW_UNIT}.json`, '{ not json');
    const discovery = fixture.run(['discover', '--write', '--scope', 'app/shop']).json;
    assert.deepEqual(discovery.written.created, []);
    assert.equal(discovery.written.skipped.length, 1);
    assert.equal(discovery.written.skipped[0].id, VIEW_UNIT);
    assert.ok(discovery.written.skipped[0].reason, 'the skipped unit has a reason');

    const text = fixture.run(['discover', '--write', '--scope', 'app/shop'], { json: false }).stdout;
    assert.ok(text.includes(`not saved: ${VIEW_UNIT}`), 'the text output names the unit that was not saved');
  });
});
