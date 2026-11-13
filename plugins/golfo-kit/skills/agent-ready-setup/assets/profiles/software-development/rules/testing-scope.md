# Testing Scope

Write only tests that exercise behavior: what the product or a script observably does. A test that cannot fail when the behavior breaks is noise, and it slows every change.

## Tests to write

- Assert observable behavior: rendered UI and interactions, use case results, adapter and mapper outputs, route handler responses, SQL run against a real database, and the effects of running a script.
- When functionality changes, add or update its tests in the same task.
- Mock at the port boundary of the project, not inside vendor internals, unless the test is the adapter test for that vendor.
- Do not mock your own database layer in integration tests; see `Data` in `patterns-we-do-not-use.md`.

## Tests not to write

Do not add these tests. When one is part of the code your task already changes, delete or rewrite it; when you find one elsewhere, report it instead of deleting it:

- Tests that only restate constants or configuration values, check that a module exports or imports something, check function arity or other language details, or snapshot static data.
- Tests that assert on mocks the test itself configured with no product logic in between, such as a use case that returns the repository double's value unchanged, or a wrapper test that only checks a mocked SDK was called.
- Tests that duplicate another case without adding coverage, assert static CSS classes with no conditional logic, or test a third-party library instead of the project's code.
- Tests that read files committed to the repository (source, migrations, styles, configs, scripts, `package.json`, docs) to assert on their text, regexes, or internal strings. Reading a file only to feed it to the real tool under test is allowed, and so is asserting on files that the code under test writes during the test (for example a script's generated output in a temporary directory).
- Tests for framework, platform, or build configuration (redirects, headers, bundler, ORM or deploy settings, environment-file loading). Verify those changes by running the app or the build.
- Tests that assert on SQL text, query chunks, or how many statements a mocked executor received. Assert the mapped result, the returned status, or the calls to external providers; to verify what the SQL does, run it against a real database.
- Tests of scripts or thin wrappers that assert the argument lists, command lines, file paths, or names they build for an external CLI or SDK. Test their own logic (parsing, decisions, redaction, error handling) or the effects of running them.
- Tests whose only purpose is to verify that tooling is configured or active (linter rules and plugins, formatter, type checker, build, hooks). Run the tool itself instead.

## Exception: tooling tests the project requires

When the project's `AGENTS.md` explicitly requires a tooling or repository-convention test (for example a test that walks the routes directory to enforce where tests live, or one that checks the linter configuration loads a project rule), that test is allowed even if it falls under the bullets above about reading committed files, framework or build configuration, script arguments, or tooling configuration:

- Write, keep, and update only the tooling tests the `AGENTS.md` names or describes; do not extend the exception to similar tests it does not ask for.
- Keep them in the location the `AGENTS.md` declares for them, and make each one fail with a message that says which convention was broken.
- If the `AGENTS.md` stops requiring a tooling test, the general rule applies again: delete it when your task touches it, or report it otherwise.
