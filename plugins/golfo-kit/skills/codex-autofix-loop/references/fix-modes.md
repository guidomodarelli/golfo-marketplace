# Modo de fix: subagente local o `@codex fix`

Leelo desde `SKILL.md` cuando `{{FIX_MODE}}` no es `local` (el default) o cuando haya que delegar un fix a Codex.

`{{FIX_MODE}}` decide quién aplica el fix de cada grupo (el triage, la agrupación y el
closeout son los mismos en todos los modos):

- **`local`** (default): solo subagentes locales con `fix-in-ephemeral-clone`. Es el
  default porque el entorno cloud de Codex no tiene credenciales para pushear a la rama:
  sus `@codex fix` preparan un commit que nunca llega al PR (ver `ae2d994` en el PR #111
  de TuTribu) y solo suman una vuelta de espera.
- **`codex`**: solo delegación a Codex con `@codex fix`. Si Codex no pushea, el
  comentario queda como falla (paso 5) y se reintenta hasta `{{CODEX_FIX_MAX_ATTEMPTS}}`
  veces; después queda pendiente y se avisa.
- **`auto`**: primero `@codex fix`; si Codex no toma el pedido, responde sin
  pushear (por ejemplo, sin permiso de escritura) o vence `{{CODEX_FIX_TTL_MIN}}`, el
  grupo cae a un subagente local en la vuelta siguiente.

Reglas del pedido a Codex:

- **Dónde se comenta**: si el grupo es inline, el `@codex fix` va como **reply en el
  hilo del primer comentario del grupo** (`pulls/{pr}/comments/<id>/replies`), así el
  pedido queda en el propio thread. Los generales y los review-bodies no tienen hilo:
  el pedido va como comentario general del PR, con link al comentario o review original.
- **Un pedido por grupo**: como los demás grupos, nunca dos tareas sobre el mismo `path`
  en paralelo. Si el grupo tiene varios inline, el reply del primer hilo lista los links
  de los otros comentarios del grupo; en esos otros hilos no se comenta hasta el closeout.
- **Nunca incluir la palabra `review`** en el texto del pedido: cualquier comentario
  `@codex` que la contenga dispara una review en lugar de una tarea de fix. Referenciá
  los review-bodies como «resumen de Codex» o por link.
- **Texto del pedido** (en español, una sola línea de instrucción + contexto):
  `@codex fix este hallazgo con el diff mínimo, sin ampliar el alcance a casos vecinos, y pusheá el commit a la rama {{BRANCH}}.`
  Para generales y review-bodies, agregá el link al comentario o resumen original.
- **No es un cierre**: el pedido no usa la plantilla de cierre ni reacciona. El cierre
  (👍 + reply con plantilla + resolver hilo) lo hace el loop recién cuando verifica el
  commit de Codex en el head del PR (paso 4).
- **Respuestas de Codex al pedido**: Codex reacciona 👀 al pedido y suele contestar en el
  mismo hilo o en el PR. Esas respuestas NO son hallazgos nuevos: se registran en
  `delegationReplyIds` y no se fixean.
- **Fallas de CI** (gate del paso 5-bis): en `codex`/`auto` se delegan con un comentario
  general `@codex fix las fallas de CI del run <run_url> con el diff mínimo` antes de usar un
  subagente local.

> **Por qué delegar en `fix-in-ephemeral-clone`:** esa skill es la dueña del
> contrato de aislamiento (clone efímero, copia de `.env*`, deps por plataforma,
> rebase pre-push, push con retry, cleanup). Este loop NO reimplementa ese flujo:
> solo arma el input (comentarios agrupados por archivo → issue), spawnea un
> subagente por grupo (con concurrencia según recursos libres) que la invoca en paralelo, y
> hace el closeout. Cualquier cambio al mecanismo de clone/fix/push vive en esa skill.

> Es un complemento del workflow de CI `.github/workflows/codex-autofix.yml`.
> El **Action** es la persistencia real 24/7 (webhook, sin sesión). Este **loop local**
> corre solo mientras Claude Code está abierto (el cron es de sesión: `durable: true`
> no se persiste en este entorno, así que el job muere al cerrar Claude).
