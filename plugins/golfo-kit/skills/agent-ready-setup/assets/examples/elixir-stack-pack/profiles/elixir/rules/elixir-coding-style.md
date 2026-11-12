# Elixir Style Rules

- Run `mix format` before committing; the project's `.formatter.exs` is the source of truth for layout.
- Keep functions small and pattern-match in function heads instead of branching with `if` or `cond` on the same value.
- Return `{:ok, value}` or `{:error, reason}` from functions that can fail, and use `with` to chain them. Raise only for programmer errors.
- Name modules by what they own (`Billing.Invoice`), not by layer (`InvoiceHelper`).
- Run `mix credo --strict` when the project has Credo; report a missing tool as `N/A` instead of installing it.
