/**
 * Local servers for the user-manual browser tests: the example manuals built from the real template and
 * DESIGN.md boilerplate, and a local viewer that embeds the manual in an iframe on the same origin or on
 * another one. Two servers on different ports are two different origins.
 */
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildExample } from '../../scripts/build-manual.mjs';

const TESTS_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const VIEWER_TEMPLATE_PATH = path.join(TESTS_DIR, 'fixtures', 'local-viewer.html');
export const CHECK_RENDERED_PATH = path.join(TESTS_DIR, '..', 'scripts', 'check-rendered.js');
export const DOCUMENT_ID = 'doc-1';
export const PUBLIC_VIEW_URL = `https://docs.example.com/d/${DOCUMENT_ID}/view`;
const LOOPBACK_HOST = '127.0.0.1';

const listen = (routes) => new Promise((resolve) => {
	const server = http.createServer((request, response) => {
		const { pathname } = new URL(request.url, `http://${LOOPBACK_HOST}`);
		const body = routes(pathname);
		if (body === null) { response.writeHead(404).end(); return; }
		response.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' }).end(body);
	});
	server.listen(0, LOOPBACK_HOST, () => resolve({ server, origin: `http://${LOOPBACK_HOST}:${server.address().port}` }));
});

/** Starts the manual origin and a second, foreign origin for the cross-origin viewer. */
export const startManualServers = async () => {
	const staged = buildExample();
	const linear = buildExample({ linear: true });
	// Published in a document viewer: the share URL names the same document as the iframe path.
	const embedded = buildExample({ viewer: 'document' }).replace(/<meta name="heritage:share-url" content="[^"]*">/, `<meta name="heritage:share-url" content="${PUBLIC_VIEW_URL}">`);
	const viewerTemplate = fs.readFileSync(VIEWER_TEMPLATE_PATH, 'utf8');
	const viewer = (manualSource) => viewerTemplate.replace('{{MANUAL_SRC}}', manualSource);
	const manualRoutes = {
		'/manual.html': staged,
		'/linear.html': linear,
		[`/d/${DOCUMENT_ID}/raw`]: embedded,
		[`/d/${DOCUMENT_ID}/view`]: viewer(`/d/${DOCUMENT_ID}/raw`),
		'/d/doc-2/view': viewer(`/d/${DOCUMENT_ID}/raw`),
		'/other/view': viewer(`/d/${DOCUMENT_ID}/raw`),
	};
	const manualServer = await listen((pathname) => manualRoutes[pathname] ?? null);
	const foreignServer = await listen((pathname) => (pathname === `/d/${DOCUMENT_ID}/view` ? viewer(`${manualServer.origin}/d/${DOCUMENT_ID}/raw`) : null));
	return {
		origin: manualServer.origin,
		foreignOrigin: foreignServer.origin,
		close: () => Promise.all([manualServer, foreignServer].map(({ server }) => new Promise((resolve) => server.close(resolve)))),
	};
};
