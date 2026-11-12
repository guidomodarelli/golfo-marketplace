# Outbound Upstream Contract Rules

These rules apply to payloads that server-side code (a route handler, server action, BFF, or infrastructure adapter) sends to an upstream endpoint, and to how that code consumes upstream responses. They are framework-neutral and complement the input-validation rules: an outbound request payload is not an upstream response and is not a public DTO of the server boundary.

## Payload ownership

- Treat every request body sent to an upstream endpoint as an endpoint-specific contract owned by the adapter or service boundary (in projects with `src/modules/<feature>/`, the infrastructure adapter behind a domain port).
- Keep the outbound payload as a named, complete entity for one upstream operation, such as `CreateShipmentUpstreamRequest` or `buildCreateShipmentPayload`.
- Keep outbound payload construction separate from the client request, the public DTO of the server boundary, the upstream response type, headers, query parameters, and transport configuration.
- Never forward the raw client request body to an upstream client, and do not use a spread of it (`{ ...body }`) as a substitute for explicit mapping. Explicit mapping prevents client-only fields from leaking and makes upstream contract changes easy to locate.
- Build the payload from input that has already been validated at the server boundary, plus the domain or integration context required by the upstream contract. Do not move public-input validation into the payload builder.
- Centralize upstream-specific field names, transformations, defaults, and conditional nested sections in the payload factory or builder. The adapter should send the built entity without hidden mutation.
- Keep optional fields omitted unless the upstream contract or business rule requires them; complete means all fields required for the operation are assembled, not that every optional field is populated.

## Factory versus builder

- For a simple payload, use a named object or small factory function close to the adapter; do not add ceremonial builder classes.
- Use a builder when the payload has meaningful composition, conditional sections, repeated transformations, or multiple construction steps. Keep one builder or factory per upstream operation rather than one generic builder for unrelated endpoints.
- Prefer names that identify both operation and upstream boundary, such as `buildCreateShipmentUpstreamRequest`, so the request contract is searchable from the endpoint integration.

## Validation boundary

- Validate untrusted client input once at the server boundary (route handler, middleware, server action, or server hook) using the repository's approved validation mechanism.
- Do not add runtime schema validation of an upstream response or error payload. Consume responses according to the adapter contract.
- Never forward a raw upstream payload (success or error) to a client response, a public error, or a log. Map what the consumer needs into the adapter's own result or public DTO.
- When a missing, `null`, `undefined`, or intentionally empty upstream value has a safe contract-approved default, apply that fallback before narrowing: use `??` for nullish values and `||` only when every falsy value is equivalent to absence. The fallback must not invent authorization, eligibility, ownership, success, or provider facts.
- Use structural narrowing only when it changes control flow or is required for safe access and no safe fallback exists. Narrowing may inspect transport/status metadata or a minimum flow discriminator such as `PROCESSING` or `FINISHED`; it must never become provider-payload validation, a field allowlist, or an error-shape parser.
- Never introduce `normalize*Response`, `parse*Response`, response-shape guards, or field-by-field response validators for provider payloads. Do not throw a response-invalid error merely because optional fields are absent or a provider shape differs from the expected example.
- If no safe fallback exists and the minimum flow discriminator is unavailable, use the adapter's safe empty/default projection when the contract permits it; otherwise map a controlled adapter failure without forwarding the raw payload and without introducing full contract validation.
- Do not treat a payload factory as a reason to revalidate an already validated request or to verify the provider's response shape.

## Express and Pages Router specifics

> **Applicability:** this section applies only when the project serves its API through Express (a BFF with `express.Router`) or the Pages Router (`getServerSideProps`). In Next.js App Router projects, use route handlers (`app/**/route.ts`) and validate at that boundary instead; the framework-neutral rules above still apply.

- Do not pass `req.body` directly to an upstream client, and do not use `{ ...req.body }` as a substitute for explicit mapping.
- Map the fields the validation middleware already parsed into the service input, and let the service build the upstream request:

  ```ts
  router.post('/shipment', createShipmentValidationMiddleware, async (req, res) => {
    const { originZipCode, destinationZipCode } = req.body;
    const shipment = await createShipment({ originZipCode, destinationZipCode });
    res.status(201).json(shipment);
  });
  ```

## Tests

- Test the observable outbound contract by asserting the request body received by the project's real HTTP mock or integration test boundary.
- Cover required fields, upstream-specific transformations, conditional sections, omission of client-only fields, and operation-specific defaults.
- Do not mock the platform HTTP client when the repository provides a real HTTP interception mechanism; use that mechanism to verify the actual request sent to the upstream endpoint.
