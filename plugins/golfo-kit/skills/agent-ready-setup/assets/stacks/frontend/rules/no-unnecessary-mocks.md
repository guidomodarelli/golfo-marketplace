# Mocking Strategy — Frontend Tests vs Service Tests

Tests run with **Vitest**. They are split into two contexts with different isolation strategies; apply the rules for the context you are in. In both, the project's own code runs for real: never `vi.mock` or `vi.spyOn` the project's internal services, components, hooks, or modules, and never mock the component libraries or platform packages listed in `frontend-testing.md`. The only doubles allowed are test implementations of domain ports passed by injection, and `nock` for outbound HTTP.

---

## Context 1: Frontend / Component Tests

Tests for React components, pages, and UI logic.

**Strategy: render the real component tree with the project's default test providers; control its data through props or through an injected port, never by mocking the service module.**

### Give the component its data through its real contract

Presentational components receive data as props: pass test data directly. When a component reads data through a port (a repository or gateway exposed by the project's provider, a hook factory, or a prop), inject an in-memory implementation of that port:

```tsx
// components/user-card/index.test.tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { TestProviders } from '@/tests/utils/test-providers';
import type { UserRepository } from '@/src/modules/users/domain/repositories/user-repository';

import { UserCard } from './index';

const createInMemoryUserRepository = (users: Array<{ id: string; name: string }>): UserRepository => ({
  findById: async (userId) => users.find((user) => user.id === userId) ?? null,
});

describe('UserCard', () => {
  it('shows the user name', async () => {
    const userRepository = createInMemoryUserRepository([{ id: '1', name: 'Ada' }]);

    render(
      <TestProviders userRepository={userRepository}>
        <UserCard userId="1" />
      </TestProviders>,
    );

    expect(await screen.findByText('Ada')).toBeInTheDocument();
  });
});
```

Adapt the port and provider names to the project's real API. When the component has no injection point and reaches the service through a module import, do not mock the module: test the service at its HTTP boundary (Context 2) and cover the component through the closest real composition (a route-level test or a test of the server component that passes props). Propose an injection point only when it improves the real design (see the `mock-first-testing-design` skill).

---

## Context 2: Service Tests

Tests for service functions that call external APIs through the project's HTTP client.

**Strategy: no mocks — let the service make real HTTP calls intercepted by an HTTP record/replay fixture tool (for example, `nock` with `nock.back`).**

### How it works

The fixture tool intercepts outbound HTTP at the transport level (`nock` patches Node's `http.request`/`https.request`, and `fetch` from `nock` 14). By default (and always in CI) it runs in `lockdown` mode: it only replays committed JSON fixtures and any request without a fixture fails without reaching the network — no network needed, no mocking required. Recording a fixture is an explicit opt-in action against test data, never a side effect of a first local run.

This means service tests exercise the real service code (URL building, response parsing, error handling) against realistic API responses.

### Setup — directly in the test file

Load fixtures inside the test file. No global config or server-side wiring needed:

```js
// services/user.test.js
// @vitest-environment node
import { fileURLToPath } from 'node:url';
import nock from 'nock';
import { afterEach, expect, test } from 'vitest';
import { getUser } from './user';

const RECORD_FIXTURES_ENV_VAR = 'NOCK_BACK_RECORD';
const REDACTED_VALUE = '[REDACTED]';
const SENSITIVE_FIELD_NAMES = ['email', 'phone', 'document', 'token'];
const URL_ENCODED_PAYLOAD_PATTERN = /^[^=&\s]+=[^&\s]*(?:&[^=&\s]+=[^&\s]*)*$/;

const isRecordingFixtures = process.env[RECORD_FIXTURES_ENV_VAR] === 'true' && !process.env.CI;

nock.back.fixtures = fileURLToPath(new URL('./fixtures', import.meta.url));
nock.back.setMode(isRecordingFixtures ? 'record' : 'lockdown');

afterEach(() => {
  nock.cleanAll();
});

const redactSensitiveFields = (value) => {
  if (Array.isArray(value)) return value.map(redactSensitiveFields);
  if (typeof value !== 'object' || value === null) return value;
  return Object.fromEntries(
    Object.entries(value).map(([fieldName, fieldValue]) => [
      fieldName,
      SENSITIVE_FIELD_NAMES.includes(fieldName) ? REDACTED_VALUE : redactSensitiveFields(fieldValue),
    ]),
  );
};

const redactSensitiveSearchParams = (encodedParams) => {
  const searchParams = new URLSearchParams(encodedParams);
  [...new Set(searchParams.keys())]
    .filter((paramName) => SENSITIVE_FIELD_NAMES.includes(paramName))
    .forEach((paramName) => searchParams.set(paramName, REDACTED_VALUE));
  return searchParams.toString();
};

const redactSensitiveQueryParams = (recordedPath) => {
  const queryStartIndex = recordedPath.indexOf('?');
  if (queryStartIndex === -1) return recordedPath;
  const redactedQuery = redactSensitiveSearchParams(recordedPath.slice(queryStartIndex + 1));
  return `${recordedPath.slice(0, queryStartIndex)}?${redactedQuery}`;
};

const parseJsonContainer = (recordedText) => {
  try {
    const parsedValue = JSON.parse(recordedText);
    return typeof parsedValue === 'object' && parsedValue !== null ? parsedValue : undefined;
  } catch {
    return undefined;
  }
};

// Nock keeps as a string every body it cannot parse as JSON (form-urlencoded, plain text, XML...).
const sanitizeRecordedPayload = (recordedPayload, payloadLabel) => {
  if (typeof recordedPayload !== 'string' || recordedPayload === '') return redactSensitiveFields(recordedPayload);
  const parsedJson = parseJsonContainer(recordedPayload);
  if (parsedJson !== undefined) return JSON.stringify(redactSensitiveFields(parsedJson));
  if (URL_ENCODED_PAYLOAD_PATTERN.test(recordedPayload)) return redactSensitiveSearchParams(recordedPayload);
  throw new Error(
    `sanitizeRecordedDefinitions: refusing to persist the ${payloadLabel} because it is a text payload that is neither JSON nor form-urlencoded and cannot be sanitized; write this fixture by hand from test data or add a sanitizer for its content type.`,
  );
};

const sanitizeRecordedDefinitions = (definitions) =>
  definitions.map(({ rawHeaders, reqheaders, ...definition }) => {
    const redactedPath = redactSensitiveQueryParams(definition.path);
    const definitionLabel = `${definition.method ?? 'GET'} ${definition.scope}${redactedPath}`;
    return {
      ...definition,
      path: redactedPath,
      body: sanitizeRecordedPayload(definition.body, `request body of ${definitionLabel}`),
      response: sanitizeRecordedPayload(definition.response, `response of ${definitionLabel}`),
    };
  });

test('returns user data', async () => {
  const { nockDone } = await nock.back('get-user.json', {
    afterRecord: sanitizeRecordedDefinitions,
  });

  try {
    const user = await getUser('1');

    expect(user).toStrictEqual({ id: 1, name: 'Ada' });
  } finally {
    nockDone();
  }
});
```

Run these tests in Vitest's `node` environment (the `// @vitest-environment node` comment or the project's Vitest config): `nock` intercepts Node's `http`/`https` modules, and native `fetch` only from `nock` 14 onward. If the project's HTTP client is `undici` (or `fetch` with an older `nock`), use `undici`'s `MockAgent` with `disableNetConnect()` and committed fixtures instead.

To record or refresh a fixture, run the test explicitly with `NOCK_BACK_RECORD=true`, outside CI and against an environment or account that only holds test data — never real user data. `afterRecord` drops `rawHeaders` and `reqheaders` (cookies, `authorization`, `set-cookie`, correlation ids) and redacts identifiers and PII from the request body, the response and the query params of `path` (Nock records the route there, query string included) before the fixture is persisted. Nock keeps as a string every body or response it cannot parse as JSON: `sanitizeRecordedPayload` redacts those strings when they are JSON or `application/x-www-form-urlencoded`, and for any other non-empty text (plain text, XML, binary payloads) it throws an error that aborts the recording and names the method, origin and redacted path; in that case write the fixture by hand from test data or add a sanitizer for that content type. Adjust `SENSITIVE_FIELD_NAMES` to the upstream contract. Path segments (for example `/users/{id}`) are not redacted: when they carry identifiers, record only against test data. Review the generated JSON before committing it, and commit it only when it contains no secrets, tokens, cookies or personal data, so CI runs without network access.

### Side effects and transport failures

Never mock an internal service module. Instead:

- When the unit depends on **another internal capability with side effects** (writing to a queue, sending a notification), that capability is a domain port: inject a test implementation of the port that records the calls, and assert on what it recorded.
- When the test needs a **transport failure without an HTTP response** (connection reset, timeout), reproduce it with `nock` (`.replyWithError(...)` or `.delay(...)` with the client's timeout). HTTP error statuses such as 500 or 404 are always covered with a fixture file.

### Creating error scenario fixtures manually

Instead of mocking, create the fixture JSON for the error case:

```json
// services/fixtures/get-user-not-found.json
[
  {
    "scope": "https://api.example.com:443",
    "method": "GET",
    "path": "/users/not-found",
    "status": 404,
    "response": { "message": "User not found", "error": "not_found" },
    "rawHeaders": ["content-type", "application/json"]
  }
]
```

---

## Quick Reference

| Test type | Mock internal services or modules? | Mock framework contexts or design system? | Isolate outbound HTTP? | Doubles allowed |
|-----------|------------------------------------|-------------------------------------------|------------------------|-----------------|
| Component / UI | Never | Never — use the project's test providers | Never call the network; data comes from props or injected ports | In-memory implementations of injected domain ports |
| Service / adapter | Never | Never | `nock` record/replay fixtures (`nock.back`) in the `node` environment | Injected domain ports for non-HTTP side effects |

---

## References

- `nock` — HTTP interceptor with record/replay fixtures (`nock.back`) for service tests, run with Vitest in the `node` environment, or the equivalent tool used by the project (for example `undici`'s `MockAgent`)
- `vitest` — test runner and the only source of test APIs (`vi.fn`, `vi.useFakeTimers`); `vi.mock` and `vi.spyOn` are not used on the project's own modules
