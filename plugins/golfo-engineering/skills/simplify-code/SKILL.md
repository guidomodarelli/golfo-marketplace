---
name: simplify-code
description: "Review changed code for reuse, simplification, efficiency, and abstraction-level cleanup, then apply the fixes. Use when the user invokes $simplify-code or /simplify-code, asks to simplify current changes, clean up a diff, reduce duplication, improve reuse, remove unnecessary complexity, tighten abstractions, or make changed code more maintainable. Quality-only review: do not hunt for correctness bugs, security issues, or broad product behavior regressions; use a code-review/security/debugging skill for those."
license: MIT
metadata:
  version: "1.0.0"
  author: "Guido Modarelli"
  category: "refactor"
  tags: "simplify-code, simplify, cleanup, duplication, reuse, code-quality"
  command: "/simplify-code"
---

# Simplify Code

## Overview

Improve the current change set by making the modified code smaller, clearer, more reusable, and less wasteful without changing intended behavior. Treat this as an edit-and-verify workflow, not just advisory review.

## Workflow

1. Identify the review scope from the user's request. Default to the current working-tree diff; if the user names files, commits, or a branch comparison, use that scope instead.
2. Inspect the diff and surrounding code before proposing changes. Prefer existing project patterns, helpers, naming, and abstractions over new architecture.
3. Look for quality cleanups only:
   - duplicated logic or markup that can be collapsed without hiding intent
   - dead, redundant, or overly defensive code introduced by the change
   - unnecessary indirection, wrappers, state, effects, conditionals, casts, or conversions
   - inefficient repeated work in hot paths, render paths, loops, or request flows
   - abstractions at the wrong altitude: too low-level at call sites, too generic for one use, or spread across modules without a clear responsibility
   - names that obscure the real concept or force readers to inspect implementation details
4. Check whether changed methods and constants live at the right repository location:
   - **`utils/` placement:** identify stateless, side-effect-free helpers that operate on generic data or cross-cutting concerns and are reused, or clearly useful for reuse, across modules. Prefer an existing domain-specific utility directory over a new global `utils/`; do not move methods there when they encode one feature's business rules, depend heavily on one module's state, or have only one caller without a real responsibility boundary.
   - **`constants/` placement:** identify shared business literals and stable values such as statuses, roles, route fragments, event names, limits, or repeated configuration keys. Reuse existing constants modules before creating one. Keep one-off trivial values local, and prefer `config/` or environment configuration for deployment-specific values, endpoints, credentials, or values expected to vary by environment.
   - Search the repository for existing utilities and constants before adding or relocating code. Apply placement cleanups only when they reduce duplication or clarify ownership without creating a vague catch-all module.
5. Apply fixes directly when they are local and behavior-preserving. Keep the patch tightly scoped to changed code and nearby support code needed for the cleanup.
6. Avoid expanding the task into bug hunting, security review, feature changes, rewrites, dependency churn, formatting-only sweeps, or unrelated refactors.
7. Run relevant tests, type checks, linters, or builds for the touched area. If no meaningful validation is available, state what was not validated and why.

## Review Heuristics

Prefer a cleanup when it makes the next reader's job easier in the actual project context. Reject a cleanup when it only makes code shorter, cleverer, or more abstract without reducing real complexity.

Use these checks while editing:

- If two places changed in parallel, consider whether a named helper, constant, component, adapter, or test fixture would make the relationship explicit.
- If a helper has only one caller, keep it only when it separates a real responsibility or clarifies a difficult operation.
- If a new abstraction needs a vague name such as `manager`, `handler`, `utils`, `data`, `config`, or `common`, re-check whether the concept is real.
- If performance cleanup is possible, prefer removing repeated work or unstable allocations before adding caches or memoization.
- If the simplification touches tests, keep tests behavior-focused. Do not assert source text, import spelling, or implementation-only structure.

## Reporting

When finished, report:

- what was simplified and why it is behavior-preserving
- any relevant tradeoff or cleanup deliberately skipped
- validation commands run and their result
