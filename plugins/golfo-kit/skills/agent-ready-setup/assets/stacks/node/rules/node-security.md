# Security Rules — Node

- Never hardcode secrets, tokens, or credentials; read them from environment variables or the project's secret manager, and never log them.
- Build SQL only with parameterized queries through the project's driver or query builder; never interpolate user input into a query.
- Run external commands with `execFile` or `spawn` and an argument array; never pass user input to `exec` or a shell.
- Never pass untrusted input to `eval`, `new Function`, `vm`, or a dynamic `require`/`import`.
- Do not merge untrusted objects into existing ones (`Object.assign`, deep merge) without an allowlist of keys; reject `__proto__`, `constructor`, and `prototype`.
- Return safe error messages to clients. On the server, log the failure as `error-handling.md` › `Diagnosable failures` defines: the cause chain as error type names and closed codes plus opaque identifiers, never stacks, messages, SQL, or provider payloads.
- Run `npm audit` (or the package manager's equivalent) when dependencies change and resolve reported vulnerabilities.

## Payload Validation Boundaries

Keep three payloads apart: client input received by the service, the public DTO the service returns to its consumers, and responses from backend/upstream providers.

### Client input

- Validate `req.body`, `req.query`, `req.params`, and every client-controlled header the route reads at the service's entry boundary: they are untrusted input, and the boundary is the only place to reject them before business logic runs.
- Use the validation library the repository already adopted (for example, zod). Add a new one only when none exists or it cannot express the requirement.
- Validate each route once; handlers consume the validated values and keep only business rules that the schema cannot express.
- Use an allowlist: define what is permitted and reject everything else, without echoing input values in the error.

### Public DTO

- Validate the DTO the service returns to its consumers before handing it over: it is the service's own contract, and validating it keeps internal fields and inconsistent shapes from leaking.
- Allowlist its public fields, types, states, and discriminators; reject an unusable DTO safely, without exposing internal diagnostics.

### Upstream responses

- Never revalidate backend/upstream responses as if they were client input: the provider owns that contract, and revalidating it couples the service to fields it does not consume and breaks on compatible upstream changes.
- Do not add schemas, validation middleware, field-by-field checks, type guards, or `normalize*Response`/`parse*Response` helpers for provider success or error payloads.
- Consume the response according to the adapter contract. Narrow structurally only when control flow or safe access requires it: prefer the HTTP status, distinguish `null`, `array`, and `object` when that changes the flow, and read minimum discriminators such as `PROCESSING` or `FINISHED`. That narrowing never becomes a full field allowlist.
- If the response cannot be consumed, map a controlled failure in the adapter or service; never forward the raw payload.
- Never request upstream response validation in reviews, fixes, verifications, or closeouts.

### Decision order

1. Check the HTTP status and the available transport metadata.
2. Narrow structurally only if control flow requires it.
3. For client input, run schema validation at the boundary, before the handler.
4. For the public DTO, run its guard or contract validation before handing it to the consumer.
5. Never turn an observation of an upstream response into full revalidation of that response.

### Required tests

- Invalid client input is rejected at the boundary.
- A valid public DTO reaches the consumer, and an unusable DTO is rejected safely.
- Upstream responses are consumed without schema revalidation.
- `PROCESSING`/`FINISHED`, `array`/`object`, or `null` are distinguished only where they change control flow.
- Handlers do not validate again what the boundary already validated.
- Raw upstream payloads never reach responses, logs, or public errors.
- Tests exercise the real validator and its observable contract; do not mock the validator.
