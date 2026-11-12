# API Configuration Rules

How API endpoints and services receive upstream configuration such as scopes.

> **Applicability:** the `config/` environment files below apply only when the project serves its API through Express (a BFF with `express.Router`) or the Pages Router (`getServerSideProps`) and already keeps per-environment files under `config/`. In Next.js App Router projects, use route handlers (`app/**/route.ts`) and read upstream configuration through the project's existing server-side configuration module (for example, validated environment variables) instead; the rule against `scope` query parameters still applies.

- Never add or forward `scope` as a query parameter (`?scope=...`, `params: { scope: ... }`, or equivalent URL construction). API scope belongs to client configuration, not request URLs.
- When an upstream client requires a scope, add a service-specific key to the existing environment files under `config/` (typically `config/local.js`, `config/default.js`, `config/production.js`, and `config/sandbox.js`) and consume it through the project's config module or the client option designed for configured scopes (for example, `scopeConfig`). Do not create a new config file solely for scope. Never hardcode environment values such as `sandbox` or `prod` in service code.
- Keep scope values in those existing `config/` files; do not duplicate them in services or handlers.
