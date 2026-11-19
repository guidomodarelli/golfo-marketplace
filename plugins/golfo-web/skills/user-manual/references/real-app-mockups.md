# Mockups with the app's exact styles

Hand-drawn mockups drift from the product: fonts, spacing, component shapes, and colors end up
approximated. When the app being documented can be opened in a browser, capture the real screens
instead. The result is design-system agnostic: it works with Material, Tailwind, Bootstrap, a company design system
or custom CSS, because it copies whatever markup and stylesheets the page actually uses.

## What the technique does

1. Opens the running app and, for each screen or state the manual shows, clones the real DOM
   fragment plus its ancestors as empty shells, so descendant selectors keep matching.
2. Keeps only the CSS rules that match that fragment, including `@media`, `@supports`,
   `@keyframes` and `@font-face`, with relative `url()` values made absolute.
3. Replaces every piece of real data with example values before anything leaves the page.
4. Renders each capture inside its own shadow root in the manual, so the app's CSS and the
   Heritage Spec CSS never collide.

## Tools

- `scripts/capture-snippet.js` — paste it into the page with the browser JavaScript tool. It
  installs `__umCap`, `__umCheck`, `__umExport` and `__umClear`, and stores captures in
  `sessionStorage` so they survive navigation within the same origin. Re-paste it after each
  navigation.
- `scripts/capture-bridge.py` — local server (127.0.0.1 only) that serves the snippet and the
  frame driver with CORS for **one** origin and stores POSTed exports:
  `python3 capture-bridge.py --origin https://<app-origin> --directory <skill>/scripts --exports /tmp/um-exports --port 8767`.
  Pick a free port first (`lsof -iTCP:<port> -sTCP:LISTEN`): other local apps squat ports (Okta
  Verify listens on 8769).
- `scripts/frame-driver.js` — `__umFrame({ width, height, snippetUrl })` drives a same-origin iframe
  at the device width chosen in Step 0 (375 × 812 for mobile, ≥ 1280 for desktop): `load(path,
  readySelector)`, `capture(name, element, { floating })`, `fill(input, value)`, `textInput(root)`,
  `button(root, text)`, `modal(text)`, `waitFor(selector)`. It re-injects the snippet after each
  navigation and captures with `fixedWidth` when the width is a phone's.
- If the page's Content Security Policy blocks evaluated code, inject scripts served by the bridge as
  a `<script>` carrying the page's own nonce:

  ```js
  const source = await fetch('http://127.0.0.1:8767/capture-snippet.js').then((response) => response.text());
  const script = document.createElement('script');
  script.nonce = [...document.scripts].map((existing) => existing.nonce).find(Boolean);
  script.textContent = source;
  document.head.appendChild(script);
  ```

- Keep each browser JavaScript call under the tool timeout (about 45 s). Split long flows (open,
  fill, confirm, wait for polling, capture) into several calls, and wait for long timers (polling
  retries, inactivity modals) with `sleep` in the shell between calls; a timed-out call can stop
  halfway and leave the page in an intermediate state.
- `scripts/embed-app-frames.mjs` — Node, no dependencies. Injects the captures into the manual
  and is safe to re-run.

## Workflow

### 1. Pick the environment

- Use the URL the user gives. Otherwise prefer a local dev server or a sandbox/test environment.
- Production is acceptable **only for read-only navigation**, and only when the user points to it.
- **The app's language may come from the user's profile, not from the browser** (`Accept-Language`
  does not change it). When the account opens in another language, capture it as it is and replace
  each app text with the reader's locale through the catalogs (`__umCap` `pairs`: pt-BR `msgstr` →
  its msgid → es-AR `msgstr`), never with your own translation; set the capture's `lang` shell to the
  reader's locale.
- If authentication, SSO, or TLS gates appear, the user completes them; never type credentials.

### 2. Plan the captures

List every mockup the manual needs, with a stable `name` and the state to reach. For example:
`main`, `filters`, `filters-experience`, `bulk-step1`, `modal-default`, `session-queue`.

