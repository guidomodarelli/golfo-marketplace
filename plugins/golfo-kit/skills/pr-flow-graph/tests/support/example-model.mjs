import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

export const SKILL_DIRECTORY = fileURLToPath(new URL('../../', import.meta.url));
export const EXAMPLE_MODEL_PATH = fileURLToPath(new URL('../../assets/example-flow-graph.json', import.meta.url));
export const CLI_PATH = fileURLToPath(new URL('../../scripts/flow-graph.mjs', import.meta.url));
export const FIXTURES_DIRECTORY = fileURLToPath(new URL('../fixtures/', import.meta.url));

/** @returns {object} A fresh copy of the example model, safe to mutate in a test. */
export function loadExampleModel() {
  return JSON.parse(readFileSync(EXAMPLE_MODEL_PATH, 'utf8'));
}
