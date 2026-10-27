---
name: codex-comment-closeout
description: "Plantilla y checklist obligatorios para responder, reaccionar o resolver cualquier comentario, hilo inline o review de Codex (chatgpt-codex-connector[bot]) en un PR: variantes ✅ Resuelto, ℹ️ Sin cambios y ⚠️ No pude aplicar, reacción, resolución del hilo y verificación del body publicado. Cargarla SIEMPRE antes de publicar una respuesta a Codex, en cualquier flujo (codex-autofix-loop, el Action codex-autofix.yml, el Auto-fix de la app de escritorio con eventos `ci-monitor-event`, inline-thread-autofix o un fix manual), aunque el usuario no la mencione. Use whenever you are about to reply to, react to, or close out a chatgpt-codex-connector[bot] comment or review."
license: MIT
metadata:
  version: "1.1.0"
  author: "Guido Modarelli"
  category: "code-review"
  tags: "code-review, codex, pull-request, closeout, template"
  command: "/codex-comment-closeout"
---

# Cierre de comentarios de Codex

Fuente de verdad del formato de respuesta a `chatgpt-codex-connector[bot]`. Aplica a **cualquier** respuesta a un comentario de Codex: el loop local [`codex-autofix-loop`](../codex-autofix-loop/SKILL.md), el Action `.github/workflows/codex-autofix.yml`, el Auto-fix de la app de escritorio (eventos `<ci-monitor-event>` que piden responder y resolver hilos), un fix manual pedido en la conversación u otra skill que cierre hilos de Codex. Nunca escribas una respuesta libre ("Corregido en …", "Fixed in …").

## Checklist por comentario

Antes de publicar, completá:

1. **Variante correcta** de la plantilla (abajo):
   - `✅ Resuelto` si hubo fix pusheado, también cuando la sugerencia era válida solo en parte (decilo en «Qué cambió»).
   - `ℹ️ Sin cambios` si evaluaste y no hacía falta, si es un borde rebuscado o si el defecto es preexistente y no bloqueante. Explicalo en «Motivo».
   - `⚠️ No pude aplicar` si falló el flujo.
   - Review-body → quote reply.
2. **Link al commit** con sha corto de 7 caracteres y URL al sha completo, verificado en el head remoto del PR (`git ls-remote` o `gh pr view --json headRefOid`) antes de publicar.
3. **`Qué cambió`** en UNA línea, en español, describiendo el efecto observable.
4. **Pie `<sub>🤖 …</sub>`** de la variante. Fuera del Action no hay run: omití ` · [run]({{run_url}})`. Si el host exige una línea extra (por ejemplo, el Auto-fix de la app pide `_🤖 Addressed by [Claude Code](https://claude.com/claude-code)_`), agregala como **última línea, después del pie**, sin reemplazar ninguna parte de la plantilla.
5. **Reacción**: 👍 en éxito, 👎 solo en «Sin cambios», ninguna en falla. El 👎 le dice a Codex que la sugerencia no era útil; nunca lo uses cuando el problema fue del flujo.
6. **Resolver** el hilo inline solo en éxito o «Sin cambios».
7. **Verificar** después de publicar: releé el body publicado (`gh api repos/<owner>/<repo>/pulls/comments/<reply_id> --jq .body`) y confirmá que empieza con el encabezado de la variante (`✅ **Resuelto** en [`…) y contiene el pie. Si no, editalo con `gh api -X PATCH …/pulls/comments/<reply_id> -f body=…` en lugar de publicar otro reply.

Si ya publicaste una respuesta libre, corregila editándola (PATCH) con la plantilla y agregá la reacción que falte; no publiques un segundo reply.

## Script de cierre

Fuera del Action, usá `scripts/closeout.sh` en lugar de armar los comandos a mano: aplica este
checklist completo (pasos 2 a 7) y es la forma recomendada de cerrar cada comentario.

```bash
bash scripts/closeout.sh --repo <owner>/<repo> --pr <n> --comment <id> --kind inline|general|review \
  --variant resolved|no-change|failed [--sha <sha completo>] [--summary "<qué cambió>"] \
  [--reason "<motivo>"] [--review-node-id <node_id>]
```

- `resolved` espera hasta que el commit esté en el head del PR antes de responder (GitHub puede tardar
  unos segundos en mostrar un push), así el link nunca apunta a un commit que el PR todavía no tiene.
- Reacciona según la variante, responde con la plantilla, relee el body publicado y lo edita si perdió
  el encabezado o el pie, y resuelve el hilo inline.
- Imprime `closeout: comment <id> <variante> reply=<id> resolved=<true|false>`; sale con 1 si GitHub
  falla o la verificación no pasa, y con 2 si faltan argumentos.

## Plantilla de comentario de cierre

Las plantillas viven en `templates/`, una por variante: son la única fuente del formato. Las
leen `scripts/closeout.sh` y quien cierre a mano; no las copies en otro lugar.

| Variante | Archivo | Reacción |
|---|---|---|
| Éxito (fix aplicado) | [`templates/resolved.md`](templates/resolved.md) | 👍 |
| Éxito sobre un review-body (quote reply; después se minimiza la review como `RESOLVED` cuando ella y sus inline estén resueltos) | [`templates/resolved-review.md`](templates/resolved-review.md) | 👍 |
| Sin cambios (no hacía falta tocar código, borde rebuscado o defecto preexistente) | [`templates/no-change.md`](templates/no-change.md) | 👎 |
| Falla del flujo (problema del Action o del loop, no de la sugerencia) | [`templates/failed.md`](templates/failed.md) | ninguna |

Placeholders: `{{sha_corto}}` (7 caracteres), `{{commit_url}}`, `{{resumen}}` (una línea),
`{{motivo}}` (una línea), `{{body_review_citado}}` (cada línea del body con `> `) y `{{run_url}}`
(solo el Action).

- Fuera del Action no hay run: se quita ` · [run]({{run_url}})` del pie.
- Sin resumen, se omite la línea «Qué cambió»; sin motivo, la línea `**Motivo:**`.
- `{{motivo}}` es obligatorio cuando el cierre es por borde rebuscado o por defecto preexistente.
  Ejemplos:
  - «caso de borde poco realista: requiere una ruta de checkout con `%VAR%` y un shim `.cmd`».
  - «defecto preexistente: estas líneas ya estaban en la base del PR; queda como follow-up fuera de este alcance».

## Regla de paridad

Cualquier cambio a `templates/` debe reflejarse en el step «Cerrar comentario» del workflow `.github/workflows/codex-autofix.yml`. La línea `**Motivo:**` de «Sin cambios» es opcional, así que el Action sigue siendo compatible aunque no la emita; agregarla allí queda como follow-up. El soporte de **review-bodies** (👍 vía GraphQL + quote reply + minimize `RESOLVED`) por ahora vive solo en el loop local; portarlo al Action queda como follow-up pendiente.
