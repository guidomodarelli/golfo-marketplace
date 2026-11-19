## Rule: Create a coverage plan and identify gaps

When asked to improve coverage, create tests, or audit quality, deliver a coverage plan and state
which routes, modules, components, and states are not covered.

### Requirements

- **Inventory**: list routes or pages, key components, and relevant hooks (according to the router
  and repo structure).
- **Test map**: link each element to its existing tests (unit, integration, e2e).
- **Gaps**: mark routes without tests, components without tests, and props or states without coverage.
- **Prioritized plan**:
  - P0: critical flows, permissions, errors, forms, integrations.
  - P1: alternative states and prop variants.
  - P2: visual or lower-risk cases.
- **Actionable output**: for each gap, propose the test type and the assert goal.
- **What counts as a gap**: a gap is missing coverage of observable behavior or a public contract —
  returned data, applied filters, persisted effects, user-visible state. Measure query- and
  style-backed code by those outcomes, since source-text or query-construction assertions do not
  protect behavior and are not needed for coverage.

### Output format

- `Checklist`: table with route or component, props or state, existing tests, and gaps.
- `Plan`: prioritized list P0/P1/P2 with recommended test type.
- `Notes`: assumptions, missing routes, or lack of context.

### Notes

- If the repo already has testing conventions, follow them (wrappers, utilities, factories).
- If there are no tests, state it and propose a minimal first set.
- Avoid a huge list: prefer a concise plan ordered by impact.
