## Mandatory execution

- Run the relevant tests before marking any change as done; verify they pass.
- When functionality is added, modified, or removed, add or update the corresponding tests in the same change.
- If tests cannot be executed in the current environment, add an Error section stating what could not be validated and why.

## Runner

- Use Vitest and import the test APIs from `vitest` (`describe`, `it`, `test`, `expect`, `vi`). Never introduce Jest or its APIs (`jest.fn`, `jest.mock`, `jest.spyOn`); when you find them in a draft, translate them to the Vitest equivalent or remove the mock.
- Run component and hook tests in a DOM environment (`jsdom` or `happy-dom`) and service, adapter, and route-handler tests in the `node` environment.

## Structure and naming

- Use `describe` with `it` or `test` blocks; group scenarios by behavior.
- Name each test after the behavior and its condition, for example `shows the error banner when the API returns 500` or `should do X when Y`. Keep the style the project already uses.
- Follow Arrange-Act-Assert (AAA) or Given-When-Then (GWT); separate the steps with a blank line or comments like `// Arrange` when it helps reading. No conditionals or loops inside test bodies.

## Placement

- Follow the test location the project's `AGENTS.md` declares: a separate `tests/` tree that mirrors the source, or colocated files.
- When it declares none, colocate `example.test.ts` / `example.test.tsx` next to `example.ts` / `example.tsx`, and keep the existing naming if the project already uses another one consistently.
- In Next.js App Router projects, never place tests inside the routes directory (`app/` or `src/app/`), where colocated files can become route artifacts: test pages, layouts, loading states, and route handlers from a separate tree that mirrors it.

## Coverage expectations

- Include at least one happy path and the significant edge cases for each key behavior.
- Cover error cases and atypical scenarios defensively.
- Assert both outputs and the side effects that matter to the behavior.
- When the project configures a coverage threshold (for example `test.coverage.thresholds` in the Vitest config), the suite must meet it. Do not demand a fixed percentage when the project configures none.

## Never test source text

- Do not use `fs`, filesystem helpers, snapshots, or raw source reads to assert exact file contents.
- Do not test implementation text in source, style files, SQL strings, ORM/query-builder call parameters, or SQL fragments such as `SELECT`, `JOIN`, `WHERE`, aliases, ordering clauses, or whitespace.
- For SQL or query behavior, validate user-facing filters, returned data, repository/service contracts, persisted effects, or integration behavior through the real query boundary when feasible.
- For styles, validate user-visible state, accessibility, class application only when it is the public styling contract, visual regression tooling, or the real build/lint command.

## Isolation

- Exercise the project's own code for real: no `vi.mock` or `vi.spyOn` on internal services, components, hooks, or modules. See [before-applying-mocks.md](before-applying-mocks.md).
- Keep tests independent: restore shared state in `afterEach` and never rely on execution order.

## Error-reporting feedback contracts

When a flow reports failures to a support diagnostic sink (error tracker) or uses an error-reporting feedback component, test the complete observable contract rather than only the visible copy:

- An actionable or unexpected failure with a real error context renders the error-reporting component and preserves the safe public message.
- Loading, expected domain states, empty results, validation feedback, and successful outcomes do not render the error-reporting component.
- Missing error context uses a safe fallback message and never fabricates context.
- Changing the selected resource, closing/reopening a modal, starting a new attempt, or retrying clears stale `errorMessage` and `errorContext` before the next request.
- A degraded `202` response with `EXTERNAL_REQUIREMENT_PENDING` and no explainable requirements preserves the public status and carries safe error context when the product contract requires support tracking.
- Error-reporting detail assertions verify allowlisted diagnostic fields and the absence of raw conditions, upstream payloads, request/response objects, headers, cookies, tokens, secrets, and full PII.
- Retry assertions verify that the callback is safe and does not create duplicate mutations.

Prefer route/service contract tests for the response `error_context` and component tests for rendering, cleanup, retry, and fallback behavior. Do not assert implementation-only logger calls unless logging is the explicit contract; assert the sanitized public/diagnostic projection instead.

## Output requirements

- Deliver runnable test code with complete imports, setup, and teardown.
- After the code, add a brief Commentary block explaining coverage and suggesting enhancements.
- End with a Validation paragraph confirming coverage, correctness, and any gaps or manual steps.
- If any part cannot be tested automatically, add an Error section describing the limitation and a manual workaround.
