---
name: pr-review-workflow
description: Procedimiento común de review de PR para todos los stacks; obtiene el diff, corre el roster de agentes que declara el command `review-pr` del stack y consolida un único reporte. Usar solo desde `review-pr`, que aporta el roster.
license: MIT
metadata:
  version: "1.0.0"
  tags: "review, pull-request, multi-provider"
---

# PR Review Workflow

Single source for the PR review procedure. Each stack's `review-pr` command declares only its agent roster and its extra checks, then follows these steps.

## 1. Get the diff

```bash
gh pr diff
```

If no PR is open, compare against the remote default branch:

```bash
BASE_BRANCH="$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD)"
git diff "$BASE_BRANCH"...HEAD
```

If `origin/HEAD` is not configured locally, set it with `git remote set-head origin --auto` and rerun the fallback.

## 2. Run the roster

Run every agent of the calling command's roster against the diff, in the listed order and honoring each agent's trigger condition. Apply the extra checks the command lists. Collect every finding before reporting.

If an agent cannot run its tools (no SAST tool configured, design system documentation unavailable, a script missing), note it in that agent's section and continue with the rest of the roster.

## 3. Consolidate and report

Present a single report:

```
## PR Review — [branch name]

### 🔴 Blocking
- [agent] [file:line] Issue — Fix: ...

### 🟡 Recommended
- [agent] [file:line] Suggestion.

### 🟢 Clean
- [agent domain]: clean

### Coverage note
- Missing tests for: ...
```

- **Blocking:** security vulnerabilities, lint or type errors, WCAG AA violations, and any other finding an agent marks as blocking.
- Include **Coverage note** only when a test reviewer reports missing coverage.
- Blocking issues must be resolved before merging.
