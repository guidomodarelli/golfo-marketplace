import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { afterEach, beforeEach, describe, test } from 'node:test';

import { createFixture } from './helpers/fixture-project.mjs';

const UNITS_DIRECTORY = '.golfo/skill-coverage/units';
const SERVER_FILE = 'lib/pages-server.ts';
const OLD_PAGE = 'app/old/page.tsx';
const OLD_VIEW = 'old.view';
const ACCOUNT_VIEW = 'account.view';
const SEARCH_VIEW = 'search.view';
const SHOP_PAGE = 'app/shop/page.tsx';
const SHOP_COMPONENT = 'components/shop/index.tsx';
const CATALOG_COMPONENT = 'components/catalog/index.tsx';
const STORE_COMPONENT = 'components/store/index.tsx';
const SHOP_PRODUCTS = 'shop.products';

/**
 * A page that loads data on the server and renders plain markup, so its only
 * proposal is the `view` unit whose functional entry is `default`.
 *
 * @param {string} title
 * @returns {string}
 */
function dataPage(title) {
  return `import { loadPage } from "@/lib/pages-server";

export default async function ${title}Page() {
  const page = await loadPage("${title}");
  return <main>{page.title}</main>;
}
`;
}

/**
 * A page that renders the products section imported from `componentPath`.
 *
 * @param {string} componentPath Component module without extension.
 * @returns {string}
 */
function productsPage(componentPath) {
  return `import { ProductsSection } from "@/${componentPath}";

export default function ProductsPage() {
  return <ProductsSection />;
}
`;
}

const PRODUCTS_SECTION = `"use client";

import { useEffect, useState } from "react";

export function ProductsSection() {
  const [products, setProducts] = useState([]);
  useEffect(() => {
    fetch("/api/products").then((response) => response.json()).then(setProducts);
  }, []);
  return <ul>{products.map((product) => <li key={product.id}>{product.name}</li>)}</ul>;
}
`;

/**
 * @param {any} discovery `discover --json` output.
 * @param {string} id
 */
function proposalById(discovery, id) {
  return discovery.proposals.find((proposal) => proposal.id === id);
}

describe('discovery relocates a unit only on an unambiguous match', () => {
  let fixture;
  const readUnit = (id) => JSON.parse(fs.readFileSync(path.join(fixture.root, UNITS_DIRECTORY, `${id}.json`), 'utf8'));
  const unitExists = (id) => fs.existsSync(path.join(fixture.root, UNITS_DIRECTORY, `${id}.json`));

  beforeEach(() => {
    fixture = createFixture({ withUnits: false });
    fixture.write(SERVER_FILE, 'export async function loadPage(title) {\n  return { title };\n}\n');
  });
  afterEach(() => fixture.cleanup());

  test('deleting a registered page does not turn unrelated new pages into its relocation', () => {
    fixture.write(OLD_PAGE, dataPage('Old'));
    assert.ok(fixture.run(['discover', '--write']).json.written.created.includes(OLD_VIEW));
    const registeredOldView = readUnit(OLD_VIEW);

    fs.rmSync(path.join(fixture.root, OLD_PAGE));
    fixture.write('app/account/page.tsx', dataPage('Account'));
    fixture.write('app/search/page.tsx', dataPage('Search'));

    const discovery = fixture.run(['discover']).json;
    for (const id of [ACCOUNT_VIEW, SEARCH_VIEW]) assert.equal(proposalById(discovery, id).existingId, null, `${id} is a new unit`);
    assert.deepEqual(discovery.relocations, []);

    const written = fixture.run(['discover', '--write']).json.written;
    assert.deepEqual([...written.created].sort(), [ACCOUNT_VIEW, SEARCH_VIEW]);
    assert.deepEqual(written.relocated, []);
    assert.deepEqual(readUnit(OLD_VIEW), registeredOldView, 'the old unit keeps its entries, route and hierarchy');
  });

  test('a named component moved to another file keeps its unit when it is the only candidate', () => {
    fixture.write(SHOP_COMPONENT, PRODUCTS_SECTION);
    fixture.write(SHOP_PAGE, productsPage('components/shop'));
    assert.ok(fixture.run(['discover', '--write', '--scope', 'app/shop']).json.written.created.includes(SHOP_PRODUCTS));

    fs.rmSync(path.join(fixture.root, SHOP_COMPONENT));
    fixture.write(CATALOG_COMPONENT, PRODUCTS_SECTION);
    fixture.write(SHOP_PAGE, productsPage('components/catalog'));

    const discovery = fixture.run(['discover', '--write', '--scope', 'app/shop']).json;
    assert.deepEqual(discovery.relocations.map(({ from, to, unitId }) => ({ from, to, unitId })), [{ from: SHOP_COMPONENT, to: CATALOG_COMPONENT, unitId: SHOP_PRODUCTS }]);
    assert.deepEqual(discovery.written.relocated, [SHOP_PRODUCTS]);
    assert.ok(readUnit(SHOP_PRODUCTS).entries.some((entry) => entry.path === CATALOG_COMPONENT && entry.symbol === 'ProductsSection'));
  });

  test('a named component copied to two files stays two new units instead of rewriting the old one', () => {
    fixture.write(SHOP_COMPONENT, PRODUCTS_SECTION);
    fixture.write(SHOP_PAGE, productsPage('components/shop'));
    assert.ok(fixture.run(['discover', '--write', '--scope', 'app/shop']).json.written.created.includes(SHOP_PRODUCTS));
    const registeredProducts = readUnit(SHOP_PRODUCTS);

    fs.rmSync(path.join(fixture.root, SHOP_COMPONENT));
    fs.rmSync(path.join(fixture.root, SHOP_PAGE));
    fixture.write(CATALOG_COMPONENT, PRODUCTS_SECTION);
    fixture.write(STORE_COMPONENT, PRODUCTS_SECTION);
    fixture.write('app/catalog/page.tsx', productsPage('components/catalog'));
    fixture.write('app/store/page.tsx', productsPage('components/store'));

    const discovery = fixture.run(['discover', '--write', '--scope', 'app']).json;
    assert.deepEqual(discovery.relocations, []);
    for (const id of ['catalog.products', 'store.products']) {
      assert.equal(proposalById(discovery, id).existingId, null, `${id} is a new unit`);
      assert.ok(unitExists(id), `${id} is written`);
    }
    assert.deepEqual(discovery.written.relocated, []);
    assert.deepEqual(readUnit(SHOP_PRODUCTS), registeredProducts);
  });
});
