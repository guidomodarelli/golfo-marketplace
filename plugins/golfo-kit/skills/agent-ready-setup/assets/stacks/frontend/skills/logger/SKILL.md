---
name: logger
description: Crea o reutiliza el logger compartido del proyecto (en utils/ o, si el proyecto usa src/modules, como infraestructura compartida en src/modules/shared/infrastructure/observability/) que envuelve la librería de logging ya declarada en package.json (proponiendo pino y pidiendo confirmación antes de instalarlo si no hay ninguna), lo nombra según el proyecto de package.json y expone los helpers logError y logWarning. Usar al configurar logging para API handlers SSR o al estandarizar el uso del logger entre API handlers.
metadata:
  tags: "context-optimized-v1.20.1"
---

# Logger Setup — SSR `/api`

Creates the project's shared logger — a single instance named after the project, with typed helpers for error and warning logs — or reuses the one that already exists. Keep it outside API subrouters.

The logger file path (`LOGGER_PATH` below) depends on the project's structure:

| Project structure | `LOGGER_PATH` | `package.json` import from that file |
|---|---|---|
| Code organized in `src/modules/<feature>/{domain,application,infrastructure}` (see `../../rules/hexagonal-architecture.md`) | `src/modules/shared/infrastructure/observability/logger.ts` | `../../../../../package.json` (or the project's root alias, for example `@/package.json`) |
| Any other structure | `utils/logger.ts` | `../package.json` |

Never create `utils/logger.ts` in a project with modules: the logger is shared infrastructure there, and `domain`/`application` never import it.

---

## Step 1 — Check prerequisites

```bash
# Verify package.json exists and has a name field
node -e "const p = require('./package.json'); if (!p.name) throw new Error('Missing name in package.json');"
```

If the command fails, ask the user to add a `name` field to `package.json` before continuing.

---

## Step 2 — Check if a logger already exists

Look for an existing shared logger before creating anything, in the expected paths and in any module that wraps a logging library:

```bash
# Expected paths
ls utils/logger.ts src/modules/shared/infrastructure/observability/logger.ts 2>/dev/null
# Any module that already wraps a logging library or exports logError/logWarning
grep -rlE "from '(pino|winston|bunyan|log4js|loglevel)'|export (const|function) (logError|logWarning)" --include='*.ts' --include='*.js' --exclude-dir=node_modules --exclude-dir=.next --exclude-dir=dist . 2>/dev/null
```

If a shared logger exists, reuse it and stop:
> "`<path>` already exists — reused, nothing created."

When the existing logger exposes different helper names, tell the user which ones the other skills should call instead of adding a second logger.

---

## Step 3 — Detect the logger library

The logger file imports a logger package, so that package must be declared before the file is created; otherwise `tsc --noEmit` fails with a missing module. The logger runs in production code, so it counts as available only when it is declared in `dependencies`: a deploy that runs `npm ci --omit=dev` (or the equivalent of the project's package manager) does not install `devDependencies`.

```bash
# Print the first logger library declared in dependencies, "<library> dev-only" when it is only in devDependencies, or NONE
node -e "const p = require('./package.json'); const runtimeDeps = p.dependencies ?? {}; const devDeps = p.devDependencies ?? {}; const known = ['pino', 'winston', 'bunyan', 'log4js', 'loglevel']; const runtimeLibrary = known.find((library) => runtimeDeps[library]); const devOnlyLibrary = known.find((library) => devDeps[library]); console.log(runtimeLibrary ?? (devOnlyLibrary ? devOnlyLibrary + ' dev-only' : 'NONE'));"
```

- If it prints a library name alone, use that library in Step 4 and do not install anything else.
- If it prints `<library> dev-only`, use that library in Step 4, but first move it to `dependencies` with the "Move to runtime" command of the table below. Run the detector again and continue only when it prints the library without `dev-only`.
- If it prints `NONE`, ask the user before installing anything, per `../../rules/established-libraries.md`: propose `pino` as a runtime dependency, say it backs the shared `logError`/`logWarning` helpers, and name the alternative the project already has (for example, the platform's own logging) or say there is none. Wait for confirmation. If the user declines, stop and report that no logger was created. After the user confirms, install it with the package manager that owns the project's lockfile:

| Lockfile | Install command | Move to runtime (`dev-only`) |
|---|---|---|
| `pnpm-lock.yaml` | `pnpm add pino` | `pnpm add --save-prod <library>` |
| `yarn.lock` | `yarn add pino` | `yarn remove <library> && yarn add <library>` |
| `bun.lockb` or `bun.lock` | `bun add pino` | `bun remove <library> && bun add <library>` |
| `package-lock.json` or no lockfile | `npm install pino` | `npm install --save-prod <library>` |

Moving an already declared logger from `devDependencies` to `dependencies` is not a new install: do it and mention it in the report. If more than one lockfile exists, ask the user which package manager the project uses before installing. If the install fails, report the command and its error and stop: do not create the logger file without its dependency.

---

## Step 4 — Create the logger at `LOGGER_PATH`

```bash
mkdir -p "$(dirname "$LOGGER_PATH")"
```

The blocks below import `package.json` as `../package.json`, which is correct for `utils/logger.ts`; at `src/modules/shared/infrastructure/observability/logger.ts`, use the import from the table at the top. Every variant keeps the same exported helpers (`logError`, `logWarning`), the same `Tags` type and the `name` from `package.json`. Libraries disagree on argument order, so adapt the import, the instance **and the calls inside both helpers** to the library detected in Step 3; never keep the Pino call shape with another library:

| Library | Instance | Call inside the helpers | Where `tags` go |
|---|---|---|---|
| `pino` | `pino({ name })` | `logger.error(tags ?? {}, message)` | First argument (merging object), message second |
| `winston` | `createLogger({ defaultMeta: { service: name }, transports: [new transports.Console()] })` | `logger.error(message, tags ?? {})` | Second argument (metadata), message first |
| `bunyan` | `bunyan.createLogger({ name })` | `logger.error(tags ?? {}, message)` | First argument (fields object), message second |
| `log4js` | `getLogger(name)` + `logger.level = 'warn'` | `logger.error(message, tags ?? {})` | Extra argument after the message |
| `loglevel` | `log.getLogger(name)` | `logger.error(message, tags ?? {})` | Extra argument after the message, forwarded to `console.error` |

`logWarning` uses the same shape with the `warn` method. Create the file with the block that matches the detected library.

`pino`:

```ts
import pino from 'pino';
import { name } from '../package.json';

type Tags = Record<string, string | number | boolean | undefined | null>;

const logger = pino({ name });

export const logError = (message: string, tags?: Tags): void => {
  logger.error(tags ?? {}, message);
};

export const logWarning = (message: string, tags?: Tags): void => {
  logger.warn(tags ?? {}, message);
};
```

`winston` (a logger without transports writes no entry and only warns about it, so declare at least the console transport):

```ts
import { createLogger, format, transports } from 'winston';
import { name } from '../package.json';

type Tags = Record<string, string | number | boolean | undefined | null>;

const logger = createLogger({
  format: format.json(),
  defaultMeta: { service: name },
  transports: [new transports.Console()],
});

export const logError = (message: string, tags?: Tags): void => {
  logger.error(message, tags ?? {});
};

export const logWarning = (message: string, tags?: Tags): void => {
  logger.warn(message, tags ?? {});
};
```

`bunyan` (it does not ship TypeScript types: declare `@types/bunyan` as a dev dependency with the "Dev types" command below before running `tsc --noEmit`; ask the user before installing it, like any other package):

```ts
import bunyan from 'bunyan';
import { name } from '../package.json';

type Tags = Record<string, string | number | boolean | undefined | null>;

const logger = bunyan.createLogger({ name });

export const logError = (message: string, tags?: Tags): void => {
  logger.error(tags ?? {}, message);
};

export const logWarning = (message: string, tags?: Tags): void => {
  logger.warn(tags ?? {}, message);
};
```

`log4js` (the default category level is `OFF`, so set a level or nothing is written):

```ts
import { getLogger } from 'log4js';
import { name } from '../package.json';

type Tags = Record<string, string | number | boolean | undefined | null>;

const logger = getLogger(name);
logger.level = 'warn';

export const logError = (message: string, tags?: Tags): void => {
  logger.error(message, tags ?? {});
};

export const logWarning = (message: string, tags?: Tags): void => {
  logger.warn(message, tags ?? {});
};
```

`loglevel` (its default level is `warn`, so both helpers are written without extra setup):

```ts
import log from 'loglevel';
import { name } from '../package.json';

type Tags = Record<string, string | number | boolean | undefined | null>;

const logger = log.getLogger(name);

export const logError = (message: string, tags?: Tags): void => {
  logger.error(message, tags ?? {});
};

export const logWarning = (message: string, tags?: Tags): void => {
  logger.warn(message, tags ?? {});
};
```

Dev types for `bunyan`, with the package manager that owns the lockfile (skip it when `@types/bunyan` is already declared):

| Lockfile | Dev types |
|---|---|
| `pnpm-lock.yaml` | `pnpm add -D @types/bunyan` |
| `yarn.lock` | `yarn add -D @types/bunyan` |
| `bun.lockb` or `bun.lock` | `bun add -d @types/bunyan` |
| `package-lock.json` or no lockfile | `npm install -D @types/bunyan` |

---

## Step 5 — Verify

```bash
<pm> run typecheck   # the project's type-check script
<pm> run lint
```

Use the package manager the lockfile declares. A script that does not exist is reported as `N/A`, per `../../rules/frontend-style.md` › `TypeScript`.

Fix any errors before reporting success.

---

## Step 6 — Report

Show the created (or reused) file path and a usage example. The example below is an Express handler from skill `/api-endpoint`, which applies only to projects with an Express BFF or the Pages Router; in a Next.js App Router project, call the helpers from the route handler (`app/**/route.ts`) that owns the response, importing them from `LOGGER_PATH`.

```ts
import { logError, logWarning } from '../../utils/logger';
import { mapKnownErrorToHttpResponse } from '../../src/errors/map-known-error-to-http-response';

try {
  const product = await getProduct(req.params.id);
  res.json(product);
} catch (error) {
  logError('[PRODUCT-GET] - error: product could not be loaded', {
    productId: req.params.id,
    errorType: error instanceof Error ? error.name : typeof error,
  });
  const publicError = mapKnownErrorToHttpResponse(error);
  res.status(publicError.statusCode).json({ error: publicError.message });
}
```

`mapKnownErrorToHttpResponse` is the project's typed error mapper described in skill `/api-endpoint`; its status mapping follows `../../rules/frontend-security.md`, section `Error Handling`.

Convention for the `message` string: `[FEATURE-DASH-SEPARATED] - error: description`, where the description is fixed text, never the caught error's message.

What goes in `tags`, per `../../rules/error-handling.md` and `../../rules/frontend-security.md`:

- Allowed: opaque, stable identifiers (`userId`, `requestId`, `traceId`, resource IDs such as `productId`), the error type name, and its stable code.
- Never: PII (emails, phone numbers, names, addresses), raw request or response payloads, error messages or stacks, secrets, tokens, cookies, or authorization headers.
