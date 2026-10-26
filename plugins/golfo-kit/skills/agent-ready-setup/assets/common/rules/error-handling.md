# Error Handling

Every failure must end in a deliberate outcome that someone can see and trace.

## Catch blocks

- Every `catch` (or error branch, in languages without exceptions) does at least one intentional thing: map an expected failure to a stable result, log an unexpected failure with context, trigger safe user feedback, or return or rethrow it to the boundary that owns the response.
- Do not add an error handler that only swallows the error or redirects control flow without classification, logging, or feedback. See also `Errors and responses` in `patterns-we-do-not-use.md`.
- When wrapping or rethrowing, keep the original error attached with your language's mechanism (for example `cause` in JavaScript or `%w` in Go).

## Diagnosable failures

A failure must say why it happened in the first log line someone reads, without exposing PII, secrets, or raw payloads.

- Every failure that reaches the boundary owning the response keeps its real error as the cause, and every own error type exposes a closed, stable code (`invalid_configuration`, `verification_unavailable`, a SQLSTATE), not free text.
- The boundary logs that cause chain as error type names and closed codes only, next to the opaque identifiers of the operation (see `Logs`): never messages, stacks, or values. A boundary that hides the cause entirely turns every failure into the same anonymous "unexpected" entry; fix the boundary rather than adding ad-hoc logs.
- Wrap configuration reads, provider calls, and database calls in the feature's typed error, with the cause, at the place they can fail. An untyped error that escapes an operation becomes an unclassified 500.
- An expected business rejection (4xx) that has a domain reason carries that reason as a typed cause with its code, so the log names the unmet requirement instead of a generic code. The client keeps receiving only its own safe contract.
- Do not answer a failure with a `200` response that carries an error object; see `Errors and responses` in `patterns-we-do-not-use.md`.
- When reproducing a reported server error, read the logged cause chain first. If a failure still logs without it, adding the missing cause is part of the fix.

## Logs

- Use structured logs with the operation name and the identifiers needed to debug it: opaque, stable identifiers such as `userId`, `requestId`, `traceId`, and resource IDs.
- Log unexpected failures once, at the boundary that owns the user-facing response.
- For retries and external provider calls, record each attempt and the final outcome with the same trace context. The layer that owns the retry loop records the attempts; if the project forbids logging in that layer (for example in services), return the attempt metadata to the boundary and log it there.
- Never log secrets, tokens, cookies, authorization headers, raw request or provider payloads, or PII (emails, phone numbers, names, addresses). Opaque identifiers are not PII for this rule, as long as they are internal identifiers and not a PII value used as a key. The stack's `security.md` may add stricter rules; the stricter rule wins.

## Error codes

When the project keeps a catalog of technical error codes:

- Give every technical error from server-side flows and external integrations (APIs, providers, databases) a stable code from that single catalog. Do not create ad-hoc or duplicated codes.
- Return the code next to the error message in technical error responses; success responses stay unchanged. When a skill's example returns only `{ error }` for a technical failure, add the catalog code in projects that keep one.
- Do not attach catalog codes to request, form, or business validation errors. Validation responses keep the codes their own contract defines (for example a validator's issue codes).
- A catalog code is an opaque support reference, not an infrastructure detail: the UI may show it as secondary text below the generic message, never instead of it, and never together with status codes, provider names, or other technical details.
- When a new flow can produce technical errors, or you find one without a code, add its code in the same task.
