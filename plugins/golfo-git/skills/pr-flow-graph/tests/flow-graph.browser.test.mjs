/**
 * The rendered page in a real browser: the graph is drawn, the filters change what is visible and
 * selecting an element shows its evidence.
 *
 * Needs Playwright with a Chromium build (playwright-core is a devDependency; CI installs Chromium
 * with `pnpm exec playwright-core install --with-deps chromium`). PLAYWRIGHT_MODULE overrides the
 * package to load. Without Playwright the suite is skipped locally and fails in CI. The page gets
 * the real ELK bundle from the elkjs devDependency, embedded the way `--inline-libraries` does, so
 * the suite does not need network.
 */
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { after, before, describe, test } from 'node:test';
import { pathToFileURL } from 'node:url';

import { checkLeanModel } from '../scripts/lib/check-lean-model.mjs';
import { BROWSER_LIBRARIES } from '../scripts/lib/flow-graph-constants.mjs';
import { renderFlowGraphHtml } from '../scripts/lib/render-html.mjs';
import { FIXTURES_DIRECTORY, loadExampleModel, loadExampleRfcModel } from './support/example-model.mjs';

const require = createRequire(import.meta.url);
const PLAYWRIGHT_CANDIDATES = [process.env.PLAYWRIGHT_MODULE, 'playwright', 'playwright-core'].filter(Boolean);
const DESKTOP_VIEWPORT = { width: 1280, height: 800 };
const SUITE_TIMEOUT_MS = 120_000;
const LEAN_SOURCE = 'theorem ok : True := trivial\n';

const loadPlaywright = () => {
  for (const candidate of PLAYWRIGHT_CANDIDATES) {
    try {
      return require(candidate);
    } catch (moduleError) {
      // Try the next candidate.
    }
  }
  return null;
};
const playwright = loadPlaywright();
const missingPlaywright = `Playwright not found (tried ${PLAYWRIGHT_CANDIDATES.join(', ')}); run pnpm install or set PLAYWRIGHT_MODULE`;
// In CI the browser suite is mandatory: a silent skip would hide a page that no longer draws.
if (!playwright && process.env.CI) throw new Error(`flow-graph.browser.test.mjs: ${missingPlaywright}`);

