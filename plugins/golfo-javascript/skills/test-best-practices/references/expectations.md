## Assertions

Use the Testing Library DOM matchers registered for Vitest (`@testing-library/jest-dom/vitest` in the setup file) for UI assertions.

### Rules

- Prefer `toStrictEqual` over `toEqual` or `toBe` when comparing objects.
- Avoid `toHaveProperty`; validate the full object shape with `toStrictEqual`.
- Avoid redundant assertions when you already compared the full object.
- Avoid partial comparisons (`toContain`, `toMatch`) if the expected value is known and stable.
- Never assert source code, style files, SQL strings, ORM/query-builder call parameters, or SQL fragments by reading files with `fs` or equivalent helpers, or by spying only on internal query construction.
- Prefer assertions against rendered UI, public function output, service/repository contracts, query results, build/lint output, or observable side effects.

### Example

```ts
// Bad
expect(object).toHaveProperty('property');
expect(object.property).toContain('partial text');

// Good
expect(object).toStrictEqual({
  property: 'exact expected value',
});
```
