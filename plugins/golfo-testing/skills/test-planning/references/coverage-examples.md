## Example coverage checklist

```md
| Route/Component | Props/State         | Existing tests       | Gaps         | Test type    | Priority |
| --------------- | ------------------- | --------------------| ------------ | -----------  | -------- |
| /roles          | items, error        | RoleList.test.tsx   | empty state  | unit         | P1       |
| /roles/:id      | roleId, loading     | -                   | no tests     | integration  | P0       |
| RoleForm        | onSubmit, isSubmitting | RoleForm.test.tsx | error submit | unit         | P1       |
```

### Summarized plan (example)

- P0: permissions and error in `/roles/:id` (integration)
- P1: prop variants in `RoleList` (empty, error, loading)
- P2: secondary visual cases in `RoleForm` (long texts)
