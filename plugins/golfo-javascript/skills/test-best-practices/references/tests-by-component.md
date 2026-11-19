## Objective

Write tests with Vitest (test APIs imported from `vitest`, in a `jsdom` or `happy-dom` environment) and
import render helpers from the project's test-utils wrapper when one exists (for example `@/tests/utils`
or `test/utils`). A wrapper usually re-exports `@testing-library/react`, registers the DOM matchers
(`@testing-library/jest-dom/vitest`, the matcher package's Vitest entrypoint) and preconfigures the
providers the app needs (i18n, store, router, theme, feature flags, injected ports). Importing from it
avoids repeating configuration across files.

If the project has no wrapper and several test files repeat the same providers, propose one instead of
copying setup into each file.

When a test depends on locale, market, or tenant configuration, pass that context through the wrapper's
options rather than mocking the i18n library. The same applies to data: pass in-memory implementations
of the ports the component reads through the wrapper's options or props, never `vi.mock` of the service
module. For example:

```tsx
import { expect, it } from 'vitest';

import { render, screen } from '@/tests/utils';

it('shows the deals heading for Brazil', () => {
  render(<MyComponent />, {
    locale: 'pt-BR',
    market: 'BR',
  });

  expect(screen.getByRole('heading', { name: 'Ofertas do dia' })).toBeInTheDocument();
});
```

Adapt the option names to the wrapper's real API; read it before writing the test.
