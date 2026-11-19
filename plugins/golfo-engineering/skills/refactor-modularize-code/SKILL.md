---
name: refactor-modularize-code
description: Refactor code to improve module boundaries, raise cohesion, decouple responsibilities, and remove harmful duplication without changing behavior, in any language and in JavaScript, TypeScript, and React in particular. Use when a file or feature mixes responsibilities, repeats business logic, leaks infrastructure details across layers, has hard-to-follow dependencies, or needs to be reorganized into clearer modules such as services, adapters, utils, helpers, constants, types, components, custom hooks, or feature-specific folders; also when splitting large JS/TS/TSX files or React components, moving inline logic out of UI, extracting custom hooks, reorganizing imports/exports with reexports, or preparing safer tests around extracted boundaries.
license: MIT
metadata:
  version: "1.0.0"
  author: "Guido Modarelli"
  category: "refactor"
  tags: "refactor, modularity, cohesion, duplication"
  command: "/refactor-modularize-code"
---

# Refactor Modularity Cohesion Deduplication

## Overview

Refactor toward clear responsibilities and smaller, more cohesive modules. Keep the change behavior-preserving, prefer the smallest useful design improvement, and remove duplication only when the shared abstraction makes the code easier to understand and maintain.

## Refactor Goals

- Separate unrelated responsibilities.
- Increase local cohesion inside each module.
- Remove duplicated logic, not just duplicated text.
- Reduce dependency fan-out and hidden coupling.
- Preserve public behavior unless the task explicitly includes a contract change.

## Shared execution

Read [ejecución compartida](../../references/refactor-execution.md) before editing. Apply its phases, metrics, and validation workflow.

## Detect Bad Boundaries

- Split when one file handles unrelated concerns such as mapping, validation, transport, persistence, presentation, and orchestration at once.
- Split when two parts of the same file would likely change for different reasons.
- Split when functions depend on different infrastructure or data shapes.
- Split when the same helper knowledge is reimplemented in several callers.
- Keep code together when the extracted module would only wrap one caller and add naming noise without clarifying a responsibility.

## Choose The Right Destination

- Use `utils/` for pure helpers with no domain ownership and no side effects.
- Use `services/` for orchestration that coordinates repositories, clients, or external systems.
- Use `adapters/` for translation across boundaries such as API payloads, DTOs, or provider-specific formats.
- Use `constants/` for shared domain vocabulary or stable configuration-like invariants.
- Use feature-local folders when the code is only meaningful inside one feature and would become harder to trace if moved to a generic shared folder.

## JavaScript, TypeScript, And React

Apply these destinations and guidelines on top of the general ones when the code is JS/TS or React.

### Extraction targets

- Use `helpers/` or `utils/` for pure, reusable derivation with no React dependency and no side effects.
- Use `types/` for shared TypeScript contracts, public props, DTOs, and domain shapes used by more than one module.
- Use `components/` for presentational React UI with clear props and minimal business logic.
- Use `hooks/` for reusable React state, effects, event orchestration, and data-flow composition.
- When moving a public symbol out of a large module, reexport it from the original module so existing imports keep resolving, and migrate callers by boundary later.

### React guidelines

- Keep rendering components focused on markup, user actions, and composition.
- Extract custom hooks only when they own reusable React lifecycle, state transitions, subscriptions, or async coordination; keep pure mapping and formatting outside hooks when it does not need React.
- When a child takes over a piece of UI, keep that piece's state in the child and coordinate with the parent through explicit props (callbacks such as `onSearchFocusChange`, reset keys) instead of lifting state or sharing refs.
- Pass stable, descriptive props instead of leaking source payloads through many component layers.
- Preserve loading, error, empty, disabled, and accessibility behavior during extraction, and keep user-facing strings aligned with the project conventions.

### TypeScript guidelines

- Prefer explicit exported types at module boundaries and keep internal helper types unexported unless callers need them.
- Avoid `any`, broad unions, and catch-all records when the original code has a narrower contract.
- Preserve existing runtime validation and error semantics.
- Use descriptive names for extracted functions, parameters, files, and folders.

## Raise Cohesion

- Keep functions in the same module when they operate on the same domain concept, input shape, or lifecycle.
- Prefer modules whose exported names can be described with one short sentence.
- Move incidental formatting, parsing, or fallback logic out of core business flows when it obscures the main intent.
- Narrow each module API to the operations the caller actually needs.
- Pass explicit dependencies instead of reaching into global state when that improves testability and local reasoning.

## Remove Duplication Safely

- Deduplicate repeated behavior, algorithms, mapping rules, and decision logic before deduplicating cosmetic syntax.
- Search for existing helpers before creating a new shared abstraction.
- Extract only the stable common part when call sites are similar but not identical.
- Keep tiny one-off repetitions inline when the shared helper would need vague parameters or conditional branches.
- Prefer a well-named intermediate function over a large generic utility.

## Refactor Patterns

- Extract pure derivation logic from controllers, hooks, routes, or components into a focused helper or mapper.
- Separate transport code from business rules so clients and routes remain thin.
- Replace repeated inline object construction with a named builder only when the shape has domain meaning or multiple call sites.
- Split large modules into `constants`, `types`, `mappers`, `validators`, and `service` files only when each new file has a clear responsibility.
- In UI code, move data loading, state transitions, and presentation apart only if the new structure reduces repeated requests or prop plumbing.

## Avoid Over-Refactoring

- Do not create generic abstractions that erase domain language.
- Do not centralize feature-local logic too early.
- Do not split a file into many micro-modules that must always be read together.
- Do not use inheritance or configuration objects when a plain function extraction is enough.
- Do not split code only because a file is long; split when responsibilities or change reasons differ.
- Do not combine unrelated extractions in the same change unless the same boundary requires them.
- Do not change behavior, error semantics, side-effect timing, cache keys, or API contracts unless the task requires it.

## Design Checks

- Confirm each resulting module has one primary reason to change.
- Confirm the names explain responsibility better than the previous structure.
- Confirm dependencies point inward toward business meaning instead of sideways across unrelated modules.
- Confirm the extracted shared code reduced duplication without introducing flag arguments or caller-specific branching.

## Validation

Apply shared validation per phase. Confirm also that removed duplication shares semantics and that new abstraction introduces no caller-specific flags or branches.

## Closeout

Summarize the extracted boundary, preserved contracts, main-file and feature metrics, and deferred phases.
