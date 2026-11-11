# API Validation Middleware Layout

> **Applicability:** applies only when the project serves its API through Express (a BFF with `express.Router`) or the Pages Router (`getServerSideProps`). In Next.js App Router projects, use route handlers (`app/**/route.ts`) and validate at that boundary instead, following `frontend-security.md#input-validation` with the project's own boundary helpers; do not create `api/middlewares/validation/` or the Express factory below.

For REST routes under api/, follow frontend-security.md#input-validation for validation behavior and schema scope. Use this rule for module placement and imports.

- Put route-specific schemas from the project's input validation library (for example, zod) and their validation middleware declarations under api/middlewares/validation/, with one module per resource or related route group.
- Export named middleware with names that identify the resource and request part, such as usersQueryValidationMiddleware or feedbackValidationMiddleware.
- Re-export those middleware from api/middlewares/validation/index.js in JavaScript projects or index.ts in TypeScript projects.
- Import middleware from the validation directory barrel, for example ./middlewares/validation; do not import each resource module directly from route files.
- Keep the barrel limited to named re-exports. Do not define schemas, add route logic, or call services in index.js / index.ts.
- Keep route modules responsible for mounting validation, authorization, and handlers. Mount validation before authorization and before any middleware or handler that reads the validated request fields.
- Match each schema to the exact req.query, req.body, req.params, or client-controlled header properties consumed by its route. Do not add validation for unrelated routes or backend/upstream response payloads.
- Validate every client-controlled header the route reads with a `headers` schema. Node lowercases incoming header names, so declare header keys in lowercase (`'x-client-version'`, not `'X-Client-Version'`) and use a non-strict `z.object` (never `.strict()`), because the request always carries other headers. The factory never replaces `req.headers`: other middleware still needs `host`, `cookie`, and the rest. It exposes only the parsed header keys in `req.validatedHeaders`; handlers must read validated headers from there, never from `req.headers` or `req.get()`.
- Before writing a resource validation module, search the project for an existing validation middleware factory (for example, `createValidationMiddleware`, `validateRequest`, or an equivalent wrapper around the input validation library) and reuse it with its existing error contract. Never import a helper path that does not exist yet.
- If the project has no such factory, first run the Preflight of skill `/api-endpoint` (section `Preflight — Detect the validation library and Express`) so the validation library is declared in `dependencies` (installing a missing library only after the user confirms it, per `established-libraries.md`), then create `utils/validation/index.js` (or `index.ts`) with the implementation below and write the resource modules that import it. When the project organizes code in `src/modules/<feature>/` (see `hexagonal-architecture.md`), place the factory as shared infrastructure (for example, `src/modules/shared/infrastructure/http/validation-middleware.ts`) instead of `utils/validation/`. The implementation uses zod; when the Preflight resolves another library, adapt only its parse call and issue mapping, keeping the error contract below.

Example layout:

~~~text
api/
  index.js
  teams.js
  middlewares/
    validation/
      index.js
      teams.js
~~~

Validation middleware factory (`utils/validation/index.js`, only when the project has none):

~~~js
export const INVALID_REQUEST_ERROR_CODE = 'INVALID_REQUEST';
export const INVALID_REQUEST_STATUS_CODE = 400;
export const INVALID_REQUEST_ERROR_MESSAGE = 'Request validation failed';

/**
 * Request property that receives the parsed data of each validated request part.
 * Headers go to a dedicated property so req.headers stays intact for the rest of the stack.
 */
const TARGET_PROPERTY_BY_REQUEST_PART = {
  params: 'params',
  query: 'query',
  body: 'body',
  headers: 'validatedHeaders',
};

const REQUEST_PARTS = Object.keys(TARGET_PROPERTY_BY_REQUEST_PART);

/**
 * Builds an Express middleware that validates request parts with zod schemas.
 * On success it replaces params, query, and body with their parsed data and exposes
 * parsed headers in req.validatedHeaders without touching req.headers; on failure it
 * responds 400 with issue paths and codes only, never echoing input values.
 * Header schemas must declare lowercase keys and must not be strict.
 * @param {{ params?: import('zod').ZodTypeAny, query?: import('zod').ZodTypeAny, body?: import('zod').ZodTypeAny, headers?: import('zod').ZodTypeAny }} schemasByRequestPart
 * @returns {import('express').RequestHandler}
 */
export const createValidationMiddleware = (schemasByRequestPart) => (req, res, next) => {
  const issues = [];
  const parsedDataByRequestPart = {};

  REQUEST_PARTS.forEach((requestPart) => {
    const schema = schemasByRequestPart[requestPart];
    if (!schema) return;

    const parseResult = schema.safeParse(req[requestPart]);
    if (parseResult.success) {
      parsedDataByRequestPart[requestPart] = parseResult.data;
      return;
    }

    parseResult.error.issues.forEach((issue) => {
      issues.push({ path: [requestPart, ...issue.path].join('.'), code: issue.code });
    });
  });

  if (issues.length > 0) {
    return res.status(INVALID_REQUEST_STATUS_CODE).json({
      error: { code: INVALID_REQUEST_ERROR_CODE, message: INVALID_REQUEST_ERROR_MESSAGE, issues },
    });
  }

  Object.entries(parsedDataByRequestPart).forEach(([requestPart, parsedData]) => {
    // Express 5 exposes req.query as a getter, so redefine it instead of assigning.
    Object.defineProperty(req, TARGET_PROPERTY_BY_REQUEST_PART[requestPart], {
      value: parsedData,
      writable: true,
      configurable: true,
      enumerable: true,
    });
  });

  return next();
};
~~~

Error contract: `400` with `{ error: { code: 'INVALID_REQUEST', message: 'Request validation failed', issues: [{ path, code }] } }`. `path` is the request part plus the zod issue path (for example, `query.teamKey` or `headers.x-client-version`) and `code` is the zod issue code. Do not include zod `message`, `received`, or the raw input, because some library messages echo submitted values.

Resource validation module:

~~~js
import { z } from 'zod';
import { createValidationMiddleware } from '../../../utils/validation';

export const teamsQueryValidationMiddleware = createValidationMiddleware({
  query: z.object({
    teamKey: z.string().trim().min(1).max(64),
  }),
});

// Header keys in lowercase; non-strict object because the request carries other headers.
export const teamsSyncValidationMiddleware = createValidationMiddleware({
  headers: z.object({
    'x-client-version': z.string().regex(/^\d+\.\d+\.\d+$/),
  }),
});
~~~

The handler reads `req.validatedHeaders['x-client-version']`; `req.headers` keeps every original header.

Barrel:

~~~js
export { teamsQueryValidationMiddleware, teamsSyncValidationMiddleware } from './teams';
~~~

Route import:

~~~js
import { teamsQueryValidationMiddleware } from './middlewares/validation';
~~~
