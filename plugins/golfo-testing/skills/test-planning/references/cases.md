## Rule: Generate base cases, edge cases, and data mocks

When asked to generate tests, propose scenarios, or create a test plan, provide base cases, edge
cases, and data mocks ready to use.

### Requirements

- **Identify inputs**: props or arguments, state, dependencies, callbacks, permissions, and i18n when applicable.
- **Base cases**: cover the main flow (render, key props, user events, state changes, async when
  applicable), scaling the number of cases to the behavior's risk and complexity.
- **Edge cases**: list boundary scenarios relevant to the unit under test, for example:
  - empty list, list with one item, very large list
  - `null` or `undefined` props when they can be missing
  - invalid or incomplete props (missing optional fields)
  - error and loading states
  - long texts or extreme values (0, negatives, maximums)
  - failing dependencies (API, hook, selector)
- **Data mocks**: propose mocks aligned to the real shape of props or responses:
  - minimal valid dataset (required fields only)
  - typical dataset (2 to 3 representative items)
  - edge dataset (empty, missing fields, or error)
- **Suggested variants**: for each edge case, provide at least one variant and the expected
  assertion (empty state, fallback, error UI, disabled, default props, etc.).
- **Valid test goals**: every case asserts observable behavior or a public contract. For code backed
  by queries, styles, or other source artifacts, assert what they produce — returned data, applied
  filters, persisted effects through real query execution, user-visible state — or rely on the real
  build/lint command, because tests tied to source text or query-construction internals break on
  harmless refactors without catching real regressions.

### Output format

- `Base cases`: list with the expected outcome or primary assertion.
- `Edge cases`: list with the expected outcome or primary assertion.
- `Mocks`: reusable data blocks.
- `Notes`: assumptions, factories, or helpers used.

### Notes

- If the repo has mock factories or helpers, reuse them.
- If there are optional callbacks, include one case with the callback missing and another
  validating the call with correct arguments.
