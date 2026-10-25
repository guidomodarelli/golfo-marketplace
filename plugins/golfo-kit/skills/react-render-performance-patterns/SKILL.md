---
name: react-render-performance-patterns
description: Apply React render-performance and update-priority patterns (startTransition/useDeferredValue for input responsiveness, useMemo/useCallback/React.memo to cut re-renders, equality guards before setState, stable identities, library-specific reset/identity gotchas, plus state and effect hygiene such as derived state computed in render instead of effects, components defined inside components, useEffectEvent, lazy useState, useRef for transient values, Activity, useTransition loading, immutable sorts in memos, and React Compiler awareness). Use this skill whenever the user reports or wants to prevent UI jank, typing lag, frozen pages, "Maximum update depth exceeded", slow tables/lists/grids/filters, or asks to optimize, memoize, speed up, or reduce re-renders in any React/Next.js component — even when they don't name a specific API. Also use when porting these optimizations to other components or projects.
license: MIT
metadata:
  version: "1.0.0"
  author: "Guido Modarelli"
  category: "frontend"
  tags: "react, performance, memoization, transitions, rendering"
  command: "/react-render-performance-patterns"
---

# React Render Performance Patterns

Patterns for components whose interactions trigger expensive re-renders — typically large filterable tables, lists or grids with rich per-row content. The goal is the same everywhere: **keep urgent interactions (typing, clicking, dropdown selection) instant while heavy work happens off the critical path, and stop re-renders that produce no visible change.**

Use these as a toolkit, not a checklist. Measure first, apply the pattern that fits the bottleneck, and always explain *why* a given change helps.

## Diagnose before optimizing

Memoization is not free — it adds dependency arrays, allocates closures, and obscures data flow. Apply it where there is a real cost, not reflexively. Before changing anything, locate the bottleneck:

1. **What feels slow?** Typing lag, slow filter/sort, janky scroll, frozen click. The symptom points to the fix: input lag → update priority (transitions); slow derived data → memoize the computation; child re-renders → stable props + `React.memo`.
2. **What re-renders on each interaction, and is the work necessary?** Use React DevTools Profiler (or "Highlight updates"). A component re-rendering is only a problem if its render is expensive or it cascades to expensive children.
3. **Is the same value being recomputed or the same state being set to an equal value?** That is the cheapest win — guard it (see Equality guards).

