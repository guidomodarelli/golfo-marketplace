# Hexagonal Architecture — Vertical Slices

Applies to projects that organize business code in modules with `domain`, `application`, and `infrastructure` layers. Keep the boundaries from the first commit and in every change.

## Structure

- Organize business code by vertical slice (`src/modules/<feature>/`), not by technical layer at the repository root.
- Do not create a generic `src/server` layer. Server-only code belongs to a feature module or to a shared module (`src/modules/shared/`).
- Keep every technical identifier in English: folders, files, modules, symbols, DTOs, ports, adapters, tests, and comments.

```text
src/modules/<feature>/
  domain/            entities/, value-objects/, repositories/ (ports)
  application/       commands/, queries/, results/, use-cases/
  infrastructure/    api/dto/, api/mapper.ts, repositories/, <provider>/
src/modules/shared/  domain/, application/, infrastructure/
```

## Dependency rule

Dependencies always point inward.

- Allowed: route entrypoints → `application`; route entrypoints → `infrastructure` only for framework wiring, adapter selection, and dependency composition; `application` → `domain`; `infrastructure` → `application` and `domain`.
- Forbidden: `domain` → `application` or `infrastructure`; `application` → `infrastructure` or a generic `lib`; UI or route entrypoints importing external DTOs; any import from a generic `src/server` folder.
- Do not access the database from route handlers; see `Architecture and dependencies` in `patterns-we-do-not-use.md`.

## Layer responsibilities

- **Route entrypoints** (pages, layouts, loading states, route handlers): framework composition roots only. They wire adapters to use cases and never host domain rules.
- **Presentational components**: receive state, messages, results, and callbacks through props. They do not call infrastructure adapters, nor client adapters from `lib` (files named `*api*`, `*client*`, or `*adapter*` are adapter code). Session lookup, async workflows, and multi-step form orchestration live in route-level or dedicated client containers.
- **`domain`**: pure business rules, entities, value objects, and ports. No framework, HTTP, provider SDK, or persistence details.
- **`application`**: use cases and internal contracts (`commands`, `queries`, `results`) that orchestrate the domain through ports. Validate and normalize inputs through value objects or application contracts, not generic helpers in `lib`.
- **`infrastructure`**: adapters for authentication, databases, HTTP clients, storage, and third-party SDKs. It owns external DTOs and their mappers. Shared server-only helpers still live under a module's infrastructure folder.
- **`lib`**: framework-safe helpers, UI utilities, and client-only adapters with no business rules. When a helper starts encoding use-case rules, provider details, or DTO mapping, move it into the owning module.

## Checklist

- Does the change keep dependencies pointing inward?
- Did any code land in a generic `src/server` folder? Move it into a module.
- Are external DTOs isolated in infrastructure, and are UI models free of vendor payloads?
- Are domain inputs modeled as value objects and application outputs as `results/` contracts?
