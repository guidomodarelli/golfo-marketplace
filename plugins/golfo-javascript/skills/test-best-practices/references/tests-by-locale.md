# Tests by locale or market with `describe.each`

## Objective

Avoid duplication in tests whose texts or behavior change by locale, market, or tenant
(for example `es-AR`, `pt-BR`, `es-MX`).

## Steps

- Extract the values that change between variants (locale or market, expected texts).
- Define an array of cases and use `describe.each` to iterate over them.
- Build the render options in `beforeEach` for each case.
- Pass the options to `render` or `renderHook`.

## Example

**Before**

```ts
describe('example', () => {
  test('some test', () => {
    render(<MyComponent />, { locale: 'pt-BR' });

    expect(screen.getByText('literal value')).toBeInTheDocument();
  });
});
```

**After**

```ts
describe.each([
  {
    locale: 'pt-BR',
    literalValue: 'literal value',
  },
])('example for $locale', ({ locale, literalValue }) => {
  let renderOptions;

  beforeEach(() => {
    renderOptions = { locale };
  });

  test('some test', () => {
    render(<MyComponent />, renderOptions);

    expect(screen.getByText(literalValue)).toBeInTheDocument();
  });
});
```

## Notes

- Use the extracted values without concatenation or transformations.
- Keep shared literals inside the test.
- Apply the same options in `renderHook` when applicable.
