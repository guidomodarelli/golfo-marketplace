---
name: api-endpoint
description: "Crea un endpoint de API SSR: un server hook (getServerSideProps) o un endpoint REST en la carpeta /api con express.Router(). Usar al agregar un nuevo endpoint, server hook o API route en proyectos con BFF Express o Pages Router; en Next.js App Router no aplica (usar route handlers)."
metadata:
  tags: "context-optimized-v1.20.1"
---

# API Endpoint Creation — SSR

> **Applicability**: applies only when the project serves its API through Express (a BFF with `express.Router`) or the Pages Router (`getServerSideProps`). In Next.js App Router projects, use route handlers (`app/**/route.ts`) and validate at that boundary instead; do not apply this skill there, and do not add `express` to an App Router project.
>
> **Prerequisite**: run `/logger` first, or reuse the project's existing logger. The examples import `logError` from `utils/logger`; when `/logger` placed it elsewhere (for example `src/modules/shared/infrastructure/observability/logger.ts` in a project with modules), import it from that path.
>
> Keep subrouters focused on routing, validation, and orchestration. Put reusable helpers in `utils/` and reusable/domain constants in `constants/`; do not add them inside `api/<resource>/`, `api/services/`, or `services/`. See `../../rules/frontend-style.md`, section `Module placement`. When the project organizes code in `src/modules/<feature>/{domain,application,infrastructure}` (see `../../rules/hexagonal-architecture.md`), the handler calls an application use case wired in the module's composition root, not a flat service, and shared helpers live under `src/modules/shared/`.
>
> For the distinction between middleend request validation and backend/upstream response payloads, follow `../../rules/frontend-security.md`, section `Input Validation`.
>
> For error-origin and public status mapping, follow `../../rules/frontend-security.md`, section `Error Handling`: preserve upstream HTTP statuses, map BFF-owned request/domain failures to 4xx, and use 5xx only for BFF-owned internal or no-status integration failures.
>
> For payloads sent upstream, follow `../../rules/upstream-contracts.md`: map validated input explicitly and let the service build the upstream request.

The project's SSR framework exposes two ways to handle server-side logic:

| Type | Location | Use when |
|---|---|---|
| **Server hook** | `app/pages/<route>/index.hooks.server.ts` (or the framework's equivalent) | Fetching data to render a page (SSR) |
| **REST endpoint** | `api/<resource>/index.ts` → mounted via `express.Router()` | Client-side calls, middle-end JSON APIs |

> **Never call `/api` routes from `getServerSideProps`** — call services directly (no HTTP roundtrip needed).

---

## Preflight — Detect the validation library and Express

The schemas of both options import the project's input validation library, the validation middleware factory of Option B depends on it too, and the REST router imports `express`; those packages must be declared before the files are created, otherwise `tsc --noEmit` fails with a missing module. They run in production code, so they count as available only when they are declared in `dependencies`: a deploy that runs `npm ci --omit=dev` (or the equivalent of the project's package manager) does not install `devDependencies`.

```bash
# Print the first validation library and express declared in dependencies (or "<library> dev-only" when it is only in devDependencies), or NONE for each
node -e "const p = require('./package.json'); const runtimeDeps = p.dependencies ?? {}; const devDeps = p.devDependencies ?? {}; const findRuntime = (known) => { const runtimeLibrary = known.find((library) => runtimeDeps[library]); if (runtimeLibrary) return runtimeLibrary; const devOnlyLibrary = known.find((library) => devDeps[library]); return devOnlyLibrary ? devOnlyLibrary + ' dev-only' : 'NONE'; }; console.log('validation-library=' + findRuntime(['zod', 'yup', 'joi', 'valibot'])); console.log('express=' + findRuntime(['express']));"
```

Resolve each line independently:

- `validation-library`: if it prints `zod`, use the examples of this skill and the factory of `../../rules/api-validation-middleware.md` as they are. If it prints `yup`, `joi` or `valibot`, keep that library: write the schemas with its API and, when Option B needs the factory, adapt only its parse call and issue mapping (for example, `schema.validate(value, { abortEarly: false })` with `error.details` in `joi`, `schema.validateSync(value, { abortEarly: false })` inside `try` with `ValidationError.inner` in `yup`, or `v.safeParse(schema, value)` with `issues` in `valibot`) while preserving the `400` error contract of that rule (issue `path` and `code` only, never input values). If the library cannot express a requirement or that contract, warn the user with the gap and stop instead of adding a second validation library. Only when it prints `NONE`, ask the user before installing `zod` (see "Ask before installing" below).
- `express`: Option A does not import it; ignore this line when you only create a server hook. For Option B, if it prints `NONE` but the project's SSR framework re-exports the router (look for existing `Router` imports under `api/`), import it from there. Otherwise the project has no Express BFF: confirm with the user that it wants one (an App Router project uses route handlers instead, see Applicability) and ask before installing `express`, together with `@types/express` as a dev dependency in TypeScript projects when it is not declared.
- `<library> dev-only` (either line): the project already chose that library but declares it only in `devDependencies`. Use it as if it were printed alone, and move it to `dependencies` with the "Move to runtime" command of the table below before creating any file. Run the detector again and continue only when it prints the library without `dev-only`.

