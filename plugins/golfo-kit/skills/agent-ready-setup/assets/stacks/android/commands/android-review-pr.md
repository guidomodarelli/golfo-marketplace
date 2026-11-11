---
name: android-review-pr
description: Ejecuta una review completa del PR actual de Android orquestando los agentes de review especializados. Usar cuando se pida revisar un pull request en un proyecto Android.
---

# Review PR — Android

Follow `.agents/skills/pr-review-workflow/SKILL.md` with this roster.

| Agent | File | Trigger condition |
|-------|------|-------------------|
| Security scanner | `.agents/agents/android-security-scanner.md` | Always |
| Performance analyzer | `.agents/agents/android-perf-analyzer.md` | Always |

Extra checks: compare the diff against `.agents/rules/android-coding-style.md` and `.agents/rules/android-testing.md`.
