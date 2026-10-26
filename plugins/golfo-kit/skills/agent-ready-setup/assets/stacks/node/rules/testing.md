# Testing Rules — Node

- Use the test runner the project already configures (Jest, Vitest, or `node:test`); do not introduce a second one.
- Test HTTP routes through the real app (for example with Supertest) and assert status, headers, and body as the client sees them.
- Replace dependencies at the boundaries the project owns (repositories, outbound clients); do not mock Node built-ins or the framework.
- Await every async assertion and fail on unhandled rejections; instead of fixed `sleep` delays, use fake timers or wait for the observable condition.
- Run repository and SQL tests against a real database (a container or the project's test database).
- Do not mock your own database layer in integration tests; see `Data` in `patterns-we-do-not-use.md`.