**Cover every variant of every screen**, not only the happy path. Derive the list from the code:
each branch of the view (empty, loading, list), each modal, each notice/snackbar, each validation
error the server can return, each limit, each creation error, each result screen (successes,
failures, empty, pending, polling that ends in error) and each guard page (invalid configuration,
forbidden). If a variant cannot be reached with the existing fixtures, create a temporary mock for it
(next section).

Reach each state **from the UI** the way a user would: open menus, modals, dropdowns, toggles,
and fill fields locally.

**In any shared environment (production, sandbox, staging), never confirm, submit, save, delete,
or apply anything.** Close modals with Cancel or ✕. A read-only lookup that populates a view (for
example adding IDs to a local queue) is allowed; the final confirmation is not.

**States that only exist after a mutation** (a result screen with successes and failures, a
"pending segments" result, a lock badge, a row marked "Failed") are captured against the app
running **locally with HTTP mocks**. There, confirming is safe because the request never leaves the
machine:

1. Start the app in its local development mode with the project's mock layer. Use the fixtures the project already has for those scenarios
   and pick inputs that hit them (for example the operator IDs and access that the scenario
   fixture keys on).
2. Before confirming, check which requests the flow makes and that each one has a fixture. With
   recording mock layers such as `frontend-mocks`, **a missing fixture proxies to the real upstream
   and writes its response to disk**, real data and headers included.
3. After each flow, run `git status --short mocks/` (or the mock directory). Delete every fixture
   that was recorded from a real upstream right away. Treat anything it shows as seen real data
   and add it to the sanitization pairs.
4. When a scenario needs a fixture that does not exist, create a temporary one with synthetic data
   only: no `headers` property and no keys that start with `x-`. List every temporary file (for
   example in `/tmp/um-temp-fixtures.txt`) and delete them all when the captures are done.
5. Report any real personal data found in committed fixtures; do not copy it into the manual.

#### Temporary mocks for every variant

- **Map the upstreams first.** Read the REST clients the flow uses (base URL config key + path) and
  compare them with the interceptors the mock layer registers. Add the missing interceptors before
  opening the app — in a worktree or temporary branch, never in the user's checkout. A confirmation
  through an unintercepted path creates real data in the shared environment.
- **One synthetic persona per variant**, reused across screens: for example a valid collaborator, an
  inactive account, another site, a position not allowed, an activity already in progress. Reuse the
  example people the project fixtures already use (`Ada Lovelace`, `Grace Hopper`) when they exist.
- **Fixtures keyed on the signed-in user** (their attributes, their permissions) need the real ID in
  the path. Read it from the page (SSR props), pass it to the shell through the bridge, write the
  fixture with synthetic content, and never print the ID in the manual. Create it **before** the
  first request that needs it.
- **Sequences:** polling endpoints take an outer array (`[pending, done]`). The mock layer keeps a
  per-file counter that wraps around and survives page loads, so give each scenario its own ID
  (`900011` result, `900012` empty, `900013` failure) instead of reusing one file.
- **Error variants of the same request:** swap the fixture content (for example a 403 for the create
  call), capture, and restore it right away. Modify shared fixtures only through a backup you
  restore and check with `git status`.
- **Verify after every flow** that nothing was recorded: `git status --short --untracked-files=all
  mocks/` must list only your temporary files, and the dev log must not say "Writing the mock".
- **Data fetched on mount or in SSR props** (a list loaded in a `useEffect`, a page prop computed in a
  server hook): a browser-side XHR stub installed after the page loads misses those requests, and
  tabs or filters often do not fetch again. In the throwaway worktree, import a stub module at the
  top of the page entry, gated by a query parameter (`?um_fixture=…`), so it runs before React
  mounts; and in the server hook, replace the props with synthetic values under `env.DEVELOPMENT`
  and the same parameter. Read flags for other variants (empty list) from `sessionStorage` when the
  stub starts. Both edits die with the worktree.
- **Password and credential forms:** never type into a password field from the browser, not even a
  test value. Seed each state (rules half met, all met, confirmation that does not match) from the
  throwaway worktree: page props filled under the fixture parameter, with example values written in
  the code. Stub the save request in the browser so it never reaches the server, and confirm in the dev
  log that nothing arrived. Do not trigger the success path when it signs the user out. In the export,
  replace every `value` of a password input with the same number of `x`, so the manual never ships an
  example password readers could copy.
