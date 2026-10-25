---
name: prevent-ssr-hydration-mismatches
description: Prevents and diagnoses React SSR hydration mismatches in server-rendered routes and components (Next.js, Remix, custom Express/Node SSR, or any framework that hydrates server HTML) by keeping server HTML and first client render deterministic. Use whenever implementing, changing, reviewing, or debugging SSR or hydration, preloaded or query-derived initial UI, server-rendered code that touches browser-only APIs, feature flags, dates, randomness, locale, timezone, media queries, storage, invalid HTML nesting, client-only libraries, hydration warnings, or content changing during initial load—even when user does not mention hydration. Do not use for purely CSR components that never hydrate server HTML.
license: MIT
metadata:
  version: "1.1.0"
  author: "Guido Modarelli"
  category: "frontend"
  tags: "react, ssr, hydration, frontend"
  command: "/prevent-ssr-hydration-mismatches"
---

# React SSR Hydration Consistency

## Core invariant

Keep this sequence deterministic:

```text
server source of truth
  → safe serialized snapshot
  → identical first client render
  → browser-only and live updates after hydration
```

Hydration compares server HTML with first client render. A later effect may intentionally update UI, but first client tree must still match server tree. Fix source of divergence instead of suppressing warning.

## Workflow

### 1. Map SSR and hydration boundary

Before editing, locate:

- server route/controller/page that builds render props;
- the framework's preloaded-state channel (page props, loader data, serialized store, or a custom serializer);
- client entrypoint calling `hydrate` or `hydrateRoot`;
- constructors, lazy initializers, render functions, and HOCs that derive initial state;
- direct reads from `window`, `document`, `navigator`, storage, `matchMedia`, current time, randomness, locale, or timezone.

Trace every value that can change visible markup. Record server value and first client value separately.

### 2. Reproduce exact mismatch

Use same URL, query, user context, device, locale, timezone, and feature-flag assignment seen in failure. Capture:

- React hydration warning and component diff;
- server-rendered markup or relevant subtree;
- preloaded state sent to browser;
- first client props/state before effects;
- browser console and `onRecoverableError` output.

Do not blame CSS, bundles, extensions, or React until server/client values are compared.

### 3. Classify root cause

Classify before choosing fix:

1. Different data source between server and client.
2. Browser-only API read during initial render.
3. Non-deterministic value (`Date`, random value, generated ID).
4. Locale/timezone/device mismatch.
5. Feature flag or external data changed without snapshot.
6. Invalid HTML nesting repaired by browser parser.
7. Client-only library rendered without stable SSR boundary.
8. External DOM mutation, such as browser extension, after code causes are ruled out.

### 4. Fix narrowest source of divergence

Prefer single shared initial source. Keep post-hydration behavior unchanged unless it causes separate defect. Avoid modifying child component when parent supplies inconsistent initial prop.

### 5. Prove consistency

Add behavior-level regression test, run relevant tests and the project's real build, then verify affected URL in browser with console and network evidence.

## Deterministic initial-state contract

### Server data is authoritative for first render

If server already has request/query/flag/data value, normalize once and serialize it. Client must consume serialized value for first render rather than rereading browser environment.

```js
// Server/controller
const initialParams = pickAllowedInitialParams(validatedQuery);

return res.render(View, {
  initialParams,
  results,
});
```

```js
// View
const initialParams = resolveInitialParams(props.initialParams);

const preloadedState = {
  ...publicProps,
  initialParams,
};

return <Page preloadedState={preloadedState}>{/* same initial tree */}</Page>;
```

Treat serialized empty object as authoritative. Falling back to `location.search` when server sent `{}` reintroduces dual source.

```js
const hasSerializedState =
  initialParams !== null &&
  typeof initialParams === 'object' &&
  !Array.isArray(initialParams);

return hasSerializedState ? initialParams : getQueryParams();
```

### Validate and allowlist request-derived state

Validate query/body/params before controller reads them, using the project's schema validation library and route conventions. Copy explicit supported keys into new object; do not spread arbitrary `req.query` into state or service options.

```js
const INITIAL_PARAM_KEYS = ['page', 'search', 'sort'];

const pickAllowedInitialParams = (query = {}) => {
  const params = {};

  INITIAL_PARAM_KEYS.forEach((key) => {
    if (Object.prototype.hasOwnProperty.call(query, key)) {
      params[key] = query[key];
    }
  });

  return params;
};
```

Preserve URL-facing representation in snapshot. Derive separate copy for service-specific conversion, such as one-based to zero-based page.

### Serialize only browser-safe data

Never put these in preloaded state, inline JSON, globals, URL, or hydration props:

