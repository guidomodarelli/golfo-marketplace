# Security Rules — Go

- Never hardcode secrets, tokens, or credentials; read them from environment variables or the project's secret manager, and never log them.
- Validate every untrusted input (request body, query, path parameters, headers) at the handler boundary before it reaches business logic, using an allowlist.
- Build SQL only with placeholders (`$1`, `?`) through `database/sql` or the project's query builder; never concatenate or `fmt.Sprintf` user input into a query.
- Run external commands with `exec.CommandContext` and separate arguments; never pass user input to a shell (`sh -c`).
- Resolve user-supplied file paths with `filepath.Clean` and confirm they stay inside the allowed root before opening them.
- Give every outbound `http.Client` and every `http.Server` explicit timeouts; never rely on the zero-timeout defaults for network calls.
- Use `crypto/rand` for tokens and identifiers that must not be guessable; never `math/rand`.
- Return safe error messages to clients. On the server, log the failure as `error-handling.md` › `Diagnosable failures` defines: the cause chain as error type names and closed codes plus opaque identifiers, never stacks, messages, SQL, or provider payloads.
- Run `govulncheck ./...` when dependencies change and resolve the vulnerabilities reported in called code.