4. **Is React Compiler on?** Check `next.config.*` (`reactCompiler: true`, or `experimental.reactCompiler` in older Next.js), the Babel/Vite config (`babel-plugin-react-compiler`) and `package.json`. With the compiler active, the manual memoization of Patterns 2–4 (`useMemo`, `useCallback`, `React.memo`, hoisted JSX) is usually redundant: profile first and add it only where the compiler bailed out (the React DevTools "Memo ✨" badge is missing, or the compiler's lint reports a skipped component). Patterns 1, 5, 6, 7 and the correctness rules in [state-and-effects.md](references/state-and-effects.md) still apply.

Order of attack that usually works: **fix update priority → memoize the expensive derived data → stabilize identities so memo/`React.memo` actually hold → add equality guards for no-op updates → fix library-specific reset/identity gotchas.**

## Pattern 1 — Split urgent from non-urgent with `startTransition`

When one event must do two things — one cheap and user-facing (keep the input and its suggestions responsive) and one expensive (re-filter/re-render a large tree) — run the cheap update urgently and wrap the expensive one in a transition so React can interrupt it for the next keystroke.

```tsx
const handleQueryChange = useCallback((nextQuery: string) => {
  // Urgent: the input and its suggestions dropdown must respond to every key.
  setQueryDraft(nextQuery);

  // Non-urgent: re-filtering re-renders the whole table. Defer it as a
  // low-priority transition so typing never blocks behind the filter pass.
  startTransition(() => {
    setAppliedFilters(parseQuery(nextQuery));
  });
}, []);
```

Why it works: state updates inside `startTransition` are interruptible. If the user types again before the heavy render finishes, React throws away the in-progress render and starts fresh, so the input never stutters.

Notes:
- The urgent update (`setQueryDraft`) must stay **outside** the transition, or it loses its priority.
- `useDeferredValue(value)` is the read-side equivalent: when you receive an expensive value as a prop and want to render a lagging copy without owning the setter, derive `const deferred = useDeferredValue(value)` and feed `deferred` to the expensive subtree. Reach for it when you can't wrap the setter.
- Optionally surface `const [isPending, startTransition] = useTransition()` to dim/spinner the stale region while the transition runs.

## Pattern 2 — Memoize the expensive subtree, with deps chosen deliberately

The most expensive thing to render is usually a list/table body. Memoize the *rendered nodes* so unrelated local state (a toolbar draft, focus, an input value) does not rebuild the whole body.

```tsx
const tableBodyRows = useMemo(() => {
  return rowModelRows.map((row) => (
    <TableRow key={row.id}>
      {row.getVisibleCells().map((cell) => (
        <TableCell key={cell.id}>{renderCell(cell)}</TableCell>
      ))}
    </TableRow>
  ));
  // columnVisibility is included on purpose: it changes which cells render
  // without changing the rowModelRows reference, so it must invalidate the memo.
  // emptyMessage is kept OUT on purpose: it flips between filtered/unfiltered
  // and would needlessly rebuild every row on the first keystroke.
}, [columnVisibility, renderCell, rowModelRows]);
```

The dependency array is the whole game:
- **Include** every value that changes *what is rendered* even if the linter can't see it referenced lexically (here `columnVisibility` toggles `getVisibleCells()` output). Document why.
- **Exclude**, deliberately and with a comment, values that change on every interaction but don't affect this subtree — pulling them in silently re-renders everything you were trying to protect.
- When you intentionally diverge from `react-hooks/exhaustive-deps`, leave the `// eslint-disable-next-line` plus a comment explaining the choice, so the next reader doesn't "fix" it back into a perf bug.

## Pattern 3 — Memoize derived data as a pipeline

When data flows through several transforms (filter → exclude → predicate → sort), memoize each stage with precise deps so a change in one input only recomputes downstream of it, not the whole chain.

```tsx
const rowsMatchingFilter   = useMemo(() => match(rows, query),        [rows, query]);
const rowsExcluding        = useMemo(() => exclude(rowsMatchingFilter, excluded), [rowsMatchingFilter, excluded]);
const rowsForTable         = useMemo(() => sort(rowsExcluding, sorting),          [rowsExcluding, sorting]);
```

Every stage must return a new value and leave its input untouched. The `sort` helper above has to use `rowsExcluding.toSorted(compare)` (or copy first: `[...rowsExcluding].sort(compare)`), never `rowsExcluding.sort(compare)`: an in-place `sort`/`reverse`/`splice` reorders the previous stage's memoized array (or the prop/state it came from), so upstream data changes behind React's back and the memo returns the same, now-mutated reference. Use `toSorted`/`toReversed`/`toSpliced`/`with` for the same reason anywhere in a derivation.

Each `useMemo` returns a stable reference when its inputs are unchanged, which keeps the *next* stage's memo (and any `React.memo` child consuming it) from invalidating. The chain is only as good as its weakest reference — one stage that rebuilds an array every render breaks every memo below it.

## Pattern 4 — Stabilize identities with `useCallback` and `React.memo`

`useMemo`/`React.memo` only help if the props feeding them keep a stable identity. An inline `onClick={() => ...}` or `columns={[...]}` rebuilt every render defeats every downstream memo.

- Wrap event handlers passed into memoized children or column definitions in `useCallback` with honest deps.
- Memoize `columns`/config objects with `useMemo` so the table/list doesn't see "new columns" each render.
- Wrap an expensive presentational child in `React.memo` so it skips re-render when its props are referentially equal. This pays off only when the parent re-renders often **and** the child's props are actually stable — otherwise it's overhead. Add a `displayName` for debuggability.

```tsx
const handleToggle = useCallback((id: string, checked: boolean) => {
  setSelected((prev) => withToggled(prev, id, checked));
}, []);

const PaymentCell = React.memo(function PaymentCell(props: PaymentCellProps) {
  /* expensive cell with popovers/menus */
});
```

## Pattern 5 — Guard against no-op state updates

Setting state to a value that is structurally equal still triggers a render (and invalidates memos that depend on it). When a handler fires on every keystroke, propagating equal values cascades into wasted re-renders of the whole tree. Compare first; bail when nothing changed.

```tsx
// In the setState updater: return the previous reference to short-circuit.
setColumnFilters((prev) => {
  const next = computeNext(prev);
  return areColumnFiltersEqual(prev, next) ? prev : next;
});

// Before propagating to channels: only push values that actually changed.
if (!areStringArraysEqual(parsed.excluded, currentExcluded)) {
  onExcludedChange(parsed.excluded);
}
```

Returning the *previous reference* from a `useState`/`useReducer` updater makes React bail out of the render entirely. Write small structural-equality helpers (`areStringArraysEqual`, `areColumnFiltersEqual`, …) rather than `JSON.stringify`, which allocates and is order-sensitive.

## Pattern 6 — Use O(1) lookup structures inside hot paths

Inside filters, predicates, and per-row render, an `array.includes`/`array.find` turns the pass into O(n·m). Build a `Map`/`Set` once (memoized) and look up in O(1).

```tsx
const lenderNamesById = useMemo(
  () => new Map(lenders.map((lender) => [lender.id, lender.name])),
  [lenders],
);
const selectedIds = useMemo(() => new Set(selection), [selection]);
// hot path: selectedIds.has(row.id)  // O(1) per row instead of O(n)
```

## Pattern 7 — Library reset/identity gotchas (TanStack Table & similar)

Headless data libraries keep internal reactive state; two recurring traps:

- **Auto-reset feedback loops.** Without pagination/expansion, leaving auto-resets on means each filter change calls `resetPageIndex` → `setPagination` → re-render → reset again: `Maximum update depth exceeded` and a frozen page while typing. Disable the resets you don't need: `autoResetPageIndex: false`, `autoResetExpanded: false`.
- **Don't depend on the library instance identity.** In TanStack Table v8 the `table` object returned by `useReactTable` keeps the same reference across renders while its internal state changes, so a memo keyed on `[table]` never invalidates and renders stale output. Depend on what actually changes instead: the state slices you render from (`table.getState().columnVisibility`, `sorting`, …) or the row model read into a local before the memo (`const rowModelRows = table.getRowModel().rows`).

## State, effects and render shape

Many re-render and correctness problems are not memoization problems: state mirrored by an effect, interaction logic modeled as state + effect, components defined inside components, effects re-subscribing because of unstable callbacks or object deps, `&&` rendering `0`, expensive `useState` initializers, manual loading flags, toggled panels that remount. Read [state-and-effects.md](references/state-and-effects.md) when the symptom involves `useEffect`, `useState` initialization, refs, `useEffectEvent`, `<Activity>`, `useTransition` for loading, or lost input focus/state on each render. Its correctness rules apply always; its re-render patterns follow the measure-first rule above.

## Applying these to other components / projects

When porting these patterns elsewhere:
1. Reproduce and locate the bottleneck first (Diagnose section). Don't memoize blindly.
2. Match the symptom to the pattern: input lag → Pattern 1; expensive derived value → Patterns 2–3; child re-renders → Pattern 4; no-op updates → Pattern 5; O(n) lookups in hot paths → Pattern 6; "max update depth"/headless lib → Pattern 7; effects, state init, remounts or lost focus → [state-and-effects.md](references/state-and-effects.md).
3. Keep the urgent path outside transitions and the heavy path inside them.
4. Leave a one-line comment on every non-obvious dependency-array choice and every intentional lint suppression — these are the lines that get silently reverted into regressions.
5. Verify: re-profile and confirm the re-render count / interaction latency actually dropped. A memo that doesn't reduce renders is just complexity.

## Anti-patterns to avoid

- Memoizing trivially cheap values (a string concat, a `+`) — the bookkeeping costs more than it saves.
- `React.memo` on a component whose props change every render — pure overhead.
- `JSON.stringify` as an equality check in a hot path — allocates and is key-order sensitive.
- Suppressing `exhaustive-deps` without a comment — the next reader can't tell a deliberate exclusion from a bug.
- Wrapping the urgent UI update inside `startTransition` — it loses priority and the input lags anyway.
- Adding `useMemo`/`useCallback`/`React.memo` in a project where React Compiler already memoizes the component.
- `sort()`/`reverse()`/`splice()` on props or state inside a memo or derivation.
- Reaching for these patterns before measuring — premature memoization hides data flow and rarely targets the real cost.
