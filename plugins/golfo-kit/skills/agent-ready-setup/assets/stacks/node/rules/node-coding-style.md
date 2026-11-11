# Coding Style Rules — Node

- Follow the linter and formatter the project already configures; do not reformat unrelated code.
- Use `async`/`await` and handle every rejection: no floating promises, and no mixing of callbacks and promises in the same flow.
- Run independent async work concurrently with `Promise.all` or `Promise.allSettled` instead of a sequential `await` inside a loop.
- Never block the event loop with synchronous I/O (`fs.*Sync`, `child_process.*Sync`) or CPU-heavy work in request handlers.
- Read configuration from environment variables once, validated at startup, in a dedicated config module; do not read `process.env` throughout the code.
- Keep route handlers thin: validate input, delegate to a service, and map the result to the response.
- Give every outbound HTTP call a timeout and propagate cancellation (`AbortSignal`) when the caller can abort.
