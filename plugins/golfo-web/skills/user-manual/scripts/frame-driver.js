/**
 * Browser helper that drives a same-origin iframe at a fixed viewport, so every screen of a flow is
 * captured at the width the readers use (375 px for mobile, 1280 px or wider for desktop).
 *
 * Inject it into any page of the app (same way as capture-snippet.js, with the page nonce), then:
 *   const driver = window.__umFrame({ width: 375, height: 812, snippetUrl: 'http://127.0.0.1:8767/capture-snippet.js' });
 *   await driver.load('/route', '.ready-selector');      navigate the iframe and re-inject the snippet
 *   await driver.capture('name', element, { floating });  __umCap inside the iframe (fixedWidth on mobile)
 *   await driver.fill(input, 'value');                   set a React-controlled input and fire `input`
 *   driver.textInput(root)                               first visible text input (skips hidden CSRF fields)
 *   driver.button(root, 'Confirmar') / driver.modal('texto visible')
 *   await driver.waitFor(selector, timeoutMs)
 *
 * Keep each browser tool call under ~45 s: split long waits (polling, inactivity timers) into separate
 * calls, or sleep in the shell between calls.
 */
(function () {
	const POLL_INTERVAL_MS = 150;
	const DEFAULT_TIMEOUT_MS = 15000;
	const MOBILE_MAX_WIDTH_PX = 480;
	const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

	window.__umFrame = ({ width = 375, height = 812, snippetUrl, frameId = 'um-capture-frame' } = {}) => {
		if (!snippetUrl) throw new Error('frame-driver:__umFrame requires snippetUrl (served by capture-bridge.py)');
		const getFrame = () => {
			let frame = document.getElementById(frameId);
			if (!frame) {
				frame = document.createElement('iframe');
				frame.id = frameId;
				// No border: a border would shrink the iframe's innerWidth below the requested viewport.
				frame.style.cssText = `position:fixed;top:0;left:0;width:${width}px;height:${height}px;z-index:2147483647;background:#fff;border:0`;
				document.body.appendChild(frame);
			}
			return frame;
		};
		const innerDocument = () => getFrame().contentDocument;
		const innerWindow = () => getFrame().contentWindow;

		const waitFor = async (selector, timeoutMs = DEFAULT_TIMEOUT_MS) => {
			const deadline = Date.now() + timeoutMs;
			while (Date.now() < deadline) {
				const element = innerDocument() && innerDocument().querySelector(selector);
				if (element) return element;
				await wait(POLL_INTERVAL_MS);
			}
			throw new Error(`frame-driver:waitFor timed out after ${timeoutMs} ms for ${selector}`);
		};

		const injectSnippet = async () => {
			if (typeof innerWindow().__umCap === 'function') return;
			const source = await fetch(snippetUrl).then((response) => response.text());
			const script = innerDocument().createElement('script');
			script.nonce = [...innerDocument().scripts].map((existing) => existing.nonce).find(Boolean);
			script.textContent = source;
			innerDocument().head.appendChild(script);
		};

		const load = async (path, readySelector) => {
			const frame = getFrame();
			await new Promise((resolve) => {
				frame.addEventListener('load', resolve, { once: true });
				frame.src = path;
			});
			if (readySelector) await waitFor(readySelector);
			await injectSnippet();
		};

		const capture = async (name, element, { floating = false, pairs = [], transform = null } = {}) => {
			if (!element) throw new Error(`frame-driver:capture got no element for ${name}`);
			await injectSnippet();
			if (innerDocument().activeElement) innerDocument().activeElement.blur();
			innerWindow().scrollTo({ top: 0, behavior: 'instant' });
			// Mobile captures keep their width in the manual; desktop captures stay responsive.
			const fixedWidth = width <= MOBILE_MAX_WIDTH_PX;
			return innerWindow().__umCap(name, element, { pairs, transform, floating, fixedWidth });
		};

		const fill = async (input, value) => {
			const prototype = input instanceof innerWindow().HTMLTextAreaElement ? innerWindow().HTMLTextAreaElement.prototype : innerWindow().HTMLInputElement.prototype;
			Object.getOwnPropertyDescriptor(prototype, 'value').set.call(input, String(value));
			input.dispatchEvent(new (innerWindow().Event)('input', { bubbles: true }));
			await wait(200);
		};

		const textInput = (root = innerDocument()) => root.querySelector('input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]), textarea');
		const button = (root, text) => [...(root || innerDocument()).querySelectorAll('button, [role="button"]')].find((element) => element.innerText.trim() === text);
		const modal = (text) => [...innerDocument().querySelectorAll('[role="dialog"], dialog')].find((element) => element.innerText.includes(text));

		return { wait, waitFor, load, capture, fill, textInput, button, modal, frame: getFrame, document: innerDocument, window: innerWindow };
	};
})();
