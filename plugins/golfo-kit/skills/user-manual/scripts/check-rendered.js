/**
 * Rendered checks for a user manual, run in the browser on the manual itself (served locally or inside
 * the destination iframe). Complements check-manual.mjs with what only exists once frames render.
 *
 *   await __umCheckRendered()            // in the manual's window
 *   await __umCheckRendered(iframe.contentWindow)   // from an embedding viewer, on its iframe
 *
 * Returns { frames, unrendered, fit, pins, order, stages, ok }:
 *   unrendered  captures that did not render (no shadow root or no height)
 *   fit         captures whose visible content is closer than 16 px to an edge (cut or cramped)
 *   pins        anchored pins that are not 14 px left of what the reader sees in their element (its text
 *               and media, or the whole box when it is filled or bordered), or that fall outside the capture
 *   order       captures whose pins are not numbered top to bottom and left to right (pins on the same row,
 *               within 12 px, go left to right). Checked on mobile captures and, for desktop captures, at
 *               1000 px or more, where the capture keeps the layout it was taken in.
 *   stages      only in a staged manual (DESIGN.md, "Lectura por etapas"): sections shown that do not match the
 *               chosen stage, map marks of hidden sections, print not showing every section, the state not
 *               restored after print, horizontal page scroll, the stage menu or the map over the content,
 *               and the section pill away from the bottom left corner. Null in a linear manual.
 * Run it at desktop width (1280 px) and at phone width (390 px): both must return ok: true.
 */
