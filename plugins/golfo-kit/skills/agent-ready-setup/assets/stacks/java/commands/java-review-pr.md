---
name: java-review-pr
description: Ejecuta una review completa del PR actual de Java orquestando los agentes de review especializados. Usar cuando se pida revisar un pull request en un proyecto Java.
---

# Review PR — Java

Follow `.agents/skills/pr-review-workflow/SKILL.md` with this roster.

| Agent | File | Trigger condition |
|-------|------|-------------------|
| Security scanner | `.agents/agents/java-security-scanner.md` | Always |
| Performance analyzer | `.agents/agents/java-perf-analyzer.md` | Always |

Extra checks: compare the diff against `.agents/rules/java-coding-style.md` and `.agents/rules/java-testing.md`.
