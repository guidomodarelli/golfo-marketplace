# Testing Rules — Frontend (React + TypeScript)

Standards for writing and reviewing tests. The `test-reviewer` agent uses this file as the reference for what a good test looks like in this stack.

---

## Framework

- Use **Vitest** with **React Testing Library (RTL)** for unit and integration tests. Import the test APIs from `vitest` (`describe`, `it`, `expect`, `vi`); never introduce Jest or its APIs (`jest.fn`, `jest.mock`, `jest.spyOn`).
- Run component tests in a DOM environment (`jsdom` or `happy-dom`) and service, adapter, and route-handler tests in the `node` environment (per file with `// @vitest-environment node`, or per project in the Vitest config).

## TDD cycle

Work test-first for every change in behavior (features, bug fixes, and architectural changes that alter behavior), always in this order. For a refactor that preserves behavior, skip the failing-test step: confirm the affected behavior is covered by passing tests before you start, add the missing behavioral coverage first if it is not, and keep those tests green throughout.

1. **Testing** — write the smallest failing test at the right layer, defining the expected behavior first. One clear behavior per test.
2. **Code** — implement the minimum code that makes it pass, respecting the module boundaries; do not skip ports, mappers, or value objects to move faster.
3. **Refactor** — only once the behavior is covered: improve naming, remove duplication, and tighten boundaries without changing behavior.
4. **Green** — the cycle ends when the new behavior is covered by passing tests.

This order also governs the generator skills (`component-creation`, `service`, `api-endpoint`): when a skill lists the test step after the implementation steps, write that test first and then implement. When a skill has no test step (for example `api-endpoint`), add the test the layer requires (an integration test for a handler or server hook) before implementing, and run it.

## What to test by layer

- **`domain`** — unit tests for entities, value objects, and pure business rules.
- **`application`** — unit tests for use cases with doubles for the domain ports, passed by injection.
- **`infrastructure`** — integration tests for adapters, DTO mappers, auth wiring, and provider or database boundaries.
- **Routes and UI** — RTL tests for server/client boundaries, rendering, and critical user flows.
- **End-to-end** — smoke coverage for critical authentication and authorization flows.

## Coverage

- When the project configures a coverage threshold (for example `test.coverage.thresholds` in the Vitest config), the suite must meet it; do not add or raise a threshold on your own.
- Every new or modified public component and function must have at least one test.
- API handlers and server hooks require integration tests.

## What to test

- **Happy path** — expected inputs produce expected outputs.
- **Error cases** — API failures, missing required fields, boundary values.
- **User interactions** — clicks, form submissions, keyboard navigation.
- **Async and error tracking states** — follow `Tests` in `user-facing-feedback.md`.
- **Middleend boundaries** — invalid input rejected at the route boundary, no duplicated validation in handlers, a valid public DTO consumed and an unusable one rejected safely, upstream responses consumed without schema revalidation, and no raw upstream payload in responses, logs, or public errors. Exercise the real validator instead of mocking it.
- Do not test implementation details — test what the user sees and does.

## Selectors (in order of preference)

1. `getByRole` — semantic and accessible.
2. `getByLabelText` — form fields.
3. `getByText` — visible content.
4. `getByTestId` — last resort, only when no semantic alternative exists.

Avoid snapshot tests as the primary assertion strategy — they detect change, not correctness.

## Mocking

- Exercise the project's own code for real: never `vi.mock` or `vi.spyOn` the project's internal services, components, hooks, or modules.
- Never mock the design system's component libraries or the SSR framework's platform packages; render and call them for real.
- **Doubles only for injected ports**: when a unit depends on a domain port (repository, gateway, clock, notifier), pass a test implementation of that port through the constructor, the factory, a prop, or the project's provider — never by intercepting module imports.
- **Outbound HTTP**: do not mock the project's HTTP client — isolate it with `nock` record/replay (`nock.back`) in the `node` environment; HTTP calls are captured as fixtures. No real HTTP calls in tests.
- Time and randomness are controlled with `vi.useFakeTimers()` / `vi.setSystemTime()`, or with an injected clock port, and restored after each test (`vi.useRealTimers()`).
- Restore shared state between tests in `afterEach` (`vi.restoreAllMocks()`, `nock.cleanAll()`, fake timers).
- See `no-unnecessary-mocks.md` for the full strategy and setup.

## React warnings

- A React development warning logged during a test fails that test: switches between controlled and uncontrolled inputs, missing or duplicated list keys, updates outside `act`, updates while rendering another component, and unknown DOM props. Install the guard once in the test setup file (wrap `console.error` and `console.warn`, keep forwarding every call, and fail in `afterEach` when a matching warning was recorded).
- Fix the component instead of silencing the console; for warnings about updates outside `act`, follow the `react-act-test-fixes` skill. Accept a warning only when it comes from a dependency that cannot be fixed in the project, in an explicit allowlist next to the guard that names the affected suite and the reason.
- A controlled input (`value`, `checked`) stays controlled for its whole life: represent "nothing selected" with the component's empty value (`""`, `false`, or a `null` the component accepts), never with `undefined`.

## Async

- Await all async interactions: `await userEvent.click(...)`, use `findBy*` queries for elements that appear after async operations.
- Never use arbitrary `setTimeout` delays to fix flakiness — find and fix the root cause.

## Structure

- Test file location: follow the convention the project's `AGENTS.md` declares (a separate `tests/` tree that mirrors the source, or colocated files). When it declares none, colocate `*.test.ts` / `*.test.tsx` next to the file under test, and keep the existing naming if the project already uses another one consistently.
- Exception, only in Next.js App Router projects (a `next` dependency with routes under `app/` or `src/app/`): never place tests inside that routes directory, where colocated files can become route artifacts. Put tests for pages, layouts, loading states, and route handlers in a separate tests tree that mirrors it. In other projects, `app/` is an ordinary source folder and colocated tests stay valid.
- Description format: start with a verb describing behavior — `"shows the error banner when the API returns 500"`.
- Follow AAA: Arrange → Act → Assert. No logic (conditionals, loops) inside test bodies.
