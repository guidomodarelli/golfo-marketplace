# Testing Rules — Go

- Use the standard `testing` package with table-driven tests and `t.Run` subtests named after the scenario.
- Run `go test -race ./...` for changes that touch goroutines, channels, or shared state.
- Mark helpers with `t.Helper()`, register cleanup with `t.Cleanup`, and use `t.TempDir()` for files instead of fixed paths.
- Replace dependencies through the interfaces the consuming package declares (hand-written fakes are preferred); do not mock the standard library.
- Test HTTP handlers with `net/http/httptest` and assert status, headers, and body as the client sees them.
- Keep tests that need external services (database, network) behind a build tag or `testing.Short()` so the default unit run stays hermetic.
