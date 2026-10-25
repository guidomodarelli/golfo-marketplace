---
name: review-performance
description: Review production-impacting performance issues in HEAD, uncommitted changes, or changed code against develop/main/master. Use when the user asks for a performance review, Review Performance HEAD, review including uncommitted changes, performance risks, latency or throughput review, or focused detection of N+1 queries, O(n²) or worse algorithms, repeated expensive work, unnecessary allocations, excessive rendering, unbounded loops, missing batching, inefficient I/O, cache misuse, or avoidable production load.
license: MIT
metadata:
  version: "1.1.0"
  author: "Guido Modarelli"
  category: "code-review"
  tags: "code-review, performance, latency, n+1, rendering, react-doctor, react-scan"
  command: "/review-performance"
---

# Review Performance

## Goal

Review changed code for performance defects that can affect production latency, throughput, cost, memory, rendering responsiveness, or service reliability. Prioritize issues with a plausible real workload impact over speculative micro-optimizations.

## Shared Contract

Read [contrato compartido de review](../../references/review-contract.md) before reviewing. It defines scope presets and the non-interactive default, base selection, repository context (`REVIEW.md`, `CLAUDE.md`, `AGENTS.md`, PR intent, root cause), effort level by risk, adversarial verification, finding labels (`Important`, `Nit`, `Pre-existing`), bug class, and the summary format. This skill adds only its focus, severity guidance, and report fields. If the relative link does not resolve because the skill is installed as a symlink, resolve the skill directory's real path first (`realpath`/`Get-Item .Target`).

## Review Approach

Performance impact depends on where the code runs and how often, so anchor each judgment in the production path the change affects (request handling, database access, service calls, background jobs, UI rendering, build-time code, tests, or tooling) and in the workload shape that exercises it (users, requests, rows, items, renders, retries, pages, files, or events).

- Start from the diff and widen to surrounding code only as far as needed to understand data size, call frequency, lifecycle, or dependency contracts.
- Report risks that scale poorly or add repeated expensive work in normal production use; a micro-optimization on a cold path is not worth the reader's attention.
- Ground findings in evidence from code paths, loops, query placement, allocations, and API boundaries. When impact depends on an assumption, state it.
- In React projects that already have `@golfo/lint`, `golfo-lint react` (react-doctor) findings on the changed files count as evidence. A suspected re-render can be confirmed in development with react-scan only when the project already has it installed and connected (`react-scan` in `devDependencies`); `golfo-lint react-scan` installs and wires it, so never run it during a review. Without react-scan, confirm with React DevTools Profiler or report the confirmation as unavailable. Never run react-doctor or react-scan outside golfo-lint, and do not install anything during a review: setup and limits live in [react-doctor y react-scan vía golfo-lint](../measured-performance-optimization/references/react-doctor-react-scan.md).

## Focus Areas

### Database And Remote Calls

Look for:

- N+1 queries or remote calls introduced inside loops, mappers, resolvers, render paths, hooks, or per-item processors.
- Missing batching, joins, eager loading, prefetching, pagination, projection, or bulk APIs.
- Query filters, sorts, or aggregations moved from the database/service layer into application memory.
- Repeated fetching of invariant data within a request, render, job, or batch.
- Cache keys that are too broad, too narrow, missing invalidation, or likely to amplify load.

### Algorithmic Complexity

Look for:

- Nested loops over request-sized or dataset-sized collections that create O(n²) or worse behavior.
- Repeated `find`, `filter`, `includes`, `indexOf`, sort, regex, parse, serialize, or deep clone work inside loops.
- Work that can be converted to maps, sets, grouping, single-pass aggregation, early exit, or precomputation.
- Unbounded iteration over user-controlled, API-controlled, or storage-controlled collections.
- Retry, polling, recursion, pagination, or queue loops without clear limits or backoff.

### Allocations And Rendering

Look for:

- Large arrays, objects, strings, buffers, DOM nodes, or intermediate collections allocated on hot paths.
- Deep clones, JSON round-trips, repeated serialization, repeated date/number formatting, or repeated expensive object creation.
- UI changes that trigger excessive renders, unstable props, recreated callbacks in large lists, missing virtualization, or expensive calculations during render.
- Logging, metrics, tracing, or error formatting that eagerly builds heavy payloads in high-volume paths.
- Temporary data structures that grow with workload and are retained longer than needed.

## Severity Guidance

- `P0`: Can take down production, exhaust a shared resource, or make a critical path unusable at expected scale.
- `P1`: Likely causes severe latency, throughput, cost, or memory regression on a common production path.
- `P2`: Plausible performance regression for moderate or large inputs, batch sizes, or list rendering.
- `P3`: Localized inefficiency with limited impact but a clear low-risk fix.

## Report Fields

Besides the shared fields, each finding includes:

- The workload shape that triggers the issue.
- The concrete performance failure mode.
- Why the changed code introduced or exposed the issue.
- A remediation direction such as batching, indexing by key, limiting input, moving work out of render, or avoiding repeated allocation.

When there are no findings, the residual risk also mentions missing profiling data or unknown production cardinality.

## Boundaries

- Do not report style-only concerns or premature micro-optimizations.
- Do not demand caching unless the cache key, lifetime, invalidation, and consistency tradeoff are clear.
- Unchanged code becomes reportable as `Pre-existing` only when the changed code newly makes it hot or reachable.
- Do not assume benchmarks pass; state what was not measured.
