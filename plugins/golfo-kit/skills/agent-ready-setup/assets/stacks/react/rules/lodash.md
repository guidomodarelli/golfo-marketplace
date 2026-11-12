# Lodash Rules — SSR + React + TypeScript

`lodash-es` is a mandatory dependency of this stack: every mandatory case below uses it. Use it only where it removes code the language cannot express as briefly; never as a wrapper around native features. Never use the CommonJS `lodash` package or its per-method subpaths (`lodash/debounce`).

## Make lodash-es available

Resolve availability in this order before importing:

1. **Re-exported by the SSR framework** → import from the framework's re-export path (see `Imports` in `react-style.md`).
2. **Declared** in `dependencies` of `package.json` → import it directly.
3. **Declared only in `devDependencies`** → move it to `dependencies` with the project's package manager (for example, `pnpm add --save-prod lodash-es`), because it runs in production code.
4. **Not declared** in `package.json`, even when it is present in `node_modules/` as a transitive dependency, bundled by the SSR framework, or the project declares the CommonJS `lodash` instead → install `lodash-es` as a runtime dependency with the package manager that owns the lockfile before writing the import. This is the one install that does not need confirmation: this rule mandates it, as stated in `established-libraries.md`.

| Lockfile | Runtime install | TypeScript types |
| --- | --- | --- |
| `pnpm-lock.yaml` | `pnpm add lodash-es` | `pnpm add -D @types/lodash-es` |
| `yarn.lock` | `yarn add lodash-es` | `yarn add -D @types/lodash-es` |
| `bun.lockb` or `bun.lock` | `bun add lodash-es` | `bun add -d @types/lodash-es` |
| `package-lock.json` or no lockfile | `npm install lodash-es` | `npm install -D @types/lodash-es` |

If more than one lockfile exists, ask which package manager the project uses before installing. If the install fails, report the command and its error and stop instead of hand-rolling a mandatory case.

In TypeScript, `lodash-es` does not ship its own declarations: declare `@types/lodash-es` as a dev dependency (it is covered by the same pre-approval) instead of typing the import as `any`.

When the project still imports the CommonJS `lodash`, switch every `lodash` import in the files the change touches to `lodash-es`. Once no file imports `lodash`, remove `lodash` and `@types/lodash` from `package.json` and mention it in the change summary.

Never add lodash-es for a case listed as forbidden below.

### Linter

Whatever linter the project runs (oxlint, ESLint, or another), a rule that reports an undeclared or extraneous dependency on a `lodash-es` import (for example `import/no-extraneous-dependencies`) is fixed by declaring `lodash-es` as above. Do not silence it with inline disable comments (`eslint-disable`, `oxlint-disable`), per-file overrides, or by registering lodash modules as core modules or allowlist entries in the linter config.

## Mandatory cases

For these cases, never hand-roll an implementation. Every method is a named import from `lodash-es`:

| Need | Use |
| --- | --- |
| Debounce or throttle a handler | `debounce`, `throttle` |
| Deep equality of objects or arrays | `isEqual` |
| Default options, flat or nested | `defaults({}, options, defaultOptions)`, `defaultsDeep` |
| Deep merge without mutating inputs | `merge({}, base, override)` |
| Unique values of a list | `uniq` |
| Unique items by a key | `uniqBy` |
| Sort by several keys or directions | `orderBy` |
| Index a list by a key | `keyBy` |
| Group a list by a key | `groupBy`, only when the target runtime lacks `Object.groupBy` |
| Split a list into fixed-size batches | `chunk` |
| Check for a plain object (`{}` or `Object.create(null)`) | `isPlainObject` |

## Existing project utils

When a change adds, modifies, or calls a project util that reimplements a mandatory case (for example `isRecord`, `unique`, `chunkArray`, `debounceFn`, `deepEqual`), replace it with the `lodash-es` method in the same change:

1. Compare semantics before swapping. `isPlainObject` rejects class instances, `Date` and `Map`; if the util accepts them, keep that behavior with `isObjectLike` plus the exclusions the util already had, and say so in the change.
2. Update every call site and delete the util, its export and its unit tests; the behavior stays covered by the tests of the call sites.
3. Call `lodash-es` directly: no wrapper util that only delegates to it, not even to keep a TypeScript type guard.

   ```ts
   // ❌ Hand-rolled check, or a wrapper that only delegates
   const isRecord = (value: unknown): value is Record<string, unknown> =>
     typeof value === 'object' && value !== null && !Array.isArray(value);

   // ✅ Import and call lodash-es at every call site
   import { isPlainObject } from 'lodash-es';

   if (isPlainObject(payload)) {
     // ...
   }
   ```

## Forbidden cases

Use the native equivalent instead:

| Lodash | Native |
| --- | --- |
| `map` | `.map()` (or `Array.from(source, callback)` for non-array iterables) |
| `each`, `forEach`, `filter`, `reduce`, `find`, `some`, `every`, `includes` | Array methods or `for...of` |
| `get`, `has` | Optional chaining (`?.`), `??`, `Object.hasOwn` |
| `cloneDeep` | `structuredClone` |
| `assign`, `keys`, `values`, `entries` | `Object.assign`, spread, `Object.keys/values/entries` |
| `omit`, `pick` | Destructuring on data objects (`const { password, ...safeUser } = user`; component props still follow the no-rest-props rule) or `Object.fromEntries` over filtered `Object.entries` |
| `groupBy` when `Object.groupBy` is available | `Object.groupBy` |
| `flatten`, `range` | `.flat()`, `Array.from({ length }, ...)` |
| `isNil`, `isNull`, `isUndefined` | `value == null`, `=== null`, `=== undefined`, or `??` when you only need a fallback value |
| `isString`, `isNumber`, `isBoolean`, `isFunction`, `isSymbol`, `isArray`, `isObject` | `typeof`, `Array.isArray`; TypeScript narrows them natively |

## Usage

- Use named imports from `lodash-es` (`import { debounce, chunk } from 'lodash-es'`); they tree-shake, so only the imported methods reach the bundle. Never use a namespace or default import (`import * as _ from 'lodash-es'`, `import _ from 'lodash-es'`), and never import from `lodash` or its subpaths (`import debounce from 'lodash/debounce'`).
- Never mutate inputs: pass a fresh target (`{}`) as the first argument to `defaults`, `defaultsDeep` and `merge`.
- In React components, create a debounced or throttled function once per component instance (`useMemo` or `useRef`) and call `.cancel()` in the effect cleanup on unmount. Otherwise it is recreated on every render, loses its pending state, and can fire after the component unmounted.
