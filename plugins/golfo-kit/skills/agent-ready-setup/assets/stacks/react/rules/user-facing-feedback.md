# User-Facing Feedback Rules — SSR + React

These rules apply when a critical or async action modifies, loads, or requests data: submit, search, navigation, edit, retry, or mutation. For user-facing copy wording, see `User-facing copy` in `react-style.md`.

## Validation and states

- Validate inputs and the allowed state before running the action; block an invalid action instead of letting it fail silently.
- Render loading, success, empty, and error explicitly and accessibly, close to the control that started the operation.
- Keep validation state, operation state, and any error tracking context separate; do not reuse one generic message for different states.
- Clear `errorMessage`, `validationMessage`, any error tracking context, timers, listeners, and `AbortController`s when the resource, facility, access, or filter changes, when a modal closes or reopens, and when a new attempt or retry starts.
- Never show an error from a previous resource while a new resource is loading or ready, and never let a previous result update a new selection.

## Incremental mutations

- Prefer incremental responses over full route refreshes: when the mutated UI can be updated from a safe result, the route handler or server action returns the minimum view model needed to update the affected state.
- Refresh the whole route only when it is justified by broad cache invalidation, data that cannot be rebuilt safely from the result, a security or authorization change, or critical cross-view synchronization. Document the reason next to the refresh.
- Tests for user-triggered mutations assert the observable outcome of an incremental update: the affected UI shows the result while unrelated state (form input, scroll, focus, open panels) is preserved. Do not assert on calls to framework refresh helpers; cover the whole-route behavior in an integration or end-to-end test when it matters.

## Async feedback and error tracking

- Use the toast or notification component of the project's UI library (for example `toast` from `@golfo/ui`, backed by Sonner) for async feedback: loading, success, information, expected warnings, and recoverable errors. Prefer its promise helper (for example `toast.promise`) for write operations so loading, success, and failure share one lifecycle. Mount the project's toaster once, as its conventions define; never mount a second one or restyle toasts locally.
- Use inline messages next to the control (not toasts) for local validation, empty lists, and valid business states. A degraded but valid response (for example a `202` with pending requirements) keeps its status and stays a business state, not a technical error.
- Wire an error tracking feedback component (for example one tied to the project's error monitoring tool) only when the project has one, a real error tracking context exists, and the failure is actionable or unexpected and needs tracking. Never fabricate a context from the component; without one, show a safe visual fallback. Do not add an error monitoring tool only to satisfy this rule.
- Enable retry only when it is safe or idempotent, or resumes known progress; a retry must never create a duplicate mutation.
- Keep the public message short, localized, and separate from the technical detail.
- The detail may include operation, stage, category, code, dependency, status, counts, and opaque stable identifiers (`userId`, `requestId`, correlation or `traceId`, resource ids). Never include the raw condition, upstream payload, full request or response, headers, cookies, tokens, secrets, or PII (emails, phone numbers, names) in the detail, logs, DTOs, or test assertions.

## Accessibility

- Associate feedback with the affected control or region.
- Use suitable roles and live regions without announcing the same error twice.
- Keep focus, close, and retry usable from the keyboard.

## Tests

- Cover happy path, error, loading, empty, retry, cancellation, and partial states when the flow has them.
- For async feedback, cover the toast or notification shown for each outcome (loading, success, failure) through what the user sees, rendering the project's real toaster instead of mocking the UI library.
- When the project has an error tracking feedback component, also cover: valid error tracking context, unexpected error without retry, fallback without context, stale-state cleanup, and no error tracking feedback in expected states.
- Test logs only when they are part of an explicit contract; prefer asserting the public projection and the sanitized detail.
