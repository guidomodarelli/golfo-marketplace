# Frontend Style Rules — SSR + React + TypeScript

Coding conventions for this stack. Always consult the documentation of the project's SSR framework and design system for their APIs before implementing — these rules cover conventions, not API details.

---

## Components

- Use function components with hooks — no class components.
- Keep components small and single-responsibility. Extract when a component has more than one reason to change.
- Extract complex logic into custom hooks (`use<Name>`).
- Avoid prop drilling beyond two levels — use context or a state manager.
- Never use rest props (`...rest`) — declare all props explicitly.
- **One component per file** — never export more than one component from a single file. A file named `user-card.tsx` exports only `UserCard`.
- **Component placement** — follow the component locations declared in the project's `AGENTS.md` (or its architecture docs). When the project declares none, use `components/<scope>/<component-name>/` (or `src/components/<scope>/<component-name>/` when the project keeps code under `src/`), where `<scope>` groups components by feature or domain and shared primitives use a generic scope such as `common`.
  - Never place components inside a file-system router's routes directory (for example the Next.js App Router `app/` directory): it only holds route files (`page.tsx`, `layout.tsx`, `loading.tsx`, `error.tsx`, `not-found.tsx`, `route.ts`, and similar). Pages import components from the component location.
  - Do not add barrel files (`index.ts` that re-export many components) unless the project already uses them; import each component from its own folder.
- **Atomic size** — keep components at the smallest meaningful unit. A component that mixes concerns (layout + data formatting + interaction) must be split.

## Design system

- Use the project's design system components for all UI elements: buttons, inputs, modals, selects, etc.
- Never build custom replacements for components the design system already provides.
- Use design system props (for example `variant`, `size`, `color`) to control appearance before adding any custom CSS.
- Only add custom CSS when the design system has no prop or component that covers the need.
- Never override internal design system component styles with custom CSS.
- When custom styles are needed, write them with the project's styling solution (for example SCSS/Sass Modules or Tailwind, whichever the project already uses) and the design system tokens; never hardcode colors, typography, spacing, breakpoints, radius, or elevation.
- Use the project's image component or provider for images, icons, and backgrounds with relative or environment-dependent paths; keep lazy loading and avoid absolute URLs.
- Always consult the design system documentation before selecting a component.

## User-facing copy

- When the project already uses an i18n library (gettext, next-intl, i18next, react-intl, or similar), route every visible React string —labels, buttons, placeholders, helper and error text, toasts, and aria labels— through its translation function (for example `i18n.gettext`, `useTranslations`, or `t`). Reuse existing message ids before creating new ones, and do not hand-edit catalogs that the i18n workflow generates.
- When the project has no i18n library, do not add one only to satisfy this rule: write user-facing copy in the language set by the project's language policy (`AGENTS.md`), keep it in the component as the framework expects, and name only the copy identifiers or keys that carry behavior.
- Write labels, buttons, headings, helper text, empty states, confirmations, and progress messages for people who use the product, not for the team that built it.
- Avoid unnecessary secondary labels and descriptions. Let the design do the explaining: before adding a subtitle, helper text, tagline, or explanatory paragraph, resolve the ambiguity with layout, hierarchy, grouping, a clearer primary label, an icon, or the design system's affordances. Do not write slogan-like headings or copy that turns the interface into an instruction manual. This does not remove accessible names (`aria-label`, visually hidden labels), validation and error messages, or text that states a consequence the user needs before acting (for example an irreversible deletion).
- Avoid implementation terms in regular UI copy, including `preflight`, `bootstrap`, `provider`, `stack`, `upstream`, `lockfile`, `schema`, `sync`, and `retry` when they describe internal mechanics. Prefer the user-visible action or outcome, such as `Reintentar` instead of `Reintentar preflight`.
- Do not expose internal component names, service names, workflow names, file names, status codes, or infrastructure details in regular UI copy. Keep those details in logs or technical documentation, not in ordinary interface text.
- Keep error messages clear and actionable. Errors may include the minimum technical detail needed to diagnose or resolve the problem, but never expose secrets or unnecessary internal data.
- Review every new or changed user-facing string from the perspective of a non-technical user; if the message explains how the system works instead of what the user can do or expect, rewrite it.

## TypeScript

- Always type props explicitly — no `any`.
- Use `interface` for object shapes; `type` for unions and aliases.
- Never use `enum` — use `const` objects with `as const` or string union types.
- Never use parameter properties in classes.
- Before closing the change, run the project's own typecheck and lint scripts from `package.json` (for example `typecheck`, `lint`, or the `ci` script that bundles them) instead of ad hoc commands such as a bare `tsc --noEmit`; fix every reported error. When one of those scripts does not exist, report that check as `N/A` instead of substituting a direct binary. Run them once at the end of the task, as `verify-changes.md` and `lint-gate.md` define, not after every file.

