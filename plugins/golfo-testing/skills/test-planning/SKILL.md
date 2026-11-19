---
name: test-planning
description: Plans tests before writing them. Cases mode lists base cases, edge cases, and data mocks aligned to the real shape. Coverage mode maps existing tests, finds gaps by route, module, or state, and prioritizes them P0/P1/P2. Use when test scenarios, initial test plans, mock data, coverage audits, or test prioritization are requested.
license: MIT
metadata:
  version: "1.0.0"
  author: "Guido Modarelli"
  category: "testing"
  tags: "testing, test-plan, edge-cases, coverage, prioritization"
  command: "/test-planning"
  plugin-dependencies: "golfo-javascript"
---

# Test Planning

Pick the mode from the request. If it asks for both, run coverage first and generate cases only for the P0 and P1 gaps.

| Mode | When | Read |
|---|---|---|
| Cases | Scenarios, an initial test plan, or mock data for one unit (component, hook, function, or endpoint) | [cases.md](references/cases.md), [cases-examples.md](references/cases-examples.md) |
| Coverage | Coverage audit, gaps, or prioritization across routes, modules, or features | [coverage.md](references/coverage.md), [coverage-examples.md](references/coverage-examples.md) |

## Quick start

- **Cases**: identify the unit's inputs (props, arguments, state, dependencies), then list base cases, edge cases, and reusable mocks, each with its expected assertion.
- **Coverage**: inventory routes, modules, and key units, map them to existing tests, mark gaps, and order the plan by impact with the test type for each gap.
- In both modes, plan only observable behavior and public contracts, and reuse the project's factories, helpers, and testing conventions.

This skill plans tests. Writing them follows `test-best-practices`, and the decision about mocks follows `mock-first-testing-design`.