### Ask before installing

Never install a package silently, per `../../rules/established-libraries.md`. Before running any install command, tell the user which packages are missing, what each one is for (schemas and the validation factory for `zod`, the REST router for `express`), and which alternative the project already has (for example, another validation library or a router re-exported by the framework), then wait for confirmation. If the user declines, reuse the existing alternative or stop and report what is missing; do not create files that import an undeclared package. Moving an already declared library from `devDependencies` to `dependencies` is not a new install: do it and mention it in the report.

After the user confirms, install only the missing packages with the package manager that owns the project's lockfile:

| Lockfile | Runtime install | Dev install | Move to runtime (`dev-only`) |
|---|---|---|---|
| `pnpm-lock.yaml` | `pnpm add zod express` | `pnpm add -D @types/express` | `pnpm add --save-prod <library>` |
| `yarn.lock` | `yarn add zod express` | `yarn add -D @types/express` | `yarn remove <library> && yarn add <library>` |
| `bun.lockb` or `bun.lock` | `bun add zod express` | `bun add -d @types/express` | `bun remove <library> && bun add <library>` |
| `package-lock.json` or no lockfile | `npm install zod express` | `npm install -D @types/express` | `npm install --save-prod <library>` |

Drop from each command the packages that are already declared or that you are replacing with an existing library or framework export. If more than one lockfile exists, ask the user which package manager the project uses before installing. If an install fails, report the command and its error and stop: do not create schemas, the validation factory or the router without their dependencies.

---

## Option A — Server Hook (`getServerSideProps`)

Consult the SSR framework documentation for the current server hooks API before implementing.

### File placement

Follow the framework's naming convention exactly; when the hooks file is paired with the page file by name, a wrong name means the hooks silently don't run.

```
app/pages/<route>/
├── index.tsx                    ← page component
└── index.hooks.server.ts        ← server-side data + API logic
```

The hooks file runs on the server before the page component renders. If the framework supports Express middlewares that run before `getServerSideProps` (for example, an exported `beforeGetServerSideProps` array), use them for authorization, redirects, request validation, or populating `res.locals`; call services directly from them, never `/api` routes.

```ts
export const beforeGetServerSideProps = [authorizeByPermission(VIEW_PERMISSION), resolvePageProps];
```

### Validate inputs

Use the validation library resolved in the Preflight. With zod, `safeParse()` returns the parsed value or the validation errors without throwing; with another library, use its non-throwing equivalent.

```ts
import { z } from 'zod';

const paramsSchema = z.object({
  id: z.string().uuid(),
});

export async function getServerSideProps(req) {
  const parsedParams = paramsSchema.safeParse(req.params);
  if (!parsedParams.success) {
    return { props: { error: true } };
  }
  // ...
}
```

Validate every client-controlled input (body, query params, path params, headers) with an allowlist schema, as required by `../../rules/frontend-security.md`, section `Input Validation`.

### Implement the handler

```ts
import { logError } from '../../../utils/logger';
import { getProduct } from '../../../src/services/product';

export async function getServerSideProps(req) {
  const parsedParams = paramsSchema.safeParse(req.params);
  if (!parsedParams.success) {
    return { props: { error: true } };
  }

  const { id: productId } = parsedParams.data;

  try {
    const product = await getProduct(productId);
    return { props: { product } };
  } catch (error) {
    logError('[PRODUCT-GET-SERVER-SIDE-PROPS] - error: product could not be loaded', {
      productId,
      errorType: error instanceof Error ? error.name : typeof error,
    });
    return { props: { error: true } };
  }
}
```

Rules:
- Never inline business logic or outbound HTTP calls — delegate to a service (skill `/service`), which uses the project's HTTP client.
- Log with `logError`/`logWarning` from the project's shared logger (skill `/logger`) — never `console.log`. Log a fixed description, the error type and stable code, and opaque identifiers (`productId`, `requestId`); never the error message, stack, raw payloads, or PII (see `../../rules/error-handling.md`).
- Never forward `scope` as a query parameter; see `../../rules/api-configuration.md`.

---

## Option B — REST Endpoint (`/api` folder)

The server mounts the `apiRouter` at `/api`. Use the project's validation middleware factory as route middleware so validation and the `400` error response live in one place. Search for an existing factory first and reuse it with its error contract; if none exists, run the Preflight and then create `utils/validation/index.(js|ts)` with the `createValidationMiddleware` implementation from `../../rules/api-validation-middleware.md` (adapted to the resolved library) before writing any module that imports it.

