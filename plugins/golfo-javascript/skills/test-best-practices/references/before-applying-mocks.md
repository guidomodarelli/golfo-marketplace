## Before isolating a dependency

- List the dependencies of the unit under test (ports, HTTP, context, storage, timers, randomness, feature flags).
- Run the project's own code for real: components, hooks, services, utilities, and modules are never replaced with `vi.mock` or `vi.spyOn`.
- Isolate only at two boundaries:
  - **Domain ports passed by injection** (repository, gateway, notifier, clock): pass an in-memory or recording implementation of the port through the constructor, factory, prop, or the project's provider.
  - **Outbound HTTP**: intercept it with `nock` record/replay fixtures (`nock.back`) in Vitest's `node` environment.
- If a dependency can only be replaced by mocking a module import, do not mock it: test it at its real boundary, and propose an injection point only when it improves the real design (see the `mock-first-testing-design` skill). If there is doubt, call out the risk and ask.

## Never mock

- **Platform components and packages** (design-system components, internal UI kits and SDKs, the framework's runtime packages, validators): render and call them for real and assert observable output.

```tsx
render(<ProductCard product={product} />);

expect(screen.getByRole('img', { name: product.title })).toHaveAttribute('src', product.thumbnail);
```

- **The project's own components and modules**: render child components for real. A slow child is a signal to fix its data source (inject its port or isolate its HTTP), not to stub it.
- **The project's HTTP client**: let it run and intercept the transport with `nock`.

## Allowed doubles

### Injected port

```ts
import { describe, expect, it } from 'vitest';

import { notifyOverdueInvoices } from './notify-overdue-invoices';
import type { InvoiceNotifier } from '../domain/invoice-notifier';

const createRecordingNotifier = () => {
  const sentInvoiceIds: string[] = [];
  const notifier: InvoiceNotifier = {
    notify: async (invoiceId) => {
      sentInvoiceIds.push(invoiceId);
    },
  };
  return { notifier, sentInvoiceIds };
};

describe('notifyOverdueInvoices', () => {
  it('notifies only the overdue invoices', async () => {
    const { notifier, sentInvoiceIds } = createRecordingNotifier();
    const invoices = [
      { id: 'invoice-1', dueDate: new Date('2026-02-15') },
      { id: 'invoice-2', dueDate: new Date('2026-01-10') },
    ];

    await notifyOverdueInvoices({ notifier, invoices, today: new Date('2026-01-31') });

    expect(sentInvoiceIds).toStrictEqual(['invoice-2']);
  });
});
```

`vi.fn()` is acceptable as the implementation of an injected port when you only need to record calls or control a return value; it is never used to replace an imported module.

### Outbound HTTP

```ts
// @vitest-environment node
import nock from 'nock';
import { afterEach, expect, it } from 'vitest';

import { getUser } from './get-user';

afterEach(() => {
  nock.cleanAll();
});

it('returns the user from the upstream API', async () => {
  const { nockDone } = await nock.back('get-user.json');

  try {
    expect(await getUser('1')).toStrictEqual({ id: '1', name: 'Ada' });
  } finally {
    nockDone();
  }
});
```

Configure `nock.back.fixtures` and the `lockdown` mode (record only explicitly, outside CI, against test data, and sanitize before persisting) as the project's testing rules describe. `nock` intercepts Node's `http`/`https`, and native `fetch` from `nock` 14; with `undici`, use its `MockAgent` with `disableNetConnect()`.

### Time and randomness

Control them with `vi.useFakeTimers()` and `vi.setSystemTime()`, or with an injected clock port, and restore them with `vi.useRealTimers()` in `afterEach`.

## Notes

- Restore shared state in `afterEach` (`vi.restoreAllMocks()`, `nock.cleanAll()`, `vi.useRealTimers()`).
- If a draft mocks an internal module (`vi.mock('@/components/...')`, `vi.mock('@/services/...')`) or uses Jest APIs, remove that mock and apply the boundaries above.
