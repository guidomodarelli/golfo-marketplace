# Next.js App Router Rules

Rules for projects that route with the Next.js App Router: a `next` dependency with routes under `app/` or `src/app/`. They add to the React and Next.js rules; for loading, error and layout boundaries, follow the project's Next.js documentation. What the routes directory holds and how its route handlers validate input are in the `AGENTS.md` of the routes directory (`app/AGENTS.md` or `src/app/AGENTS.md` by default): read it before you change a file there.

## Server and client components

- Components are Server Components by default. Mark one with `"use client"` only when it needs browser APIs, client state, or event handlers, and keep that boundary as low in the tree as possible.
- A page or layout loads its initial data on the server and passes it as props, as `server-first-data-flow.md` describes.
