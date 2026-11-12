---
name: react-review-pr
description: Ejecuta una review completa del PR actual orquestando los agentes de review especializados y consolidando sus resultados. Usar cuando se pida revisar un pull request.
---

# Review PR — React

Follow `.agents/skills/pr-review-workflow/SKILL.md` with this roster.

| Agent | File | Trigger condition |
|-------|------|-------------------|
| Security scanner | `.agents/agents/react-security-scanner.md` | Always |
| Accessibility reviewer | `.agents/agents/a11y-reviewer.md` | Always |
| Performance analyzer | `.agents/agents/react-perf-analyzer.md` | Always |
| Test reviewer | `.agents/agents/test-reviewer.md` | Use the activation rules in `test-reviewer.md` |
| Lint reviewer | `.agents/agents/lint-reviewer.md` | Use the activation rules in `lint-reviewer.md` |
