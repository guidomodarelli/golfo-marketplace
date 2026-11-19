---
name: test-best-practices
description: Standardizes automated tests with Vitest and Testing Library — naming and AAA structure, placement per the project's AGENTS.md (colocated *.test.ts(x) by default, never inside App Router routes), coverage expectations, strict assertions, isolation limited to injected domain ports and nock HTTP fixtures (no mocks of internal services, components, the design system or platform packages), per-locale or per-market variants, error-reporting feedback contracts (retries, loading, empty states, stale errors, async modal flows), and running tests before closing any change. Use whenever creating, updating, refactoring, or reviewing tests, including drafts that use Jest APIs.
license: MIT
metadata:
  version: "2.0.0"
  author: "Guido Modarelli"
  category: "testing"
  tags: "testing, vitest, react, testing-library, nock, i18n"
  command: "/test-best-practices"
---

## Quick start

- Use Vitest (`vi.*`, APIs imported from `vitest`); never default to Jest. Translate Jest APIs found in drafts to Vitest or remove the mock.
- Open `references/conventions.md` for every request: mandatory execution, naming, structure, placement, coverage, error-reporting contracts, and the output blocks.
- For component/hook tests, also open `references/tests-by-component.md`, `references/expectations.md`, and `references/before-applying-mocks.md`.
- For texts or behavior that vary by locale, market, or tenant, open `references/tests-by-locale.md` and apply the `describe.each` pattern.

## Non-negotiable rules

- Never `vi.mock` or `vi.spyOn` the project's internal services, components, hooks, or modules, and never mock the design system or framework/platform packages.
- Doubles only for domain ports passed by injection; outbound HTTP is isolated with `nock` record/replay fixtures in the `node` environment.
- Never assert source text, styles, SQL strings, or query-builder call parameters; assert observable behavior or public contracts.
- Meet the coverage threshold only when the project configures one.
- Run the relevant tests before marking a change as done; if they cannot run, state what was not validated and why.

## Resources

- See [conventions.md](references/conventions.md) for execution, naming, placement, coverage, error-reporting contracts, and output requirements.
- See [tests-by-component.md](references/tests-by-component.md) for the project's test-utils wrapper and provider setup.
- See [expectations.md](references/expectations.md) for assertion rules and examples.
- See [before-applying-mocks.md](references/before-applying-mocks.md) for the isolation workflow: injected ports, `nock`, and time.
- See [tests-by-locale.md](references/tests-by-locale.md) for `describe.each` patterns across locales, markets, or tenants.
