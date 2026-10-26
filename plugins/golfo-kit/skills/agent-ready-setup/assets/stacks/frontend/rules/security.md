# Security Rules — Frontend (SSR + React + TypeScript)

Baseline security rules for SSR React applications. These rules are always active and condition all code generation. The `security-scanner` agent uses this file as its baseline checklist and as supplementary context for the findings of any configured security tool.

---

## Secrets & PII

- Never hardcode secrets, tokens, or API keys — read them at runtime from the project's secrets manager.
- Never log PII (emails, phone numbers, names, addresses, document numbers), raw request or response payloads, or credentials (secrets, tokens, cookies, authorization headers). Use the project's logger.
- Opaque, stable identifiers are allowed in logs and are expected for debugging: `userId`, `requestId`, `traceId`, and resource IDs. They must be internal identifiers, never a PII value used as an identifier (for example, an email as a user key).
- Never receive PII or tokens via query parameters — use request body.
- Never expose sensitive data in React state or Context, nor in a client store if the project uses one — keep it server-side only.

## Input Validation

- Middleend endpoints must validate all untrusted client-controlled request inputs (body, query params, path params, headers) at the controller/handler boundary using the project's input validation library (for example, zod).
- Validate each route once at that boundary; handlers consume the already validated values and keep only business rules that the schema cannot express.
- Validate the public DTO that the middleend returns to its client or consumer before handing it over: that DTO is the middleend's own contract, and validating it keeps internal fields and inconsistent shapes from leaking. Reject an unusable DTO safely, without exposing internal diagnostics.
- Never revalidate payloads received from backend/upstream services; they are response data, not client input. Consume them according to the adapter contract instead of adding a second validation step.
- Never validate the complete format or contract of a backend/upstream success payload or error payload at runtime. Do not add a schema, allowlist, field-by-field check, type guard, or error-shape parser for the provider response.
- Prefer a safe fallback before structural narrowing when absence, `null`, `undefined`, or an intentionally empty value can use an adapter-approved default. Use `??` for nullish fallback and `||` only when every falsy value is intentionally equivalent to absence; never use a fallback that fabricates authorization, eligibility, ownership, success, or provider facts.
- Use structural narrowing only when it changes control flow or enables safe access and no safe fallback exists. Valid examples are HTTP status or transport metadata, `null` versus `array` versus `object`, or a minimum discriminator such as `PROCESSING` or `FINISHED`. This narrowing is not upstream contract verification and must not become a complete field allowlist, type guard, or error-shape parser.
- Never add a `normalize*Response`/`parse*Response` helper, response-shape guard, field-by-field response validator, or client-error throw solely because an upstream or backend response differs from an expected shape. Apply approved defaults first; narrow only to choose a flow or avoid unsafe access.
- If an upstream response cannot be consumed after safe fallback and the minimum flow discriminator is unavailable, continue with the adapter's safe empty/default projection when the contract permits it; otherwise map a controlled integration failure without forwarding the raw payload or introducing full contract validation.
- Whenever code needs to validate a variable, function argument, method argument, or intermediate value that is not a backend/upstream response payload, prefer the project's input validation library over native validation.
- If the input validation library cannot express the complete requirement, keep it as the primary validation and add only the narrowly scoped native checks that are still necessary, such as `Number.isSafeInteger`.
- Use allowlist strategy for client-controlled inputs and public middleend DTOs — define what is permitted, reject everything else.
- Never trust user-provided identifiers directly — retrieve user identity from session or JWT claims.

### Validation decision order

1. Check the HTTP status and the available transport metadata.
2. Apply an adapter-approved safe fallback, then structural narrowing only if control flow still requires it.
3. For client input, run schema validation at the middleend boundary, before the handler.
4. For the public middleend DTO, run its guard or contract validation before handing it to the client or consumer.
5. Never turn an observation of an upstream response into full revalidation of that response.

Never request upstream response validation in reviews, fixes, verifications, or closeouts.

### Validation tests

- Invalid client input is rejected at the middleend boundary.
- A valid public DTO reaches the consumer, and an unusable DTO is rejected safely.
- Upstream responses are consumed without schema revalidation.
- `PROCESSING`/`FINISHED`, `array`/`object`, or `null` are distinguished only where they change control flow.
- Handlers do not validate again what the boundary already validated.
- Raw upstream payloads never reach responses, logs, or public errors.
- Tests exercise the real validator and its observable contract; do not mock the validator.

## XSS Prevention