(function () {
	const MIN_GAP_PX = 16;
	const PIN_GAP_PX = 14;
	// Inside a full-width target: pin radius (12) + inset (4).
	const PIN_INSIDE_PX = 16;
	const TOLERANCE_PX = 2;
	// Pins whose centers are this close vertically are on the same row and read left to right.
	const ROW_TOLERANCE_PX = 12;
	const DESKTOP_LAYOUT_MIN_PX = 1000;
	const RENDER_WAIT_MS = 2500;
	// Section pill: left:24px; bottom:24px, and 16px below 720px (DESIGN.md, "Píldora de sección").
	const PILL_CORNER_PX = 24;
	const PILL_CORNER_COMPACT_PX = 16;
	const COMPACT_MAX_WIDTH_PX = 719;

	// Left edge of what the reader actually sees inside an element (text, images, icons), which can be far
	// from the element's own box when it is a wide cell or row.
	// Same rule as the capture runtime: a filled or bordered box counts whole; otherwise its text and media.
	const TRANSPARENT = /^transparent$|rgba\([^)]*,\s*0\)$/;
	const visibleBox = (element, view) => {
		const style = view.getComputedStyle(element);
		const background = style.backgroundColor;
		const filled = background && background !== 'transparent' && !TRANSPARENT.test(background);
		const bordered = parseFloat(style.borderLeftWidth) > 0 && !TRANSPARENT.test(style.borderLeftColor);
		if (filled || bordered) return element.getBoundingClientRect();
		const box = { left: Infinity, top: Infinity, right: -Infinity, bottom: -Infinity };
		const add = (rect) => {
			if (!rect.width || !rect.height) return;
			box.left = Math.min(box.left, rect.left); box.top = Math.min(box.top, rect.top);
			box.right = Math.max(box.right, rect.right); box.bottom = Math.max(box.bottom, rect.bottom);
		};
		const range = element.ownerDocument.createRange();
		const walker = element.ownerDocument.createTreeWalker(element, view.NodeFilter.SHOW_TEXT);
		for (let node = walker.nextNode(); node; node = walker.nextNode()) {
			if (!node.textContent.trim()) continue;
			range.selectNodeContents(node);
			[...range.getClientRects()].forEach(add);
		}
		element.querySelectorAll('img, svg, picture, canvas, input, button, textarea, select').forEach((media) => add(media.getBoundingClientRect()));
		if (box.left === Infinity) return element.getBoundingClientRect();
		return { left: box.left, top: box.top, width: box.right - box.left, height: box.bottom - box.top };
	};

	const visibleBounds = (pageElement, view) => {
		const box = { left: Infinity, top: Infinity, right: -Infinity, bottom: -Infinity };
		pageElement.querySelectorAll('[data-capture-root], [data-capture-root] *').forEach((element) => {
			const rect = element.getBoundingClientRect();
			const style = view.getComputedStyle(element);
			if (!rect.width || !rect.height || style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return;
			box.left = Math.min(box.left, rect.left);
			box.top = Math.min(box.top, rect.top);
			box.right = Math.max(box.right, rect.right);
			box.bottom = Math.max(box.bottom, rect.bottom);
		});
		return box;
	};

	const hiddenSectionIds = (manual) => [...manual.querySelectorAll('section.section')].filter((section) => !section.getClientRects().length).map((section) => section.getAttribute('aria-labelledby'));
	const stagedSnapshot = (view) => ({ state: JSON.stringify(view.HeritageStages.state()), hidden: hiddenSectionIds(view.document).join(',') });
	const isShown = (element) => Boolean(element && element.getClientRects().length && element.getBoundingClientRect().width);

	// Staged reading: what is shown matches the chosen stage, navigation never covers the content.
	const stageProblems = (view, before, hiddenWhilePrinting) => {
		const manual = view.document;
		const problems = [];
		if (hiddenWhilePrinting.length) problems.push(`print hides sections: ${hiddenWhilePrinting.join(', ')}`);
		const after = stagedSnapshot(view);
		if (after.state !== before.state || after.hidden !== before.hidden) problems.push(`state not restored after print: ${before.state} → ${after.state}`);
		const state = view.HeritageStages.state();
		const hidden = hiddenSectionIds(manual);
		const expectedVisible = state.mode === 'all' ? null : view.HeritageStages.sectionsOf(state.stage);
		[...manual.querySelectorAll('section.section')].forEach((section) => {
			const id = section.getAttribute('aria-labelledby');
			const shouldShow = !expectedVisible || expectedVisible.includes(id);
			if (shouldShow === hidden.includes(id)) problems.push(`section ${id} is ${shouldShow ? 'hidden' : 'shown'} in ${state.mode === 'all' ? 'Ver todo' : `stage ${state.stage}`}`);
			const tick = manual.querySelector(`.section-rail a[href="#${id}"]`);
			if (tick && Boolean(tick.closest('li').hidden) !== hidden.includes(id)) problems.push(`section map mark of ${id} does not follow its section`);
		});
		if (manual.documentElement.scrollWidth > view.innerWidth + TOLERANCE_PX) problems.push(`horizontal page scroll: ${manual.documentElement.scrollWidth}px in a ${view.innerWidth}px window`);
		const visibleSections = [...manual.querySelectorAll('section.section')].filter(isShown).map((section) => section.getBoundingClientRect());
		const menu = manual.querySelector('.stage-menu');
		if (isShown(menu) && visibleSections.some((box) => box.right > menu.getBoundingClientRect().left + TOLERANCE_PX)) problems.push('the stage menu overlaps the content');
		const rail = manual.querySelector('.section-rail');
		if (isShown(rail) && visibleSections.some((box) => box.left < rail.getBoundingClientRect().right - TOLERANCE_PX)) problems.push('the section map overlaps the content');
		const pill = manual.querySelector('.section-pill');
		if (isShown(pill)) {
			const corner = view.innerWidth <= COMPACT_MAX_WIDTH_PX ? PILL_CORNER_COMPACT_PX : PILL_CORNER_PX;
			const box = pill.getBoundingClientRect();
			if (Math.abs(box.left - corner) > TOLERANCE_PX || Math.abs(view.innerHeight - box.bottom - corner) > TOLERANCE_PX) problems.push(`section pill is not at the bottom left corner (left ${Math.round(box.left)}, bottom ${Math.round(view.innerHeight - box.bottom)})`);
		}
		return problems;
	};

	window.__umCheckRendered = async (view = window) => {
		const manual = view.document;
		const stagedBefore = view.HeritageStages ? stagedSnapshot(view) : null;
		view.dispatchEvent(new view.Event('beforeprint'));
		await new Promise((resolve) => setTimeout(resolve, RENDER_WAIT_MS));
		const hiddenWhilePrinting = stagedBefore ? hiddenSectionIds(manual) : [];
		const hosts = [...manual.querySelectorAll('.app-frame')];
		const unrendered = hosts.filter((host) => !host.shadowRoot || host.getBoundingClientRect().height < 40).map((host) => host.dataset.cap);
		const fit = hosts.flatMap((host) => {
			const pageElement = host.shadowRoot && host.shadowRoot.querySelector('.app-frame__page');
			if (!pageElement) return [];
			const pageRect = pageElement.getBoundingClientRect();
			const box = visibleBounds(pageElement, view);
			if (box.left === Infinity) return [[host.dataset.cap, 'empty']];
			const gaps = [box.top - pageRect.top, pageRect.bottom - box.bottom, box.left - pageRect.left, pageRect.right - box.right].map(Math.round);
			// Full-width app screens touch the sides by design; only top/bottom cuts and overflow matter there.
			const cut = gaps[0] < MIN_GAP_PX || gaps[1] < MIN_GAP_PX || gaps[2] < 0 || gaps[3] < 0;
			return cut ? [[host.dataset.cap, gaps]] : [];
		});
		const pins = [];
		manual.querySelectorAll('.hotspot-stage').forEach((stage) => {
			const host = stage.querySelector('.app-frame');
			stage.querySelectorAll('.hotspot').forEach((pin) => {
				const key = `${host ? host.dataset.cap : 'mockup-body'}#${pin.dataset.hotspot}`;
				if (!host) return;
				if (!pin.dataset.target) { pins.push([key, 'no data-target']); return; }
				const candidates = host.shadowRoot ? [...host.shadowRoot.querySelectorAll(pin.dataset.target)] : [];
				const target = pin.dataset.targetText ? candidates.find((element) => element.textContent.trim() === pin.dataset.targetText) : candidates[0];
				if (!target) { pins.push([key, `target not found: ${pin.dataset.target} ${pin.dataset.targetText || ''}`.trim()]); return; }
				const pinRect = pin.getBoundingClientRect();
				const rect = visibleBox(target, view);
				// 14 px left of what the reader sees, 14 px right of it when the target starts at the capture's edge,
				// or just inside its left edge when there is no room on either side.
				const pinCenter = pinRect.left + pinRect.width / 2;
				const leftGap = Math.round(rect.left - pinCenter);
				const rightGap = Math.round(pinCenter - (rect.left + rect.width));
				const insideGap = Math.round(pinCenter - rect.left);
				const placements = pin.dataset.side === 'right' ? [rightGap - PIN_GAP_PX] : [leftGap - PIN_GAP_PX, rightGap - PIN_GAP_PX, insideGap - PIN_INSIDE_PX];
				const horizontal = PIN_GAP_PX + placements.reduce((best, offset) => (Math.abs(offset) < Math.abs(best) ? offset : best));
				const vertical = Math.round(pinRect.top + pinRect.height / 2 - (rect.top + rect.height / 2));
				if (Math.abs(horizontal - PIN_GAP_PX) > TOLERANCE_PX || Math.abs(vertical) > TOLERANCE_PX) pins.push([key, [leftGap, vertical]]);
				// A pin anchored to a full-width element lands on (or past) the capture's edge and shows cut.
				const stageRect = stage.getBoundingClientRect();
				if (pinRect.left < stageRect.left || pinRect.right > stageRect.right) pins.push([key, 'outside the capture: anchor it to a compact element']);
			});
		});
		// Pins are numbered in reading order: top to bottom, then left to right on the same row.
		const order = [];
		manual.querySelectorAll('.hotspot-stage').forEach((stage) => {
			const host = stage.querySelector('.app-frame');
			const isMobile = Boolean(stage.closest('.mockup--mobile'));
			if (!host || (!isMobile && view.innerWidth < DESKTOP_LAYOUT_MIN_PX)) return;
			const placed = [...stage.querySelectorAll('.hotspot')].map((pin) => {
				const rect = pin.getBoundingClientRect();
				return { number: Number(pin.dataset.hotspot), x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
			});
			const reading = [...placed].sort((a, b) => (Math.abs(a.y - b.y) <= ROW_TOLERANCE_PX ? a.x - b.x : a.y - b.y)).map((pin) => pin.number);
			const numbered = [...reading].sort((a, b) => a - b);
			if (reading.some((number, index) => number !== numbered[index])) order.push([host.dataset.cap, reading]);
		});
		// The checks ran in the print state (captures rendered, every section shown); afterwards the manual goes back.
		view.dispatchEvent(new view.Event('afterprint'));
		const stages = stagedBefore ? stageProblems(view, stagedBefore, hiddenWhilePrinting) : null;
		return { width: view.innerWidth, frames: hosts.length, unrendered, fit, pins, order, stages, ok: !unrendered.length && !fit.length && !pins.length && !order.length && !(stages && stages.length) };
	};
})();
