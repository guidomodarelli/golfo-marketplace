# Root Cause Bug Fixes

When correcting an error, bug, crash, regression, or similar failure, diagnose and repair its cause before optimizing for speed, fewer lines, or a smaller diff. Simplicity is a criterion for choosing between fixes that address the cause; it does not justify leaving the faulty operation in place.

## Diagnose before choosing the fix

- Reproduce the failure when possible. Trace the failing operation, its caller, the relevant contract, and the boundary responsible for handling it. Read installed dependency behavior or authoritative documentation when the diagnosis depends on framework semantics.
- Distinguish confirmed causes from hypotheses. A stack trace, request, failing test, or controlled reproduction must support the diagnosis; without that evidence, explain what remains unverified.
- Correct the invalid operation, missing validation, incorrect ordering, or broken error propagation in the component that owns it. Cover the causal path and affected consumers without expanding into unrelated hardening or refactors.
- Do not fix a problem with a fallback that hides it (a default value, a retry, a catch that substitutes a result, a guard that skips the failing path). Use the debugger or a controlled reproduction when needed to find the cause. See also `Errors and responses` in `patterns-we-do-not-use.md`.
- When the owning component is a library, the backend, or another repository, make the change there. If you do not know where the change belongs or do not have access, ask the user for the location or the access instead of patching the consumer.

## Preserve framework contracts

- Do not introduce blanket wrappers, monkey patches, overridden registration methods, or replacement framework components to compensate for an application bug. Keep the project framework, Express, and other dependencies behind their supported APIs.
- For an async handler, trace operations that can reject or throw, including input reads and preparation before an existing `try`. Await promises inside the `try` when its `catch` owns rejection handling; returning a promise without awaiting it does not let that `catch` handle a later rejection. Forward failures at the owning application boundary, for example with `next(error)` in an Express handler.
- Check that the intended error middleware is registered after the relevant routes or subrouters. Adding that middleware alone does not capture promises that the installed router does not observe; repair the handler's propagation too.
- Preserve deliberate fallbacks, business responses, and observability when fixing unexpected failures. Do not silence errors, fabricate success, or change a public contract to hide the defect.
- Use an adapter or dependency change only when evidence shows an actual integration or library limitation and the supported alternatives have been evaluated. A temporary containment measure must be identified as temporary, with its remaining cause and removal condition; do not report containment as a completed root-cause fix.

## Prove the correction

- Validate observable behavior through the affected public flow. When practical, demonstrate that the reproduction fails before the fix and passes afterward; exercise real framework or SDK behavior when it is responsible for the failure.
- For a crash caused by rejected async work, verify both the error response and the continued availability of the server or worker. A successful response on the happy path alone does not prove the error path is repaired.
- Report the supported cause, the correction at its owning boundary, the verification performed, and any remaining uncertainty. Remove temporary fault injection after verification unless the user explicitly wants it retained for their test.
