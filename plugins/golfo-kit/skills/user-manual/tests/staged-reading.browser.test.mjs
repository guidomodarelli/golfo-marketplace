/**
 * Staged reading and viewer links in a real browser (DESIGN.md, "Lectura por etapas" and "Copiar enlace a
 * una sección"), on the example manual built from the template and the DESIGN.md boilerplate.
 *
 * Needs Playwright with a Chromium build. Resolution order: PLAYWRIGHT_MODULE (path or package name), then
 * the packages playwright and playwright-core. PLAYWRIGHT_CHROMIUM_EXECUTABLE points to a Chromium binary
 * when the one bundled with that Playwright version is not installed. Without Playwright the suite is skipped
 * and says so. The local viewer does not certify a published viewer: that check is manual.
 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { after, before, describe, test } from 'node:test';
import { CHECK_RENDERED_PATH, DOCUMENT_ID, PUBLIC_VIEW_URL, startManualServers } from './support/manual-server.mjs';

const require = createRequire(import.meta.url);
const PLAYWRIGHT_CANDIDATES = [process.env.PLAYWRIGHT_MODULE, 'playwright', 'playwright-core'].filter(Boolean);
const DESKTOP = { width: 1280, height: 900 };
const PHONE = { width: 390, height: 844 };
const STAGE_SECTIONS = {
	orientation: ['purpose', 'audience', 'permissions'],
	workflow: ['access', 'happy-path', 'practice', 'unhappy-paths'],
	reference: ['limits', 'faq', 'glossary'],
};
const ALL_SECTIONS = Object.values(STAGE_SECTIONS).flat();
const RESPONSIVE_WIDTHS = [390, 740, 819, 820, 1048, 1280, 1600];
const DESKTOP_MENU_MIN_WIDTH = 820;
const STEP_TIMEOUT_MS = 10000;
const SUITE_TIMEOUT_MS = 600000;

const loadPlaywright = () => {
	for (const candidate of PLAYWRIGHT_CANDIDATES) {
		try { return require(candidate); } catch (moduleError) { /* next candidate */ }
	}
	return null;
};
const playwright = loadPlaywright();
const skipReason = playwright ? false : `Playwright not found (tried ${PLAYWRIGHT_CANDIDATES.join(', ')}); set PLAYWRIGHT_MODULE to run the staged reading browser tests`;