Keep REST route schemas and middleware in `api/middlewares/validation/<resource>.(js|ts)`, then import their named exports from `api/middlewares/validation/index.js` or `index.ts`. See `../../rules/api-validation-middleware.md`.

### File placement

```
api/
├── index.ts                            ← mounts all resource routers
├── middlewares/
│   └── validation/
│       ├── index.ts                    ← re-exports route validation middleware
│       └── product.ts                  ← product request schemas and middleware
└── product/
    └── index.ts                        ← product router
```

### 1. Create the resource router

> Para implementar `getProduct`, `createProduct` y cualquier servicio que el handler consuma, seguí el skill `/service`.

```ts
// api/product/index.ts
import { Router } from 'express';
import {
  createProductValidationMiddleware,
  getProductValidationMiddleware,
} from '../middlewares/validation';
import { logError } from '../../utils/logger';
import { mapKnownErrorToHttpResponse } from '../../src/errors/map-known-error-to-http-response';
import { getProduct, createProduct } from '../../src/services/product';

const router = Router();

router.get('/product/:id', getProductValidationMiddleware, async (req, res) => {
  try {
    const product = await getProduct(req.params.id);
    res.json(product);
  } catch (error) {
    logError('[PRODUCT-GET] - error: product could not be loaded', {
      productId: req.params.id,
      errorType: error instanceof Error ? error.name : typeof error,
    });
    const publicError = mapKnownErrorToHttpResponse(error);
    return res.status(publicError.statusCode).json({ error: publicError.message });
  }
});

router.post('/product', createProductValidationMiddleware, async (req, res) => {
  const { name, price } = req.body;

  try {
    const product = await createProduct({ name, price });
    res.status(201).json(product);
  } catch (error) {
    logError('[PRODUCT-CREATE] - error: product could not be created', {
      errorType: error instanceof Error ? error.name : typeof error,
    });
    const publicError = mapKnownErrorToHttpResponse(error);
    return res.status(publicError.statusCode).json({ error: publicError.message });
  }
});

export default router;
```

`mapKnownErrorToHttpResponse` is the project's typed error mapper and must follow the error-origin policy linked at the top of this skill. If the project uses a different module path, update the import before copying the example; do not leave the mapper as an implicit dependency.

The handler maps the validated body explicitly instead of forwarding `req.body`, so client-only fields never reach the service or the upstream request.

When a route consumes a client-controlled header, validate it in the same middleware with a `headers` schema. Node lowercases header names, so declare lowercase keys and keep the object non-strict (never `.strict()`), because the request carries other headers. The factory leaves `req.headers` intact and exposes only the parsed keys in `req.validatedHeaders`; read the value from there:

```ts
// api/middlewares/validation/product.ts
import { z } from 'zod';
import { createValidationMiddleware } from '../../../utils/validation';

export const syncProductValidationMiddleware = createValidationMiddleware({
  params: z.object({ id: z.string().uuid() }),
  headers: z.object({
    'x-client-version': z.string().regex(/^\d+\.\d+\.\d+$/),
  }),
});

// api/product/index.ts
router.post('/product/:id/sync', syncProductValidationMiddleware, async (req, res) => {
  const clientVersion = req.validatedHeaders['x-client-version'];
  // ...
});
```

An invalid or missing header returns the same `400` contract with `path: 'headers.x-client-version'`, without echoing the submitted value.

In TypeScript, declare `validatedHeaders` once through Express `Request` module augmentation (for example, `validatedHeaders?: Record<string, unknown>`) so `tsc --noEmit` accepts the handler.

### 2. Mount in `api/index.ts`

```ts
import { Router } from 'express';
import productRouter from './product';

const apiRouter = Router();

apiRouter.use(productRouter);

export default apiRouter;
```

Rules:
- Define the validation middleware in `api/middlewares/validation/<resource>.(js|ts)` and mount its named export as the first route middleware — never access `req.body/params/query` or a client-controlled header without prior validation; read validated headers from `req.validatedHeaders`, never from `req.headers` or `req.get()`.
- Never import `createValidationMiddleware` (or any validation helper) from a path that does not exist: reuse the project's factory or create it first.
- For path/query params (always strings), coerce non-string types in the schema (for example, `z.coerce.number()`); for booleans, parse the allowed string values explicitly instead of relying on truthiness.
- Never inline business logic — delegate to a service.
- Never disable CSRF protection without a formal security review.
- Everything else (allowlists, PII in logs, error details, status mapping) follows `../../rules/frontend-security.md`.
- Never install a package without the user's confirmation (see "Ask before installing").

---

## Verify

```bash
<pm> run typecheck   # the project's type-check script
<pm> run lint
```

Use the package manager the lockfile declares. A script that does not exist is reported as `N/A`, per `../../rules/frontend-style.md` › `TypeScript`.
