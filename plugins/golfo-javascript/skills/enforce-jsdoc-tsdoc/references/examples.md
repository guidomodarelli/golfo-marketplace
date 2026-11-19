## Examples

### File header

```js
/**
 * Provides catalog pricing helpers for the product detail page.
 *
 * @module pricingHelpers
 */
```

### Async function

```js
/**
 * Fetches role details for a given role identifier.
 *
 * @param {string} roleId - Role identifier to fetch (non-empty).
 * @param {object} options - Request options.
 * @param {AbortSignal} [options.signal] - Abort signal used to cancel the request.
 * @returns {Promise<object>} Role details payload.
 * @throws {Error} When the request fails, including the roleId in the error message.
 */
export async function fetchRoleDetails(roleId, { signal } = {}) {
  // ...
}
```

### Function with no meaningful return value

```js
/**
 * Logs an analytics event for a user action.
 *
 * @param {string} eventName - Analytics event name.
 * @param {object} payload - Event metadata.
 * @returns {void} No return value.
 * @throws {Error} When the event payload is invalid.
 */
function trackEvent(eventName, payload) {
  // ...
}
```

### Class

```js
/**
 * Builds and validates checkout totals from line items.
 *
 * @extends BaseTotals
 */
export class CheckoutTotalsBuilder extends BaseTotals {
  /**
   * Initializes the totals builder with line items.
   *
   * @param {Array<object>} items - Line items to aggregate.
   */
  constructor(items) {
    super();
    // ...
  }
}
```

### Constant or variable

```js
/**
 * Default retry delays in milliseconds for pricing API calls.
 *
 * @type {number[]}
 */
export const DEFAULT_RETRY_DELAYS_MS = [100, 250, 500];
```

## TypeScript (TSDoc) examples

### Async function

```ts
/**
 * Fetches role details for a given role identifier.
 *
 * @param roleId - Role identifier to fetch (non-empty).
 * @param options - Request options.
 * @returns Role details payload.
 * @throws When the request fails, including the roleId in the error message.
 */
export async function fetchRoleDetails(
  roleId: string,
  options: { signal?: AbortSignal } = {},
): Promise<RoleDetails> {
  // ...
}
```

### Generic function with @typeParam

```ts
/**
 * Finds the first element matching the predicate.
 *
 * @typeParam T - The type of elements in the array.
 * @param items - Array of elements to search.
 * @param predicate - Function that returns true for the desired element.
 * @returns The first matching element, or undefined if none matches.
 */
export function findFirst<T>(
  items: T[],
  predicate: (item: T) => boolean,
): T | undefined {
  // ...
}
```

### Interface

```ts
/**
 * Represents checkout totals calculated from line items.
 */
export interface CheckoutTotals {
  /** Subtotal before discounts and taxes. */
  subtotal: number;
  /** Total discount amount applied. */
  discount: number;
  /** Final total after discounts and taxes. */
  total: number;
}
```

### Constant

```ts
/** Default retry delays in milliseconds for pricing API calls. */
export const DEFAULT_RETRY_DELAYS_MS: readonly number[] = [100, 250, 500];
```

### Enum

```ts
/** Possible states of a payment transaction. */
export enum PaymentStatus {
  /** Payment has been created but not yet processed. */
  Pending = 'pending',
  /** Payment was completed successfully. */
  Completed = 'completed',
  /** Payment failed or was rejected. */
  Failed = 'failed',
}
```

### Simple behavioral comment with items

```ts
/**
 * Extracts a safe request identifier from request metadata.
 *
 * The helper:
 * 1. Verifies that the header is a string.
 * 2. Trims outer whitespace with `trim()`.
 * 3. Rejects empty values and control characters.
 * 4. Returns `undefined` when the value is unsafe.
 *
 * Example:
 * `'  trace-123  '` → `'trace-123'`
 * `'   '` → `undefined`
 * `'trace\\n123'` → `undefined`
 *
 * @param request - Request containing optional correlation metadata.
 * @returns A safe identifier or undefined when unavailable.
 */
export const getRequestCorrelationId = (request: Request): string | undefined => {
  // ...
};
```

Use this style for non-obvious behavior with several user- or system-visible rules. Keep one-line comments for obvious constants and simple functions.

## Notes

### JSDoc (.js)
- If a parameter is optional, document it with brackets: `@param {Type} [name] - ...`.
- If a parameter has a default value, mention it in the description.
- For callbacks, document the callback signature (e.g. `{(value: string) => void}`) and describe when it is called.
- If `@throws` does not apply, do not add it.
- Use `@type` for constants/variables when the type or shape is not obvious from the initializer.
- Use `@module <name>` for files that export; use `@file` for scripts without exports.

### TSDoc (.ts, .tsx)
- Do not include type annotations in `@param` or `@returns`; TypeScript types are the source of truth.
- Use `@typeParam` when generic type parameters benefit from a description.
- Use `@remarks` for extended context beyond the summary.
- Use `@example` with fenced code blocks for non-obvious usage.
- Use `@defaultValue` for optional parameters or properties with defaults.
- Use `@internal` for implementation details not intended for external consumers.