- cookies, session IDs, CSRF values, access/refresh tokens;
- authorization headers or request headers;
- secrets, credentials, internal configuration;
- unnecessary PII or full authenticated-user payloads.

Send minimum public fields required to render. Rely on the framework's serializer rather than hand-built script/JSON injection. React escaping does not make sensitive data safe to expose.

## Browser-only APIs

Reading browser state during first client render is unsafe when server cannot produce same value:

- `window`, `document`, `navigator`;
- `localStorage`, `sessionStorage`;
- `matchMedia`, viewport width, DOM measurements;
- browser-only SDKs.

Do not use `typeof window !== 'undefined'` branch that changes markup:

```jsx
// Wrong: server and first client render different trees.
return typeof window === 'undefined' ? <Skeleton /> : <Dashboard />;
```

Render stable shared fallback first, then update after hydration:

```jsx
const [browserPreference, setBrowserPreference] = useState(null);

useEffect(() => {
  setBrowserPreference(readBrowserPreference());
}, []);

return browserPreference === null
  ? <StableFallback />
  : <PreferenceAwareView value={browserPreference} />;
```

If server already knows device/context, serialize it and use same value on client instead of waiting for effect. Prefer the project's existing media-query helper that receives server device context.

### Preferences visible on first paint (theme, density, locale UI)

The effect-based fallback above is correct but flashes the default before the stored value applies. For a preference that changes the whole page's look, pick the first option that works:

1. **Server already knows it.** Store the preference in a cookie when the user changes it and read it during SSR, so the HTML ships final (`<html data-theme="dark">`). No script, no flash, no mismatch.
2. **Server cannot know it** (first visit, value only in `localStorage`, system `prefers-color-scheme`). Inline a tiny blocking script in `<head>` that runs before first paint and before hydration, reads the value and sets an attribute or class on `document.documentElement`. CSS keys off that attribute, so React-rendered markup stays identical on server and client.

