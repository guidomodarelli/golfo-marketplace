# Server-First Data Flow

Load data on the server by default and adapt external data in exactly one place.

The default strategy applies to projects with server rendering (for example Next.js, Remix, or a custom SSR server). In client-only apps (for example Vite or Create React App), load each route's initial data from one route-level container instead, and treat the client-side fetching section as the default. The client-side fetching section applies to every frontend project. The middleend mapping section applies to projects organized in modules (see `hexagonal-architecture.md`); in projects with a flat `services/` layout, keep that layout and still never pass raw upstream payloads to route props. The `service` and `api-endpoint` skills generate the flat layout: in a modular project, place what they generate in the module's `infrastructure` and route it through a use case.

## Default strategy

- Load initial data through server-side entrypoints (server components, pages, layouts, loaders).
- Give each route segment a single primary data entrypoint whenever possible.
- Do not scatter external fetches across presentational components when the route can resolve them on the server.

## Middleend mapping

- External contracts belong to infrastructure: `src/modules/<feature>/infrastructure/api/dto/*` and `src/modules/<feature>/infrastructure/api/mapper.ts`.
- Internal contracts for the UI belong to application: `commands/`, `queries/`, and `results/`.
- Follow one conversion flow:

```text
External API/SDK -> infrastructure DTO -> infrastructure mapper -> domain entity/value object -> use case -> application result -> route view model/component props
```

- Never pass provider DTOs directly to route components or props.
- A route, server component, or action that calls external infrastructure translates failures into a safe, localized UX and never exposes raw provider messages, stack traces, or internal diagnostics.

## Client-side fetching

- Fetch on the client only when the server is not a fit: user-triggered refreshes, incremental interactions, or post-render mutations.
- Keep client fetching behind use cases and adapters; components never call third-party SDKs directly.
- When a route needs client fetching plus session state, split container and presenter: the container owns session, fetching, mutation state, and validation flow; the presenter renders props and emits callbacks.
