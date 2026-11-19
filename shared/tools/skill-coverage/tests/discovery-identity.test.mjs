import assert from 'node:assert/strict';
import { afterEach, beforeEach, describe, test } from 'node:test';

import { createFixture } from './helpers/fixture-project.mjs';

const SHOP_PAGE = 'app/shop/page.tsx';
const SHOP_COMPONENT = 'components/shop/index.tsx';
const SHOP_SERVER = 'lib/shop-server.ts';
const SECTION_UNIT = 'shop.products';
const VIEW_UNIT = 'shop.view';

const STATIC_PAGE = `import { ProductsSection } from "@/components/shop";

export default function ShopPage() {
  return <ProductsSection />;
}
`;

const LOADING_PAGE = `import { ProductsSection } from "@/components/shop";
import { loadShop } from "@/lib/shop-server";

export default async function ShopPage() {
  const shop = await loadShop();
  return <ProductsSection title={shop.title} />;
}
`;

const PRODUCTS_SECTION = `"use client";

import { useEffect, useState } from "react";

export function ProductsSection({ title }) {
  const [products, setProducts] = useState([]);
  useEffect(() => {
    fetch("/api/products").then((response) => response.json()).then(setProducts);
  }, []);
  return (
    <section>
      <h2>{title}</h2>
      <ul>{products.map((product) => <li key={product.id}>{product.name}</li>)}</ul>
    </section>
  );
}
`;

/**
 * @param {any} discovery `discover --json` output.
 * @param {string} id
 */
function proposalById(discovery, id) {
  return discovery.proposals.find((proposal) => proposal.id === id);
}

describe('discovery identity uses functional entries only', () => {
  let fixture;
  beforeEach(() => {
    fixture = createFixture({ withUnits: false });
    fixture.write(SHOP_COMPONENT, PRODUCTS_SECTION);
    fixture.write(SHOP_PAGE, STATIC_PAGE);
    fixture.write(SHOP_SERVER, 'export async function loadShop() {\n  return { title: "Shop" };\n}\n');
    fixture.git('add', '-A');
    fixture.git('commit', '--quiet', '-m', 'shop page');
  });
  afterEach(() => fixture.cleanup());

  test('a page that starts loading data gets its own view unit next to the section unit that composes it', () => {
    const firstDiscovery = fixture.run(['discover', '--write', '--scope', 'app/shop']).json;
    assert.deepEqual(firstDiscovery.written.created, [SECTION_UNIT], 'only the data-loading section is a unit while the page is static');
    const section = proposalById(firstDiscovery, SECTION_UNIT);
    assert.ok(section.entries.some((entry) => entry.follow === false && entry.path === SHOP_PAGE && entry.symbol === 'default'), 'the section unit is composed by the page');

    fixture.write(SHOP_PAGE, LOADING_PAGE);
    const discovery = fixture.run(['discover', '--scope', 'app/shop']).json;
    assert.equal(proposalById(discovery, SECTION_UNIT).existingId, SECTION_UNIT);
    const view = proposalById(discovery, VIEW_UNIT);
    assert.ok(view, 'the page load is proposed as a view');
    assert.equal(view.existingId, null, 'the page composing a section is not the identity of that section unit');
    assert.deepEqual(discovery.relocations, []);

    const written = fixture.run(['discover', '--write', '--scope', 'app/shop']).json.written;
    assert.deepEqual(written.created, [VIEW_UNIT]);
    assert.deepEqual(written.relocated, []);
    assert.equal(fixture.check(VIEW_UNIT).state, 'unreviewed');
  });

  test('a stale composition entry does not turn another page view into a relocation', () => {
    fixture.write(SHOP_PAGE, LOADING_PAGE);
    fixture.writeUnit('legacy.products', {
      entries: [
        { path: SHOP_COMPONENT, symbol: 'ProductsSection' },
        { follow: false, path: 'app/legacy/page.tsx', symbol: 'default' },
      ],
      hierarchy: { module: 'legacy', page: '/legacy', section: 'ProductsSection', subflow: 'ProductsSection' },
    });

    const discovery = fixture.run(['discover', '--scope', 'app/shop']).json;
    assert.equal(proposalById(discovery, VIEW_UNIT).existingId, null);
    assert.deepEqual(discovery.relocations, []);
    assert.equal(proposalById(discovery, SECTION_UNIT).existingId, 'legacy.products', 'functional entries still match');
  });
});
