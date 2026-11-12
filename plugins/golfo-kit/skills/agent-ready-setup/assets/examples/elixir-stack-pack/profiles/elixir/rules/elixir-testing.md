# Elixir Testing Rules

- Tests use ExUnit and live under `test/`, mirroring `lib/`, with names ending in `_test.exs`.
- Mark a test module `async: true` unless it touches shared state (the database without the SQL sandbox, global config, named processes).
- Describe behavior in the test name: `test "rejects an expired token"`.
- Isolate external services behind a behaviour and a test implementation configured in `config/test.exs`; do not mock modules you own.
- Run `mix test` for the files you changed before finishing, and the whole suite before a pull request.
