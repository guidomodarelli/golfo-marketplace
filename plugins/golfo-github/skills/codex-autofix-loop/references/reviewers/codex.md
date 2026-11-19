# Perfil de revisor `codex` (default)

Es el perfil con el que está escrito `prompt-template.md`: con `{{REVIEWER}}` = `codex`, los pasos se siguen tal cual. Este archivo solo junta los valores de los **puntos de variación** de la tabla «Perfiles de revisor» de `SKILL.md`, para compararlos con otros perfiles.

| Punto | Con `codex` |
|---|---|
| Bot (`{{REVIEWER_BOT}}`) | `chatgpt-codex-connector[bot]` |
| Estado | `.codex-autofix/processed-{{PR}}.json` |
| Monitor | `Monitor codex-autofix PR #{{PR}}` |
| Pedido de review de ronda | Comentario general `@codex review`, sin texto extra (paso 6) |
| Ack del pedido | Reacción 👀 del bot sobre el pedido (paso 2-bis) |
| Review terminada del head | Último estado `codex-review-state:v1` con `code_review.commit_sha` = head y `status == "completed"`; sin ese marcador, una review o un receipt con `**Reviewed commit:**` del head (paso 6, «Fin de la última ronda») |
| Review fallida | `code_review.status == "failed"` posterior al pedido (paso 2-quater) |
| Review limpia | Estado JSON sin hallazgos o, en el formato viejo, «Codex Review: Didn't find any major issues» del head (paso 5-bis) |
| Severidad | Badges `P0`–`P3` en el body (paso 3-pre) |
| Modos de fix | `local`, `codex` y `auto` ([fix-modes.md](../fix-modes.md)) |
| Cierre | `closeout.sh --reviewer codex` (o sin `--reviewer`) |

Fuentes de hallazgos y lo que se descarta (resumen `codex-pull-request-review-summary`, receipts `codex-review-receipt:v1`, respuestas a `@codex fix`): paso (2) del prompt.