```tsx
const THEME_BOOTSTRAP_SCRIPT = `(function(){try{var stored=localStorage.getItem('${THEME_STORAGE_KEY}');var theme=stored||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');document.documentElement.dataset.theme=theme;}catch(error){}})();`;

<html lang={locale} suppressHydrationWarning>
  <head>
    <script nonce={cspNonce} dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP_SCRIPT }} />
  </head>
  <body>{children}</body>
</html>
```

- Touch only `<html>`/`<body>` attributes, never text or elements React renders: changing React-owned markup before hydration recreates the mismatch.
- `suppressHydrationWarning` goes on `<html>` only, because the script changes its attributes on purpose; it applies one level deep and does not cover children.
- Script content is a static constant: never interpolate user data, request values or server responses into it. Pass the CSP nonce if the project uses one. Wrap storage access in `try/catch` (private mode, disabled storage).
- Components that need the value in JS read it after hydration (from the attribute or storage) behind the stable fallback above; prefer the project's existing theme provider if it already implements this script.
- Write the cookie as well when the user changes the preference, so later visits use option 1.

Source: rules `rendering-hydration-no-flicker` and `rendering-hydration-suppress-warning` from vercel-labs/agent-skills `react-best-practices` (MIT, Vercel), adapted.

## Time, randomness, IDs, locale, and timezone

Avoid values generated independently during render:

- `Date.now()`, `new Date()` used in visible output;
- `Math.random()`;
- counters or module-global IDs;
- locale formatting based on implicit runtime defaults;
- timezone-sensitive formatting with different server/client zones.

Choose matching strategy:

- Calculate once on server and serialize value.
- Use fixed locale/timezone supplied by request context.
- Use stable domain ID from data.
- Use React `useId` only when component tree/order is identical.
- Defer truly browser-specific display until after hydration behind stable placeholder.

Do not “fix” mismatch by freezing stale data forever. Snapshot only initial render; reconcile live data after hydration.

## Data and feature flags

External data or feature flags can change between SSR and hydration. Capture per-request snapshot used to render HTML and serialize same decision/result.

Do not reevaluate initial feature flag in browser before hydration. After hydration, subscribe/refetch only when product behavior requires live updates.

When data cannot be serialized safely, render stable non-sensitive boundary and fetch after hydration. Keep initial server and client boundary identical.

## HTML structure

Browser parser repairs invalid HTML before React hydrates. Check:

- block elements nested inside `<p>`;
- nested interactive elements (`button` inside `button`, link inside link);
- invalid table/list children;
- duplicated/relocated `<html>`, `<body>`, metadata, or form elements;
- different wrapper/tag chosen by server and client.

Fix semantic markup. Do not suppress parser-caused mismatch.

## Client-only libraries

For library that reads browser globals during import/render:

1. Keep SSR boundary deterministic.
2. Render identical placeholder on server and first client render.
3. Load/import library after hydration when possible.
4. Isolate library to smallest client-only subtree.
5. Preserve dimensions to avoid layout shift.

Do not convert whole page to CSR when only one widget is client-only.

## `suppressHydrationWarning`

Use only when difference is unavoidable, local, harmless, and intentionally not reconciled—for example externally controlled timestamp text, or the `<html>` attributes set by a pre-hydration preference script (see "Preferences visible on first paint"). Apply at smallest element and document reason. It silences only that element's own attributes and text, one level deep: children still warn, and the DOM still keeps the server value until something re-renders it.

Never use it to hide:

- different query/props/state sources;
- browser-only branching;
- invalid nesting;
- feature-flag drift;
- missing snapshot;
- broad page/subtree mismatch.

A warning suppression is not proof of consistent DOM.

## Regression test recipe

Prefer real platform components and behavior over mocks. Build same tree for SSR and hydration.

```jsx
const tree = buildTree({ initialParams: { search: 'foo' } });
const serverMarkup = renderToString(tree);
const recoverableErrors = [];
const container = createTestContainerFromTrustedMarkup(serverMarkup);

act(() => {
  hydrateRoot(container, tree, {
    onRecoverableError: (error) => recoverableErrors.push(error),
  });
});

expect(recoverableErrors).toStrictEqual([]);
expect(within(container).getByRole('textbox')).toHaveValue('foo');
```

Test both:

- non-empty serialized state that controls conditional markup;
- serialized empty/default state while browser URL/storage differs, proving snapshot remains authoritative;
- relevant locale/timezone/device/flag scenario;
- no recoverable hydration error;
- observable DOM and interaction, not source-code strings.

Use test-only trusted `renderToString` output when constructing hydration container. Never use untrusted HTML.

## Build and runtime validation

1. Run focused regression tests.
2. Run related existing component/controller tests.
3. Run lint for modified files.
4. Run the project's real development and production builds.
5. Start app at project development URL.
6. Hard reload affected deep link with exact query/context.
7. Inspect browser console for hydration warnings.
8. Capture snapshot and XHR/fetch statuses without exposing headers/cookies.
9. Report `PASS`, `FAIL`, or `BLOCKED`; never present auth/environment block as success.

Use the project's runtime-verification tooling or browser automation for browser runtime evidence.

### Agent compatibility

Steps 6–8 use whichever browser mechanism the session actually has, per row «Verificar en un navegador» of [`agent-capabilities.md`](../../references/agent-capabilities.md); look for the concrete tool in the session or in `PATH`, not for the agent's name. What matters here: hydration warnings are logged **while the page loads**, so the mechanism must capture console output from the first script, not only after you attach.

- Claude in Chrome or a connected browser MCP: open the deep link, hard reload, then read the console.
- Codex `chrome@openai-bundled` plugin: `tab.reload()` and then `tab.dev.logs({ levels: ["error", "warn"] })`.
- Hermes `browser_exec`: register the listener before navigating (for example a CDP script added on new document), then reload. If it fails to start twice, use the terminal fallback.
- Any agent with a shell: Chrome headless with `--enable-logging --log-file` or Playwright with `page.on("console")` before `page.goto` ([commands](../../references/agent-capabilities.md#verificación-en-navegador-por-terminal)). They have no user session: use them for routes that render without sign-in or with the project's test credentials.

If the route needs the user's session and no real-browser tool is available, report runtime validation as `BLOCKED` and add an `Agent limitations` section to the final report with what was not checked and how to check it.

## Scope boundaries

- General fetch architecture and async effect cancellation: use `react-data-fetching-best-practices`.
- Render performance: use `react-render-performance-patterns`.
- User-facing translations: follow the project's i18n conventions.
- Route input schemas: apply the project's input-validation conventions alongside this skill.

This skill owns consistency between SSR HTML and first client render.

## Final checklist

- Same source controls server HTML and first client render.
- Serialized empty/default state remains authoritative.
- Request-derived values validated and copied by allowlist.
- No secrets, tokens, headers, sessions, or unnecessary PII serialized.
- No browser-only reads changing initial markup.
- Time/random/IDs/locale/timezone deterministic.
- Data and feature flags use same initial snapshot.
- HTML nesting valid.
- Client-only libraries have stable minimal boundary.
- `suppressHydrationWarning` absent or narrowly justified.
- First-paint preferences come from a cookie read on the server; a pre-hydration script, if used, only touches `<html>`/`<body>` attributes and interpolates no user data.
- `renderToString` + `hydrateRoot` regression passes with zero recoverable errors.
- Project build passes.
- Browser hard reload checked and result reported with evidence.