describe('staged reading in a real browser', { skip: skipReason, timeout: SUITE_TIMEOUT_MS }, () => {
	let browser;
	let servers;

	before(async () => {
		const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined;
		browser = await playwright.chromium.launch({ executablePath });
		servers = await startManualServers();
	});
	after(async () => {
		await browser?.close();
		await servers?.close();
	});

	const openPage = async (pathname, { viewport = DESKTOP, reducedMotion = 'no-preference', origin = servers.origin } = {}) => {
		const context = await browser.newContext({ viewport, reducedMotion });
		await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: servers.origin });
		await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: servers.foreignOrigin });
		const page = await context.newPage();
		const warnings = [];
		page.on('console', (message) => { if (message.type() === 'warning') warnings.push(message.text()); });
		page.on('pageerror', (error) => warnings.push(`pageerror: ${error.message}`));
		await page.goto(`${origin}${pathname}`);
		return { page, context, warnings };
	};
	const manualFrame = async (page) => {
		const frame = page.frames().find((candidate) => candidate !== page.mainFrame());
		await frame.waitForFunction(() => window.HeritageViewer && window.HeritageNavigation, null, { timeout: STEP_TIMEOUT_MS });
		return frame;
	};
	const stageState = (target) => target.evaluate(() => window.HeritageStages.state());
	const shownSections = (target) => target.evaluate(() => [...document.querySelectorAll('section.section')].filter((section) => section.getClientRects().length).map((section) => section.getAttribute('aria-labelledby')));
	// The destination has focus and is in view, under any sticky bar (the last sections cannot reach the top).
	const waitForLanding = (target, id) => target.waitForFunction((targetId) => {
		const element = document.getElementById(targetId);
		if (!element || document.activeElement !== element) return false;
		const box = element.getBoundingClientRect();
		const bar = document.querySelector('.stage-bar');
		const barBottom = bar && bar.getClientRects().length ? bar.getBoundingClientRect().bottom : 0;
		return box.top >= barBottom && box.bottom <= window.innerHeight;
	}, id, { timeout: STEP_TIMEOUT_MS });
	const runRenderedChecks = async (target) => {
		await target.addScriptTag({ path: CHECK_RENDERED_PATH });
		return target.evaluate(() => window.__umCheckRendered());
	};

	test('shows one stage with its orientation, reading estimate and recap', async () => {
		const { page, context, warnings } = await openPage('/manual.html');
		assert.deepEqual(await stageState(page), { mode: 'stage', stage: 'orientation', stages: Object.keys(STAGE_SECTIONS) });
		assert.deepEqual(await shownSections(page), STAGE_SECTIONS.orientation);
		const reading = await page.locator('#stage-orientation .stage-reading').textContent();
		assert.match(reading, /^Lectura estimada: [1-9]\d* min \(referencia de 200 palabras por minuto; no incluye ejercicios ni simuladores\)\.$/);
		assert.equal(await page.locator('[data-stage-recap="orientation"] .stage-concepts > li').count(), 3);
		assert.equal(await page.locator('[data-stage-recap="workflow"]').isVisible(), false);
		assert.equal(await page.locator('.stage-menu').isVisible(), true);
		assert.equal(await page.locator('.stage-bar').isVisible(), false);
		assert.deepEqual(warnings, []);
		await context.close();
	});

	test('the menu lists the chapters and sections of the active stage and jumps to them', async () => {
		const { page, context } = await openPage('/manual.html');
		assert.equal(await page.locator('#stage-outline-orientation').isVisible(), true);
		assert.equal(await page.locator('#stage-outline-workflow').isVisible(), false);
		await page.locator('.stage-menu .stage-option', { hasText: 'Usar el flujo' }).click();
		const outline = page.locator('#stage-outline-workflow');
		assert.deepEqual(await outline.locator('.stage-outline-chapter > .stage-outline-link').allTextContents(), ['Crear una solicitud', 'Practicar y resolver errores']);
		assert.deepEqual(await outline.locator('.stage-outline-sections a').evaluateAll((links) => links.map((link) => link.getAttribute('href').slice(1))), STAGE_SECTIONS.workflow);
		await outline.locator('a[href="#unhappy-paths"]').click();
		await waitForLanding(page, 'unhappy-paths');
		assert.equal(new URL(page.url()).hash, '#unhappy-paths');
		await outline.locator('a[href="#chapter-practice-and-errors"]').click();
		await waitForLanding(page, 'chapter-practice-and-errors');
		await context.close();
	});

	test('chapters: reading estimate, grouped index sheet and deep links', async () => {
		const { page, context } = await openPage('/manual.html#chapter-create', { viewport: PHONE });
		await waitForLanding(page, 'chapter-create');
		assert.equal((await stageState(page)).stage, 'workflow');
		assert.deepEqual(await page.evaluate(() => window.HeritageStages.chaptersOf('workflow')), [
			{ id: 'create', sections: ['access', 'happy-path'] },
			{ id: 'practice-and-errors', sections: ['practice', 'unhappy-paths'] },
		]);
		assert.match(await page.locator('#chapter-create .stage-chapter-reading').textContent(), /^Lectura estimada del capítulo: [1-9]\d* min\.$/);
		await page.locator('.section-pill').click();
		const groups = await page.locator('#toc-sheet .stage-sheet-group .toc-label').allTextContents();
		assert.deepEqual(groups, ['Etapa 1 · Antes de empezar', 'Etapa 2 · Usar el flujo', 'Crear una solicitud', 'Practicar y resolver errores', 'Etapa 3 · Resolver y consultar']);
		// Every section is still listed once, in order, between the group labels.
		const indexed = await page.locator('#toc-sheet a').evaluateAll((links) => links.map((link) => link.getAttribute('href').slice(1)));
		assert.deepEqual(indexed.filter((id) => ALL_SECTIONS.includes(id)), ALL_SECTIONS);
		await context.close();
	});

	test('recap: position, reading progress and previous / next stage', async () => {
		const { page, context } = await openPage('/manual.html');
		const recap = page.locator('[data-stage-recap="orientation"]');
		assert.match(await recap.locator('.stage-recap-meta').textContent(), /^Etapa 1 de 3 · [1-9]\d* min$/);
		assert.equal(await recap.locator('.stage-pager-previous').count(), 0);
		assert.equal(await page.locator('.stage-menu .stage-option[data-read]').count(), 0);
		await recap.scrollIntoViewIfNeeded();
		await page.waitForFunction(() => window.HeritageStages.progress().includes('orientation'), null, { timeout: STEP_TIMEOUT_MS });
		const orientationOption = page.locator('.stage-menu .stage-option', { hasText: 'Antes de empezar' });
		assert.equal(await orientationOption.locator('.stage-option-status').textContent(), 'leída');
		assert.equal(await orientationOption.locator('.stage-option-status').isVisible(), true);
		await recap.locator('.stage-pager-next').click();
		await waitForLanding(page, 'stage-workflow');
		assert.equal((await stageState(page)).stage, 'workflow');
		await page.locator('[data-stage-recap="workflow"] .stage-pager-previous').click();
		await waitForLanding(page, 'stage-orientation');
		assert.equal(await page.locator('[data-stage-recap="reference"] .stage-pager-next').count(), 0);
		await context.close();
	});

	test('Alt+I opens the index sheet when there is no top index', async () => {
		const { page, context } = await openPage('/manual.html');
		await page.locator('body').click({ position: { x: 5, y: 5 } });
		await page.keyboard.press('Alt+KeyI');
		await page.locator('#toc-sheet').waitFor({ state: 'visible' });
		await context.close();
	});

	test('the compact stage bar stays below the fixed language switch', async () => {
		const { page, context } = await openPage('/manual.html', { viewport: PHONE });
		await page.evaluate(() => {
			const languageSwitch = document.createElement('div');
			languageSwitch.className = 'lang-switch';
			languageSwitch.innerHTML = '<button type="button" data-lang="es">ES</button><button type="button" data-lang="pt">PT</button>';
			document.body.prepend(languageSwitch);
			window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'instant' });
		});
		const layout = await page.evaluate(() => {
			const switchBox = document.querySelector('.lang-switch').getBoundingClientRect();
			const barBox = document.querySelector('.stage-bar').getBoundingClientRect();
			const center = document.elementFromPoint(switchBox.left + switchBox.width / 2, switchBox.top + switchBox.height / 2);
			return { barTop: barBox.top, switchBottom: switchBox.bottom, switchReachable: Boolean(center && center.closest('.lang-switch')) };
		});
		assert.ok(layout.barTop >= layout.switchBottom, JSON.stringify(layout));
		assert.equal(layout.switchReachable, true);
		await context.close();
	});

	test('the index reaches a section of a hidden stage and shows the full current title', async () => {
		const { page, context } = await openPage('/manual.html#practice', { viewport: PHONE });
		await waitForLanding(page, 'practice');
		await page.locator('.section-pill').click();
		const sheet = page.locator('#toc-sheet');
		await sheet.waitFor({ state: 'visible' });
		const current = page.locator('.toc-sheet-current');
		assert.equal(await current.textContent(), 'Sección actual · 06 · Práctica guiada con un simulador de solicitudes pendientes de revisión');
		assert.equal(await current.evaluate((element) => element.scrollWidth <= element.clientWidth && element.getBoundingClientRect().top >= 0), true);
		assert.equal(await sheet.locator('a[aria-current="location"]').count(), 1);
		// The sheet is the complete index: hidden stages included.
		const indexed = await sheet.locator('a').evaluateAll((links) => links.map((link) => link.getAttribute('href').slice(1)));
		assert.deepEqual(indexed.filter((id) => ALL_SECTIONS.includes(id)), ALL_SECTIONS);
		await sheet.locator('a[href="#faq"]').click();
		await waitForLanding(page, 'faq');
		assert.equal((await stageState(page)).stage, 'reference');
		assert.equal(new URL(page.url()).hash, '#faq');
		await context.close();
	});

	test('direct links, reload and history reveal the stage of their destination', async () => {
		const { page, context } = await openPage('/manual.html#limits');
		await waitForLanding(page, 'limits');
		assert.equal((await stageState(page)).stage, 'reference');
		await page.reload();
		await waitForLanding(page, 'limits');
		await page.goto(`${servers.origin}/manual.html#purpose`);
		await waitForLanding(page, 'purpose');
		await page.locator('#purpose ~ p a[href="#faq"]').click();
		await waitForLanding(page, 'faq');
		assert.equal((await stageState(page)).stage, 'reference');
		await page.goBack();
		await waitForLanding(page, 'purpose');
		assert.equal((await stageState(page)).stage, 'orientation');
		await page.goForward();
		await waitForLanding(page, 'faq');
		await context.close();
	});

	test('changing stages and «Ver todo» keep nodes, listeners and simulator state', async () => {
		const { page, context } = await openPage('/manual.html');
		const originalIds = await page.evaluate(() => [...document.querySelectorAll('section.section')].map((section) => section.id || section.getAttribute('aria-labelledby')));
		await page.locator('.stage-menu .stage-option', { hasText: 'Usar el flujo' }).click();
		await waitForLanding(page, 'stage-workflow');
		assert.equal(new URL(page.url()).hash, '#access');
		await page.evaluate(() => { window.simulatorNode = document.getElementById('request-simulator'); });
		const send = page.locator('.simulator-send');
		await send.click();
		await send.click();
		await page.locator('.stage-menu .stage-option', { hasText: 'Antes de empezar' }).click();
		assert.deepEqual(await shownSections(page), STAGE_SECTIONS.orientation);
		await page.locator('.stage-menu .stage-option-all').click();
		assert.deepEqual(await shownSections(page), ALL_SECTIONS);
		assert.equal(await page.locator('.stage-option-all').getAttribute('aria-pressed'), 'true');
		assert.equal(await page.evaluate(() => document.getElementById('request-simulator') === window.simulatorNode), true);
		assert.equal(await page.locator('.simulator-count').textContent(), '2');
		await send.click();
		assert.equal(await page.locator('.simulator-count').textContent(), '3');
		const finalIds = await page.evaluate(() => [...document.querySelectorAll('section.section')].map((section) => section.id || section.getAttribute('aria-labelledby')));
		assert.deepEqual(finalIds, originalIds);
		// Every rail mark is back once every section shows.
		assert.equal(await page.locator('.section-rail li[hidden]').count(), 0);
		await context.close();
	});

	test('keyboard: the stage menu works with Tab and Enter, Alt+arrows stay in the shown stage', async () => {
		const { page, context } = await openPage('/manual.html');
		let focusedTitle = '';
		for (let attempt = 0; attempt < 80 && !focusedTitle.includes('Usar el flujo'); attempt += 1) {
			await page.keyboard.press('Tab');
			focusedTitle = await page.evaluate(() => (document.activeElement.matches('.stage-option') ? document.activeElement.textContent : ''));
		}
		assert.match(focusedTitle, /Usar el flujo/);
		await page.keyboard.press('Enter');
		await waitForLanding(page, 'stage-workflow');
		const visited = [];
		for (let step = 0; step < STAGE_SECTIONS.workflow.length + 2; step += 1) {
			await page.keyboard.press('Alt+ArrowDown');
			await page.waitForTimeout(1200);
			visited.push(await page.evaluate(() => document.activeElement.id));
		}
		assert.ok(visited.every((id) => STAGE_SECTIONS.workflow.includes(id)), `Alt+↓ left the stage: ${visited.join(', ')}`);
		assert.equal((await stageState(page)).stage, 'workflow');
		await context.close();
	});

	test('phone sidebar: modal focus, Escape, tap outside, choosing a stage and crossing the breakpoint', async () => {
		const { page, context } = await openPage('/manual.html', { viewport: PHONE });
		const toggle = page.locator('.stage-bar-toggle');
		const drawer = page.locator('#stage-drawer');
		const scrollLocked = () => page.evaluate(() => document.documentElement.classList.contains('has-open-stage-drawer'));
		const focusInDrawer = () => page.evaluate(() => document.getElementById('stage-drawer').contains(document.activeElement));
		assert.equal(await page.locator('.stage-menu').isVisible(), false);
		await toggle.click();
		await drawer.waitFor({ state: 'visible' });
		assert.equal(await scrollLocked(), true);
		assert.equal(await toggle.getAttribute('aria-expanded'), 'true');
		for (let step = 0; step < 8; step += 1) {
			await page.keyboard.press('Tab');
			assert.equal(await focusInDrawer(), true, 'focus left the modal sidebar');
		}
		await drawer.evaluate((element) => Promise.all(element.getAnimations().map((animation) => animation.finished)));
		const drawerBox = await drawer.boundingBox();
		assert.ok(Math.abs(drawerBox.x + drawerBox.width - PHONE.width) <= 1 && drawerBox.width <= 340, 'the sidebar opens from the right');
		await page.keyboard.press('Escape');
		await drawer.waitFor({ state: 'hidden' });
		assert.equal(await page.evaluate(() => document.activeElement.classList.contains('stage-bar-toggle')), true);
		assert.equal(await scrollLocked(), false);

		await toggle.click();
		await drawer.waitFor({ state: 'visible' });
		await page.mouse.click(10, PHONE.height / 2);
		await drawer.waitFor({ state: 'hidden' });
		assert.equal(await page.evaluate(() => document.activeElement.classList.contains('stage-bar-toggle')), true);

		await toggle.click();
		await drawer.locator('.stage-option', { hasText: 'Resolver y consultar' }).click();
		await drawer.waitFor({ state: 'hidden' });
		await waitForLanding(page, 'stage-reference');
		assert.match(await page.locator('.stage-bar-status').textContent(), /^Etapa 3\/3 · Resolver y consultar$/);

		await toggle.click();
		await drawer.waitFor({ state: 'visible' });
		await page.evaluate(() => { window.controlsNode = document.querySelector('.stage-controls'); });
		await page.setViewportSize(DESKTOP);
		await drawer.waitFor({ state: 'hidden' });
		assert.equal(await scrollLocked(), false);
		assert.equal(await page.evaluate(() => document.querySelector('.stage-menu .stage-controls') === window.controlsNode), true);
		assert.equal(await page.locator('[id="stage-drawer"]').count(), 1);
		await context.close();
	});

	test('the sidebar slides in, and does not with reduced motion', async () => {
		for (const [reducedMotion, animated] of [['no-preference', true], ['reduce', false]]) {
			const { page, context } = await openPage('/manual.html', { viewport: PHONE, reducedMotion });
			await page.locator('.stage-bar-toggle').click();
			const animations = await page.locator('#stage-drawer').evaluate((drawer) => drawer.getAnimations().length);
			assert.equal(animations > 0, animated, `reducedMotion=${reducedMotion}`);
			await context.close();
		}
	});

	test('rendered checks pass at every width: layout, print state and its restoration', async () => {
		for (const width of RESPONSIVE_WIDTHS) {
			const { page, context } = await openPage('/manual.html#happy-path', { viewport: { width, height: 900 } });
			await waitForLanding(page, 'happy-path');
			const result = await runRenderedChecks(page);
			assert.deepEqual(result.stages, [], `width ${width}: ${JSON.stringify(result.stages)}`);
			assert.equal(result.ok, true, `width ${width}`);
			assert.equal(await page.locator('.stage-menu').isVisible(), width >= DESKTOP_MENU_MIN_WIDTH, `menu at ${width}`);
			assert.equal(await page.locator('.stage-bar').isVisible(), width < DESKTOP_MENU_MIN_WIDTH, `bar at ${width}`);
			assert.equal((await stageState(page)).stage, 'workflow');
			await context.close();
		}
	});

	test('rendered checks report a stage menu over the content', async () => {
		const { page, context } = await openPage('/manual.html');
		await page.addStyleTag({ content: 'html.has-stages body{padding-right:24px;}' });
		const result = await runRenderedChecks(page);
		assert.equal(result.ok, false);
		assert.ok(result.stages.includes('the stage menu overlaps the content'), JSON.stringify(result.stages));
		await context.close();
	});

	test('print media shows every stage without the stage navigation', async () => {
		const { page, context } = await openPage('/manual.html');
		await page.emulateMedia({ media: 'print' });
		assert.deepEqual(await shownSections(page), ALL_SECTIONS);
		assert.equal(await page.locator('.stage-menu').isVisible(), false);
		await page.emulateMedia({ media: 'screen' });
		assert.deepEqual(await shownSections(page), STAGE_SECTIONS.orientation);
		await context.close();
	});

	test('the linear variant keeps its top index and navigation', async () => {
		const { page, context } = await openPage('/linear.html');
		assert.equal(await page.locator('.stage-menu, .stage-bar').count(), 0);
		await page.locator('nav.toc a[href="#faq"]').click();
		await waitForLanding(page, 'faq');
		assert.equal(new URL(page.url()).hash, '#faq');
		assert.deepEqual(await shownSections(page), ALL_SECTIONS);
		assert.equal(await page.locator('.section-rail li[hidden]').count(), 0);
		await page.locator('.section-pill').click();
		assert.equal(await page.locator('.toc-sheet-current').textContent(), 'Sección actual · 09 · Preguntas frecuentes');
		assert.equal(await page.locator('#toc-sheet a[aria-current="location"]').count(), 1);
		await context.close();
	});

	test('document viewer adapter, same origin and same document: public URL, copy and viewer history', async () => {
		const { page, context } = await openPage(`/d/${DOCUMENT_ID}/view?href=faq`);
		const frame = await manualFrame(page);
		await waitForLanding(frame, 'faq');
		assert.equal(await frame.evaluate(() => window.HeritageViewer.reason), 'synchronized');
		assert.equal((await stageState(frame)).stage, 'reference');
		await frame.locator('section[aria-labelledby="limits"] .section-link').click();
		await frame.locator('section[aria-labelledby="limits"] .section-link', { hasText: 'Enlace copiado' }).waitFor();
		// Synchronized, the public URL is the one the reader sees in the viewer.
		assert.equal(await page.evaluate(() => navigator.clipboard.readText()), `${servers.origin}/d/${DOCUMENT_ID}/view?href=limits`);
		assert.equal(new URL(page.url()).search, '?href=limits');
		// Viewer history (Back/Forward on the public URL) moves the manual, revealing the stage.
		await page.evaluate(() => {
			history.pushState(null, '', '?href=permissions');
			history.pushState(null, '', '?href=glossary');
		});
		await page.goBack();
		await waitForLanding(frame, 'permissions');
		assert.equal((await stageState(frame)).stage, 'orientation');
		await context.close();
	});

	test('document viewer adapter keeps old viewer hash links working', async () => {
		const { page, context } = await openPage(`/d/${DOCUMENT_ID}/view#faq`);
		const frame = await manualFrame(page);
		await waitForLanding(frame, 'faq');
		assert.equal((await stageState(frame)).stage, 'reference');
		await context.close();
	});

	for (const { name, pathname, origin, reason } of [
		{ name: 'another document', pathname: '/d/doc-2/view', reason: 'different-document' },
		{ name: 'an unrecognized host', pathname: '/other/view', reason: 'unrecognized-host' },
		{ name: 'another origin', pathname: `/d/${DOCUMENT_ID}/view`, origin: 'foreign', reason: 'cross-origin' },
	]) {
		test(`document viewer adapter in ${name}: local navigation only, viewer URL untouched`, async () => {
			const { page, context, warnings } = await openPage(pathname, { origin: origin === 'foreign' ? servers.foreignOrigin : servers.origin });
			const viewerUrl = page.url();
			const frame = await manualFrame(page);
			assert.equal(await frame.evaluate(() => window.HeritageViewer.reason), reason);
			await frame.locator('section[aria-labelledby="purpose"] .section-link').click();
			await frame.locator('section[aria-labelledby="purpose"] .section-link.is-copied').waitFor();
			assert.equal(page.url(), viewerUrl);
			assert.equal(new URL(frame.url()).hash, '#purpose');
			// Without a verified viewer, the public link comes from the declared share URL, in the viewer format.
			assert.equal(await page.evaluate(() => navigator.clipboard.readText()), `${PUBLIC_VIEW_URL}?href=purpose`);
			assert.ok(warnings.some((warning) => warning.includes('Heritage:documentViewer') && warning.includes(reason)), 'the limitation is declared');
			await frame.locator('.section-pill').click();
			await frame.locator('#toc-sheet a[href="#glossary"]').click();
			await waitForLanding(frame, 'glossary');
			assert.equal(page.url(), viewerUrl);
			await context.close();
		});
	}
});