- Never use `dangerouslySetInnerHTML` with untrusted content — use `DOMPurify` if HTML rendering is required.
- Never inject raw JSON or JS objects into HTML responses — use a safe serializer that escapes HTML-sensitive characters (for example, `serialize-javascript`).
- Never weaken or bypass Content Security Policy (CSP).

## HTTP & Outbound Calls

- Use the project's HTTP client for all external HTTP calls.
- Never pass user-controlled input directly to `fetch`, `axios`, or `http.request` — validate destinations against a static allowlist.
- Never use GET for state-modifying operations.
- Never configure CORS without formal security review — never use wildcards (`*`).

## Secure Coding

- Never use `Math.random()` — use `crypto.randomBytes()` or `crypto.randomInt()` from `node:crypto`.
- Never use sequential or predictable identifiers (auto-increment, UUID v1/v6/v7, timestamp-based) — use `crypto.randomUUID()` from `node:crypto` (UUID v4).
- Never use string concatenation for SQL queries — use parameterized queries or ORM.
- Never use `eval()`, `Function()`, or `setTimeout`/`setInterval` with strings.
- Never use deprecated crypto (MD5, SHA1, DES, RC4) — use AES-256, SHA-256, RSA-2048+.
- Never use regexes with exponential complexity on user input — validate for ReDoS resistance.

## Error Handling

Treat the middleend/BFF as an error-origin boundary: preserve statuses received from upstream, and translate only failures owned by the BFF into its public HTTP contract.

- Preserve the HTTP status received from upstream, including upstream 4xx and 5xx. The BFF may sanitize or adapt the public error body, but must not replace an upstream status with a BFF-owned status merely because the payload is being translated.
- For failures owned by the BFF and attributable to the request or domain state, return the corresponding 4xx: `400` for malformed requests, `401` for missing or invalid authentication, `403` for insufficient permissions, `404` for missing resources, `409` for state conflicts, or `422` for semantically invalid or unprocessable input.
- For failures owned by the BFF that are genuinely unexpected or internal, return an appropriate 5xx. Use `502`/`504` for integration failures such as an upstream transport failure, timeout, or response without a usable HTTP status; choose the status according to the failure cause.
- Do not use a generic 5xx fallback for a known BFF client/domain error, and do not convert an upstream 4xx into a BFF 5xx. Preserve a safe public message and log the diagnostic cause server-side without exposing internals.
- Do not classify hydration or partial-attribute failures by symptom alone. First identify the origin: when client-controlled input or domain state caused incomplete attributes, map the cause to its applicable BFF-owned 4xx; when upstream transport/status metadata or adapter classification identifies a dependency failure, preserve the upstream status or map a no-status integration failure to the appropriate 5xx. Do not validate the full upstream success or error payload to make that classification.
- If the adapter cannot consume an upstream response, map a controlled integration failure at that boundary without forwarding the raw payload or introducing full upstream contract validation.
- Keep upstream status reporting truthful in every diagnostic artifact (error tracking details, structured logs, metrics): report only the real HTTP status returned by the upstream dependency, and report `unknown` when the dependency returned no status. A BFF-synthesized `503`/`504` chosen as the public response status is never the upstream status and must not be labeled as one; when the BFF owns a status mapping, keep it separate from the reported upstream status so diagnostics never invent upstream facts.
- When a shared helper extracts an HTTP status from a caught error to report it as the upstream status, never let it read that status from the BFF's own typed/domain error classes — a malformed-payload error, a domain validation error, or a rule/eligibility classification carries a `status` the BFF assigned for its own public contract, not a fact the dependency reported. Give any error that legitimately wraps a real dependency failure its own explicit `upstreamStatus` field, populated only from that failure, and have the shared helper trust that field (an `instanceof` check on the BFF's own error hierarchy, or equivalent) instead of falling back to `status`/`response.status` for those classes; reserve that fallback for raw, unclassified transport rejections. Test both origins: a raw upstream failure and a BFF-owned typed-error failure must never produce the same reported upstream status.
- Never expose stack traces or internal error details to users — return generic messages.
- Never log sensitive data in error handlers; log the error type, its stable code, and the opaque identifiers of the operation instead (see `error-handling.md`).
- Do not return `200` responses that carry an error object; see `Errors and responses` in `patterns-we-do-not-use.md`.

## Authorization

- Use the project's approved authentication and authorization libraries for all new auth/authz implementations; never hand-roll them.
- Always validate that user actions follow valid business workflows server-side.
- Never enforce critical business logic validations from user-controlled input.
- Do not put authorization logic in the client; see `Security and UI` in `patterns-we-do-not-use.md`.
