/**
 * Public contract of the static validator (check-manual.mjs) and the builder (build-manual.mjs),
 * through their CLIs, on manuals built from the real template and DESIGN.md boilerplate.
 */
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { after, before, describe, test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { buildExample } from '../scripts/build-manual.mjs';

const SCRIPTS_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'scripts');
const CHECK_MANUAL = path.join(SCRIPTS_DIR, 'check-manual.mjs');
const BUILD = path.join(SCRIPTS_DIR, 'build-manual.mjs');
const NAVIGATION_SCRIPT = path.join(SCRIPTS_DIR, '..', 'assets', 'boilerplate', 'navigation.js');
const LANGUAGE_SCRIPT = path.join(SCRIPTS_DIR, '..', 'assets', 'boilerplate', 'language.js');
const DOCUMENT_LINKS_SCRIPT = path.join(SCRIPTS_DIR, '..', 'assets', 'boilerplate', 'document-links.js');
const LANGUAGE_MARKER = '// Idioma: el documento se escribe en español';
const DOCUMENT_LINKS_MARKER = '// Navegación entre documentos Heritage';
const VIEWER_ADAPTER_WARNING = 'the document viewer adapter is missing';

let workspace;
let staged;
let linear;

const writeManual = (name, html) => {
	const file = path.join(workspace, name);
	fs.writeFileSync(file, html);
	return file;
};
const run = (script, ...args) => {
	const result = spawnSync(process.execPath, [script, ...args], { encoding: 'utf8' });
	return { status: result.status, output: `${result.stdout}${result.stderr}` };
};
const checkManual = (name, html) => run(CHECK_MANUAL, writeManual(name, html));
const replaceOnce = (html, search, replacement) => {
	assert.ok(html.includes(search), `fixture does not contain ${search}`);
	return html.replace(search, replacement);
};

before(() => {
	workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'user-manual-check-'));
	staged = buildExample();
	linear = buildExample({ linear: true });
});
after(() => fs.rmSync(workspace, { recursive: true, force: true }));