- **Mock debug logs (`DEBUG=mock:*`) print request headers**, session ids included. Never dump them;
  grep only the lines you need and delete the log at the end.

### 3. Capture

```js
// after pasting capture-snippet.js
__umCap('main', document.querySelector('.page-root'), { pairs: [['Real Name', 'Ada Lovelace'], ['9282', '621601']] });
__umCap('filters', document.querySelector('[role="dialog"]'), { floating: true, pairs });
__umCap('card-list', document.querySelector('.list'), {
  pairs,
  transform: (clone) => clone.querySelectorAll('.list__row:nth-child(n+3)').forEach((row) => row.remove()),
});
```

- `element`: the smallest node that shows the whole state. For portals, modals, and popovers,
  capture the dialog or popover itself and pass `floating: true`.
- `transform(clone)`: trim long lists (keep 1–3 rows), drop pagination, or remove content the
  manual does not document. Never edit the live page.
- Check the returned `blockedSheets`. A cross-origin stylesheet that blocks `cssRules` is not
  copied; report it and fall back to a hand-drawn mockup if the capture loses its styles.
- Close transient layers (dropdowns, tooltips, focus rings) before capturing unless they are the
  point of the mockup. Blur the active element first.
- `floating: true` also releases the viewport-based `max-height` of inner scroll areas whose
  content already fits (a modal body capped at `100vh - N`). Otherwise the manual cuts them at
  its own viewport height.

#### Responsive captures: media queries become container queries

`@media` queries evaluate against the **viewport**, and in the manual that is the reader's screen,
not the frame. Copied as they are, a breakpoint fires in the frame for the wrong width.

So the snippet rewrites them:

- **Width-only queries** (`(max-width: 719px)`, `screen and (min-width: 1200px)`, comma lists)
  become `@container um-viewport (…)`. The runtime makes each capture's content that container and
  sizes it at `min(capture viewport width, reader viewport width)` (fixed-width mobile captures stay
  at their width). A desktop capture shows the desktop layout on a desktop reader and the app's own
  mobile layout on a phone, and it re-lays out when the window is resized.
- **`vw`** becomes `cqw` (container width) and **`vh`** is resolved to pixels against the capture
  viewport height (`captureViewportHeight`): a frame has no height of its own, and leaving `vh` live
  makes captures as tall as the reader's window, which moves everything positioned in them.
- **Queries that also use height, orientation or aspect ratio** are resolved against the capture
  viewport and flattened, as before. Queries about the reader (hover, reduced motion, print) stay
  conditional. `@container`, `@layer` and `@supports` keep their wrapper.

Consequences:

- Capture desktop screens in a window at least 1280 px wide; the narrower layouts come from the
  app's own breakpoints at reading time.
- Inline pixel sizes the app computed from the layout (a dropdown as wide as its field, a popover
  position) only match the layout they were measured in; if a floating layer does not line up in a
  narrow reader, capture that state on mobile too.
- Exports made before this change keep flattened queries; recapture them to get responsive frames.

#### Mobile captures (375 px)

When the flow is used on mobile (Step 0), capture **every** screen at 375 px; when it is used on
both, capture the screens whose mobile layout differs:

1. Inject `frame-driver.js` in any page of the app and create the driver:
   `const driver = __umFrame({ width: 375, height: 812, snippetUrl: 'http://127.0.0.1:8767/capture-snippet.js' })`.
   The iframe is same-origin and borderless (a border shrinks `innerWidth`), so it shares
   `sessionStorage` with the tab and its viewport is exactly 375 px.
2. Navigate with `await driver.load(path, readySelector)` and reach each state inside the iframe.
   React-controlled inputs need `await driver.fill(input, value)` (native setter + `input` event).
   Pick the field with `driver.textInput(dialog)`: the first `input` of a form is often a **hidden
   CSRF field**, and writing there silently does nothing.
