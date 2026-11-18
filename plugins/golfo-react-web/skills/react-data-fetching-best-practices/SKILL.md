---
name: react-data-fetching-best-practices
description: Best practices for React data fetching, server-first. Use when adding or updating data flows so data needed for the first render is read on the server (Server Components, loaders, route handlers) and the client fetches only when an interaction requires it; client fetching happens from a single entry point (prefer a container component), duplicated requests are avoided via shared state, loading/error states show user feedback, endpoint responses are mapped to props, and async useEffect flows avoid race conditions with AbortController cancellation, cleanup, and safe state updates. Also use for stale responses overwriting newer ones, canceled requests logged as errors, or a client wrapper that does not accept a signal.
license: MIT
metadata:
  version: "1.0.0"
  author: "Guido Modarelli"
  category: "frontend"
  tags: "react, data-fetching, server-first, containers, loading-states, useEffect, abortcontroller, race-conditions"
  command: "/react-data-fetching-best-practices"
---

# React Data Fetching Best Practices

## Quick start

Read data on the server whenever it is available during the request. Fetch from the client only for data that an interaction requests later, do it once in the container component, share it with child views, handle loading/error feedback, map endpoint responses into view props, and cancel stale requests in async effects.

## 1. Server-first: decide where the data is read

1. Data that the first render needs and that is available during the request is read on the server: a Server Component, a route loader, or the framework's server data hook. It reaches the UI as props, without a client request after hydration.
2. Data requested after an interaction (search, filter, pagination, polling, refetch, mutation) may start in the browser, but goes through a same-origin route handler or BFF endpoint of the app, never straight to an upstream service.
3. Fetch in the client only when one of the cases above requires it; do not add a `useEffect` fetch for data the server could have rendered.

For the routing hierarchy, the BFF boundary (authentication, validation, authorization, ownership), browser-safe DTOs, and the exceptions that allow a direct upstream call, apply `refactor-ssr-data-fetching` instead of repeating it here.

## 2. Client fetching workflow

1. Pick a single entry point for data fetching (prefer the container or route-level component, or one hook it owns).
2. Share fetched data across views instead of re-fetching per view; reuse the data-fetching library or cache the project already has before writing effects by hand.
3. Track loading and error states and render user feedback for each state, distinguishing a real empty result from loading or failure.
4. Map endpoint responses to view props to keep UI components focused on rendering.

### Guidelines

- **Single entry point**: Fetch data in one place (container, route component, or hook) and pass it down as props.
- **No duplicate calls**: Reuse shared state or cache results when multiple views need the same data.
- **State feedback**: Always render explicit loading and error feedback, not just empty UI.
- **Endpoint to props**: Normalize or map API responses into view-friendly props to separate data concerns from UI.
- **Separation of concerns**: Keep data fetching logic out of presentational components whenever possible.

## 3. Async effects without race conditions

When an async `useEffect` can run more than once (for example, because its dependencies change quickly), cancel the in-flight request with `AbortController`; a boolean `canceled` flag alone does not cancel the request and is not the primary mitigation.

- Create `const controller = new AbortController()` inside the effect and pass `signal: controller.signal` to the HTTP client (Fetch, Axios, or the project's REST client). If the project's client wrapper does not accept `signal`, extend it to accept `{ signal }` and forward it to the underlying request.
- Return a cleanup that always calls `controller.abort()`.
- Keep an effect-local `isActive` guard as a safety net for late microtasks or non-abortable work.
- Ignore cancellation errors explicitly (`error.name === 'AbortError'` for Fetch, `error.code === 'ERR_CANCELED'` or `error.name === 'CanceledError'` for Axios): no log, no error state, no toast.
- Keep error messages specific: name the operation that failed and the key identifiers (for example `userId`).

Read [async-effect-cancellation.md](references/async-effect-cancellation.md) for a copy-ready implementation.

## Quick checklist

- Data available during the request is read on the server, not fetched by the client after hydration.
- Client requests after an interaction go through a same-origin route handler or BFF endpoint.
- Client fetching has a single entry point in the container or route component.
- Shared data prevents duplicate requests across views.
- Loading, error, and empty states render clear feedback.
- Endpoint responses are mapped to view props.
- Async effects abort stale requests in their cleanup and ignore cancellation errors.
