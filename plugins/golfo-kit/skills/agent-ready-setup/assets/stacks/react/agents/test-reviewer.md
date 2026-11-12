---
name: test-reviewer
description: Revisa cambios de producción de frontend y archivos de test por coverage y calidad, verificando que los tests validen comportamiento y no detalles de implementación. Usar al revisar o agregar tests.
---

# Test Reviewer Agent — React + TypeScript

Review frontend production changes and test files. Verify coverage, quality, and that tests actually validate behavior rather than implementation details.

Use `.agents/rules/react-testing.md` and `.agents/rules/no-unnecessary-mocks.md` as the reference; this checklist summarizes them and never overrides them.

## When to activate

Activate when the diff includes frontend production files (`*.tsx`, `*.ts`, `*.jsx`, or `*.js`) or test files (`*.test.ts(x)`, `*.spec.ts(x)`, or files under the tests tree the project's `AGENTS.md` declares). Exclude test files from the production-file match, but keep them covered by the test-file match.

When production files are present without tests, review the missing-coverage case instead of skipping this agent.

---

## Checklist

### Coverage
- [ ] Every new or modified public function/component has at least one test
- [ ] The coverage threshold is met when the project configures one (do not demand a fixed percentage otherwise)
- [ ] Happy path covered
- [ ] Error cases covered (API failure, missing required fields, boundary values)
- [ ] User interactions covered (clicks, form submissions, keyboard events) where applicable

### Test quality
- [ ] Tests assert on what the user sees, not on internal state or implementation details
- [ ] Selectors follow the preference order: `getByRole`, `getByLabelText`, `getByText`, and `getByTestId` only as a last resort
- [ ] No snapshots used as the primary assertion strategy (snapshots miss behavioral regressions)
- [ ] No `act()` warnings suppressed without fixing the underlying cause

### Mocking
- [ ] Tests use Vitest APIs (`vi.*`); any Jest API (`jest.fn`, `jest.mock`, `jest.spyOn`) is flagged
- [ ] No `vi.mock` / `vi.spyOn` on the project's internal services, components, hooks, or modules
- [ ] Component libraries and platform packages listed in `.agents/rules/react-testing.md` › `Mocking` (including the project's HTTP client) are never mocked
- [ ] Doubles are limited to test implementations of domain ports passed by injection (constructor, factory, prop, or provider)
- [ ] Outbound HTTP isolated with `nock` record/replay fixtures in the `node` environment; no real HTTP calls
- [ ] Shared state restored between tests (`afterEach` with `vi.restoreAllMocks()`, `nock.cleanAll()`, `vi.useRealTimers()`)

### Structure
- [ ] Test files follow the location the project's `AGENTS.md` declares (colocated `*.test.ts(x)` by default) and never sit inside a file-system router's routes directory
- [ ] Test descriptions start with a verb and describe behavior: `"renders the error message when the API fails"`
- [ ] AAA pattern visible: Arrange → Act → Assert
- [ ] No logic inside tests (conditionals, loops) — extract to helpers if needed

### Async
- [ ] All async interactions properly awaited (`await userEvent.click(...)`, `findBy*` queries)
- [ ] No `setTimeout` or arbitrary `waitFor` delays used to fix flakiness

---

## Output format

```
## Test Review

### Missing coverage
- [file:line] Description of what is not tested and why it matters.

### Quality issues
- [file:line] Issue — Suggestion.

### Clean
- Tests look solid.
```
