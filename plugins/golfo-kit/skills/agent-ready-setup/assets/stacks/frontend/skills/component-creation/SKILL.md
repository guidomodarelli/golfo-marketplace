---
name: component-creation
description: Crea un componente React siguiendo las convenciones del equipo con el design system y el framework SSR del proyecto. Usar cuando se pida crear un componente, widget o elemento de UI.
metadata:
  tags: "context-optimized-v1.20.1"
---

# Component Creation — Frontend (SSR + React + design system)

Step-by-step guide for creating a React component following team conventions.

---

## Step 1 — Define scope

Before writing code, answer:
- What does this component display or do?
- Does it need server-side data? → If yes, the server entrypoint (a Server Component page or layout, a loader, or the project's server hook) loads it and passes it as props; the component does not fetch it.
- Does the design system already have a component for this? → Consult the design system documentation first.
- Does it need browser APIs, client state, or event handlers? → Only then mark it as a client component (`"use client"` in the Next.js App Router); otherwise keep it a Server Component.
- Where does it live? → Use the component location declared in the project's `AGENTS.md` (or its architecture docs). When none is declared, use `components/<scope>/<component-name>/` (or `src/components/<scope>/<component-name>/` when the project keeps code under `src/`). `<scope>` is the feature or domain that owns it; shared primitives use a generic scope such as `common`.
- Never create a component inside the App Router `app/` directory (or any file-system routes directory): it only holds route files such as `page.tsx`, `layout.tsx`, `loading.tsx`, `error.tsx`, and `route.ts`.

---

## Step 2 — Create the directory

Use the location decided in Step 1:

```
components/<scope>/<component-name>/
├── index.tsx
└── styles.module.scss   ← only if custom styles are needed and the project uses SCSS Modules
```

If the project's `AGENTS.md` declares another structure (for example a different stylesheet name, or Tailwind classes instead of a stylesheet), follow it. Use PascalCase for component names and kebab-case for directories and filenames. One component per file — `index.tsx` exports only `<ComponentName>`. Import the component from its folder path so resolution uses `index.tsx`.

---

## Step 3 — Write the component (`index.tsx`)

```tsx
/** Props of `<ComponentName>`; document a prop only when its behavior is not obvious. */
interface <ComponentName>Props {
  // Declare all props explicitly — no rest props (...rest)
}

/**
 * Add JSDoc/TSDoc when the component's intent, side effects, or contract are not evident
 * from its name and props (see `Comments` in `frontend-style.md`).
 */
export function <ComponentName>({ }: <ComponentName>Props) {
  return (
    // Use design system components for all UI elements
    // Never use dangerouslySetInnerHTML with untrusted content
    // Keep sensitive data out of component state — pass only what is needed for display
  );
}
```

While writing, apply `../../rules/frontend-style.md` (sections `Components`, `Design system`, `User-facing copy`, `TypeScript`, and `Comments`) and `../../rules/frontend-security.md` (sections `Secrets & PII` and `XSS Prevention`).

---

## Step 4 — Add styles

Only add custom styles if the design system (for example the project's shared UI library such as `@golfo/ui`) has no prop or component that covers the need. Use the project's styling solution: a `styles.module.scss` next to `index.tsx` for SCSS Modules (with the class naming convention the project declares, such as BEM), or utility classes when the project uses Tailwind. Use design system tokens; keep custom CSS minimal.

---

## Step 5 — Write the test

Place the test where the project keeps component tests (for example `tests/unit/components/<component-name>.test.tsx` or `__tests__/<component-name>.test.tsx` next to the component); follow the existing pattern. Use Vitest with Testing Library (`@testing-library/react` and `@testing-library/user-event`); never use `jest.*` APIs.

```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TestProviders } from '<path-to>/tests/utils/test-providers';
import { describe, expect, it } from 'vitest';
import { <ComponentName> } from '<path-to>/components/<scope>/<component-name>';

describe('<ComponentName>', () => {
  it('renders <expected output>', () => {
    // Arrange
    render(
      <TestProviders>
        <ComponentName />
      </TestProviders>,
    );

    // Assert
    expect(screen.getByRole('...')).toBeInTheDocument();
  });

  it('handles <user interaction>', async () => {
    // Arrange
    const user = userEvent.setup();
    render(
      <TestProviders>
        <ComponentName />
      </TestProviders>,
    );

    // Act
    await user.click(screen.getByRole('button', { name: /label/i }));

    // Assert
    expect(screen.getByText('...')).toBeInTheDocument();
  });
});
```

Test checklist:
- [ ] Happy path renders correctly.
- [ ] Error states render the right feedback.
- [ ] User interactions produce the expected outcome.
- [ ] No snapshot tests as the primary assertion.
- [ ] No `jest.*` APIs, and no `vi.mock` / `vi.spyOn` of internal modules, services, hooks, or the shared UI library.
- [ ] Doubles only for ports the component receives by injection (props or a context provider the test renders); HTTP that cannot be avoided is intercepted with `nock` (or the project's existing HTTP interceptor), never by mocking the HTTP client.
- [ ] Component libraries and platform packages rendered for real, never mocked (`../../rules/frontend-testing.md`, section `Mocking`, and `../../rules/no-unnecessary-mocks.md`).

---

## Step 6 — Import

Import the component directly from its folder (`@/components/<scope>/<component-name>`). Do not create or extend a barrel file unless the project already uses one for that scope.

---

## Step 7 — Verify

Run the project's own scripts from `package.json` with its package manager (the one its lockfile declares), never ad hoc commands such as a bare `tsc --noEmit` or `npx eslint`:

```bash
<pm> run test -- <path-to-the-new-test>   # the spec that covers the component
<pm> run typecheck                         # or the script the project defines for type checking
<pm> run lint                              # once at the end of the task
```

If a script does not exist, report it as `N/A` instead of inventing one (see `verify-changes.md` and `lint-gate.md`).
