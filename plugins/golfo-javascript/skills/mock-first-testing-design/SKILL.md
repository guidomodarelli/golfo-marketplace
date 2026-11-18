---
name: mock-first-testing-design
description: Decide how a test isolates a hard dependency without contaminating production code — prefer real integration, limit doubles to domain ports passed by injection and nock HTTP fixtures, never mock the project's internal services, components or modules (no vi.mock / vi.spyOn on them), and refactor production code only when the change improves the real design. Use when creating, updating, or reviewing automated tests and there is a risk of mocking internal code, adding test-only branches, exporting internals just for tests, or changing production contracts only to make a test easier.
license: MIT
metadata:
  version: "2.0.0"
  author: "Guido Modarelli"
  category: "testing"
  tags: "testing, vitest, test-doubles, dependency-injection, ports, nock, design"
  command: "/mock-first-testing-design"
---

# Mock First Testing Design

Use this skill to keep tests isolated at the right boundary without mocking the project's own code and without contaminating production code with test-only decisions. Tests run with Vitest.

## Quick Start

- Identify the dependency that makes the test hard: database, outbound HTTP, filesystem, time, randomness, framework wrapper, side effect, or another module of the project.
- Prefer real integration first: run the project's own services, components, hooks, and modules for real, and use the real database or the project's test database when feasible.
- Isolate only at two boundaries:
  - **Domain ports passed by injection** (repository, gateway, notifier, clock): pass an in-memory, recording, or fixed implementation of the port.
  - **Outbound HTTP**: intercept it with `nock` record/replay fixtures in Vitest's `node` environment.
- Never `vi.mock` or `vi.spyOn` the project's internal services, components, hooks, or modules, and never mock the design system or framework/platform packages.
- Refactor production code only when the refactor improves design for real usage: clearer responsibilities, lower coupling, explicit dependencies, or smaller units with stable contracts.
- Reject changes whose only purpose is making the test easier.

## Decision Rule

Ask this question before changing production code:

> If this change did not help testing, would it still be a good design change?

- If the answer is `no`, keep production code as-is and solve the test with real integration, an existing injected port, `nock`, or better test setup.
- If the answer is `yes`, the refactor is acceptable if it improves the system independently of the test — for example, turning a hidden, hardcoded collaborator into an explicit port that another real consumer also needs.

When the only way to isolate a dependency would be mocking a module import, that is not an option: either test through the real boundary or apply a refactor that passes this rule.

## Prefer These Patterns

- Run the real implementation of everything the project owns.
- Pass an in-memory fake of a repository port when the test needs controlled data.
- Pass a recording implementation of a port (or `vi.fn()` as the port's implementation) when the interaction is the behavior, such as a notification being sent.
- Isolate outbound HTTP with `nock` fixtures; HTTP error statuses are fixtures too.
- Control time with `vi.useFakeTimers()` / `vi.setSystemTime()` or an injected clock port, and restore it after each test.
- Apply dependency injection when it makes dependencies explicit in real design, not only in tests.
- Favor SOLID-oriented refactors that reduce coupling and improve cohesion as a side effect of better design.

## Reject These Patterns

- Do not `vi.mock` or `vi.spyOn` the project's own services, components, hooks, or modules, nor mock the design system or platform packages.
- Do not introduce Jest or its APIs; use Vitest.
- Do not add `isTest`, `testMode`, or similar branches in production code.
- Do not export internals only to reach them from tests.
- Do not change public contracts only to simplify assertions.
- Do not split or unwrap framework-dependent code only to bypass HOCs, wrappers, or runtime glue in tests.
- Do not modify business logic solely to make a failing test pass.
- Do not add tests that read source, style, or SQL files with `fs` or equivalent packages to assert exact text, substrings, snapshots, or SQL fragments.
- Do not replace those checks with tests that only spy on ORM/query-builder function parameters or internal query-construction calls.

## Acceptable Refactors

Accept a refactor when it:

- makes dependencies explicit, typically as a domain port injected through a constructor, factory, prop, or provider;
- separates unrelated responsibilities;
- removes hidden side effects;
- creates smaller, cohesive units with stable behavior; or
- simplifies orchestration without weakening the public contract.

Reject a refactor when it:

- exists only for test reachability;
- introduces test-only seams with no product value; or
- leaks implementation details that should stay private.

## Review Checklist

- Confirm the test runs the project's own code for real and isolates only an injected port or outbound HTTP.
- Flag any `vi.mock` / `vi.spyOn` on internal code, any mock of the design system or platform packages, and any Jest API.
- Confirm production behavior and public contracts remain driven by functional needs.
- Confirm any new seam is a real design improvement, not a testing bypass.
- Confirm the chosen double matches the test goal: controlled data (fake port), observation (recording port), or HTTP (`nock` fixture).
- Call out test-only production changes explicitly during review and request a real-integration or design-driven alternative.
