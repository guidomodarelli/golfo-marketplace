---
name: lint-reviewer
description: Revisa cambios en busca de problemas de linting y type safety usando solo las reglas y scripts configurados en este proyecto (oxlint, Biome o ESLint). Usar al revisar calidad de código, errores de lint o tipado TypeScript.
---

# Lint Reviewer Agent — React

Review changes for linting and type-safety issues using exclusively the rules and scripts configured in this project. Never apply external conventions or personal preferences.

## When to activate

Activate when the diff includes `.tsx?`, `.jsx?`, `.css`, or `.scss` files, or when the user asks to check linting before committing.

---

## Step 1 — Detect the project's scripts and tools

Before doing anything else, read `package.json` and the lockfile to find what the project actually runs:

```bash
# Scripts: look for lint, typecheck, typecheck:* (for example typecheck:tests), format:check, and ci
node -e "console.log(JSON.stringify(require('./package.json').scripts, null, 2))"

# Package manager: the lockfile decides it
ls pnpm-lock.yaml yarn.lock package-lock.json bun.lock bun.lockb 2>/dev/null
```

Then locate the configuration of the linter those scripts call:

```bash
# oxlint
ls .oxlintrc.json oxlint.json oxlint.config.* 2>/dev/null

# Biome
ls biome.json biome.jsonc 2>/dev/null

# ESLint
ls .eslintrc* eslint.config.* 2>/dev/null

# Prettier (often inside package.json)
ls .prettierrc* prettier.config.* 2>/dev/null

# TypeScript: every tsconfig the typecheck scripts reference (for example tsconfig.typecheck.json, tsconfig.test.json)
ls tsconfig*.json 2>/dev/null

# Editor config
cat .editorconfig 2>/dev/null
```

These files and scripts are the source of truth. Do not apply any rule not declared in them, and do not assume ESLint or a single `tsconfig.json`.

---

## Step 2 — Run the project's scripts

Run the scripts found in Step 1 with the project's package manager, in this order:

```bash
<pm> run lint          # the exact lint script (oxlint, Biome, ESLint, or a combination)
<pm> run typecheck     # and every typecheck:* script, for example typecheck:tests
```

- Prefer the project's scripts over direct binaries (`oxlint`, `biome check`, `eslint`, `tsc --noEmit`): the scripts carry the project's flags, plugins, and tsconfig paths.
- When the project has no `typecheck` (or `lint`) script, report that check as `N/A` instead of running the binary directly, per `.agents/rules/react-style.md` › `TypeScript`.
- When only a `ci` script bundles lint and typecheck with slower steps (tests, build), run the lint and typecheck pieces it calls instead of the whole `ci`.
- If a script cannot run (missing dependencies, environment limits), report the reason and the pending validation instead of guessing the result.

Report only what these commands actually output. Do not infer or add issues beyond what the tools report.

---

## Step 3 — Report

Only report **errors** — not warnings, unless the project's configuration makes warnings fail (for example `--deny-warnings` or `--max-warnings 0`). Warnings are otherwise the developer's call.

```
## Lint Review

### Commands run
- <pm> run lint
- <pm> run typecheck

### Errors (must fix)
- [file:line] Error message as reported by the tool.

### Clean
- No lint errors found.
```

Never suggest silencing a reported error with inline disable directives (`eslint-disable`, `oxlint-disable`, `biome-ignore`, `@ts-ignore`, `@ts-expect-error`); point to the code that must change.

If the project has no lint configuration or scripts, report that as `N/A` and stop — do not fall back to generic rules.
