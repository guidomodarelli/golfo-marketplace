# Next.js App Router Rules

Rules for projects that route with the Next.js App Router: a `next` dependency with routes under `app/` or `src/app/`. They add to the React and Next.js rules; for loading, error and layout boundaries, follow the project's Next.js documentation.

## The routes directory

- `app/` (or `src/app/`) holds only route files: `page.tsx`, `layout.tsx`, `loading.tsx`, `error.tsx`, `not-found.tsx`, `route.ts`, and the framework's other special files. Never place components there; pages import them from the component location in `react-style.md`.
- Never place tests inside the routes directory, where colocated files can become route artifacts. Put tests for pages, layouts, loading states, and route handlers in a separate tests tree that mirrors it. Outside App Router projects, `app/` is an ordinary source folder and colocated tests stay valid.

## Server and client components

- Components are Server Components by default. Mark one with `"use client"` only when it needs browser APIs, client state, or event handlers, and keep that boundary as low in the tree as possible.
- A page or layout loads its initial data on the server and passes it as props, as `server-first-data-flow.md` describes.

## Route handlers

- Serve the API through route handlers (`app/**/route.ts`) and validate every client-controlled input at that boundary, following `react-security.md#input-validation` with the project's own boundary helpers. The Express and Pages Router layout of `api-validation-middleware.md` and `api-configuration.md` does not apply.
- Read upstream configuration through the project's server-side configuration module (for example, validated environment variables), never from a `config/` file created for it.
