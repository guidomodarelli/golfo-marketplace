## App Router routes

This folder is the Next.js App Router routes directory. These rules add to `.agents/rules/nextjs-app-router.md` and the React and Next.js rules.

### What goes here

- Only route files: `page.tsx`, `layout.tsx`, `loading.tsx`, `error.tsx`, `not-found.tsx`, `route.ts`, and the framework's other special files. Never place components here; pages import them from the component location in `react-style.md`.
- Never place tests here, where colocated files can become route artifacts. Put tests for pages, layouts, loading states, and route handlers in a separate tests tree that mirrors this folder.

### Route handlers

- Serve the API through route handlers (`route.ts`) and validate every client-controlled input at that boundary, following `react-security.md#input-validation` with the project's own boundary helpers. The Express and Pages Router layout of `api-validation-middleware.md` and `api-configuration.md` does not apply.
- Read upstream configuration through the project's server-side configuration module (for example, validated environment variables), never from a `config/` file created for it.
