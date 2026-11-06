---
name: business-flow-design
description: >-
  Diseña o revisa un flujo de negocio para web apps o apps nativas y escribe su
  definición en docs/flows/: pasos, transiciones, resultados, reanudación, pasos
  irreversibles, diferencias por plataforma y versionado. Usar al crear un flujo
  nuevo, agregar o reordenar pasos, o revisar uno existente (checkout, onboarding,
  reclamos, wizards de varios pasos), aunque el pedido solo diga "agregá un paso" o
  "armá el flujo". No usar para cambios de copy o estilos que no tocan los pasos.
license: MIT
metadata:
  version: "1.0.0"
  tags: "business-flows, multi-platform, design"
---

# Business Flow Design

Write the definition of a business flow, check it for dead ends, and leave it where the team can find it. The rules this procedure applies live in `.agents/rules/business-flows.md`.

## 1. Read what exists

- Look for the flow in `docs/flows/` and in the code. When changing a flow, start from its current behavior, not from memory.
- Find out which engine or navigation library the project already uses for flows, and which clients the flow runs on. Design for that engine; do not propose a new one.
- Ask the user only what the code cannot answer: the business outcome, who the actors are, and which rules are mandatory. Ask once, with everything you need.

## 2. Write the definition

Create or update `docs/flows/<flow-name>.md` with these sections. Write `N/A` and the reason when one does not apply, so a reader can tell it was considered.

```markdown
# <Flow name>

**Goal:** <business outcome, in one sentence>
**Clients:** <web, Android, ...>
**Version:** <number>

## Entry points
<Each way in: menu, deep link, shared URL, notification; and the prerequisites of each.>

## Steps
| Step | Purpose | Data it needs | Who decides | On success | On failure |
| --- | --- | --- | --- | --- | --- |

## Outcomes
<Completed, abandoned, failed, blocked: what the user sees and what state remains.>

## Irreversible steps
<Which ones, how a retry stays idempotent, and what back does afterwards.>

## Resuming
<What happens on a reload, a restored process, a session that expired, or another device.>

## Platform differences
<Presentation and navigation only: URLs, system back, process death. Business rules do not differ.>

## Changes to this flow
<What happens to users already inside it, and to old clients that receive a step they do not know.>

## Events
<Events per step, with flow, step, and version identifiers.>
```

## 3. Check it

Walk the definition and fix what fails before reporting:

- Every step can be reached, and every step leads to an outcome.
- Every failure has a next step: retry, an alternative, or a named outcome.
- Every entry point checks its prerequisites and works without the previous steps having run in this session.
- Every irreversible step has an idempotency mechanism and a defined back behavior.
- Every business decision has an owner, and the server owns what matters beyond one session.

When changing an existing flow, also list what happens to users who are already inside it.

## 4. Report

State the path of the definition, the checks that failed and how you fixed them, and the decisions that need a person: product rules you could not derive from the code, written as questions. Do not implement the flow unless the user asked for it; if they did, implement from this definition and test each transition as `.agents/rules/business-flows.md` asks.
