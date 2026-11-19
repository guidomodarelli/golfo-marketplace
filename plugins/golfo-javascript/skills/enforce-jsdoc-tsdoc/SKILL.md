---
name: enforce-jsdoc-tsdoc
description: Adds or updates JSDoc (.js) and TSDoc (.ts, .tsx) where documentation helps readers, such as public APIs, exported helpers, domain logic, and non-obvious constructs, with placement rules and required tags, skipping blocks that only restate obvious code. Use when creating or editing .js, .ts, or .tsx files.
license: MIT
metadata:
  version: "1.0.0"
  author: "Guido Modarelli"
  category: "developer-experience"
  tags: "jsdoc, tsdoc, documentation, javascript, typescript"
  command: "/enforce-jsdoc-tsdoc"
---

## Quick start

- For `.js` files, use **JSDoc** syntax. For `.ts` and `.tsx` files, use **TSDoc** syntax.
- Read [rule.md](references/rule.md) for required coverage, placement, fields, and English-only documentation.
- Use [examples.md](references/examples.md) for templates (async, void-return, classes, constants, file headers).
- Document when the language, complexity, or intent of the code makes it relevant; prioritize non-obvious constructs, public APIs, and domain logic.
- Prefer simple documentation when possible: use a short summary followed by a numbered list for multiple behavioral rules and a small example for input/output transformations. Avoid verbose narrative and comments that restate obvious code.
