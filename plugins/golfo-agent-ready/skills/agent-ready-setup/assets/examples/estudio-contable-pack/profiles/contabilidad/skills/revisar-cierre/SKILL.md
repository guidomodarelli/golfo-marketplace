---
name: revisar-cierre
description: Hace revisar el cierre mensual de un cliente por los subagentes del estudio (auditor contable e investigador normativo) y consolida un solo informe antes de entregarlo. Usar cuando se pida revisar, auditar o controlar un cierre antes de mandarlo al cliente.
---

# Revisar un cierre

Seguí `.agents/skills/orchestrate-agents/SKILL.md` con este roster, en la sesión principal.

| Subagente | Archivo | Cuándo |
|-----------|---------|--------|
| Auditor contable | `.agents/agents/auditor-contable.md` | Siempre |
| Investigador normativo | `.agents/agents/investigador-normativo.md` | Cuando el cierre tiene algo `[a verificar]` o un vencimiento que depende de una norma |

- Al auditor pasale la ruta del cierre, la de su conciliación y las carpetas de comprobantes del mes.
- Al investigador pasale cada punto `[a verificar]` como una pregunta concreta, con el período y el tipo de contribuyente.
- En el informe consolidado, una diferencia de importes que el auditor marca es bloqueante.
- No edites el cierre durante la revisión: el informe dice qué corregir y la persona decide.
