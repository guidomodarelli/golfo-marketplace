# Environment Readiness

A missing configuration value or an outdated local database must show up when the app starts, not as a server error in the middle of a flow.

## Environment variables

- Every environment variable a feature reads is added, in the same change, to the project's example environment file and to a single startup requirements registry, with the feature that needs it and a severity: `blocking` when the feature cannot work without it, `degraded` when the feature turns itself off.
- When a present value can still be unusable (JSON, keys, URLs, enums), the requirement validates it with the same parser the feature uses at runtime, so a malformed value fails at startup too.
- The startup check logs every unmet requirement with the feature, the variable names, and the validation's error types and codes; never values. In local development a blocking requirement stops the app before any flow runs. In production the check only logs: the affected feature keeps failing closed on its own, and the log says why.
- Skip the check during builds that run without runtime secrets.
- Do not paper over a missing variable with a hardcoded fallback.

## Local database

- The local development start command warns when the configured database lacks versioned migrations from the repository, naming the database host and the pending migrations. It never blocks startup when the check itself cannot run; it says why.
- Apply pending migrations on the developer's own disposable database (a personal branch or local instance) before testing a flow by hand, following `database.md` for where migrations may run.
- When a feature needs local secrets or enrolled key material to work (signing keys, encryption keyrings), the command that prepares the local database generates development-only values when they are missing, stores them only in a git-ignored local environment file, and enrolls them in that same local database. Never reuse those values in another environment.
