---
name: review-maintainability
description: Review maintainability risks in HEAD, uncommitted changes, or the current branch against develop, falling back to main or master when develop does not exist. Use when the user asks for a maintainability review, Review Maintainability HEAD, review including uncommitted changes, review against develop/main/master, or focused review of concurrency and thread safety, race conditions, deadlocks, unbounded concurrency, logic bugs, null handling, edge cases, type errors, memory leaks, connection leaks, resource leaks, or unbounded growth in changed code.
license: MIT
metadata:
  version: "1.0.0"
  author: "Guido Modarelli"
  category: "code-review"
  tags: "code-review, maintainability, concurrency, leaks, bugs"
  command: "/review-maintainability"
---

# Review Maintainability

## Goal

Review only the changes introduced by the current target. Prioritize defects that can cause incorrect behavior, unsafe concurrent execution, or resource growth/leaks. Report findings first, in Spanish, with precise file and line references.

## Shared Contract

Read [contrato compartido de review](../../references/review-contract.md) before reviewing. It defines scope presets and the non-interactive default, base selection, repository context (`REVIEW.md`, `CLAUDE.md`, `AGENTS.md`, PR intent, root cause), effort level by risk, adversarial verification, finding labels (`Important`, `Nit`, `Pre-existing`), bug class, and the summary format. This skill adds only its focus, severity guidance, and report fields. If the relative link does not resolve because the skill is installed as a symlink, resolve the skill directory's real path first (`realpath`/`Get-Item .Target`).

## Review Approach

Classifying changed files by runtime responsibility (UI, API route, service, persistence, background job, shared utility, test, config, or documentation) helps decide where concurrency, correctness, or leak risks are plausible.

- Start from the diff and open surrounding implementation when changed code depends on invariants outside it.
- Follow control flow across module boundaries when changed functions call each other, because many defects live in the interaction rather than in either side.
- Prefer concrete failures over style comments: a maintainability opinion belongs in the report only when it creates a plausible defect in one of the focus areas.

## Focus Areas

### Concurrency And Thread Safety

Look for:

- Race conditions from async operations resolving out of order.
- Missing cancellation, stale writes, or state updates after teardown.
- Shared mutable state used across requests, sessions, jobs, or tests.
- Deadlocks, lock-order inversions, missing unlocks, or blocking waits inside async/event-loop code.
- Unbounded concurrency from `Promise.all`, loops that start async work without limits, worker pools without caps, queue consumers without backpressure, or retries without bounds.
- Timer, listener, subscription, stream, or observer lifecycles that can overlap unexpectedly.

### Incorrect Behavior Bugs

Look for:

- Logic errors, inverted conditions, unreachable branches, and off-by-one mistakes.
- Null, undefined, empty, missing, or malformed input paths.
- Edge cases around pagination, sorting, filtering, retries, dates, time zones, locale, numeric conversion, and partial API responses.
- Type mismatches, unsafe casts, shape drift between API/service/UI layers, and assumptions not enforced by validation.
- Error handling that swallows failures, reports success after partial failure, retries the wrong operation, or returns inconsistent state.

### Leaks And Resource Management

Look for:

- Memory leaks from retained closures, caches, maps, arrays, global registries, event listeners, or subscriptions.
- Connection, file, stream, transaction, lock, browser, worker, or interval resources not closed on success and failure paths.
- Unbounded growth in caches, queues, logs, telemetry buffers, retry state, polling, or accumulated DOM/application state.
- Missing cleanup in tests that can leak timers, listeners, mocks, servers, or global state into later tests.

## Severity Guidance

- `P0`: Data loss or corruption, or a crash/deadlock on a critical path under normal use.
- `P1`: Incorrect behavior or a leak on a common path that users or operators will hit.
- `P2`: Incorrect behavior or resource growth limited to less common inputs, timing, or load.
- `P3`: Localized defect with limited impact and a clear low-risk fix.

## Report Fields

Besides the shared fields, each finding includes:

- The concrete failure mode.
- Why the changed code introduced or exposed the issue.

## Boundaries

- Do not report formatting, naming, architecture, or style issues unless they directly cause one of the focus-area defects.
