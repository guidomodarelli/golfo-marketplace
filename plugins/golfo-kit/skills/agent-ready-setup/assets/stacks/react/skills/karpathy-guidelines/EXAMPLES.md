# Examples

Real-world code examples demonstrating the four principles. Each example shows what LLMs commonly do wrong and how to fix it.

---

## 1. Think Before Coding

### Example 1: Hidden Assumptions

**User Request:** "Add a feature to export user data"

**❌ What LLMs Do (Wrong Assumptions)**

```typescript
async function exportUsers(format = 'json') {
  const users = await userService.getAll();

  if (format === 'json') {
    const blob = new Blob([JSON.stringify(users)], { type: 'application/json' });
    downloadBlob(blob, 'users.json');
  } else if (format === 'csv') {
    const rows = users.map(u => `${u.id},${u.email},${u.name}`).join('\n');
    const blob = new Blob([rows], { type: 'text/csv' });
    downloadBlob(blob, 'users.csv');
  }
}
```

**Problems:**

- Assumed it should export ALL users (what about pagination? privacy?)
- Assumed a browser download (what if it's a background job or API response?)
- Assumed which fields to include
- Assumed CSV structure without checking actual data shape

**✅ What Should Happen (Surface Assumptions)**

```
Before implementing, I need to clarify:

1. **Scope**: Export all users or filtered subset? (privacy implications)
2. **Format**: You mentioned "export" - did you mean:
   - Download file in browser?
   - Background job with email notification?
   - API endpoint returning data?
3. **Fields**: Which user fields? (some might be sensitive)
4. **Volume**: How many users typically? (affects approach — streaming vs. bulk)

Simplest approach: Add a service method that returns paginated JSON,
then the caller decides what to do with it.
Would need more info for file-based exports.

What's your preference?
```

### Example 2: Multiple Interpretations

**User Request:** "Make the search faster"

**❌ What LLMs Do (Pick Silently)**

```typescript
// Adds memoization, debounce, and async processing
// without asking which "faster" matters
const search = useMemo(
  () =>
    debounce(async (query: string): Promise<Result[]> => {
      // 200 lines of optimization
    }, 300),
  []
);
```

**✅ What Should Happen**

```
"Make the search faster" could mean:

1. **Faster API response time** (< 100ms instead of 500ms)
   - Add server-side caching
   - Optimize the query in the service
   - Estimated effort: 2 hours

2. **Fewer API calls** (reduce network noise)
   - Add debounce on the input
   - Estimated effort: 30 minutes

3. **Faster perceived speed** (UX)
   - Show skeleton loaders immediately
   - Progressive results
   - Estimated effort: 3 hours

Current search triggers an API call on every keystroke.
Which aspect matters most for your use case?
```

---

## 2. Simplicity First

### Example 1: Over-abstraction

**User Request:** "Add a function to calculate discount"

**❌ What LLMs Do (Overengineered)**

```typescript
interface DiscountStrategy {
  calculate(amount: number): number;
}

class PercentageDiscount implements DiscountStrategy {
  constructor(private percentage: number) {}
  calculate(amount: number): number {
    return amount * (this.percentage / 100);
  }
}

class FixedDiscount implements DiscountStrategy {
  constructor(private fixedAmount: number) {}
  calculate(amount: number): number {
    return Math.min(this.fixedAmount, amount);
  }
}

interface DiscountConfig {
  strategy: DiscountStrategy;
  minPurchase?: number;
  maxDiscount?: number;
}

class DiscountCalculator {
  constructor(private config: DiscountConfig) {}

  applyDiscount(amount: number): number {
    if (amount < (this.config.minPurchase ?? 0)) return 0;
    const discount = this.config.strategy.calculate(amount);
    return Math.min(discount, this.config.maxDiscount ?? Infinity);
  }
}

// Usage requires 10+ lines of setup for a simple calculation
```

**✅ What Should Happen (Simple)**

```typescript
function calculateDiscount(amount: number, percent: number): number {
  return amount * (percent / 100);
}

// Usage
const discount = calculateDiscount(100, 10); // 10 off
```

**When to add complexity:** Only when you actually need multiple discount types. If that requirement comes later, refactor then.

### Example 2: Speculative Features

**User Request:** "Save user preferences"

**❌ What LLMs Do (Unnecessary Features)**

```typescript
class PreferenceManager {
  constructor(
    private restclient: RestClient,
    private cache?: Cache,
    private validator?: Validator,
  ) {}

  async save(
    userId: string,
    prefs: Record<string, unknown>,
    options: { merge?: boolean; validate?: boolean; notify?: boolean } = {},
  ): Promise<boolean> {
    if (options.validate) {
      const errors = this.validator?.validate(prefs);
      if (errors?.length) throw new ValidationError(errors);
    }

    let payload = prefs;
    if (options.merge) {
      const existing = await this.get(userId);
      payload = { ...existing, ...prefs };
    }

    await this.restclient.put(`/api/users/${userId}/preferences`, { data: payload });

    if (this.cache) {
      this.cache.set(`prefs:${userId}`, payload);
    }

    if (options.notify) {
      await this.notifyPreferenceChange(userId, payload); // nobody asked for this
    }

    return true;
  }
}
```

**✅ What Should Happen (Just What Was Asked)**

```typescript
async function savePreferences(
  userId: string,
  preferences: Record<string, unknown>,
): Promise<void> {
  await restclient.put(`/api/users/${userId}/preferences`, { data: preferences });
}
```

**Add later if needed:** Caching (when performance matters), validation (when bad data appears), merging (when requirement emerges).

---

## 3. Surgical Changes

### Example 1: Drive-by Refactoring

**User Request:** "Fix the bug where empty emails crash the validator"

**❌ What LLMs Do (Too Much)**

```diff
  function validateUser(userData: Record<string, string>) {
-   // Check email format
-   if (!userData.email) {
+   /** Validate user data. */
+   const email = (userData.email ?? '').trim();
+
+   // Validate email
+   if (!email) {
      throw new Error('Email required');
-   if (!userData.email.includes('@')) {
+   if (!email.includes('@') || !email.split('@')[1].includes('.')) {
      throw new Error('Invalid email');
    }
-   // Check username
-   if (!userData.username) {
+   // Validate username
+   const username = (userData.username ?? '').trim();
+   if (!username) {
      throw new Error('Username required');
+   if (username.length < 3) {
+     throw new Error('Username too short');
+   }
+   if (!/^[a-z0-9]+$/i.test(username)) {
+     throw new Error('Username must be alphanumeric');
+   }
  }
```

**Problems:**

- "Improved" email validation beyond the bug fix
- Added username validation nobody asked for
- Changed comments and added JSDoc

**✅ What Should Happen (Surgical)**

```diff
  function validateUser(userData: Record<string, string>) {
    // Check email format
-   if (!userData.email) {
+   const email = userData.email ?? '';
+   if (!email || !email.trim()) {
      throw new Error('Email required');
    }
-   if (!userData.email.includes('@')) {
+   if (!email.includes('@')) {
      throw new Error('Invalid email');
    }

    // Check username
    if (!userData.username) {
      throw new Error('Username required');
    }
  }
```

**Only changed:** The specific lines that fix empty email handling.

### Example 2: Style Drift

**User Request:** "Add logging to the upload function"

**❌ What LLMs Do (Reformat Everything)**

```diff
- async function uploadFile(filePath: string, destination: string) {
+ async function uploadFile(filePath: string, destination: string): Promise<boolean> {
+   /** Upload file to destination with logging. */
    try {
-     const response = await restclient.post(destination, { data: { file: filePath } })
-     if (response.status === 200) {
-       return true
-     } else {
-       return false
-     }
+     const response = await restclient.post(destination, { data: { file: filePath } });
+     const success = response.status === 200;
+
+     if (!success) {
+       logWarning(`[UPLOAD] - error: upload failed, status=${response.status}`);
+     }
+
+     return success;
    } catch (e) {
-     console.error(`Error: ${e}`)
+     logError(`[UPLOAD] - error: ${e}`);
      return false
    }
  }
```

**Problems:**

- Added a return type nobody asked for
- Added JSDoc
- Changed semicolon style
- Reformatted boolean return logic

**✅ What Should Happen (Match Existing Style)**

```diff
+ import { logError, logWarning } from '../utils/logger'
+
  async function uploadFile(filePath: string, destination: string) {
    try {
      const response = await restclient.post(destination, { data: { file: filePath } })
      if (response.status === 200) {
        return true
      } else {
+       logWarning(`[UPLOAD] - error: upload failed, status=${response.status}`)
        return false
      }
    } catch (e) {
-     console.error(`Error: ${e}`)
+     logError(`[UPLOAD] - error: ${e}`)
      return false
    }
  }
```

**Matched:** No semicolons, no type annotations, existing boolean pattern, single-quote style. Logging uses the project helpers from skill `/logger`.

---

## 4. Goal-Driven Execution

### Example 1: Vague vs. Verifiable

**User Request:** "Fix the authentication flow"

**❌ What LLMs Do (Vague Approach)**

```
I'll fix the authentication flow by:
1. Reviewing the code
2. Identifying issues
3. Making improvements
4. Testing the changes

[Proceeds to make changes without clear success criteria]
```

**✅ What Should Happen (Verifiable Goals)**

```
To "fix authentication," I need to define success criteria.
What specific issue are we solving?

If the issue is "users stay logged in after password change":

Plan:
1. Write test: Change password → verify old token rejected by API
   Verify: Test fails (reproduces bug)

2. Implement: Invalidate session on password change in the server hook
   Verify: Test passes

3. Check edge cases: Multiple active tabs, concurrent changes
   Verify: Additional tests pass

4. Verify no regression: Existing auth tests still pass
   Verify: Full test suite green

What's the specific auth issue you're seeing?
```

### Example 2: Multi-Step with Verification

**User Request:** "Add rate limiting to the API endpoints"

**❌ What LLMs Do (All at Once)**

```typescript
// Implements full rate limiting with Redis, multiple strategies,
// configuration system, and monitoring in one 300-line commit.
// No clear verification steps.
```

**✅ What Should Happen (Incremental with Verification)**

```
Plan for rate limiting:

1. Add basic in-memory rate limiting to one endpoint
   Verify:
   - Test: 100 requests → first 10 succeed, rest get 429
   - Manual: curl the endpoint 11 times, see rate limit error

2. Extract to middleware (apply to all /api routes via the shared API router)
   Verify:
   - Test: Rate limits apply to /api/users and /api/items
   - Existing endpoint tests still pass

3. Add configuration (rates per endpoint)
   Verify:
   - Test: /api/search allows 10/min, /api/users allows 100/min
   - Config parsed from the project's config module correctly

Each step is independently verifiable and deployable.
Start with step 1?
```

### Example 3: Test-First Verification

**User Request:** "The sorting breaks when there are duplicate scores"

**❌ What LLMs Do (Fix Without Reproducing)**

```typescript
// Immediately changes sort logic without confirming the bug
function sortScores(scores: Score[]) {
  return [...scores].sort((a, b) => b.score - a.score || a.name.localeCompare(b.name));
}
```

**✅ What Should Happen (Reproduce First)**

```typescript
// 1. First, write a test that reproduces the issue
it('sorts stably when scores are equal', () => {
  const scores = [
    { name: 'Alice', score: 100 },
    { name: 'Bob', score: 100 },
    { name: 'Charlie', score: 90 },
  ];

  const result1 = sortScores(scores);
  const result2 = sortScores(scores);

  // The bug: order is non-deterministic for duplicates
  expect(result1[0].name).toBe(result2[0].name);
  expect(result1[1].name).toBe(result2[1].name);
});

// Verify: Test fails with inconsistent ordering

// 2. Now fix with stable sort
function sortScores(scores: Score[]) {
  return [...scores].sort((a, b) => b.score - a.score || a.name.localeCompare(b.name));
}

// Verify: Test passes consistently
```

---

## Anti-Patterns Summary

| Principle           | Anti-Pattern                                          | Fix                                                              |
| ------------------- | ----------------------------------------------------- | ---------------------------------------------------------------- |
| Think Before Coding | Silently assumes format, fields, export target        | List assumptions explicitly, ask for clarification               |
| Simplicity First    | Strategy pattern for single discount calculation      | One function until complexity is actually needed                 |
| Surgical Changes    | Reformats semicolons, adds types while fixing a bug   | Only change lines that fix the reported issue                    |
| Goal-Driven         | "I'll review and improve the auth flow"               | "Write test for bug X → make it pass → verify no regressions"   |

## Key Insight

The "overcomplicated" examples aren't obviously wrong — they follow design patterns and best practices. The problem is **timing**: they add complexity before it's needed, which:

- Makes code harder to understand
- Introduces more bugs
- Takes longer to implement
- Harder to test

The "simple" versions are:

- Easier to understand
- Faster to implement
- Easier to test
- Can be refactored later when complexity is actually needed

**Good code is code that solves today's problem simply, not tomorrow's problem prematurely.**
