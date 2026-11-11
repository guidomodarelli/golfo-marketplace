# Coding Style Rules — Go

- Format every changed file with `gofmt` (or `goimports`) and keep `go vet` clean; the project's linter configuration (for example `golangci-lint`) decides the remaining style.
- Return errors as the last value and handle them where they occur. Wrap with context using `fmt.Errorf("operation: %w", err)` and compare with `errors.Is` or `errors.As`, never by message text.
- Do not `panic` for expected failures; reserve it for programmer errors during initialization.
- Pass `context.Context` as the first parameter of every function that performs I/O or can block, and propagate it instead of creating `context.Background()` mid-call.
- Keep packages small and named by responsibility (`billing`, `httpapi`), never `util`, `common`, or `helpers`. Accept interfaces and return concrete types; declare an interface in the package that consumes it.
- Do not add generic abstractions with a single implementation; see `Architecture and dependencies` in `patterns-we-do-not-use.md`.
- Every goroutine has an owner that can stop it (context cancellation or a closed channel) and waits for it to finish (`sync.WaitGroup` or `errgroup`).
- Export only what other packages use, and document every exported identifier with a comment that starts with its name.
