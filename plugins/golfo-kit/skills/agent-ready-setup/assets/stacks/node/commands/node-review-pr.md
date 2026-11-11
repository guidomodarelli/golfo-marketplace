---
name: node-review-pr
description: Ejecuta una review completa del PR actual de Node.js orquestando los agentes de review especializados. Usar cuando se pida revisar un pull request en un proyecto Node.js.
---

# Review PR — Node

Follow `.agents/skills/pr-review-workflow/SKILL.md` with this roster.

| Agent | File | Trigger condition |
|-------|------|-------------------|
| Security scanner | `.agents/agents/node-security-scanner.md` | Always |
| Performance analyzer | `.agents/agents/node-perf-analyzer.md` | Always |

Extra checks: compare the diff against `.agents/rules/node-coding-style.md` and `.agents/rules/node-testing.md`.
