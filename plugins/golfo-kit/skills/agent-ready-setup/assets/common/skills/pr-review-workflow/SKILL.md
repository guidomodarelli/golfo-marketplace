---
name: pr-review-workflow
description: Procedimiento común de review de PR para todos los stacks; obtiene el diff, corre el roster de agentes que declara el command `<stack>-review-pr` del stack y consolida un único reporte. Usar solo desde el `<stack>-review-pr` de un stack, que aporta el roster.
license: MIT
metadata:
  version: "1.2.0"
  tags: "review, pull-request, multi-provider"
---

# PR Review Workflow

Single source for the PR review procedure. Each stack's `<stack>-review-pr` command (`frontend-review-pr`, `node-review-pr`, ...) declares only its agent roster and its extra checks, then follows these steps. With several stacks, each command reviews with its own roster.

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

## 2. Record the review context

Read the rules, skills and `AGENTS.md` from the checked-out commit; never run `/agent-ready-setup`, `bootstrap.sh` or `.agents/hooks/sync-marketplace.sh` during a review, because that would change the context under review.

Identify the context version from `.agents/agent-ready.lock.json` in the same commit:

```bash
python3 - <<'EOF'
import json

lock = json.load(open(".agents/agent-ready.lock.json", encoding="utf-8"))
source = lock["source"]
profiles = ",".join(lock.get("profileOrder", []))
revision = source.get("revision") or "none"
print(f"{source.get('plugin')} {source.get('version')} revision={revision} "
      f"content={source['contentDigest'][:12]} profiles={profiles}")
EOF
```

If the file is missing, the context is not pinned: say so in the report instead of guessing a version.

## 3. Run the roster

Run every agent of the calling command's roster against the diff, in the listed order and honoring each agent's trigger condition. Apply the extra checks the command lists. Collect every finding before reporting.

If an agent cannot run its tools (no SAST tool configured, design system documentation unavailable, a script missing), note it in that agent's section and continue with the rest of the roster.

## 4. Consolidate and report

Present a single report:

```
## PR Review — [branch name]

Context: [output of step 2, or "not pinned: no .agents/agent-ready.lock.json"]

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
- Always include the **Context** line, so the same commit shows which rules and skills the review used.
- Blocking issues must be resolved before merging.