3. Capture with `await driver.capture(name, element, { floating })`; on mobile it passes
   `fixedWidth`, so the manual renders the capture 375 px wide inside `.mockup--mobile`.
4. `embed-app-frames.mjs` gives every capture its own stylesheet, so mobile rules never restyle
   desktop captures.

### 4. Sanitize: mandatory, no exceptions

- Build `pairs` from the **real values visible in the fragment**: names, surnames, initials in
  avatars, user and entity IDs, usernames, emails, phones, addresses, leaders, internal
  facility or tenant names, and free text typed by real users. Replace them with obvious example
  values used consistently across all captures (the same example person everywhere).
- `pairs` also cover `aria-label`, `title`, `alt`, `value`, `placeholder`, `href`, `id`, `for` and
  ancestor attributes, not just visible text.
- Replace longer strings first (a full name before a first name).
- The snippet drops **hidden inputs** (CSRF tokens, session ids) and reduces absolute `href` and
  `action` values to their path, so environment hosts do not travel in the payload. Still check:
  the runtime removes `href` at render time, but the payload is in the manual's source.
- Same-origin images (`<img src="/icon.webp">`) would resolve against the manual's host and show
  empty, so the snippet inlines every **loaded** one as a data URI. `__umCap` lists the ones that were
  not loaded yet (`unloadedImages`, lazy images below the fold): scroll them into view and capture
  again. `check-manual.mjs` fails on any root-relative image left in the payload.
- Before exporting, run `__umCheck([...all real values seen])` with the signed-in user's name, username,
  user id and account ID among them. It must return `[]`. If not, recapture with more pairs, or
  post-process the stored HTML.
- After embedding, `grep` the final manual for the same values. Zero hits is the requirement.

### 5. Export and embed

- Prefer the bridge: `await __umExport('app-captures.json', { endpoint:
  'http://127.0.0.1:8767' })` writes it to the bridge's `--exports` directory, without browser
  downloads. Without `endpoint` it downloads to the browser's folder (see "Downloads" in `SKILL.md`).
- **Verify the file on disk before `__umClear()`.** From the second download on a site, Chrome may
  block it silently or show a "download multiple files" prompt that only the user can accept
  (**Allow** / **Permitir**). If the file does not appear within a few seconds, ask the user about
  that prompt instead of waiting. If downloads stay blocked, POST the payload to the local snippet
  server instead: an endpoint bound to `127.0.0.1` that accepts only the app's origin and plain
  `[a-z0-9-]+.json` file names.
- Sanitization pairs match **within one text node or attribute**. A value split across elements
  (`ID: <span>50</span>`), or text such as `ID: 50` with no delimiter to anchor a pair, can
  survive. `__umCheck` catches it; fix it by post-processing the exported HTML before embedding.
- In the manual, put an empty host inside each mockup, after the `mockup-bar`:

  ```html
  <div class="mockup">
    <div class="mockup-bar">…</div>
    <div class="app-frame" data-cap="filters"></div>
  </div>
  <div class="figcap">Panel “Filtrar” con los seis filtros (datos de ejemplo).</div>
  ```

- The `mockup-url` holds only the path of the captured page (`/tools/user-management`) or the
  dialog title, never the host of the environment it was captured from.

- Embed:

  ```bash
  node <skill-dir>/scripts/embed-app-frames.mjs ~/Downloads/app-captures.json user-guides/<slug>.html --page-background=<app page background>
  ```

  `--page-background` is the app's page color, so cards and modals sit on the same background as
  in the product. Read it from the app's `body` computed style.

- Pass several exports to combine sessions (for example old captures plus new local-mock and
  mobile captures). Rule indexes are remapped, and for a repeated capture name the later file wins:

  ```bash
  node <skill-dir>/scripts/embed-app-frames.mjs old.json local.json mobile.json user-guides/<slug>.html --page-background=#ededed --host-css=design-system-host.css
  ```

- `--host-css=<file>` adds rules for the design system's floating layers when the generic host CSS
  is not enough, for example releasing a modal's inner scroll area or pinning a popover root:

  ```css
  [data-capture-root] .ds-modal__scroll,[data-capture-root] .ds-modal__content{max-height:none!important;overflow:visible!important;}
  ```

