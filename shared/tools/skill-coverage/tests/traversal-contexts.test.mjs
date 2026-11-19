import assert from 'node:assert/strict';
import { after, before, beforeEach, describe, test } from 'node:test';

import { UI_SKILL, createFixture } from './helpers/fixture-project.mjs';

const ROUTE_FILE = 'app/api/notes/route.ts';
const PANEL_FILE = 'components/notes/index.tsx';
const SHARED_FILE = 'lib/shared.ts';
const TEXT_FILE = 'lib/text.ts';

// The route handler and the panel both import the shared helper; only the
// panel (a UI entry) has depth left to follow the helper into `lib/text.ts`,
// since the UI/UX policy follows a server entry one hop only.
const NOTES_FILES = {
  [PANEL_FILE]: 'import { formatNote } from "@/lib/shared";\n\nexport function NotesPanel() {\n  return <p>{formatNote("panel")}</p>;\n}\n',
  [ROUTE_FILE]: 'import { formatNote } from "@/lib/shared";\n\nexport async function POST() {\n  return Response.json({ message: formatNote("route") });\n}\n',
  [SHARED_FILE]: 'import { noteLabel } from "./text";\n\nexport function formatNote(value) {\n  return `${noteLabel}: ${value}`;\n}\n',
  [TEXT_FILE]: 'export const noteLabel = "Nota";\n',
};

const NOTES_UNIT = 'notes.panel.compose';

// The server entry goes first, so the narrower traversal reaches the shared
// helper before the UI one.
const NOTES_ENTRIES = [
  { path: ROUTE_FILE, symbol: 'POST' },
  { path: PANEL_FILE, symbol: 'NotesPanel' },
];

const PARSER_MODES = [
  { env: {}, name: 'with symbol analysis' },
  { env: { GOLFO_COVERAGE_PARSER: 'none' }, name: 'without a parser' },
];

for (const parserMode of PARSER_MODES) {
  describe(`inputs reached by entries with different traversal scopes (${parserMode.name})`, () => {
    let fixture;
    let verifiedHead;

    /**
     * Runs the real CLI in this parser mode and fails on a non-zero exit.
     *
     * @param {string[]} args
     * @returns {any} Parsed JSON output.
     */
    const runCli = (args) => {
      const result = fixture.run(args, { env: parserMode.env });
      assert.equal(result.status, 0, `skill-coverage ${args.join(' ')} failed: ${result.stderr}`);
      return result.json;
    };

    /** Records an accredited UI/UX run for the unit in this parser mode. */
    const verifyNotesUnit = () => {
      const { runId } = runCli(['begin', '--unit', NOTES_UNIT, '--skill', UI_SKILL, '--mode', 'full']);
      runCli(['evidence', '--run', runId, '--kind', 'review', '--outcome', 'pass', '--summary', 'state matrix and feedback channels reviewed']);
      runCli(['evidence', '--run', runId, '--kind', 'test', '--exec', `"${process.execPath}" -e "process.exit(0)"`]);
      runCli(['evidence', '--run', runId, '--kind', 'browser', '--outcome', 'pass', '--summary', 'walked loading, error and data states with Playwright']);
      assert.equal(runCli(['record', '--run', runId, '--result', 'verified']).result, 'verified');
    };

    before(() => {
      fixture = createFixture({ withUnits: false });
      for (const [relativePath, content] of Object.entries(NOTES_FILES)) fixture.write(relativePath, content);
      fixture.writeUnit(NOTES_UNIT, { entries: NOTES_ENTRIES, hierarchy: { module: 'Notes', page: 'Panel', section: 'Compose', subflow: 'Format' } });
      verifyNotesUnit();
      fixture.git('add', '-A');
      fixture.git('commit', '--quiet', '-m', 'record coverage');
      verifiedHead = fixture.git('rev-parse', 'HEAD');
    });
    beforeEach(() => {
      fixture.git('reset', '--quiet', '--hard', verifiedHead);
      fixture.git('clean', '--quiet', '-fd');
    });
    after(() => fixture?.cleanup());

    test('a dependency of a shared helper reached first at the server depth limit is still tracked for the UI entry', () => {
      const inputs = runCli(['inputs', '--unit', NOTES_UNIT, '--skill', UI_SKILL]);
      assert.equal(inputs.truncated, false);
      assert.ok(TEXT_FILE in inputs.files, `${TEXT_FILE} is analyzed`);
      assert.ok(
        Object.keys(inputs.inputs).some((key) => key.startsWith(`${TEXT_FILE}#`)),
        `an input of ${TEXT_FILE} is tracked, got: ${Object.keys(inputs.inputs).join(', ')}`,
      );
    });

    test('changing the text the shared helper imports makes the unit stale', () => {
      fixture.replace(TEXT_FILE, '"Nota"', '"Nota nueva"');
      const check = runCli(['check', '--unit', NOTES_UNIT, '--skill', UI_SKILL]);
      assert.equal(check.freshness, 'stale');
      assert.notEqual(check.decision, 'skip');
      assert.ok(
        check.relevantChanges.some((change) => change.key.startsWith(`${TEXT_FILE}#`)),
        `the change in ${TEXT_FILE} is relevant, got: ${check.relevantChanges.map((change) => change.key).join(', ')}`,
      );
    });
  });
}