describe('rendered page in a real browser', { skip: playwright ? false : missingPlaywright, timeout: SUITE_TIMEOUT_MS }, () => {
  let browser;
  let workDirectory;
  let pageUrl;
  let rfcPageUrl;
  let offlinePageUrl;

  const openPage = async (url, contextOptions = {}) => {
    // Reduced motion by default: positions are read right after an action, without waiting for a glide.
    const context = await browser.newContext({ viewport: DESKTOP_VIEWPORT, reducedMotion: 'reduce', ...contextOptions });
    const page = await context.newPage();
    const problems = [];
    page.on('pageerror', (pageError) => problems.push(String(pageError)));
    page.on('console', (message) => {
      if (message.type() === 'error') problems.push(message.text());
    });
    await page.goto(url);
    return { page, problems };
  };
  const nodeLabels = (page) => page.locator('#graph .graph-node .node-label').allTextContents();
  const waitForNodeCount = (page, count) => page.waitForFunction(
    (expected) => document.querySelectorAll('#graph .graph-node').length === expected,
    count,
  );

  before(async () => {
    workDirectory = mkdtempSync(path.join(tmpdir(), 'pr-flow-graph-browser-'));
    const elkLibrary = BROWSER_LIBRARIES.find((library) => library.name === 'elkjs');
    const inlinedLibraries = new Map([[elkLibrary.url, readFileSync(require.resolve('elkjs/lib/elk.bundled.js'), 'utf8')]]);
    const leanPath = path.join(workDirectory, 'FlowModel.lean');
    writeFileSync(leanPath, LEAN_SOURCE);
    const leanCheck = checkLeanModel(leanPath, { command: process.execPath, commandArguments: [path.join(FIXTURES_DIRECTORY, 'fake-lean.mjs')] });

    const pagePath = path.join(workDirectory, 'graph.html');
    writeFileSync(pagePath, renderFlowGraphHtml(loadExampleModel(), { inlinedLibraries, leanSource: leanCheck.source }));
    pageUrl = pathToFileURL(pagePath).href;

    const rfcPagePath = path.join(workDirectory, 'rfc-graph.html');
    writeFileSync(rfcPagePath, renderFlowGraphHtml(loadExampleRfcModel(), { inlinedLibraries }));
    rfcPageUrl = pathToFileURL(rfcPagePath).href;

    const offlinePagePath = path.join(workDirectory, 'offline.html');
    writeFileSync(offlinePagePath, renderFlowGraphHtml(loadExampleModel()));
    offlinePageUrl = pathToFileURL(offlinePagePath).href;

    browser = await playwright.chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined });
  });

  after(async () => {
    await browser?.close();
    rmSync(workDirectory, { recursive: true, force: true });
  });

  test('draws every node, group and relationship of the change flow without page errors', async () => {
    const { page, problems } = await openPage(pageUrl);
    await waitForNodeCount(page, 7);

    assert.equal(await page.locator('#graph .graph-edge').count(), 7);
    assert.deepEqual(await page.locator('#graph .graph-group text').allTextContents(), ['UI', 'Flux', 'Datos']);
    assert.equal(await page.locator('#graph .graph-node.added').count(), 3);
    assert.equal(await page.locator('#graph .graph-node.removed').count(), 1);
    assert.equal(await page.locator('#graph .graph-edge.inferred').count(), 1);
    assert.deepEqual(problems, []);
  });

  test('keeps every node inside the viewport and apart from the others', async () => {
    const { page } = await openPage(pageUrl);
    await waitForNodeCount(page, 7);

    const { canvas, boxes } = await page.evaluate(() => ({
      canvas: document.getElementById('graph').getBoundingClientRect().toJSON(),
      boxes: [...document.querySelectorAll('#graph .graph-node rect')].map((rectangle) => rectangle.getBoundingClientRect().toJSON()),
    }));

    for (const box of boxes) {
      assert.ok(box.left >= canvas.left && box.right <= canvas.right && box.top >= canvas.top && box.bottom <= canvas.bottom, 'node outside the canvas');
    }
    for (const [index, first] of boxes.entries()) {
      for (const second of boxes.slice(index + 1)) {
        const overlaps = first.left < second.right && second.left < first.right && first.top < second.bottom && second.top < first.bottom;
        assert.equal(overlaps, false, 'two nodes overlap');
      }
    }
  });

  test('"Antes" hides what the pull request added and "Después" hides what it removed', async () => {
    const { page } = await openPage(pageUrl);
    await waitForNodeCount(page, 7);

    await page.getByRole('button', { name: 'Antes' }).click();
    await waitForNodeCount(page, 4);
    const labelsBefore = await nodeLabels(page);
    await page.getByRole('button', { name: 'Después' }).click();
    await waitForNodeCount(page, 6);
    const labelsAfter = await nodeLabels(page);

    assert.ok(labelsBefore.includes('WishlistClient') && !labelsBefore.includes('FavoritesStore'));
    assert.ok(labelsAfter.includes('FavoritesStore') && !labelsAfter.includes('WishlistClient'));
    assert.equal(await page.locator('#graph .graph-node.added').count(), 0, 'a single version of the code is shown without highlights');
  });

  test('the toggle that hides what the pull request did not touch says how much it hides, and keeps direct neighbours', async () => {
    const model = loadExampleModel();
    model.nodes.push(
      { id: 'analytics-tracker', label: 'AnalyticsTracker', kind: 'service', change: 'unchanged' },
      { id: 'analytics-api', label: 'POST /events', kind: 'external', change: 'unchanged' },
    );
    model.edges.push({
      id: 'tracker-requests-api', source: 'analytics-tracker', target: 'analytics-api', kind: 'requests', change: 'unchanged',
      confidence: 'verified', evidence: [{ path: 'app/src/main/java/shop/analytics/AnalyticsTracker.kt', line: 30 }],
    });
    const elkLibrary = BROWSER_LIBRARIES.find((library) => library.name === 'elkjs');
    const inlinedLibraries = new Map([[elkLibrary.url, readFileSync(require.resolve('elkjs/lib/elk.bundled.js'), 'utf8')]]);
    const pagePath = path.join(workDirectory, 'with-unrelated.html');
    writeFileSync(pagePath, renderFlowGraphHtml(model, { inlinedLibraries }));
    const { page } = await openPage(pathToFileURL(pagePath).href);
    await waitForNodeCount(page, 9);

    // Two unrelated nodes and the relationship between them.
    await page.getByLabel('Ocultar lo que el PR no tocó (3)').check();
    await waitForNodeCount(page, 7);

    const labels = await nodeLabels(page);
    assert.ok(!labels.includes('AnalyticsTracker') && !labels.includes('POST /events'));
    assert.ok(labels.includes('Dispatcher'), 'an unchanged neighbour of a changed relationship stays');
  });

  test('selecting a node shows its evidence linked to the pull request diff', async () => {
    const { page } = await openPage(pageUrl);
    await waitForNodeCount(page, 7);

    await page.locator('#graph .graph-node', { hasText: 'FavoritesStore' }).click();

    const detail = page.locator('#detail');
    await detail.getByRole('heading', { name: 'FavoritesStore' }).waitFor();
    const evidenceLink = detail.getByRole('link', { name: 'app/src/main/java/shop/favorites/FavoritesStore.kt:21' });
    assert.match(await evidenceLink.getAttribute('href'), /\/pull\/128\/files#diff-[0-9a-f]{64}R21$/);
    assert.equal(await page.locator('#graph .graph-node.selected').count(), 1);
  });

  test('an RFC graph speaks of today and of the RFC, and points the proposal at the RFC lines', async () => {
    const { page, problems } = await openPage(rfcPageUrl);
    await waitForNodeCount(page, 4);

    assert.equal(await page.title(), 'Flujo del RFC — RFC 0042: Cancelar un pedido antes del envío');
    assert.equal(await page.locator('#eyebrow').textContent(), 'Flujo propuesto en un RFC');
    assert.match(await page.locator('#subtitle').textContent(), /RFC docs\/rfcs\/0042-cancel-order\.md sobre el código de main/);

    // "Hoy" is the code as it is: what the RFC adds is not there yet.
    await page.getByRole('button', { name: 'Hoy' }).click();
    await waitForNodeCount(page, 3);
    assert.ok(!(await nodeLabels(page)).includes('cancelOrder'));
    await page.getByRole('button', { name: 'Con el RFC' }).click();
    await waitForNodeCount(page, 4);

    await page.locator('#graph .graph-node', { hasText: 'cancelOrder' }).click();
    const detail = page.locator('#detail');
    await detail.getByRole('heading', { name: 'cancelOrder' }).waitFor();
    const evidenceItem = detail.locator('.evidence li');
    assert.equal(await evidenceItem.count(), 1);
    assert.equal(await evidenceItem.textContent(), 'docs/rfcs/0042-cancel-order.md:11en el RFC');
    assert.equal(await evidenceItem.getByRole('link').count(), 0, 'an RFC has no diff to link to');

    await page.getByRole('button', { name: 'orderRoutes → cancelOrder: POST /orders/:id/cancel' }).click();
    await detail.getByText('Verificada en el RFC', { exact: true }).waitFor();
    assert.deepEqual(problems, []);
  });

  test('selecting an inferred relationship from the list with the keyboard explains why it is inferred', async () => {
    const { page } = await openPage(pageUrl);
    await waitForNodeCount(page, 7);

    await page.getByRole('button', { name: 'Dispatcher → FavoritesStore: actualiza' }).focus();
    await page.keyboard.press('Enter');

    const detail = page.locator('#detail');
    await detail.getByText('Inferida', { exact: true }).waitFor();
    assert.match(await detail.textContent(), /inyección de dependencias/);
    assert.equal(await page.locator('#graph .graph-edge.selected').count(), 1);
  });

  test('the business view draws states and transitions with their triggers', async () => {
    const { page } = await openPage(pageUrl);
    await waitForNodeCount(page, 7);

    await page.getByRole('tab', { name: 'Flujo de negocio' }).click();
    await waitForNodeCount(page, 4);

    assert.deepEqual((await nodeLabels(page)).sort(), ['Es favorito', 'Guardando', 'No es favorito', 'No se pudo guardar']);
    assert.ok((await page.locator('#graph .graph-edge text').allTextContents()).includes('La API falla [sin red o 5xx]'));
  });

  test('the formal model tab shows the Lean source that passed the gate', async () => {
    const { page } = await openPage(pageUrl);
    await waitForNodeCount(page, 7);

    await page.getByRole('tab', { name: 'Modelo formal' }).click();

    assert.equal(await page.locator('#formal-model pre').textContent(), LEAN_SOURCE);
    assert.equal(await page.locator('#graph').isVisible(), false);
  });

  test('without the Lean model there is no formal model tab', async () => {
    const { page } = await openPage(offlinePageUrl, { offline: true });

    assert.deepEqual(await page.getByRole('tab').allTextContents(), ['Flujo de cambios', 'Flujo de negocio']);
  });

  test('when the library cannot be loaded the page says so and still lists the flow', async () => {
    const { page } = await openPage(offlinePageUrl, { offline: true });

    await page.locator('#canvas-message').getByText('No se pudo cargar la librería').waitFor();

    assert.equal(await page.locator('#element-list button').count(), 14);
    await page.getByRole('button', { name: 'FavoritesRepository', exact: true }).click();
    await page.locator('#detail').getByRole('heading', { name: 'FavoritesRepository' }).waitFor();
  });

  describe('movable canvas', () => {
    const POSITION_TOLERANCE_PX = 1;
    const nodeBox = (page, label) => page.locator('#graph .graph-node', { hasText: label }).locator('rect').evaluate((rectangle) => rectangle.getBoundingClientRect().toJSON());
    const centerOf = (box) => ({ x: box.left + box.width / 2, y: box.top + box.height / 2 });
    const assertSamePoint = (actual, expected, message) => {
      assert.ok(Math.abs(actual.x - expected.x) <= POSITION_TOLERANCE_PX && Math.abs(actual.y - expected.y) <= POSITION_TOLERANCE_PX, `${message}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
    };
    /** A spot of the canvas with no node or edge under it, so a press there only pans. */
    const emptySpot = async (page) => {
      const canvas = await page.locator('#graph').evaluate((element) => element.getBoundingClientRect().toJSON());
      return { x: canvas.left + 40, y: canvas.top + 40 };
    };

    test('the wheel zooms keeping the point under the cursor in place', async () => {
      const { page } = await openPage(pageUrl);
      await waitForNodeCount(page, 7);
      const before = await nodeBox(page, 'FavoritesStore');
      const cursor = centerOf(before);

      await page.mouse.move(cursor.x, cursor.y);
      await page.mouse.wheel(0, -100);
      const zoomedIn = await nodeBox(page, 'FavoritesStore');
      await page.mouse.wheel(0, 100);
      await page.mouse.wheel(0, 100);
      const zoomedOut = await nodeBox(page, 'FavoritesStore');

      assert.ok(zoomedIn.width > before.width * 1.2, 'wheel up zooms in');
      assertSamePoint(centerOf(zoomedIn), cursor, 'zoom in moved the point under the cursor');
      assert.ok(zoomedOut.width < before.width, 'wheel down zooms out');
      assertSamePoint(centerOf(zoomedOut), cursor, 'zoom out moved the point under the cursor');
    });

    test('dragging the background moves the graph by the same distance and selects nothing', async () => {
      const { page } = await openPage(pageUrl);
      await waitForNodeCount(page, 7);
      const before = centerOf(await nodeBox(page, 'FavoritesStore'));
      const start = await emptySpot(page);

      await page.mouse.move(start.x, start.y);
      await page.mouse.down();
      await page.mouse.move(start.x + 120, start.y + 45, { steps: 6 });
      await page.mouse.up();

      assertSamePoint(centerOf(await nodeBox(page, 'FavoritesStore')), { x: before.x + 120, y: before.y + 45 }, 'the graph did not follow the drag');
      assert.equal(await page.locator('#graph .selected').count(), 0);
    });

    test('a drag that starts on a node pans without selecting it, and a click selects it', async () => {
      const { page } = await openPage(pageUrl);
      await waitForNodeCount(page, 7);
      const start = centerOf(await nodeBox(page, 'FavoritesStore'));

      await page.mouse.move(start.x, start.y);
      await page.mouse.down();
      await page.mouse.move(start.x + 60, start.y, { steps: 4 });
      await page.mouse.up();
      const selectedAfterDrag = await page.locator('#graph .selected').count();
      await page.mouse.click(start.x + 60, start.y);

      assert.equal(selectedAfterDrag, 0);
      assert.equal(await page.locator('#graph .graph-node.selected .node-label').textContent(), 'FavoritesStore');
    });

    test('a two-finger pinch zooms around the point between the fingers', async () => {
      const { page } = await openPage(pageUrl, { hasTouch: true });
      await waitForNodeCount(page, 7);
      const before = await nodeBox(page, 'FavoritesStore');
      const middle = centerOf(before);
      const session = await page.context().newCDPSession(page);
      const touch = (type, spread) => session.send('Input.dispatchTouchEvent', {
        type,
        touchPoints: type === 'touchEnd' ? [] : [
          { x: Math.round(middle.x - spread), y: Math.round(middle.y), id: 1 },
          { x: Math.round(middle.x + spread), y: Math.round(middle.y), id: 2 },
        ],
      });

      await touch('touchStart', 40);
      for (const spread of [50, 60, 70, 80]) await touch('touchMove', spread);
      await touch('touchEnd');
      const after = await nodeBox(page, 'FavoritesStore');

      assert.ok(Math.abs(after.width / before.width - 2) < 0.1, `fingers twice as far apart zoom to twice the size, got ${after.width / before.width}`);
      assertSamePoint(centerOf(after), { x: Math.round(middle.x), y: Math.round(middle.y) }, 'the pinch moved the point between the fingers');
      assert.equal(await page.locator('#graph .selected').count(), 0, 'a pinch is not a click');
    });

    test('the keyboard moves, zooms and fits the graph', async () => {
      const { page } = await openPage(pageUrl);
      await waitForNodeCount(page, 7);
      const fitted = await nodeBox(page, 'FavoritesStore');

      await page.locator('#graph').focus();
      await page.keyboard.press('ArrowRight');
      await page.keyboard.press('ArrowDown');
      const panned = await nodeBox(page, 'FavoritesStore');
      await page.keyboard.press('+');
      const zoomed = await nodeBox(page, 'FavoritesStore');
      await page.keyboard.press('-');
      await page.keyboard.press('-');
      const zoomedOut = await nodeBox(page, 'FavoritesStore');
      await page.keyboard.press('0');
      const refitted = await nodeBox(page, 'FavoritesStore');

      assertSamePoint(centerOf(panned), { x: centerOf(fitted).x - 60, y: centerOf(fitted).y - 60 }, 'arrows did not move the view by one step');
      assert.ok(zoomed.width > panned.width && zoomedOut.width < panned.width);
      assertSamePoint(centerOf(refitted), centerOf(fitted), '0 did not fit the graph back');
      assert.ok(Math.abs(refitted.width - fitted.width) <= POSITION_TOLERANCE_PX);
    });

    test('the zoom buttons zoom and "Ajustar" brings the whole graph back', async () => {
      const { page } = await openPage(pageUrl);
      await waitForNodeCount(page, 7);
      const fitted = await nodeBox(page, 'FavoritesStore');

      await page.getByRole('button', { name: 'Acercar' }).click();
      const zoomedIn = await nodeBox(page, 'FavoritesStore');
      await page.getByRole('button', { name: 'Alejar' }).click();
      await page.getByRole('button', { name: 'Alejar' }).click();
      const zoomedOut = await nodeBox(page, 'FavoritesStore');
      await page.getByRole('button', { name: 'Ajustar' }).click();

      assert.ok(zoomedIn.width > fitted.width && zoomedOut.width < fitted.width);
      assertSamePoint(centerOf(await nodeBox(page, 'FavoritesStore')), centerOf(fitted), '"Ajustar" did not restore the view');
    });
  });

  describe('phone layout', () => {
    const PHONE = { viewport: { width: 390, height: 844 }, hasTouch: true };
    const MIN_CANVAS_SHARE_OF_VIEWPORT = 0.75;
    const canvasHeight = (page) => page.locator('#graph').evaluate((element) => element.getBoundingClientRect().height);

    test('gives most of the screen to the canvas, with the panel and the filters folded', async () => {
      const { page } = await openPage(pageUrl, PHONE);
      await waitForNodeCount(page, 7);

      assert.ok(await canvasHeight(page) >= PHONE.viewport.height * MIN_CANVAS_SHARE_OF_VIEWPORT, `canvas is ${await canvasHeight(page)}px tall`);
      assert.equal(await page.locator('#side-panel').isVisible(), false);
      assert.equal(await page.getByRole('group', { name: 'Momento' }).isVisible(), false);
      assert.equal(await page.getByRole('button', { name: 'Detalle' }).getAttribute('aria-expanded'), 'false');
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth), 0);
    });

    test('opens at a readable size on the start of the flow, laid out from top to bottom', async () => {
      const { page } = await openPage(pageUrl, PHONE);
      await waitForNodeCount(page, 7);
      const readBoxes = () => page.evaluate(() => ({
        canvas: document.getElementById('graph').getBoundingClientRect().toJSON(),
        boxes: Object.fromEntries([...document.querySelectorAll('#graph .graph-node')].map((node) => [node.querySelector('.node-label').textContent, node.querySelector('rect').getBoundingClientRect().toJSON()])),
      }));
      const isInside = (box, canvas) => box.left >= canvas.left && box.right <= canvas.right && box.top >= canvas.top && box.bottom <= canvas.bottom;

      const opened = await readBoxes();
      await page.getByRole('button', { name: 'Ajustar' }).tap();
      const fitted = await readBoxes();

      const firstNode = opened.boxes.ProductDetailFragment;
      // 52 px is the height of a node at full size; below about 35 px its two lines stop being readable.
      assert.ok(firstNode.height >= 35, `nodes open ${firstNode.height}px tall`);
      assert.ok(isInside(firstNode, opened.canvas), 'the first element of the flow is on screen');
      assert.ok(opened.boxes.ToggleFavoriteAction.top > firstNode.bottom, 'the flow goes down on a portrait screen');
      assert.ok(Object.values(fitted.boxes).every((box) => isInside(box, fitted.canvas)), '"Ajustar" shows the whole graph');
    });

    test('tapping a node opens the panel as a drawer with its detail, and closing gives the canvas back', async () => {
      const { page } = await openPage(pageUrl, PHONE);
      await waitForNodeCount(page, 7);

      await page.locator('#graph .graph-node', { hasText: 'FavoritesStore' }).tap();
      const panel = page.locator('#side-panel');
      await panel.getByRole('heading', { name: 'FavoritesStore' }).waitFor();
      // The drawer slides in; its final place is the one that matters.
      await panel.evaluate((element) => Promise.all(element.getAnimations().map((animation) => animation.finished)));
      const panelBox = await panel.boundingBox();
      const focusedWhileOpen = await page.evaluate(() => document.activeElement.id);
      await page.getByRole('button', { name: 'Cerrar el panel' }).tap();

      assert.ok(panelBox.width <= PHONE.viewport.width * 0.9 && panelBox.x + panelBox.width <= PHONE.viewport.width + 1, 'the drawer leaves part of the canvas visible');
      assert.equal(focusedWhileOpen, 'close-panel');
      assert.equal(await panel.isVisible(), false);
      assert.equal(await page.locator('#backdrop').isVisible(), false);
      assert.equal(await page.evaluate(() => document.activeElement.id), 'toggle-panel', 'focus returns to the button that opens the panel');
      assert.equal(await page.locator('#graph .graph-node.selected').count(), 1, 'the selection stays on the canvas');
    });

    test('the panel also opens from its button and closes with the backdrop or Escape', async () => {
      const { page } = await openPage(pageUrl, PHONE);
      await waitForNodeCount(page, 7);
      const panel = page.locator('#side-panel');
      const toggle = page.getByRole('button', { name: 'Detalle' });

      await toggle.tap();
      const openedByButton = await panel.isVisible();
      const listedElements = await page.locator('#element-list button').count();
      await page.locator('#backdrop').tap({ position: { x: 10, y: 400 } });
      const closedByBackdrop = !(await panel.isVisible());
      await toggle.tap();
      await page.keyboard.press('Escape');

      assert.ok(openedByButton && closedByBackdrop);
      assert.equal(listedElements, 14);
      assert.equal(await panel.isVisible(), false);
      assert.equal(await toggle.getAttribute('aria-expanded'), 'false');
    });

    test('"Filtros" unfolds the moment buttons, the changed-only toggle and the legend', async () => {
      const { page } = await openPage(pageUrl, PHONE);
      await waitForNodeCount(page, 7);
      const filters = page.getByRole('button', { name: 'Filtros' });
      const foldedHeight = await canvasHeight(page);

      await filters.tap();
      await page.getByRole('button', { name: 'Después' }).tap();
      await waitForNodeCount(page, 6);
      const unfoldedHeight = await canvasHeight(page);
      await filters.tap();

      assert.ok(unfoldedHeight < foldedHeight, 'the filters take room only while unfolded');
      assert.equal(await page.getByRole('group', { name: 'Momento' }).isVisible(), false);
      assert.equal(await filters.getAttribute('aria-expanded'), 'false');
      assert.equal(await page.locator('#graph .graph-node').count(), 6, 'a folded filter keeps applying');
      assert.equal(Math.round(await canvasHeight(page)), Math.round(foldedHeight));
    });

    test('every control is at least 44 px tall for a finger', async () => {
      const { page } = await openPage(pageUrl, PHONE);
      await waitForNodeCount(page, 7);
      await page.getByRole('button', { name: 'Filtros' }).tap();

      const heights = await page.locator('header button:visible, .zoom-controls button:visible').evaluateAll((buttons) => buttons.map((button) => button.getBoundingClientRect().height));

      assert.ok(heights.length >= 8);
      assert.ok(heights.every((height) => height >= 44), `heights: ${heights.join(', ')}`);
    });
  });

  describe('verification, focus and tour', () => {
    const PASSED_CHECKS = ['model-shape', 'evidence-exists', 'change-matches-diff', 'relationship-names-endpoint', 'diff-coverage', 'outputs'].map((id) => ({
      id, label: `Check ${id}`, status: 'passed', detail: 'Detalle.',
    }));
    const writeVerifiedPage = (name, checks) => {
      const elkLibrary = BROWSER_LIBRARIES.find((library) => library.name === 'elkjs');
      const inlinedLibraries = new Map([[elkLibrary.url, readFileSync(require.resolve('elkjs/lib/elk.bundled.js'), 'utf8')]]);
      const pagePath = path.join(workDirectory, name);
      writeFileSync(pagePath, renderFlowGraphHtml(loadExampleModel(), { inlinedLibraries, verification: { checks } }));
      return pathToFileURL(pagePath).href;
    };

    test('a graph checked against the code says so and lists each check', async () => {
      const { page } = await openPage(writeVerifiedPage('verified.html', PASSED_CHECKS));
      await waitForNodeCount(page, 7);

      assert.equal((await page.locator('#verification-chip').textContent()).trim(), '✓Verificado contra el código');
      assert.equal(await page.locator('#checks li.passed').count(), 6);
    });

    test('a graph whose repository checks were skipped says it was not verified, also on a phone with the filters folded', async () => {
      const skippedChecks = PASSED_CHECKS.map((check) => (check.id === 'diff-coverage' ? { ...check, status: 'skipped' } : check));
      const { page } = await openPage(writeVerifiedPage('unverified.html', skippedChecks), { viewport: { width: 390, height: 844 }, hasTouch: true });
      await waitForNodeCount(page, 7);

      const chip = page.locator('#verification-chip');
      assert.equal((await chip.textContent()).trim(), '!Sin verificar contra el código');
      assert.equal(await chip.isVisible(), true);
      assert.equal(await page.getByRole('group', { name: 'Momento' }).isVisible(), false);
    });

    test('a page rendered without a verification record does not claim to be verified', async () => {
      const { page } = await openPage(pageUrl);
      await waitForNodeCount(page, 7);

      assert.match(await page.locator('#verification-chip').textContent(), /Sin verificar/);
      assert.match(await page.locator('#checks').textContent(), /Sin registro de verificación/);
    });

    test('selecting a node keeps what touches it in focus and steps the rest back', async () => {
      const { page } = await openPage(pageUrl);
      await waitForNodeCount(page, 7);

      await page.locator('#graph .graph-node', { hasText: 'FavoritesStore' }).click();
      const relatedNodes = await page.locator('#graph .graph-node.related .node-label').allTextContents();
      const dimmedOpacity = await page.locator('#graph .graph-node', { hasText: 'WishlistClient' }).evaluate((node) => getComputedStyle(node).opacity);
      const relatedEdgeCount = await page.locator('#graph .graph-edge.related').count();
      await page.mouse.click(DESKTOP_VIEWPORT.width / 2, 420);

      assert.deepEqual(relatedNodes.sort(), ['Dispatcher', 'FavoritesRepository', 'ProductDetailFragment']);
      assert.equal(relatedEdgeCount, 3);
      assert.ok(Number(dimmedOpacity) < 0.5, `an unrelated node keeps opacity ${dimmedOpacity}`);
      assert.equal(await page.locator('#graph.has-focus').count(), 0, 'clicking the background gives the whole graph back');
    });

    test('the tour walks the relationships in the order of the model, by step or on its own', async () => {
      const { page } = await openPage(pageUrl);
      await waitForNodeCount(page, 7);
      const caption = page.locator('#tour-caption');
      const playButton = page.getByRole('button', { name: 'Recorrer el flujo' });

      await page.getByRole('button', { name: 'Paso siguiente' }).click();
      const firstStep = await caption.textContent();
      await page.getByRole('button', { name: 'Paso anterior' }).click();
      const wrappedStep = await caption.textContent();
      await playButton.click();
      const pressedWhilePlaying = await playButton.getAttribute('aria-pressed');
      const stepWhilePlaying = await caption.textContent();
      await playButton.click();
      await page.getByRole('button', { name: 'Después' }).click();
      await waitForNodeCount(page, 6);

      assert.equal(firstStep, '1 / 7 · ProductDetailFragment → ToggleFavoriteAction: tap en favorito');
      assert.match(wrappedStep, /^7 \/ 7 · /);
      assert.equal(pressedWhilePlaying, 'true');
      assert.match(stepWhilePlaying, /^1 \/ 7 · /, 'playing after the last step starts the flow over');
      assert.equal(await playButton.getAttribute('aria-pressed'), 'false');
      assert.equal(await caption.isVisible(), false, 'a new filter ends the tour');
    });

    test('the toggle that hides untouched elements is not offered when there is nothing to hide', async () => {
      const { page } = await openPage(pageUrl);
      await waitForNodeCount(page, 7);

      assert.equal(await page.locator('#only-changed-toggle').isVisible(), false);
    });

    test('with motion allowed the changed relationships flow and a fit glides back; with reduced motion nothing loops', async () => {
      const infiniteAnimationCount = (page) => page.evaluate(() => document.getAnimations().filter((animation) => animation.effect.getComputedTiming().iterations === Infinity).length);
      const viewBox = (page) => page.locator('#graph').getAttribute('viewBox');
      const moving = await openPage(pageUrl, { reducedMotion: 'no-preference' });
      await waitForNodeCount(moving.page, 7);
      const still = await openPage(pageUrl);
      await waitForNodeCount(still.page, 7);

      const fittedViewBox = await viewBox(moving.page);
      await moving.page.getByRole('button', { name: 'Acercar' }).click();
      await moving.page.getByRole('button', { name: 'Ajustar' }).click();
      await moving.page.waitForFunction((expected) => document.getElementById('graph').getAttribute('viewBox') === expected, fittedViewBox);
      await still.page.locator('#graph .graph-node', { hasText: 'FavoritesStore' }).click();

      // Six relationships are added or modified; the removed one no longer flows.
      assert.equal(await infiniteAnimationCount(moving.page), 6);
      assert.equal(await infiniteAnimationCount(still.page), 0);
      assert.deepEqual(moving.problems, []);
    });
  });

  test('on a wide screen the panel starts open and folding it widens the canvas', async () => {
    const { page } = await openPage(pageUrl);
    await waitForNodeCount(page, 7);
    const canvasWidth = () => page.locator('#graph').evaluate((element) => element.getBoundingClientRect().width);
    const widthWithPanel = await canvasWidth();

    await page.getByRole('button', { name: 'Detalle' }).click();
    const widthWithoutPanel = await canvasWidth();
    const isFiltersButtonVisible = await page.getByRole('button', { name: 'Filtros' }).isVisible();
    await page.getByRole('button', { name: 'Detalle' }).click();

    assert.equal(Math.round(widthWithoutPanel), DESKTOP_VIEWPORT.width);
    assert.ok(widthWithPanel < widthWithoutPanel);
    assert.equal(isFiltersButtonVisible, false, 'the filters are always unfolded on a wide screen');
    assert.equal(await page.locator('#side-panel').isVisible(), true);
    assert.equal(await page.locator('#backdrop').isVisible(), false);
  });

  test('shows a ref given as a full commit hash abbreviated', async () => {
    const model = loadExampleModel();
    model.pullRequest.baseRef = '94abba778008ed056b3dd28353fc7faf22c242d5';
    const pagePath = path.join(workDirectory, 'commit-refs.html');
    writeFileSync(pagePath, renderFlowGraphHtml(model));
    const { page } = await openPage(pathToFileURL(pagePath).href, { offline: true });

    assert.deepEqual(await page.locator('#subtitle code').allTextContents(), ['feature/favorites-from-detail', '94abba7']);
  });

  test('a phone-width viewport keeps the page without horizontal scroll', async () => {
    const { page } = await openPage(pageUrl, { viewport: { width: 390, height: 844 } });
    await waitForNodeCount(page, 7);

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

    assert.equal(overflow, 0);
  });
});
