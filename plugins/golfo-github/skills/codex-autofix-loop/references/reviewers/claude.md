# Perfil de revisor `claude`

Leelo cuando `{{REVIEWER}}` = `claude` (lo fija `claude-autofix-loop` o un pedido como «loop de Claude para el PR N»). El loop es el mismo de `SKILL.md` y `prompt-template.md`: guard, triage, fan-out, closeout, gate de CI, topes y merge no cambian. Este perfil solo reemplaza los **puntos de variación** de la tabla «Perfiles de revisor» de `SKILL.md`. Donde el prompt dice «Codex», `@codex review` o `codex-review-state:v1`, aplicá la fila correspondiente de acá; lo que este archivo no menciona se hace igual que con Codex.

## De dónde vienen las reviews de Claude

El revisor es el workflow de GitHub Actions que corre [`anthropics/claude-code-action`](https://github.com/anthropics/claude-code-action) con el plugin oficial `code-review` y `--comment`, por ejemplo:

```yaml
on:
  pull_request:
    types: [opened, synchronize, ready_for_review, reopened]
# ...
prompt: "/code-review:code-review --comment ${{ github.repository }}/pull/${{ github.event.pull_request.number }}"
```

Publica como `claude[bot]`:

- **Sin hallazgos**: un comentario general cuyo body empieza con `## Code review` y dice `No issues found. Checked for bugs and CLAUDE.md compliance.`
- **Con hallazgos**: un comentario **inline** por hallazgo (herramienta `create_inline_comment`), con descripción, cita de la regla del `CLAUDE.md` o del bug y, si el fix es chico, un bloque `suggestion`. Versiones anteriores del plugin, en cambio, publicaban un comentario general `## Code review` con `Found N issues:` y una lista numerada con links `blob/<sha>/<path>#L<a>-L<b>`.

`{{CLAUDE_REVIEW_WORKFLOW}}` es el `name:` de ese workflow (default `Claude Code Review`). Detectalo al lanzar: el archivo de `.github/workflows/` del head que usa `anthropics/claude-code-action` con un `prompt` que invoca `code-review`. Si el repo no tiene ninguno, el perfil `claude` no aplica: avisá en una línea y no lances el loop.

Un segundo workflow que responde a menciones `@claude` (por ejemplo `claude.yml`) **no es el revisor**: sus respuestas son tareas, no hallazgos.

## Puntos de variación

| Punto | Con `claude` |
|---|---|
| Bot (`{{REVIEWER_BOT}}`) | `claude[bot]` |
| Estado | `.codex-autofix/processed-claude-{{PR}}.json` (así un loop de Codex del mismo PR no comparte dedup) |
| Monitor | `Monitor claude-autofix PR #{{PR}}` |
| Pedido de review de ronda | El push del loop: el workflow corre solo en `synchronize`. No se postea ningún comentario. |
| Ack del pedido (reemplaza la 👀) | Existe un run de `{{CLAUDE_REVIEW_WORKFLOW}}` para el head |
| Review terminada del head | El run más nuevo de ese head está `completed` |
| Review fallida | Ese run terminó `failure`, `timed_out`, `startup_failure` o `cancelled` sin otro run más nuevo del mismo head |
| Review limpia | Run `success` y ningún hallazgo nuevo de `claude[bot]` (ver «Review limpia») |
| Severidad | No hay badges: el plugin solo publica hallazgos que validó como de alta señal |
| Modos de fix | Solo `local` |
| Cierre | `closeout.sh --reviewer claude` |

## Estado de la review del head

Una sola consulta da la evidencia de los pasos 2-ter, 2-quater, 5-bis y 6:

```bash
gh run list --repo {{OWNER}}/{{REPO}} --workflow "{{CLAUDE_REVIEW_WORKFLOW}}" --commit <head> --event pull_request \
  --limit 20 --json databaseId,status,conclusion,createdAt,startedAt,attempt --jq 'sort_by(.createdAt) | last // empty'
```

Llamá RUN a ese resultado. Sin RUN no hay review pedida para el head; con `status != "completed"` la review está corriendo.

## Reemplazos paso por paso

- **(0) Monitor**: el mismo `command` con `bot='claude[bot]'`. Para Claude, el cambio de checks ya cubre el fin del run del workflow (es un check del PR), y los inline nuevos llegan como comentarios del bot.
- **(2) Fuentes**:
  - Inline de `claude[bot]` sin `in_reply_to_id`: hallazgos.
  - Comentarios generales de `claude[bot]`: solo es hallazgo el que empieza con `## Code review` y trae `Found N issues` (formato viejo). Va como un grupo general, igual que un review-body accionable. El `No issues found` no es hallazgo: no reacciones, no respondas y no lo marques, solo lo lee la «Review limpia». Cualquier otro comentario general del bot (respuestas a una mención `@claude`, comentarios de seguimiento con «Claude finished…» o «working…») tampoco es hallazgo.
  - Review-bodies de `claude[bot]`: procesalos solo si traen una sugerencia accionable real, como con Codex (paso 3b). Las reviews que el bot crea para colgar un inline suelen tener body vacío.
- **(2-bis) Re-disparo**: no aplica, porque no hay trigger por comentario. Un run que nunca arranca lo resuelve el timeout del paso 2-quater.
- **(2-ter) Review inicial**: el workflow corre al abrir el PR. Si `reviewRounds` es `0`, el PR no tiene ningún comentario de `claude[bot]` y pasó `{{INITIAL_REVIEW_GRACE_MIN}}` sin RUN para el head, arrancá el reloj sin postear nada: `reviewRequestedAt` = `createdAt` del PR y `lastReviewedSha` = head. Un PR draft no dispara el workflow hasta `ready_for_review`.
- **(2-quater) Timeout y review fallida**:
  - Reintentar una review = `gh run rerun <RUN.databaseId> --repo {{OWNER}}/{{REPO}}`, en lugar de postear `@codex review`. Solo sirve si existe RUN para el head; sin RUN no hay nada que reintentar, así que el primer vencimiento solo suma a `reviewTimeoutRetries` y reinicia el reloj, y el segundo avisa y auto-cancela («PR #N: Claude no revisó el head en X min»).
  - Review fallida = RUN `completed` con una de las conclusiones de la tabla y `startedAt` posterior a `reviewRequestedAt`. Un `cancelled` por la `concurrency` del workflow, con otro run más nuevo del mismo head, no es falla: manda el más nuevo.
  - Igual que con Codex, una ronda vencida o una review fallida **nunca** llevan al merge.
- **(3-pre) Triage**: el plugin ya descarta preexistentes, nits y falsos positivos, así que la mayoría de sus hallazgos son realistas. Igual clasificalos: un hallazgo que cita una regla del `CLAUDE.md` que no aplica al archivo, o que el código ya resuelve, se cierra como «ℹ️ Sin cambios» con el motivo.
- **(4) y (5) Cierre**: `closeout.sh … --reviewer claude`. Un hallazgo del formato viejo (comentario general con varios ítems) se cierra con una sola respuesta general que resume cada ítem.
- **(5-bis) Review limpia**: ver la sección siguiente. El GATE DE CI no cambia, salvo que el run de `{{CLAUDE_REVIEW_WORKFLOW}}` en rojo no se trata como CI fallida a fixear con un subagente: es una review fallida y la resuelve el paso 2-quater. Para mergear ya tiene que estar en `success`, porque lo exige la review limpia.
- **(6) Nueva ronda**: donde el prompt dice «posteá `@codex review`», no postees nada. Si la vuelta pusheó fixes, ese push ya pidió la review: aplicá la misma unidad de estado (`reviewRounds += 1`, `lastReviewedSha` = head, `reviewRequestedAt` = ahora, `reviewTimeoutRetries` = `0`). El «Head avanzado sin review» tampoco postea: si ya hay RUN para el head, adoptalo como la ronda; si no, arrancá el reloj y esperá al run.
- **Fix por delegación**: con `{{FIX_MODE}}` `codex` o `auto`, avisá en una línea que el perfil `claude` solo admite `local` y seguí con `local`. Una mención `@claude` en el hilo podría pushear el fix (si el repo tiene el workflow de menciones con `contents: write`), pero ese camino todavía no tiene reglas de ack, commit ni fallas.

## Review limpia

Chequeala cuando no queden ítems de Claude sin resolver (igual que el paso 5-bis). Es limpia si:

1. RUN existe para el head actual, está `completed` y su `conclusion` es `success`.
2. Ningún comentario de `claude[bot]` creado desde `RUN.startedAt` es un hallazgo sin cerrar (inline sin `in_reply_to_id`, o general `## Code review` con `Found`).

Hay dos formas de limpia, y la PushNotification del merge dice cuál fue:

- **Explícita**: hay un comentario general de `claude[bot]` con `No issues found` creado desde `RUN.startedAt`.
- **Silenciosa**: el run terminó `success` sin publicar nada. El plugin se saltea la review cuando el PR es draft, cerrado, trivial o **ya tiene un comentario de Claude** (paso 1 del comando `code-review`). Por eso, desde la segunda ronda, el workflow suele terminar en silencio aunque el loop haya pusheado fixes. El loop la trata como limpia porque no hay otra evidencia que esperar, igual que los fixes de la última ronda de Codex, que se mergean sin otra review. Si querés que cada push tenga una review real, cambiá el `prompt` del workflow para que no corte cuando Claude ya comentó (por ejemplo, «revisá solo los commits nuevos desde tu último comentario»); el loop no edita el workflow por su cuenta.

Una review limpia sobre un head que no es el actual no vale: seguí al paso 6, igual que con Codex.
