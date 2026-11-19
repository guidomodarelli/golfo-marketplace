#!/usr/bin/env node
/**
 * Embeds real-app captures (from capture-snippet.js) into a user manual.
 *
 * Usage: node embed-app-frames.mjs <captures.json> [more-captures.json ...] <manual.html> [--page-background=#ededed] [--host-css=<file>]
 *
 * --host-css appends design-system rules to the host CSS, for example to release a modal's inner scroll
 * area whose max-height depends on the viewport of the app.
 *
 * The manual marks each preview with an empty host element:
 *   <div class="app-frame" data-cap="<capture name>"></div>
 * Optional on the host: data-mute="<selector>" grays the icons and images of the matching elements of the
 * capture, except those matching data-mute-except (the card of this manual in the app's menu).
 * This script injects, between marker comments (re-runs replace the previous block):
 *   - a JSON payload with the used CSS, @font-face rules and one template per capture;
 *   - a small runtime that renders every host inside its own shadow root, so the app's CSS and
 *     the manual's CSS never leak into each other.
 * Several exports can be combined; when two contain the same capture name, the later file wins.
 * A manual with a Portuguese version embeds only the Spanish captures: the runtime translates them with
 * the "captures" table of the language script (DESIGN.md, "Selector de idioma").
 * Every capture gets its own stylesheet with its rules in the order the page applied them, so the
 * cascade (which rule wins between equal specificities) matches the app. Captures taken with
 * `fixedWidth` (mobile) also keep their viewport width.
 * No dependencies beyond Node's standard library.
 */
import fs from 'node:fs';

const positional = process.argv.slice(2).filter((argument) => !argument.startsWith('--'));
const flags = process.argv.slice(2).filter((argument) => argument.startsWith('--'));
const manualPath = positional.pop();
const capturesPaths = positional;
if (!capturesPaths.length || !manualPath) {
	console.error('Usage: node embed-app-frames.mjs <captures.json> [more-captures.json ...] <manual.html> [--page-background=<css color>] [--host-css=<file>]');
	process.exit(1);
}
const flagValue = (name) => (flags.find((flag) => flag.startsWith(`--${name}=`)) || '').slice(name.length + 3);
const pageBackground = flagValue('page-background') || 'transparent';
const hostCssPath = flagValue('host-css');
const extraHostCss = hostCssPath ? fs.readFileSync(hostCssPath, 'utf8') : '';

const START = '<!-- app-frames:start -->';
const END = '<!-- app-frames:end -->';
const META_ATTRIBUTE = 'data-app-frames-meta';
// Fonts injected by browser extensions or unrelated locales must not travel with the manual.
const FOREIGN_RULE = /chrome-extension:|moz-extension:|safari-web-extension:/;

// Every export has its own rule registry, so rule indexes are remapped into one merged registry.
const rules = [];
const ruleIndex = new Map();
const captures = new Map();
let meta = { capturedAt: null };
for (const path of capturesPaths) {
	const exported = JSON.parse(fs.readFileSync(path, 'utf8'));
	const remap = exported.rules.map((rule) => {
		if (!ruleIndex.has(rule)) {
			ruleIndex.set(rule, rules.length);
			rules.push(rule);
		}
		return ruleIndex.get(rule);
	});
	for (const capture of exported.caps) captures.set(capture.name, { ...capture, rules: capture.rules.map((index) => remap[index]) });
	if (exported.meta?.capturedAt && (!meta.capturedAt || exported.meta.capturedAt > meta.capturedAt)) meta = { ...meta, capturedAt: exported.meta.capturedAt };
}

