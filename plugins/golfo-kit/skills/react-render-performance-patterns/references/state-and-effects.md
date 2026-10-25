# State, Effects and Render Shape

Companion to the SKILL.md patterns. Several items adapt rules from vercel-labs/agent-skills `react-best-practices` (MIT, Vercel), rewritten for this skill.

## Contents

- Correctness rules (apply always)
- Re-render patterns (apply when profiling shows the cost)
- Out of scope here

The first section lists bugs, not optimizations: fix them whenever you see them. The second section follows the SKILL.md rule — measure first, then apply the pattern that matches the cost you saw. With React Compiler active, several of the second-section patterns are already done for you (see "React Compiler" in SKILL.md).

## Correctness rules

### Derive values during render, not in an effect

If a value can be computed from current props and state, compute it in the render body. Copying it into state through `useEffect` costs an extra render and lets the copy drift from its source.

```tsx
// Wrong: state mirror kept in sync by an effect.
const [visibleOrders, setVisibleOrders] = useState<Order[]>([]);
useEffect(() => setVisibleOrders(orders.filter(isOpen)), [orders]);

// Right: derive it (wrap in useMemo only if the filter is measurably expensive).
const visibleOrders = orders.filter(isOpen);
```

To reset state when an identity prop changes, give the component a `key` instead of an effect that calls `setState`.

### Put interaction logic in the event handler

A side effect caused by a specific action (submit, click, drop) belongs in that handler. Modeling it as `setSubmitted(true)` plus an effect that watches `submitted` re-runs the effect when unrelated deps change and can fire the action twice.

```tsx
function handleSaveClick() {
  saveDraft(draft);
  notifySaved();
}
```

### Never define a component inside another component

`const Row = () => ...` inside a parent's body is a new component type on every render, so React unmounts and remounts it: inputs lose focus on each keystroke, local state resets, effects re-run, animations restart. Move it to module scope and pass what it needs as props.

### Do not list an Effect Event in dependencies

`useEffectEvent` returns a function whose identity changes on purpose every render. Call it from inside the effect (or a subscription the effect creates) and keep only the reactive values in the dependency array; adding the Effect Event makes the effect re-run every render.

```tsx
const onTick = useEffectEvent((elapsedMs: number) => reportProgress(jobId, elapsedMs));
useEffect(() => {
  const intervalId = setInterval(() => onTick(Date.now() - startedAt), POLL_INTERVAL_MS);
  return () => clearInterval(intervalId);
}, [startedAt]);
```

Use `useEffectEvent` (stable since React 19.2; on older versions, a ref updated with the latest handler in an effect) when an effect must read the latest callback or value without re-subscribing whenever it changes.

### Use a functional update when the next state depends on the previous one

`setItems((current) => [...current, nextItem])` always reads the latest state, so callbacks don't close over stale values and don't need the state in their deps. Direct values are fine when the new state does not depend on the old one (`setStatus('idle')`).

### Render conditionally with an explicit boolean

`{count && <Badge count={count} />}` renders a literal `0` when `count` is `0` (and `NaN` likewise). Use `count > 0 ? <Badge count={count} /> : null` or coerce with `Boolean(count)`.

### Keep derivations immutable

Code inside `useMemo`, a selector or a render-time derivation must not mutate its inputs. `Array.prototype.sort`, `reverse` and `splice` mutate in place: called on a prop or on state they change the parent's data, break referential checks and can leave memos returning a reordered input. Use `toSorted`, `toReversed`, `toSpliced` and `with`, or copy first (`[...rows].sort(compare)`) when the target runtime lacks them.

### Run app-wide initialization once per load

`useEffect(() => initAnalytics(), [])` runs again on every remount and twice under Strict Mode in development. Put one-time client setup in the entry module, or guard it with a module-level flag in client code. This is client-only: on the server, module scope is shared by concurrent requests, so request data never goes there (`refactor-ssr-data-fetching` → [server-cache-and-concurrency.md](../../refactor-ssr-data-fetching/references/server-cache-and-concurrency.md#estado-de-módulo)).

## Re-render patterns

Apply these when the Profiler shows the component re-rendering or recomputing often enough to matter.

| Cost you observed | Pattern |
|---|---|
| Expensive initial value recomputed every render (`useState(buildIndex(items))`, `JSON.parse(storage)`) | Lazy init: `useState(() => buildIndex(items))`. Not needed for primitives or cheap literals. |
| High-frequency value (pointer position, scroll offset, timer id, "is dragging") re-renders the tree but no UI reads it during render | Store it in `useRef`; update the DOM node directly if it must move something on screen. |
| Effect re-runs because an object dep changes identity while the field it uses did not | Depend on the primitive (`[order.id]`, not `[order]`), or derive a boolean outside the effect (`const isCompact = width < COMPACT_BREAKPOINT_PX`) and depend on that. |
| Component subscribes to continuous state but only needs a threshold | Subscribe to the derived boolean (`useMediaQuery(...)`) instead of the raw value (`useWindowWidth()`). |
| Component subscribes to dynamic state (search params, storage) only to read it inside a callback | Read it at the point of use inside the handler instead of subscribing at render. |
| One `useMemo`/`useEffect` does independent jobs with different deps | Split it: one hook per job, so a change in one input reruns only its job (the SKILL.md Pattern 3 pipeline). |
| `React.memo` child keeps re-rendering although callers pass nothing new | A non-primitive default param (`onSelect = () => {}`, `items = []`) is a new value every render: hoist it to a module constant (`const NO_ITEMS: Item[] = []`). |
| Large static JSX or SVG rebuilt on every render | Hoist the element to module scope. React Compiler does this automatically. |
| Expensive panel, tab or menu toggles often and loses state or remounts slowly | On React 19.2+, wrap it in `<Activity mode={isOpen ? 'visible' : 'hidden'}>` to keep state and DOM while hidden (older versions: keep it mounted and hide it with CSS, or lift its state). Effects are cleaned up while hidden, so subscriptions resume on show. |
| Manual `isLoading` flag around a non-urgent update, flipping in `try/finally` | React 19+ only (check `react` in `package.json`): `const [isPending, startTransition] = useTransition()` and run the update inside `startTransition`; `isPending` covers the whole async action. On React 18, `startTransition` takes only a sync callback and `isPending` resets before the `await` finishes, so keep the explicit loading state there and resets even when it throws. Transitions make rendering interruptible, not responses ordered: two overlapping async actions can finish out of order and the older one can overwrite newer state, so keep an ordering guard (request id or `AbortController` checked before the `setState` after the `await`). Request lifecycle, abort and error states follow `react-data-fetching-best-practices`. |

## Out of scope here

- Fetching data in effects, deduplication and race cancellation: `react-data-fetching-best-practices`.
- Values that differ between server HTML and first client render (dates, storage, theme): `prevent-ssr-hydration-mismatches`.
- Storage reads in hot paths and listener cost on scroll or touch: `measured-performance-optimization` → [main-thread-long-tasks.md](../../measured-performance-optimization/references/main-thread-long-tasks.md).
- What each loading, empty or error state shows: `ui-ux-flow-patterns`.
