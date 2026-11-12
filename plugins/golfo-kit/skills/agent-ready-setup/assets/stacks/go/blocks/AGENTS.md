<!-- Managed by agent-ready-setup: this section is replaced on every sync. Add project instructions outside it. -->
## Go

The Go stack of agent-ready-setup covers Go modules. Its rules are listed above with the `go-` prefix (`.agents/rules/go-security.md`, `.agents/rules/go-testing.md`).

To review a pull request, run `/go-review-pr`: it runs the `go-security-scanner` and `go-perf-analyzer` agents.
