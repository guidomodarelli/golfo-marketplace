---
name: go-review-pr
description: Ejecuta una review completa del PR actual de Go orquestando los agentes de review especializados. Usar cuando se pida revisar un pull request en un proyecto Go.
---

# Review PR — Go

Follow `.agents/skills/pr-review-workflow/SKILL.md` with this roster.

| Agent | File | Trigger condition |
|-------|------|-------------------|
| Security scanner | `.agents/agents/go-security-scanner.md` | Always |
| Performance analyzer | `.agents/agents/go-perf-analyzer.md` | Always |

Extra checks: compare the diff against `.agents/rules/go-coding-style.md` and `.agents/rules/go-testing.md`.
