/**
 * Public contract of check-rendered.mjs through its CLI, in headless Chromium: a manual that respects the
 * layout passes at every width, and one whose stage menu covers the content fails with its reason.
 * Like the browser suite, it is skipped locally without Playwright and mandatory in CI.
 */
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { after, before, describe, test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { buildExample } from '../scripts/build-manual.mjs';

const CHECK_RENDERED = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'scripts', 'check-rendered.mjs');
const PLAYWRIGHT_CANDIDATES = [process.env.PLAYWRIGHT_MODULE, 'playwright', 'playwright-core'].filter(Boolean);
const require = createRequire(import.meta.url);
const hasPlaywright = PLAYWRIGHT_CANDIDATES.some((candidate) => { try { require.resolve(candidate); return true; } catch (moduleError) { return false; } });
if (!hasPlaywright && process.env.CI) throw new Error('check-rendered-cli.test.mjs: Playwright not found; run pnpm install');
const CLI_TIMEOUT_MS = 120000;

let workspace;
const run = (...args) => {
	const result = spawnSync(process.execPath, [CHECK_RENDERED, ...args], { encoding: 'utf8', timeout: CLI_TIMEOUT_MS });
	return { status: result.status, output: `${result.stdout}${result.stderr}` };
};

before(() => { workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'user-manual-rendered-')); });
after(() => fs.rmSync(workspace, { recursive: true, force: true }));

describe('check-rendered CLI', { skip: hasPlaywright ? false : 'Playwright not found; run pnpm install or set PLAYWRIGHT_MODULE' }, () => {
	test('passes the staged example at desktop and phone width', () => {
		const file = path.join(workspace, 'staged.html');
		fs.writeFileSync(file, buildExample());
		const result = run(file);
		assert.equal(result.status, 0, result.output);
		assert.match(result.output, /staged\.html at 1280px: ok/);
		assert.match(result.output, /staged\.html at 390px: ok/);
	});

	test('fails a manual whose stage menu covers the content and says why', () => {
		const file = path.join(workspace, 'overlap.html');
		fs.writeFileSync(file, buildExample().replace('</head>', '<style>html.has-stages body{padding-right:24px;}</style>\n</head>'));
		const result = run(file, '--widths', '1280');
		assert.equal(result.status, 1, result.output);
		assert.match(result.output, /at 1280px: FAILED/);
		assert.match(result.output, /ERROR stages: .*the stage menu overlaps the content/);
	});
});

describe('check-rendered CLI when Chromium cannot start', { skip: hasPlaywright ? false : 'Playwright not found; run pnpm install or set PLAYWRIGHT_MODULE' }, () => {
	test('fails and exits instead of hanging on the open server', () => {
		const file = path.join(workspace, 'no-browser.html');
		fs.writeFileSync(file, buildExample());
		const result = spawnSync(process.execPath, [CHECK_RENDERED, file], {
			encoding: 'utf8',
			timeout: CLI_TIMEOUT_MS,
			env: { ...process.env, PLAYWRIGHT_CHROMIUM_EXECUTABLE: path.join(workspace, 'no-such-chromium') },
		});
		assert.equal(result.error, undefined, 'the CLI hung until the timeout');
		assert.equal(result.status, 1, `${result.stdout}${result.stderr}`);
		assert.match(result.stderr, /check-rendered: /);
	});
});

describe('check-rendered CLI usage', () => {
	test('rejects missing files and invalid widths before launching a browser', () => {
		assert.equal(run(path.join(os.tmpdir(), 'no-such-manual.html')).status, 2);
		const file = path.join(workspace, 'any.html');
		fs.writeFileSync(file, '<!DOCTYPE html><title>x</title>');
		const widths = run(file, '--widths', 'wide');
		assert.equal(widths.status, 2);
		assert.match(widths.output, /--widths needs positive integers/);
	});
});