- The script writes `<span data-app-frames-meta>Capturas: YYYY-MM-DD</span>` into the
  header's `doc-meta` (and replaces it on re-runs), so readers know how current the screens are.
- The runtime renders frames lazily (IntersectionObserver, 800 px ahead). Each host gets
  `role="img"` and `aria-label="Captura de pantalla: <figcap>"`, while the rendered capture is
  `inert` and `aria-hidden`. `beforeprint` renders everything for print and PDF.

- Every mockup is followed by a `div.figcap`; the runtime uses it as the frame's `aria-label`.
  Mobile captures go in `.mockup.mockup--mobile` (410 px, centered), which keeps pins in place.
- App pages often have `position: fixed` headers or action bars. The runtime makes each capture's
  content their containing block, so they stay inside the frame at the captured width; without it
  the fit step would scale the whole capture down to a sliver.
- Pages with `min-height: 100vh` keep the captured height (vh resolved), which can leave a lot of
  empty space. Release it per manual with `--host-css`
  (`[data-capture-root] .page-wrapper{min-height:0!important}`) when the empty area adds nothing.
- A container sized from `vh` with its own scroll (`overflow:auto`, a grid row filling the screen)
  becomes a fixed-height box that **cuts what was below the fold** (the last row of a menu). Release
  its height and the parent's (`[data-capture-root].page{height:auto!important}`,
  `[data-capture-root] .list{height:auto!important;overflow:visible!important}`) so the capture shows
  every item, and check the last item is visible.
- Pins on captures use `data-target` (DESIGN.md, "Puntos sobre capturas"); the runtime places them
  after every fit and resize. Verify the distance pin → element at 1280 px and 390 px.

### 6. Everything you want to show must be fully visible

A capture that shows a dropdown, menu, popover, tooltip or modal is only useful if that layer is
**entirely inside the frame**. The embed runtime fits each frame after rendering:

- trims captured empty space above and below;
- keeps floating layers (popovers, the modal ✕) inside with 16px of air;
- narrows the content when a fixed-position layer sticks out of a fluid root;
- scales down as a last resort.

Still, measure every frame in the browser. Lazy frames only render when visible, and
IntersectionObserver does not fire in a background tab, so first force every frame to render with
`window.dispatchEvent(new Event('beforeprint'))` and wait a few seconds. The check must return
`[]`:

```js
[...document.querySelectorAll('.app-frame')].flatMap((host) => {
  const page = host.shadowRoot.querySelector('.app-frame__page');
  const pageRect = page.getBoundingClientRect();
  const box = { l: Infinity, t: Infinity, r: -Infinity, b: -Infinity };
  page.querySelectorAll('[data-capture-root], [data-capture-root] *').forEach((element) => {
    const rect = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    if (!rect.width || !rect.height || style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return;
    box.l = Math.min(box.l, rect.left); box.t = Math.min(box.t, rect.top);
    box.r = Math.max(box.r, rect.right); box.b = Math.max(box.b, rect.bottom);
  });
  const gaps = [box.t - pageRect.top, pageRect.bottom - box.b, box.l - pageRect.left, pageRect.right - box.r].map(Math.round);
  return gaps.some((gap) => gap < 16) ? [[host.dataset.cap, gaps]] : [];
});
```

Then look at a screenshot of each frame that shows an open layer. If a layer is cut, recapture it
from a position where it opens inside its container, or trim the fragment with `transform`.

### 6b. The cascade order must match the app

Which rule wins between two selectors of the **same specificity** depends only on their order.
Real case: the design system ships `.ds-button__content *{display:block}` and the app ships
`.change-rep-modal__icon-label{display:inline-flex}`. The app CSS loads later, so in the product
the icon sits centered next to its text. In the manual the design system rule won, the label became a
block, and the ★/↺ icons sat above the baseline.

- `capture.rules` lists each capture's rules in the order the page walked its stylesheets, which
  is the cascade order. `embed-app-frames.mjs` gives each capture its own stylesheet in exactly
  that order and shares the rule texts by index. **Never sort rules globally or by registry
  index**: the registry grows in discovery order across captures and pages, which is not the
  cascade order.
