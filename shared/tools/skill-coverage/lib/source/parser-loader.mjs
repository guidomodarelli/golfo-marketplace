/**
 * Finds a TypeScript/JSX parser without adding dependencies to the golfo plugins:
 * the Babel parser the consumer project already installs, either directly
 * (`@babel/parser`) or the copy Next.js ships. Without one, the engine falls
 * back to whole-file fingerprints and says so in every result.
 */
import { createRequire } from 'node:module';
import path from 'node:path';

/** Environment variable that forces a parser module path, or `none` to disable symbol analysis. */
export const PARSER_ENVIRONMENT_VARIABLE = 'GOLFO_COVERAGE_PARSER';

const PARSER_CANDIDATES = ['@babel/parser', 'next/dist/compiled/babel/parser'];

/**
 * @typedef {{ name: string, parse: (code: string, options: object) => any } | null} LoadedParser
 */

/**
 * Loads the first parser found from the project, then from this tool.
 *
 * @param {string} projectRoot
 * @returns {LoadedParser} `null` when no parser is available or it was disabled.
 */
export function loadParser(projectRoot) {
  const requested = process.env[PARSER_ENVIRONMENT_VARIABLE];
  if (requested === 'none') return null;
  const candidates = requested ? [requested] : PARSER_CANDIDATES;
  const bases = [path.join(projectRoot, 'package.json'), import.meta.url];
  for (const base of bases) {
    const requireFrom = createRequire(base);
    for (const candidate of candidates) {
      try {
        const parserModule = requireFrom(candidate);
        if (typeof parserModule?.parse === 'function') return { name: candidate, parse: parserModule.parse };
      } catch {
        // Not installed from this base: try the next candidate.
      }
    }
  }
  return null;
}
