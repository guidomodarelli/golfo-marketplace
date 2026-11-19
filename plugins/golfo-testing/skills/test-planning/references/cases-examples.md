## Examples

### Suggested matrix for a list component

**Base cases**
- renders title and subtitle -> `getByText` finds both
- renders items and shows count -> `getAllByRole('listitem')` has the expected length
- calls `onSelect` with the correct `id` -> `toHaveBeenCalledWith('id')`

**Edge cases**
- empty items -> shows empty state
- `null` items -> does not crash and shows fallback
- item without `name` -> uses default `name`
- `error` present -> shows error message
- `isLoading` true -> shows skeleton

### Quick matrix (table)

```md
Case | Data | Expectation
base render | itemsTypical | list visible
no items | itemsEmpty | empty state
error | errorProp | error message
```

### Reusable data mocks

```ts
const itemMinimal = { id: '1', name: 'Anna' };
const itemTypical = { id: '2', name: 'Brian', role: 'admin' };

const itemsTypical = [itemMinimal, itemTypical];
const itemsEmpty = [];
const itemsMissingFields = [{ id: '3' }];

const errorProp = { message: 'Network error' };
```