- When a frame looks slightly off (an icon misaligned, a gap missing, text wrapping differently),
  compare computed styles instead of guessing. Open the same state in the app, then measure the
  same element in the app and inside the frame's shadow root:

  ```js
  // Run in the app, then in the manual with root = host.shadowRoot; compare the two outputs.
  const describeTree = (element) => {
    const base = element.getBoundingClientRect();
    return [element, ...element.querySelectorAll('*')].map((node) => {
      const style = getComputedStyle(node);
      const rect = node.getBoundingClientRect();
      return [node.tagName, style.display, style.float, style.lineHeight, Math.round(rect.top - base.top), Math.round(rect.width)];
    });
  };
  ```

  The first differing `display` or position points at the rule that lost or won in the wrong
  order. Check `capture.rules` for both rules, then fix the embed, not the captured HTML.

### 7. Verify visually

Serve the manual locally (`python3 -m http.server --bind 127.0.0.1`), open it in the browser and
compare every frame against the live screen. Scroll with `behavior: 'instant'` before each
screenshot, because `html{scroll-behavior:smooth}` makes `scrollIntoView` animate and the
screenshot lands mid-scroll. Fix anything that differs: a floating layer still
off-flow, a shell adding height, or a missing font. Also confirm that the frames render in the
final destination (for example the document viewer where it is published). Delete the downloaded JSON when done, or tell
the user where it is.

## Fallback

Use hand-drawn Heritage Spec mockups (`mockup-body`) only when the app cannot be opened, a gate
blocks access, or stylesheets are cross-origin and blocked. In that case, say in the report that
the mockups are approximations.

## Troubleshooting

- **Dates in the capturing browser's locale:** `toLocaleDateString(undefined, …)` follows the browser
  (an en-US Chrome writes `10/05/2026` for 5 October). Rewrite them in the export to the readers'
  format (`05/10/2026`) before embedding, and check the source to know which call formats them.
- **Root-relative images in a capture** (`<img src="/icon.webp">` not loaded when captured):
  `check-manual.mjs` reports them. Fetch each file from the local dev server and replace the `src`
  with a data URI in the export, or recapture after the images load.
- **Pins on a page with tabs:** a capture of the whole page also holds the hidden tab panels, so a
  selector such as `.ds-button__content` + text can match a hidden copy first. Scope the
  `data-target` to the visible panel's own class.

- **A row of a grid list captured alone loses its layout** (name and buttons piled up in the middle):
  the grid template lives in inline styles of the list container, and ancestors are copied as empty
  shells. Capture the whole list and remove the other rows in `transform`. For the same reason, scope
  pin selectors to the captured part (`.sub-list .ds-checkbox__checkbox`), not to a class that an
  ancestor shell also has (`.card-row`).
- **A tooltip or coachmark that sticks out of its modal** (`fit` reports a negative gap): capture the
  modal's overlay (`.ds-modal__overlay`) with `floating: true`, so the layer fits as in the app.
- **The dev server waits on an interactive upgrade prompt** in a throwaway worktree: pipe the
  answer (for example `yes n | npm run start-dev`) so it answers no and keeps going.
- **Dev server does not start:** use the Node version in `.nvmrc` (some frameworks reject unsupported
  majors), run `npm ci` in a worktree instead of reusing another branch's `node_modules`, and build
  the artifacts the dev server expects (for example the remote-modules manifest produced by the
  project's `postbuild` webpack config).
- **A lookup says "invalid" but no request reached the server:** the value never got into React
  state; fill the visible input with the native setter (`driver.fill`).
- **A modal title is missing from `innerText`:** some design systems render the title outside the
  visible text; find the modal by its class or body text instead.
- **The viewer shows an old version** right after publishing: refresh the viewer's cache and reload with a cache-busting query.
- **Checks of the current section or scroll fail only in automation:** the tab is in the background
  (`document.visibilityState === 'hidden'`), where `requestAnimationFrame` and scroll events do not
  run. Bring the tab to the front or dispatch the event manually.
