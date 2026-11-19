import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

export const SKILL_DIRECTORY = fileURLToPath(new URL('../../', import.meta.url));
export const EXAMPLE_MODEL_PATH = fileURLToPath(new URL('../../assets/example-flow-graph.json', import.meta.url));
export const CLI_PATH = fileURLToPath(new URL('../../scripts/flow-graph.mjs', import.meta.url));
export const FIXTURES_DIRECTORY = fileURLToPath(new URL('../fixtures/', import.meta.url));

export const EXAMPLE_RFC_MODEL_PATH = fileURLToPath(new URL('../../assets/example-rfc-flow-graph.json', import.meta.url));
export const EXAMPLE_RFC_DOCUMENT_PATH = fileURLToPath(new URL('../../assets/example-rfc.md', import.meta.url));

/**
 * Code the example RFC proposes to change, as it is today. `assets/example-rfc-flow-graph.json`
 * points at these lines.
 */
export const EXAMPLE_RFC_CODE_FILES = {
  'src/orders/order-routes.js': [
    "const router = require('express').Router();",
    "const { getOrder } = require('./get-order');",
    '',
    "router.get('/orders/:id', async (req, res) => {",
    '  res.json(await getOrder(req.params.id));',
    '});',
    'module.exports = router;',
  ].join('\n'),
  'src/orders/get-order.js': [
    "const orders = require('./order-repository');",
    '',
    'async function getOrder(orderId) {',
    '  return orders.findById(orderId);',
    '}',
    'module.exports = { getOrder };',
  ].join('\n'),
  'src/orders/order-repository.js': [
    "const db = require('../db');",
    '',
    'async function findById(orderId) {',
    '  return db.orders.find(orderId);',
    '}',
    'module.exports = { findById };',
  ].join('\n'),
};

/** @returns {object} A fresh copy of the example model, safe to mutate in a test. */
export function loadExampleModel() {
  return JSON.parse(readFileSync(EXAMPLE_MODEL_PATH, 'utf8'));
}

/** @returns {object} A fresh copy of the example RFC model, safe to mutate in a test. */
export function loadExampleRfcModel() {
  return JSON.parse(readFileSync(EXAMPLE_RFC_MODEL_PATH, 'utf8'));
}