describe('check-manual: reading modes', () => {
	test('accepts the staged example (with chapters) without a top TOC', () => {
		const result = checkManual('staged.html', staged);
		assert.equal(result.status, 0, result.output);
		assert.match(result.output, /10 sections, 0 mockups, 0 errors/);
	});

	test('keeps the linear gates: the linear example passes and needs its TOC', () => {
		assert.equal(checkManual('linear.html', linear).status, 0);
		const withoutToc = checkManual('linear-no-toc.html', linear.replace(/<nav class="toc"[\s\S]*?<\/nav>/, ''));
		assert.equal(withoutToc.status, 1);
		assert.match(withoutToc.output, /ERROR toc: no nav\.toc entries found/);
		assert.match(withoutToc.output, /ERROR toc: section #purpose is missing from the TOC/);
	});

	test('rejects a top TOC in a staged manual', () => {
		const toc = '<nav class="toc" aria-labelledby="toc-label"><div class="toc-label" id="toc-label">Contenido</div><ol><li><a href="#purpose"><span class="toc-num">01</span>Para qué sirve</a></li></ol></nav>';
		const result = checkManual('staged-toc.html', replaceOnce(staged, '</header>', `</header>\n${toc}`));
		assert.equal(result.status, 1);
		assert.match(result.output, /ERROR toc: a staged manual has no top nav\.toc/);
	});

	test('rejects an unknown reading mode and stage markup without the staged mode', () => {
		const unknown = checkManual('unknown-mode.html', replaceOnce(staged, 'content="stages"', 'content="chapters"'));
		assert.equal(unknown.status, 1);
		assert.match(unknown.output, /ERROR stages: unknown heritage:reading-mode "chapters"/);
		const withoutMeta = checkManual('no-mode.html', replaceOnce(staged, '<meta name="heritage:reading-mode" content="stages">', ''));
		assert.equal(withoutMeta.status, 1);
		assert.match(withoutMeta.output, /ERROR stages: stage markup without <meta name="heritage:reading-mode"/);
	});
});

describe('check-manual: stage structure', () => {
	const cases = [
		['a recap without three key concepts', (html) => replaceOnce(html, '<li>Una solicitud tiene pedido, responsable y estado.</li>', ''), /stages: stage "orientation" recap has 2 key concepts; it needs exactly 3/],
		['a section of another stage in the middle', (html) => replaceOnce(html, 'data-section="audience" data-stage="orientation"', 'data-section="audience" data-stage="workflow"'), /stages: section "audience" has data-stage="workflow" inside stage "orientation"/],
		['a stage without its recap', (html) => html.replace(/<aside class="stage-recap" data-stage-recap="reference"[\s\S]*?<\/aside>/, ''), /stages: stage "reference" has no \.stage-recap/],
		['an intro without its reading estimate', (html) => replaceOnce(html, '<p class="stage-reading"></p>', ''), /stages: stage "orientation" intro has no \.stage-reading/],
		['an intro id that is not stage-<id>', (html) => replaceOnce(html, 'id="stage-workflow"', 'id="workflow-stage"'), /stages: stage "workflow" intro needs id="stage-workflow"/],
		['a chapter with a single section', (html) => replaceOnce(html, '<section class="section" aria-labelledby="unhappy-paths"', '<div class="stage-chapter" id="chapter-errors" data-chapter="errors" data-stage="workflow"><h2 class="stage-chapter-title">Errores</h2></div>\n<section class="section" aria-labelledby="unhappy-paths"'), /stages: chapter "practice-and-errors" has 1 section\(s\); it needs at least 2/],
		['sections before the first chapter', (html) => replaceOnce(html, '<div class="stage-chapter" id="chapter-create"', '<section class="section" aria-labelledby="intro-extra" data-stage="workflow"><div class="section-num">00</div><h2 class="section-title" id="intro-extra">Antes</h2></section>\n<div class="stage-chapter" id="chapter-create"'), /stages: stage "workflow" has sections before its first chapter/],
		['a chapter of another stage', (html) => replaceOnce(html, 'data-chapter="create" data-stage="workflow"', 'data-chapter="create" data-stage="reference"'), /stages: chapter "create" has data-stage="reference" inside stage "workflow"/],
		['a chapter id that is not chapter-<id>', (html) => replaceOnce(html, 'id="chapter-create"', 'id="create-chapter"'), /stages: chapter "create" needs id="chapter-create"/],
		['the staged script missing', (html) => html.replace(/<!-- heritage:staged-reading-script:start -->[\s\S]*?<!-- heritage:staged-reading-script:end -->/, ''), /stages: the staged reading script is missing/],
		['the staged styles missing', (html) => html.replace(/<!-- heritage:staged-reading-style:start -->[\s\S]*?<!-- heritage:staged-reading-style:end -->/, ''), /stages: the staged reading styles are missing/],
	];
	for (const [name, mutate, expected] of cases) {
		test(`rejects ${name}`, () => {
			const result = checkManual(`${name.replace(/\W+/g, '-')}.html`, mutate(staged));
			assert.equal(result.status, 1, result.output);
			assert.match(result.output, expected);
		});
	}

	test('recognizes stage blocks with extra classes, like the browser selectors', () => {
		const result = checkManual('extra-classes.html', replaceOnce(replaceOnce(staged, 'class="stage-intro" id="stage-orientation"', 'class="stage-intro is-featured" id="stage-orientation"'), 'class="stage-recap" data-stage-recap="orientation"', 'class="stage-recap is-compact" data-stage-recap="orientation"'));
		assert.equal(result.status, 0, result.output);
	});

	test('rejects a manual without the embedded stage contract', () => {
		const withoutContract = staged.replace(/<script>\n\/\/ Contrato de etapas Heritage[\s\S]*?<\/script>\n/, '');
		assert.notEqual(withoutContract, staged);
		const result = checkManual('no-contract.html', withoutContract);
		assert.equal(result.status, 1);
		assert.match(result.output, /stages: the stage contract script is missing/);
	});

	test('warns when the embedded staged script is outdated', () => {
		const result = checkManual('outdated.html', replaceOnce(staged, "var WORDS_PER_MINUTE = 200;", "var WORDS_PER_MINUTE = 200; // old copy"));
		assert.equal(result.status, 0);
		assert.match(result.output, /warn {2}stages: the script differs from assets\/staged-reading\/staged-reading\.js/);
	});
});

describe('check-manual: viewer links', () => {
	test('warns about a document viewer share URL without its adapter, not with it', () => {
		assert.match(checkManual('viewer-without-adapter.html', staged).output, new RegExp(VIEWER_ADAPTER_WARNING));
		const withAdapter = checkManual('viewer-with-adapter.html', buildExample({ viewer: 'document' }));
		assert.equal(withAdapter.status, 0, withAdapter.output);
		assert.doesNotMatch(withAdapter.output, new RegExp(VIEWER_ADAPTER_WARNING));
	});
});

describe('build-manual CLI', () => {
	test('refreshes the embedded assets instead of duplicating them', () => {
		const file = writeManual('embed-twice.html', staged);
		assert.equal(run(BUILD, file).status, 0);
		assert.equal(fs.readFileSync(file, 'utf8'), staged);
	});

	test('keeps an embedded viewer adapter when refreshing without --viewer', () => {
		const withViewer = buildExample({ viewer: 'document' });
		const file = writeManual('embed-viewer-twice.html', withViewer);
		assert.equal(run(BUILD, file).status, 0);
		assert.equal(fs.readFileSync(file, 'utf8'), withViewer);
	});

	test('fails clearly on manuals it cannot extend and on unknown viewers', () => {
		const withoutNavigation = run(BUILD, writeManual('no-navigation.html', staged.replace(/\/\/ Navegación e interacciones Heritage/, '// otro script')));
		assert.equal(withoutNavigation.status, 1);
		assert.match(withoutNavigation.output, /has no Heritage navigation script/);
		const unknownViewer = run(BUILD, writeManual('unknown-viewer.html', staged), '--viewer', 'other');
		assert.equal(unknownViewer.status, 1);
		assert.match(unknownViewer.output, /unknown viewer "other"/);
		assert.equal(run(BUILD).status, 2);
		assert.equal(run(BUILD, '--boilerplate', path.join(workspace, 'a.html'), '--example', path.join(workspace, 'b.html')).status, 2);
	});

	test('refreshes an outdated navigation script, also in a linear manual', () => {
		const outdated = linear.replace('var SHOW_AFTER_PX = 480;', 'var SHOW_AFTER_PX = 480; // old copy');
		assert.notEqual(outdated, linear);
		const before = checkManual('linear-outdated.html', outdated);
		assert.match(before.output, /warn {2}navigation: the script differs from assets\/boilerplate\/navigation\.js/);
		const file = writeManual('linear-refresh.html', outdated);
		assert.equal(run(BUILD, file).status, 0);
		assert.equal(fs.readFileSync(file, 'utf8'), linear);
		assert.doesNotMatch(checkManual('linear-refreshed.html', fs.readFileSync(file, 'utf8')).output, /navigation: the script differs/);
	});

	test('fills the language and document-link scripts from their marker lines and keeps them current', () => {
		const withMarkers = linear.replace('</body>', `<script>\n${LANGUAGE_MARKER}\n</script>\n<script>\n${DOCUMENT_LINKS_MARKER}\n</script>\n</body>`);
		const file = writeManual('marker-scripts.html', withMarkers);
		assert.equal(run(BUILD, file).status, 0);
		const filled = fs.readFileSync(file, 'utf8');
		assert.ok(filled.includes(fs.readFileSync(LANGUAGE_SCRIPT, 'utf8').trim()));
		assert.ok(filled.includes(fs.readFileSync(DOCUMENT_LINKS_SCRIPT, 'utf8').trim()));
		// A second refresh changes nothing, and a manual without those scripts does not get them.
		assert.equal(run(BUILD, file).status, 0);
		assert.equal(fs.readFileSync(file, 'utf8'), filled);
		assert.doesNotMatch(linear, new RegExp(LANGUAGE_MARKER));
	});

	test('warns when an embedded document-link script is outdated', () => {
		const link = '<a class="menu-back" href="https://docs.example.com/d/menu/view" data-document-link>Ir al menú</a>';
		const html = linear.replace('<body>\n', `<body>\n${link}\n`).replace('</body>', `<script>\n${fs.readFileSync(DOCUMENT_LINKS_SCRIPT, 'utf8').trim()} // old copy\n</script>\n</body>`);
		const result = checkManual('document-links-outdated.html', html);
		assert.match(result.output, /warn {2}document links: the script differs from assets\/boilerplate\/document-links\.js/);
	});

	test('writes the starting boilerplate with the base styles and the navigation script embedded', () => {
		const file = path.join(workspace, 'boilerplate.html');
		const result = run(BUILD, '--boilerplate', file);
		assert.equal(result.status, 0, result.output);
		const html = fs.readFileSync(file, 'utf8');
		assert.ok(html.includes(fs.readFileSync(NAVIGATION_SCRIPT, 'utf8').trim()));
		assert.match(html, /<style>\n\/\* Heritage Spec: estilos base[\s\S]*:root\{/);
		assert.doesNotMatch(html, /heritage:base-style|heritage:navigation-script/);
		// Refreshing the starting document changes nothing: it already is current.
		assert.equal(run(BUILD, file).status, 0);
		assert.equal(fs.readFileSync(file, 'utf8'), html);
	});
});