## Function parameters

- Never use boolean parameters to switch a function's behavior. A call like `getItems(locale, true, true)` is unreadable at the call site, is easy to call with arguments in the wrong order, and every extra flag doubles the hidden combinations, including invalid ones.
- Use a semantic string that names the state or mode instead. When several flags describe one state, collapse them into a single value that only allows valid combinations:

  ```ts
  // ❌ What do `true, true` mean? Is `featuredOnly` without `activeOnly` valid?
  function getItems(locale: string, activeOnly = false, featuredOnly = false) {}
  getItems(locale, true, true);

  // ✅ The call reads as intent and invalid combinations cannot be expressed
  type ItemListScope = 'all' | 'active' | 'active-featured';

  function getItems(locale: string, scope: ItemListScope = 'all') {}
  getItems(locale, 'active-featured');
  ```

- Declare the allowed values as a string union type, or as an `as const` object in `constants/` when the values are reused across modules. Never use `enum` (see TypeScript).
- When replacing an existing boolean parameter, update every call site in the same change; do not keep the boolean and the string side by side.
- This rule covers parameters that select behavior. Boolean props that follow design system or DOM conventions (`disabled`, `checked`, `open`), predicate return values, and boolean fields that come from an upstream payload stay boolean.

## Naming

| Entity | Convention | Example |
|--------|-----------|---------|
| Components | PascalCase | `UserProfile` |
| Hooks | camelCase with `use` prefix | `useUserProfile` |
| Files & directories | kebab-case | `user-profile.tsx` |
| Constants | UPPER_SNAKE_CASE | `MAX_RETRIES` |
| Functions & variables | camelCase | `getUserProfile` |

## Module placement

- Follow the module layout declared in the project's `AGENTS.md` or architecture docs (for example `src/modules/<feature>/{domain,application,infrastructure}`) before applying the defaults below.
- Keep route entrypoints (route handlers, server actions, pages) focused on validation at the boundary, orchestration, and calls to use cases or services. Do not add shared utilities or reusable constants inside them.
- In projects without feature modules, place shared or reusable utility functions in `utils/` and domain/configuration constants in `constants/`. With feature modules, keep them in the owning module (`src/modules/<feature>/constants/`, or `src/modules/shared/...` when several modules reuse them), as `hexagonal-architecture.md` describes. Extract anything reused or carrying domain meaning.
- **Applies only when the project serves its API with Express:** keep subrouters focused on route registration, middleware mounting, orchestration, and service calls, and do not add shared utilities or reusable constants inside `api/<resource>/`, `api/services/`, or `services/` modules. Place route-specific request schemas and validation middleware built with the project's input validation library in `api/middlewares/validation/`, re-exported from its `index.js` or `index.ts` barrel, and keep the subrouter responsible for mounting the middleware and handler; see `api-validation-middleware.md`.

## Performance

- Avoid unnecessary object cloning with spread — pass objects directly when no mutation is needed.
- Use `React.memo`, `useMemo`, and `useCallback` only when profiling confirms a render bottleneck — not preemptively. When it does, stabilize the handlers passed to memoized children with `useCallback` instead of inline functions.
- Lazy-load routes and heavy components.

## Imports

- When the project's SSR framework re-exports a package, import it from the framework's re-export — never from the underlying package directly.
- Never install packages that the SSR framework already bundles (for example `react` or `react-dom`).
- Check the framework's `package.json` in `node_modules/` before installing any new dependency.
- For `lodash-es` availability, mandatory and forbidden methods, see `lodash.md`.

## Logging

- Use the project's logger; never use `console.*` in application code.
- Write each log message with operation, stage, outcome, code, and safe context. Opaque, stable identifiers (`userId`, `requestId`, `traceId`, resource ids) are allowed and encouraged for diagnosis; never log PII (emails, phone numbers, names, addresses), raw request or response payloads, tokens, cookies, or secrets (see `Secrets & PII` in `security.md`).

## Comments

- Comment the WHY, not the WHAT. Well-named identifiers explain themselves.
- Only add inline comments for non-obvious constraints, workarounds, or invariants.
- Document exported components, hooks, functions, and types with JSDoc/TSDoc when their intent, contract, or complexity is not evident from the signature (props with non-obvious behavior, side effects, thrown errors, invariants); follow the `enforce-jsdoc-tsdoc` skill when it is available. Do not add JSDoc that only restates the name or the types.
