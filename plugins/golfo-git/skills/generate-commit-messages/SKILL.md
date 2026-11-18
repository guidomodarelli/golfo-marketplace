---
name: generate-commit-messages
description: "Collect the information required to draft and apply a high-quality commit message, then commit the current changes. Use when the user asks to generate or write a commit message, commit the current/staged changes, or invokes /generate-commit-messages."
license: MIT
metadata:
  version: "1.0.0"
  author: "Guido Modarelli"
  category: "git-workflow"
  tags: "git, commit, commitlint, conventional-commits"
  command: "/generate-commit-messages"
---

# Generate Commit Messages

Collect the information required to draft and apply a high-quality commit message.

## Scope

- Focus only on understanding the current uncommitted changes.
- Analyze and commit only staged changes when staged changes exist.
- If there are no staged changes, analyze all current uncommitted changes and stage them with «git add -A» before commit.
- Do not propose new code changes.
- Do not execute destructive commands.
- Do not run typecheck, lint, build, tests, coverage or other quality gates as
  part of this skill: validating the changes belongs to the task that produced
  them, and this skill only drafts the message and commits. Git hooks still run
  as part of «git commit». If there is no evidence in the current session that
  the relevant tests ran and passed for these changes, say so explicitly in the
  final message to the user (what was not validated and why) instead of running
  them here.
- Run «git commit» directly using the generated message after the selected scope is properly staged.

## Gather

- What changed: key files and the most relevant modifications.
- Why it changed: inferred intent or problem being solved.
- Impact: behavior, UX, DX, performance, or operational effects.
- Risks: edge cases, regressions, or follow-up considerations.
- Commit message rules: inspect repository commitlint configuration files before drafting.
  Check common locations such as `.commitlintrc`, `.commitlintrc.js`,
  `.commitlintrc.cjs`, `.commitlintrc.json`, `commitlint.config.js`,
  `commitlint.config.cjs`, and `package.json` commitlint settings.

## Apply Step

- Run «git commit» without asking for confirmation.

## Style Constraints

- Keep everything concrete and repository-specific.
- Respect the repository commitlint configuration when it exists.
- If commitlint extends `@commitlint/config-conventional` or otherwise requires
  `type-empty`/`subject-empty`, include a conventional header with type prefix.
  Example: write «feat: Add new feature» instead of «add new feature».
- If commitlint defines `header-max-length`, keep the header within that limit.
- If commitlint defines `body-max-line-length`, wrap body lines within that limit.
- If commitlint defines `subject-case`, format the subject to match that rule.
- Only omit the type prefix when no repository commitlint rule requires it.
- Do not include issue numbers in the title or description.
- Use imperative mood for the commit title and body where applicable.
  Examples: «add feature», «fix bug», «update docs».
- If referring to identifiers, use «identifier».
- When mentioning functions or variables, wrap their names with «...».
  Example: «update function «myFunction» to handle edge cases».
- If a variable starts with «$», escape it with a backslash.
  Example: «fix issue with \$var when it is null».
- Replace backticks with «...».

## Message Format

- Always include a commit title followed by a blank line and a detailed description.
- The description must explain:
  - The reasoning behind the changes.
  - Important implementation details.
  - Potential impacts.