let manual = fs.readFileSync(manualPath, 'utf8');
const hosts = [...new Set([...manual.matchAll(/class="app-frame"[^>]*data-cap="([^"]+)"/g)].map((match) => match[1]))];
const missing = hosts.filter((name) => !captures.has(name));
if (missing.length) {
	console.error(`Missing captures for: ${missing.join(', ')}`);
	process.exit(1);
}

const usedCaptures = hosts.map((name) => captures.get(name));
const isForeign = (index) => FOREIGN_RULE.test(rules[index]);
const isFontFace = (index) => rules[index].startsWith('@font-face');
const fontFaces = [...new Set(usedCaptures.flatMap((capture) => capture.rules))].filter((index) => isFontFace(index) && !isForeign(index)).map((index) => rules[index]);
// Rules are shared by index, but each capture keeps its own order: capture.rules lists them in the
// order the page walked its stylesheets. Sorting them globally would break the cascade, for example
// letting a design-system rule override an app rule of the same specificity that loaded after it.
const payloadRules = [];
const payloadIndex = new Map();
const captureRules = Object.fromEntries(usedCaptures.map((capture) => [
	capture.name,
	capture.rules.filter((index) => !isFontFace(index) && !isForeign(index)).map((index) => {
		if (!payloadIndex.has(index)) {
			payloadIndex.set(index, payloadRules.length);
			payloadRules.push(rules[index]);
		}
		return payloadIndex.get(index);
	}),
]));
const widths = Object.fromEntries(usedCaptures.filter((capture) => capture.viewportWidth).map((capture) => [capture.name, capture.viewportWidth]));
// Responsive captures lay out at min(capture viewport, reader viewport), so their container queries
// (converted from the app's width media queries) pick the layout the app would show on the reader's screen.
const viewports = Object.fromEntries(usedCaptures.filter((capture) => !capture.viewportWidth && capture.captureViewportWidth).map((capture) => [capture.name, capture.captureViewportWidth]));

// Shells are layout wrappers copied only so descendant selectors match; they must not add layout,
// overlays or viewport positioning. Floating roots (modals, popovers) are pinned in the flow.
// Layout containment makes each capture's content the containing block of `position: fixed`
// descendants (app headers and action bars), so they keep the captured width instead of following the
// reader's viewport or the frame padding.
const HOST_CSS = `
.app-frame__page{background:${pageBackground};overflow:hidden;text-align:left;}
.app-frame__content{position:relative;contain:layout;container:um-viewport / inline-size;}
[data-shell]{position:relative!important;inset:auto!important;transform:none!important;width:auto!important;height:auto!important;min-height:0!important;max-height:none!important;overflow:visible!important;margin:0!important;padding:0!important;background:transparent!important;display:block!important;box-shadow:none!important;border:0!important;opacity:1!important;visibility:visible!important;}
[data-capture-root]{margin-left:auto!important;margin-right:auto!important;opacity:1!important;visibility:visible!important;}
[data-capture-root][style*="position: relative"]{inset:auto!important;transform:none!important;}
`;

const payload = JSON.stringify({ fontFaces, rules: payloadRules, captureRules, hostCss: HOST_CSS + extraHostCss, widths, viewports: viewports, templates: Object.fromEntries(hosts.map((name) => [name, captures.get(name).html])) })
	.replace(/<\//g, '<\\/')
	.replace(/<!--/g, '\\u003c!--'); // "<\!--" is not a valid JSON escape; \u003c is, and keeps the HTML parser out

const block = `${START}
<script id="app-frames-data" type="application/json">${payload}</script>
<script>
// Renders each captured screen in its own shadow root, lazily, and fits it so every visible layer
// (including popovers and dropdowns that float outside their parent) shows whole with 16px of air.
(function () {
	var MARGIN = 16;
	var LAZY_ROOT_MARGIN = '800px 0px';
	var data = JSON.parse(document.getElementById('app-frames-data').textContent);
	var fonts = document.createElement('style');
	fonts.textContent = data.fontFaces.join('\\n');
	document.head.appendChild(fonts);
	function toSheet(cssText) {
		var sheet = new CSSStyleSheet();
		sheet.replaceSync(cssText);
		return sheet;
	}
	var hostSheet = toSheet(data.hostCss);
	// data-mute="<selector>" on a host grays the media (icons, images) of every matching element of the
	// capture except the ones matching data-mute-except, so the element the text talks about stands out
	// (the card of this manual in a capture of the app's menu).
	var muteSheet = toSheet('[data-muted] :is(img,svg,picture,canvas){filter:grayscale(1);opacity:0.45;}');
	function mute(host, content) {
		var group = host.getAttribute('data-mute');
		if (!group) return;
		var except = host.getAttribute('data-mute-except');
		content.querySelectorAll(group).forEach(function (element) {
			var kept = except && (element.matches(except) || element.querySelector(except) || element.closest(except));
			if (kept) element.removeAttribute('data-muted');
			else element.setAttribute('data-muted', '');
		});
	}
	function captureSheet(name) {
		return toSheet((data.captureRules[name] || []).map(function (index) { return data.rules[index]; }).join('\\n'));
	}
	var hosts = Array.prototype.slice.call(document.querySelectorAll('.app-frame'));

	function visibleBounds(content) {
		var box = { left: Infinity, top: Infinity, right: -Infinity, bottom: -Infinity };
		content.querySelectorAll('[data-capture-root], [data-capture-root] *').forEach(function (element) {
			var rect = element.getBoundingClientRect();
			if (!rect.width || !rect.height) return;
			var style = getComputedStyle(element);
			if (style.visibility === 'hidden' || style.display === 'none' || style.opacity === '0') return;
			box.left = Math.min(box.left, rect.left);
			box.top = Math.min(box.top, rect.top);
			box.right = Math.max(box.right, rect.right);
			box.bottom = Math.max(box.bottom, rect.bottom);
		});
		return box;
	}

	function fit(page, content, fixedWidth, captureViewportWidth) {
		content.style.zoom = '';
		content.style.margin = '0px';
		if (fixedWidth) content.style.width = fixedWidth + 'px';
		else if (captureViewportWidth) content.style.width = Math.min(captureViewportWidth, window.innerWidth) + 'px';
		else content.style.width = '';
		var pageRect = page.getBoundingClientRect();
		var available = pageRect.width - MARGIN * 2;
		var box = visibleBounds(content);
		if (box.left === Infinity) return;
		// Layers positioned in fixed pixels (popovers, menus) can stick out of a fluid root: narrow the
		// content by that amount so the root shrinks and the layer lands inside it.
		var rootRect = content.querySelector('[data-capture-root]').getBoundingClientRect();
		var sticking = Math.max(0, box.right - rootRect.right);
		if (sticking > 0) {
			content.style.width = (content.getBoundingClientRect().width - sticking) + 'px';
			box = visibleBounds(content);
		}
		// Anything still wider than the page scales down until the widest layer fits.
		var scale = 1;
		for (var attempt = 0; attempt < 4 && box.right - box.left > available + 0.5; attempt += 1) {
			scale *= available / (box.right - box.left);
			content.style.zoom = String(scale);
			box = visibleBounds(content);
		}
		var contentRect = content.getBoundingClientRect();
		content.style.marginTop = (contentRect.top - box.top) + 'px';
		content.style.marginBottom = (box.bottom - contentRect.bottom) + 'px';
		box = visibleBounds(content);
		pageRect = page.getBoundingClientRect();
		var leftOverflow = pageRect.left + MARGIN - box.left;
		var rightOverflow = box.right - (pageRect.right - MARGIN);
		if (leftOverflow > 0) content.style.marginLeft = leftOverflow + 'px';
		else if (rightOverflow > 0) content.style.marginLeft = -rightOverflow + 'px';
		// Fixed-viewport (mobile) captures are centered, like a phone screen on the page.
		else if (fixedWidth) content.style.marginLeft = Math.max(0, (available - (box.right - box.left)) / 2) + 'px';
	}

	// Pins with data-target follow their element after every fit, so they never drift with the reader's
	// width or a capture's height. --x/--y stay as the fallback until the frame renders.
	var PIN_GAP_PX = 14;
	var PIN_RADIUS_PX = 12;
	var PIN_INSET_PX = 4;
	// What the reader sees of a target: a filled or bordered box (a button, a chip) counts whole; otherwise
	// only its text and media, so a pin on a wide or centered block lands next to the words, not the block.
	// Transparent colors (a box shadow or border kept for focus rings) do not make a box visible.
	var TRANSPARENT = /^transparent$|rgba\\([^)]*,\\s*0\\)$/;
	function visibleBox(target) {
		var style = getComputedStyle(target);
		var background = style.backgroundColor;
		var filled = background && background !== 'transparent' && !TRANSPARENT.test(background);
		var bordered = parseFloat(style.borderLeftWidth) > 0 && !TRANSPARENT.test(style.borderLeftColor);
		if (filled || bordered) return target.getBoundingClientRect();
		var box = { left: Infinity, top: Infinity, right: -Infinity, bottom: -Infinity };
		var add = function (rect) {
			if (!rect.width || !rect.height) return;
			box.left = Math.min(box.left, rect.left); box.top = Math.min(box.top, rect.top);
			box.right = Math.max(box.right, rect.right); box.bottom = Math.max(box.bottom, rect.bottom);
		};
		var range = target.ownerDocument.createRange();
		var walker = target.ownerDocument.createTreeWalker(target, NodeFilter.SHOW_TEXT);
		for (var node = walker.nextNode(); node; node = walker.nextNode()) {
			if (!node.textContent.trim()) continue;
			range.selectNodeContents(node);
			Array.prototype.forEach.call(range.getClientRects(), add);
		}
		target.querySelectorAll('img, svg, picture, canvas, input, button, textarea, select').forEach(function (media) { add(media.getBoundingClientRect()); });
		if (box.left === Infinity) return target.getBoundingClientRect();
		return { left: box.left, top: box.top, width: box.right - box.left, height: box.bottom - box.top };
	}

	function placeHotspots(host) {
		var stage = host.closest('.hotspot-stage');
		if (!stage || !host.shadowRoot) return;
		var stageRect = stage.getBoundingClientRect();
		stage.querySelectorAll('.hotspot[data-target]').forEach(function (pin) {
			var candidates = Array.prototype.slice.call(host.shadowRoot.querySelectorAll(pin.getAttribute('data-target')));
			var text = pin.getAttribute('data-target-text');
			var target = text
				? candidates.filter(function (element) { return element.textContent.trim() === text; })[0]
				: candidates[0];
			if (!target) return;
			var rect = visibleBox(target);
			if (!rect.width || !rect.height) return;
			// Without room on the left (the target starts at the capture's edge), the pin goes to its right.
			// data-side="right" puts it on the right, for targets glued to text on their left (a "+2" after a value).
			var left = rect.left - stageRect.left - PIN_GAP_PX;
			if (pin.getAttribute('data-side') === 'right' || left < PIN_RADIUS_PX) left = rect.left + rect.width - stageRect.left + PIN_GAP_PX;
			// No room on either side (a full-width button): inside its left edge, over its padding.
			if (left > stageRect.width - PIN_RADIUS_PX) left = rect.left - stageRect.left + PIN_RADIUS_PX + PIN_INSET_PX;
			pin.style.left = left + 'px';
			pin.style.top = (rect.top + rect.height / 2 - stageRect.top) + 'px';
		});
	}

	// Screen readers get the caption as the image description; the capture itself stays inert.
	// A label written by hand in the manual is kept; the one written here follows the language.
	function describe(host) {
		if (host.hasAttribute('aria-label') && !host.__umDescribed) return;
		host.__umDescribed = true;
		var mockup = host.closest('.mockup');
		var caption = mockup && mockup.nextElementSibling && mockup.nextElementSibling.classList.contains('figcap')
			? mockup.nextElementSibling.textContent.trim()
			: '';
		var title = mockup ? (mockup.querySelector('.mockup-url') || {}).textContent : '';
		host.setAttribute('role', 'img');
		// The Portuguese version (<html lang="pt-BR">, set by the language script) names it in Portuguese.
		var prefix = /^pt/i.test(document.documentElement.lang) ? 'Captura de tela: ' : 'Captura de pantalla: ';
		host.setAttribute('aria-label', prefix + (caption || title || host.getAttribute('data-cap')));
	}

	// The capture in the reader's language: the Spanish template translated in place with the "captures"
	// table of the language script, or a full Portuguese copy (captureTemplates) when its structure differs.
	function fill(host, content, name) {
		var language = window.HeritageLanguage;
		var override = language && language.captureTemplate(name);
		if (!host.__umFilled || override || host.__umOverridden) {
			content.innerHTML = override || data.templates[name] || '';
			content.querySelectorAll('a[href]').forEach(function (link) { link.removeAttribute('href'); });
		}
		host.__umFilled = true;
		host.__umOverridden = Boolean(override);
		if (language && !override) language.translate(content, 'captures');
		mute(host, content);
	}

	function render(host) {
		if (host.shadowRoot) return;
		var name = host.getAttribute('data-cap');
		var root = host.attachShadow({ mode: 'open' });
		root.adoptedStyleSheets = [captureSheet(name), hostSheet, muteSheet];
		var page = document.createElement('div');
		page.className = 'app-frame__page';
		page.style.padding = MARGIN + 'px';
		var content = document.createElement('div');
		content.className = 'app-frame__content';
		// flow-root keeps captured margins inside, so empty space above the screen can be trimmed.
		content.style.display = 'flow-root';
		fill(host, content, name);
		host.__umContent = content;
		page.setAttribute('inert', '');
		page.setAttribute('aria-hidden', 'true');
		page.appendChild(content);
		root.appendChild(page);
		host.style.minHeight = '';
		var refit = function () {
			fit(page, content, data.widths[name], (data.viewports || {})[name]);
			placeHotspots(host);
			// Overlays placed by other scripts (menu links over the cards of a menu) follow the capture too.
			host.dispatchEvent(new CustomEvent('heritage:frame-fit', { bubbles: true }));
		};
		host.__umRefit = refit;
		// setTimeout instead of requestAnimationFrame: rAF does not fire in background tabs.
		(document.fonts ? document.fonts.ready : Promise.resolve()).then(function () { setTimeout(refit, 0); });
		new ResizeObserver(refit).observe(host);
	}

	// The reader's viewport decides the layout of responsive captures, so a window resize refits them even
	// when the frame keeps its width.
	var resizeTimer = null;
	window.addEventListener('resize', function () {
		clearTimeout(resizeTimer);
		resizeTimer = setTimeout(function () {
			hosts.forEach(function (host) { if (host.__umRefit) host.__umRefit(); });
		}, 150);
	});

	hosts.forEach(function (host) {
		describe(host);
		// Reserve space so the lazy frames do not collapse the page before they render.
		if (!host.shadowRoot) host.style.minHeight = '240px';
	});
	if ('IntersectionObserver' in window) {
		var observer = new IntersectionObserver(function (entries) {
			entries.forEach(function (entry) {
				if (!entry.isIntersecting) return;
				observer.unobserve(entry.target);
				render(entry.target);
			});
		}, { rootMargin: LAZY_ROOT_MARGIN });
		hosts.forEach(function (host) { observer.observe(host); });
	} else {
		hosts.forEach(render);
	}
	// Printing and PDF export must include every screen, even the ones never scrolled into view.
	window.addEventListener('beforeprint', function () { hosts.forEach(render); });
	// In-page navigation renders every frame above its target first, so their real heights do not
	// push the target down while the page scrolls to it.
	// Language switch in the same page: the document is already translated (captions, pin targets), so
	// every rendered capture is translated and fitted again, and its pins follow their elements.
	document.addEventListener('heritage:language-change', function () {
		hosts.forEach(function (host) {
			describe(host);
			if (!host.__umContent) return;
			fill(host, host.__umContent, host.getAttribute('data-cap'));
			host.__umRefit();
		});
	});
	document.addEventListener('heritage:before-scroll', function (event) {
		var target = event.detail && event.detail.target;
		if (!target) return;
		hosts.forEach(function (host) {
			if (host.compareDocumentPosition(target) & Node.DOCUMENT_POSITION_FOLLOWING) render(host);
		});
	});
})();
</script>
${END}`;

const existing = new RegExp(`${START}[\\s\\S]*?${END}`);
// The header says when the screens were captured; the "Código" line already says which code they show.
if (meta.capturedAt) {
	const label = `Capturas: ${meta.capturedAt}`;
	// Global: a manual with a Portuguese version repeats the header inside <template id="lang-pt">.
	const metaSpan = new RegExp(`<span ${META_ATTRIBUTE}>[^<]*</span>`, 'g');
	if (metaSpan.test(manual)) manual = manual.replace(metaSpan, `<span ${META_ATTRIBUTE}>${label}</span>`);
	else manual = manual.replace(/(<div class="doc-meta">[\s\S]*?)(\s*<\/div>)/, `$1\n    <span ${META_ATTRIBUTE}>${label}</span>$2`);
}
manual = existing.test(manual) ? manual.replace(existing, block) : manual.replace(/<\/body>/i, `${block}\n</body>`);
if (!manual.includes('.app-frame{')) manual = manual.replace(/<\/style>/i, '.app-frame{display:block;}\n</style>');
fs.writeFileSync(manualPath, manual);
console.log(`Embedded ${hosts.length} frames (${Object.keys(widths).length} fixed-viewport), ${payloadRules.length} CSS rules (${fontFaces.length} @font-face), ${Buffer.byteLength(manual)} bytes.`);
