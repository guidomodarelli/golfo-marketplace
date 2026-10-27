#!/usr/bin/env node
/**
 * Runs the rendered checks of check-rendered.js on a manual from the terminal, in headless Chromium, at each
 * width: captures rendered and fitted, pins in place and in reading order, and the staged contract.
 *
 * Usage:
 *   node check-rendered.mjs <manual.html> [--widths 1280,390]
 *
 * Needs Playwright: PLAYWRIGHT_MODULE (path or package name), else the packages playwright and
 * playwright-core (a devDependency of the repo). PLAYWRIGHT_CHROMIUM_EXECUTABLE points to a Chromium binary
 * when the one of that Playwright version is not installed. The manual is served from its own folder on
 * 127.0.0.1, so relative files resolve as they would in the viewer.
 *
 * Exit code: 0 when every width returns ok, 1 when any does not, 2 on bad usage or without Playwright.
 */
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const CHECK_RENDERED_PATH = path.join(path.dirname(fileURLToPath(import.meta.url)), 'check-rendered.js');
// The widths DESIGN.md asks to verify: desktop and phone.
const DEFAULT_WIDTHS = [1280, 390];
const VIEWPORT_HEIGHT_PX = 900;
const LOOPBACK_HOST = '127.0.0.1';
const PLAYWRIGHT_CANDIDATES = [process.env.PLAYWRIGHT_MODULE, 'playwright', 'playwright-core'].filter(Boolean);
const CONTENT_TYPES = { '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml' };

const parseArguments = (argv) => {
	const options = { manual: null, widths: DEFAULT_WIDTHS };
	for (let index = 0; index < argv.length; index += 1) {
		if (argv[index] === '--widths') options.widths = (argv[(index += 1)] || '').split(',').map(Number);
		else if (!options.manual && !argv[index].startsWith('--')) options.manual = argv[index];
		else throw new Error(`check-rendered: unexpected argument ${argv[index]}`);
	}
	if (!options.manual) throw new Error('check-rendered: missing <manual.html>');
	if (!fs.existsSync(options.manual)) throw new Error(`check-rendered: ${options.manual} does not exist`);
	if (!options.widths.length || options.widths.some((width) => !Number.isInteger(width) || width <= 0)) throw new Error('check-rendered: --widths needs positive integers separated by commas');
	return options;
};

const loadPlaywright = () => {
	const require = createRequire(import.meta.url);
	for (const candidate of PLAYWRIGHT_CANDIDATES) {
		try { return require(candidate); } catch (moduleError) { /* next candidate */ }
	}
	return null;
};

/** Serves the manual's folder; only files inside it are reachable. */
const serveFolder = (folder) => new Promise((resolve) => {
	const server = http.createServer((request, response) => {
		const requested = path.normalize(path.join(folder, decodeURIComponent(new URL(request.url, `http://${LOOPBACK_HOST}`).pathname)));
		if (!requested.startsWith(folder) || !fs.existsSync(requested) || fs.statSync(requested).isDirectory()) { response.writeHead(404).end(); return; }
		response.writeHead(200, { 'content-type': CONTENT_TYPES[path.extname(requested)] || 'application/octet-stream' }).end(fs.readFileSync(requested));
	});
	server.listen(0, LOOPBACK_HOST, () => resolve(server));
});

const main = async () => {
	let options;
	try {
		options = parseArguments(process.argv.slice(2));
	} catch (usageError) {
		console.error(usageError.message);
		return 2;
	}
	const playwright = loadPlaywright();
	if (!playwright) {
		console.error(`check-rendered: Playwright not found (tried ${PLAYWRIGHT_CANDIDATES.join(', ')}); run pnpm install or set PLAYWRIGHT_MODULE`);
		return 2;
	}
	const manualPath = path.resolve(options.manual);
	const server = await serveFolder(path.dirname(manualPath));
	let browser = null;
	let allOk = true;
	// The browser starts inside the cleanup scope: if Chromium fails to launch, the server still closes
	// and the CLI exits instead of staying alive on an open port.
	try {
		browser = await playwright.chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined });
		const url = `http://${LOOPBACK_HOST}:${server.address().port}/${encodeURIComponent(path.basename(manualPath))}`;
		for (const width of options.widths) {
			const page = await browser.newPage({ viewport: { width, height: VIEWPORT_HEIGHT_PX } });
			await page.goto(url);
			await page.addScriptTag({ path: CHECK_RENDERED_PATH });
			const result = await page.evaluate(() => window.__umCheckRendered());
			await page.close();
			allOk = allOk && result.ok;
			const problems = ['unrendered', 'fit', 'pins', 'order', 'stages'].filter((key) => result[key] && result[key].length).map((key) => `${key}: ${JSON.stringify(result[key])}`);
			console.log(`check-rendered: ${path.basename(manualPath)} at ${width}px: ${result.ok ? 'ok' : 'FAILED'} (${result.frames} capture(s))`);
			problems.forEach((problem) => console.log(`  ERROR ${problem}`));
		}
	} finally {
		if (browser) await browser.close();
		server.close();
	}
	return allOk ? 0 : 1;
};

main().then((code) => { process.exitCode = code; }, (runError) => {
	console.error(`check-rendered: ${runError.message}`);
	process.exitCode = 1;
});
