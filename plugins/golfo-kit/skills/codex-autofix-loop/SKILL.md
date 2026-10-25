---
name: codex-autofix-loop
description: "Lanza y opera el loop que auto-fixea comentarios de Codex (chatgpt-codex-connector[bot]) en un PR: clone efímero → fix → push → closeout del hilo, o `@codex fix` en el propio hilo (modos `codex`/`auto` con fallback local), con dedup por PR, tope de rondas, timeout por ronda, guard de auto-cancelación y merge sin preguntar ni esperar revisión humana tras el gate de CI, también al terminar la última ronda. Lanzarlo solo, sin que lo pidan, apenas el agente abre un PR con `gh pr create`. Adapta la espera a cada agente (Monitor en Claude Code, watcher en background en Hermes, en foreground en Codex, o una ronda por invocación). Para un solo comentario de Codex alcanza con `codex-comment-closeout`. Use when the user asks to relaunch/start the Codex auto-fix loop for a PR, right after the agent opens a pull request (gh pr create) even if nobody asked, set up Codex comment auto-fixing, mentions docs/codex-autofix-loop.md, processed-PR.json, or the codex-autofix workflow."
license: MIT
metadata:
  version: "1.6.1"
  author: "Guido Modarelli"
  category: "code-review"
  tags: "code-review, codex, pull-request, autofix, convergence"
  command: "/codex-autofix-loop"
---

# Codex auto-fix loop (local, vía Claude Code)

Loop local que escucha comentarios de **Codex** (`chatgpt-codex-connector[bot]`)
en un PR y **spawnea subagentes en paralelo** (uno por GRUPO de archivo, tantos
como permitan la CPU, la RAM y el disco libres en cada vuelta) que delegan el fix en la skill
[`fix-in-ephemeral-clone`](../fix-in-ephemeral-clone/SKILL.md) —invocada vía
la herramienta `Skill` (`/fix-in-ephemeral-clone`)— tratando cada comentario
como la "issue" a resolver (clone efímero depth-1 → fix → validar → push a la rama
del PR). Cada subagente trabaja en su propio clone efímero aislado; como todos
pushean a la misma rama, ante non-fast-forward cada subagente reintegra (rebase
+ resolución de conflictos + revalidación del fix propio y de los cambios
integrados de los otros subagentes) y recién ahí pushea, repitiendo el ciclo
hasta el límite de `fix-in-ephemeral-clone` (máximo 3 ciclos non-fast-forward;
al agotarlo reporta `CONCURRENT_PUSH_RETRY_EXHAUSTED`).
Después el loop principal hace el closeout en el hilo (reacción 👍 + reply con link
al commit + resolver el hilo inline).

Además del subagente local, el loop puede **delegar el fix al propio Codex**
([Act on review findings](https://learn.chatgpt.com/docs/third-party/github#act-on-review-findings)):
deja un comentario `@codex fix …` en el propio hilo del hallazgo (o en el PR cuando
no hay hilo), Codex abre una tarea cloud con el PR como contexto y pushea el fix a la
rama si tiene permiso. Qué camino se usa lo decide `{{FIX_MODE}}` (ver «Modo de fix»).

Cubre **tres fuentes** de comentarios de Codex:
1. **Inline** (`pulls/{pr}/comments`): atados a un `path` + `line`; closeout = 👍 + reply en el hilo + resolver el hilo.
2. **Generales** (`issues/{pr}/comments`): comentarios sueltos del PR; closeout = 👍 + reply.
3. **Review-body de primer nivel** (`pulls/{pr}/reviews`, anchor `#pullrequestreview-…`): el resumen que Codex postea al enviar una review. Se procesa **solo cuando el body trae una sugerencia accionable real** (no un mero resumen). Closeout = 👍 + **quote reply** (citando el body). Cuando el review-body **y todos sus comments inline** quedan resueltos, se **minimiza la review con estado `RESOLVED`** (queda oculta/colapsada). `PullRequestReview` implementa `Reactable` y `Minimizable`, así que reacción y minimize van por GraphQL sobre su `node_id`.

## Cierre de cada comentario

Toda respuesta, reacción o resolución de un comentario de Codex sigue la skill
[`codex-comment-closeout`](../codex-comment-closeout/SKILL.md): plantilla, checklist,
reacción y verificación del body publicado. Leela antes del primer closeout de la corrida.
Este loop solo decide **cuándo** cerrar y con qué variante.

## Regla de alcance y convergencia

El loop tiene que **converger y terminar**. Aplicá la
[política de convergencia](../../references/review-convergence.md)
compartida con `review-fix-loop`: tope de rondas, registro de findings, fix por clase de
bug y qué bloquea. Si el link relativo no resuelve porque la skill está instalada
por symlink, resolvé antes el path real del directorio de la skill. Cada fix de un caso muy rebuscado agrega complejidad y dispara más
comentarios de borde en la siguiente `@codex review`, y el loop no termina nunca. Por eso
el LOOP PRINCIPAL clasifica cada comentario antes de agrupar o spawnear (paso 3-pre del
prompt):

- **Realista** (puede pasar en el uso normal, o es un bug, un riesgo de seguridad o una
  pérdida de datos plausible): se fixea.
- **Borde razonable** (poco frecuente pero creíble, con un fix acotado y testeable):
  se fixea, con el diff mínimo.
- **Borde rebuscado** (exige combinaciones improbables o entornos exóticos, por ejemplo
  una ruta de checkout con `%VAR%` pasando por un shim `.cmd`, o rediseñar un subsistema
  para cubrir algo hipotético): NO se fixea. Se cierra con «ℹ️ Sin cambios» y un
  `**Motivo:**` de una línea que explica por qué no aplica, se resuelve el hilo y se
  marca como procesado.
- **Preexistente** (las líneas señaladas ya existían en el merge base del PR: comprobalo
  con `git blame <merge-base> -- <path>` o `git show <merge-base>:<path>`): NO se fixea,
  salvo que sea seguridad o pérdida de datos, o una línea que el PR ya modifica y el fix
  sea trivial. Se cierra con «ℹ️ Sin cambios» y el motivo «defecto preexistente: …»,
  se resuelve el hilo y se registra como `pre-existing`. No abre otra ronda.
- **Nit** (badge `P3` de Codex o sugerencia sin impacto funcional): se fixea solo si en la
  misma vuelta hay otro fix realista y el nit es barato y local. Si la vuelta solo tiene
  nits, se cierran con «ℹ️ Sin cambios» y el motivo «nit no bloqueante», así no abren una
  ronda nueva. Codex en GitHub suele reportar solo `P0`/`P1`, así que esto es raro.

**Clase de bug.** Al fixear un hallazgo realista, el subagente corrige todas las
apariciones del mismo patrón **dentro del diff del PR** (no solo la línea señalada), sin
tocar código fuera del PR ni sumar casos de borde vecinos. Así Codex no vuelve a marcar el
mismo patrón, una línea por ronda.

Ante la duda entre «borde razonable» y «rebuscado», mirá el costo: si el fix es chico,
local y testeable, hacelo; si exige rediseño, dependencias nuevas o tocar varios
módulos por un caso hipotético, es rebuscado. En un riesgo de seguridad sin solución
simple, aplicá la mitigación razonable, documentá el riesgo residual y cerrá con
«✅ Resuelto» aclarando en «Qué cambió» que quedó resuelto en parte, sin sobre-diseñar.
Si Codex repite en una review posterior un hallazgo ya cerrado como «Sin cambios», volvé
a cerrarlo igual, con el mismo motivo, sin spawnear subagente.

**Corte por convergencia:** si en una vuelta todos los hallazgos de la última review de
Codex se cerraron como «Sin cambios» (rebuscados, preexistentes, nits o repetidos) y no
hubo ningún commit nuevo, el head no cambió y Codex no va a publicar una review limpia. En
ese caso NO postees otro `@codex review` y mergeá, igual que en la terminación por review
limpia (paso 5-bis), siempre después del GATE DE CI. Mergeá con
`gh pr merge {{PR}} --repo {{OWNER}}/{{REPO}} --squash --delete-branch`. Si el merge tiene
éxito, auto-cancelá el loop y mandá una PushNotification de una línea («PR #N mergeado:
solo quedaban hallazgos cerrados como Sin cambios»). Si el merge falla (checks pendientes,
conflicto, branch protection), dejá el loop vivo para reintentar en la próxima vuelta y
avisá el motivo una sola vez.

**Tope de rondas (merge al terminar la última ronda):** una ronda es cada `@codex review`
que postea el loop; la review inicial del PR es la ronda 0. La última ronda es la review
que llega después de postear el `@codex review` número `{{MAX_REVIEW_ROUNDS}}`. El loop la
termina como cualquier otra: triagea sus hallazgos, fixea los realistas, cierra los hilos y
espera a que se vacíe `inFlight`. Después NO postea otro `@codex review` y **mergea sin
preguntar**: no usa `AskUserQuestion`, no pide confirmación en el chat y no espera
aprobación humana. El merge final se rige por estas reglas:

- **Persistencia**: el loop marca `finalMergePending: true` en el JSON. Desde ahí, cada
  vuelta reintenta el merge (paso 6, «Merge final pendiente») y ya no pide reviews.
- **GATE DE CI**: es el único requisito, el mismo del paso 5-bis. Con checks pendientes
  o un merge fallido (conflicto, branch protection), el loop sigue vivo y reintenta. Con
  checks en rojo, aplica el manejo de CI fallida (fix con diff mínimo), sin postear
  `@codex review`, y vuelve a pasar el gate.
- **Comando**: `gh pr merge {{PR}} --repo {{OWNER}}/{{REPO}} --squash --delete-branch
  --match-head-commit <head>`, con el head que pasó el gate. Así un push concurrente hace
  fallar el merge en vez de mergear un commit que no pasó CI.
- **Hallazgos sin fix**: en la última ronda cada hallazgo tiene un solo intento. Si falla,
  queda `failed` con `terminal: true` y no se reintenta (paso 5). Esos hallazgos no
  bloquean el merge. Van listados
  con su link en la PushNotification de cierre («PR #N mergeado al terminar la última
  ronda (R/R): …»), para que una persona los retome en un PR nuevo.
- **Commits ajenos**: si el head trae commits que no son fixes del loop (por ejemplo, un
  merge de la rama base) y ya no quedan rondas, el loop no pide review ni mergea: avisa y
  se auto-cancela (paso 6, «Head avanzado sin review»).

Los fixes de la última ronda no pasan por otra review de Codex: es el costo de cortar en
el tope, y la CI verde sigue siendo obligatoria. Con `{{MAX_REVIEW_ROUNDS}}` =
`sin límite`, este tope nunca se agota (`reviewRounds >= {{MAX_REVIEW_ROUNDS}}` es
siempre falso): el loop sigue hasta la review limpia, el corte por convergencia, el tope
de solo tests o el cierre del PR.

**Tope de rondas de solo tests:** una ronda es «de solo tests» cuando todos los commits que
entraron al PR desde la última clasificación (los fixes de esa ronda y cualquier commit
ajeno al loop) tocan únicamente archivos de tests o evals (los que matchean
`{{TEST_PATH_PATTERNS}}`); si la lista completa de archivos no se puede obtener, la ronda
no cuenta como de solo tests. En esas rondas Codex suele seguir encontrando variantes de las
mismas aserciones (por ejemplo, regex de evals evaluadas línea por línea) y el loop no
converge aunque el código del producto ya esté resuelto. Por eso el loop cuenta en
`testOnlyRounds` las rondas de solo tests **consecutivas**; una ronda que corrige algo
fuera de los tests vuelve el contador a `0`. Si `testOnlyRounds` llega a
`{{MAX_TEST_ONLY_ROUNDS}}`, NO postees otro `@codex review`: mergeá el PR como en el
«Corte por convergencia» (siempre después del GATE DE CI del paso 5-bis) y auto-cancelá
el loop con una PushNotification de una línea («PR #N mergeado: {{MAX_TEST_ONLY_ROUNDS}}
rondas seguidas solo corregían tests»). Este tope aplica aunque el usuario haya subido o
levantado `{{MAX_REVIEW_ROUNDS}}`, y gana el que se alcance primero. El tope alcanzado
queda persistido: el loop lo reevalúa en cada vuelta (aunque esa vuelta no fixee nada)
hasta que el merge salga o el PR se cierre, y mientras siga alcanzado no pide más reviews.

**Timeout de ronda:** cada ronda (cada `@codex review` que postea el loop, incluida la
review inicial pedida en el paso 2-ter) tiene un reloj. Así el loop no queda vivo para
siempre si Codex nunca publica la review: en el PR #29 la review de la ronda 1 quedó
`running` 9,5 h y el loop esperó sin hacer nada.

- **Reloj**: `reviewRequestedAt` guarda el momento en que el loop posteó el `@codex review`
  de la ronda. El repost de un trigger sin 👀 (paso 2-bis) no lo reinicia, así que un
  trigger que Codex nunca leyó también termina en este timeout.
- **Vencimiento**: la ronda vence cuando pasaron `{{REVIEW_ROUND_TIMEOUT_MIN}}` min desde
  `reviewRequestedAt` y Codex no publicó una review **terminada** de `lastReviewedSha`. La
  evidencia es la misma que en el «Fin de la última ronda» del paso 6. La 👀 y un estado
  `running` no frenan el reloj: muestran que Codex tomó el pedido, no que la review vaya a
  llegar, y el PR #29 quedó colgado justo en `running`.
- **Primer vencimiento**: reintentá una sola vez. Si `reviewTimeoutRetries` es menor que
  `{{REVIEW_ROUND_TIMEOUT_RETRIES}}`, reposteá `@codex review`. En la misma unidad, sumá 1
  a `reviewTimeoutRetries`, poné `reviewRequestedAt` en ahora, guardá el head actual en
  `lastReviewedSha` y persistí el JSON. **No sumes a `reviewRounds`**: una review que nunca
  llegó no consume el tope de rondas.
- **Segundo vencimiento**: mandá una PushNotification de una línea («PR #N: Codex no
  publicó la review en X min», con X = `{{REVIEW_ROUND_TIMEOUT_MIN}}` ×
  (`{{REVIEW_ROUND_TIMEOUT_RETRIES}}` + 1)), poné `reviewTimedOut: true` y **auto-cancelá
  el loop**. Si quedan ids en `inFlight`, esperá a que vuelvan sus subagentes y cancelá en
  la primera vuelta sin `inFlight`. Se auto-cancela, en vez de quedar vivo con un aviso, porque sin review no
  hay nada que procesar: cada vuelta del cron o del watcher gasta un turno del agente
  (unas 190 vueltas en las 9,5 h del PR #29) y el aviso queda perdido entre ellas. El
  JSON se conserva, así que relanzar retoma la misma ronda.
- **Nunca mergea**: una ronda vencida no es una review limpia. Tampoco cuenta para el
  corte por convergencia, el tope de solo tests ni el fin de la última ronda, aunque la CI
  esté verde y no queden hallazgos abiertos.
- **Relanzar tras el timeout**: con `reviewTimedOut: true`, el paso 2 de «Cómo
  relanzarlo» lo vuelve a `false` y pone `reviewTimeoutRetries` en `0`. Como el reloj ya
  venció, la primera vuelta repostea `@codex review` y arranca un reloj nuevo. Relanzar un
  loop que no se canceló por timeout no toca estos campos, así que no regala reintentos.

**Sin espera de revisión humana:** el loop no frena el merge para que una persona
apruebe, sin importar qué archivos toque el PR ni el tamaño del diff. Los únicos
requisitos para mergear son la review limpia de Codex (o el corte por convergencia, el
tope de solo tests o el fin de la última ronda) y el GATE DE CI. Ningún merge del loop
se consulta con el usuario. Si el repo tiene branch protection que exige una aprobación, `gh pr merge`
falla y el loop lo trata como cualquier merge fallido: avisa el motivo una vez y reintenta.

## Modo de fix: subagente local o `@codex fix`

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

## Compatibilidad entre agentes

El prompt de abajo usa herramientas de Claude Code (`Monitor`, `CronCreate`/`CronList`/
`CronDelete`, `TaskStop`, `Agent`, `PushNotification`). Antes de lanzarlo, leé
[`references/agent-modes.md`](references/agent-modes.md) y elegí el modo según las
herramientas **realmente presentes en la sesión**, no según el nombre del agente
(protocolo común en [`agent-capabilities.md`](../../references/agent-capabilities.md)):

- **A. Monitor + cron** (Claude Code): el prompt tal cual.
- **B. Watcher en background** (Hermes): `scripts/wait-for-pr-event.sh` acotado en background
  con aviso al terminar, rearmado tras cada vuelta hasta `{{MAX_WATCH_CYCLES}}` ciclos.
- **C. Watcher en foreground dentro del turno** (Codex y otros agentes con terminal): el mismo
  script esperado en primer plano, ciclo por ciclo, hasta `{{MAX_INTURN_CYCLES}}` ciclos; cubre la
  escucha del PR, el respaldo por timeout y el relanzado tras `@codex review`.
- **D. Una ronda por invocación** (sin shell para comandos largos, o si el usuario lo pide): una
  vuelta del prompt, sin monitor, cron ni esperas, y cierre con instrucciones para relanzar.

En todos los modos se mantienen el dedup de `processed-<PR>.json`, los topes de rondas, el
timeout de ronda, el guard de auto-cancelación y los gates de merge (review limpia del head + CI verde). Lo que el
modo desactiva se reporta al cierre en `Limitaciones del agente`.

## Arranque automático al abrir un PR

Cada vez que el agente abre un PR con `gh pr create`, lanzá este loop para ese PR **en el
mismo turno, sin preguntar ni esperar a que alguien lo pida**. Vale para cualquier flujo:
`feature-branch-pr`, `stacked-pr`, un release o un fix en otro repo. Así ningún PR queda
esperando la review de Codex sin nadie que procese sus comentarios.

1. Leé el PR recién creado con `gh pr view <url-devuelta> --json number,headRefName,baseRefName,isDraft`
   y tomá de ahí `{{OWNER}}/{{REPO}}`, `{{PR}}` y `{{BRANCH}}`.
2. Seguí «Cómo relanzarlo» con el tope del paso 0 (por defecto
   `{{DEFAULT_MAX_REVIEW_ROUNDS}}`) y el modo de «Compatibilidad entre agentes». Si Codex
   no hace la review automática, el paso (2-ter) del prompt la pide.
3. En el cierre del flujo que abrió el PR, reportá una línea: «Loop de Codex lanzado
   para el PR #N (tope R rondas)».

No lo lances, y decí en una línea por qué, cuando:

- La base del PR es otra rama de feature (una capa intermedia de un stack). Mergearla
  antes que su parent rompe el stack. El loop se lanza cuando esa capa pasa a apuntar a
  la rama de integración (`develop`, `main`, `master` o la default del repo).
- El PR es la capa base de un stack que `stacked-pr` todavía está armando. El merge borra
  la rama que las capas siguientes usan de base. El loop se lanza cuando todas las capas
  están publicadas y el golden diff está validado.
- El PR es draft: `gh pr merge` no puede mergearlo.
- El usuario pidió explícitamente no lanzarlo.
- Ya hay un loop vivo para ese PR (cron, `Monitor` o watcher con su número): reutilizalo
  en vez de armar otro.

## Cómo relanzarlo (cualquier PR)

0. Definí `{{MAX_REVIEW_ROUNDS}}` **sin preguntarle al usuario**: decide cuánto puede
   iterar el loop sin supervisión.
   - Si el pedido ya lo indica, usalo: un entero positivo («tope 5») o `sin límite` (el
     loop solo corta por review limpia, convergencia, tope de solo tests o cierre del PR).
   - Si no lo indica (o el valor no es un entero positivo ni «sin límite»), usá
     `{{DEFAULT_MAX_REVIEW_ROUNDS}}` rondas y seguí con el setup.

   No uses `AskUserQuestion` ni hagas una pregunta en el chat por el tope: el loop arranca
   directo. El tope elegido no cambia `{{MAX_TEST_ONLY_ROUNDS}}`, que sigue aplicando igual.
1. Reemplazá los placeholders del prompt de abajo (`{{OWNER}}`, `{{REPO}}`,
   `{{PR}}`, `{{BRANCH}}`) por los del PR objetivo.
2. Inicializá el estado de dedup del PR (vacío procesa todo el backlog; con ids
   ya cargados procesa solo los nuevos):
   ```
   .codex-autofix/processed-{{PR}}.json  ->  {"pr":{{PR}},"processedCommentIds":[],"inFlight":{},"codexAttempts":{},"delegationReplyIds":[],"reviewRounds":0,"testOnlyRounds":0,"testOnlyHeadSha":null,"lastReviewedSha":null,"reviewRequestedAt":null,"reviewTimeoutRetries":0,"reviewTimedOut":false,"finalMergePending":false,"outcomes":{}}
   ```
   (`inFlight` registra los comentarios que tienen un subagente o un pedido
   `@codex fix` trabajando; `codexAttempts` cuenta los pedidos a Codex por comment id;
   `delegationReplyIds` guarda los ids de los pedidos `@codex fix` y de las respuestas
   de Codex a esos pedidos; `reviewRounds` cuenta los `@codex review` que posteó el loop;
   `testOnlyRounds` cuenta las rondas consecutivas cuyos commits solo tocaron tests o evals
   (ver «Tope de rondas de solo tests») y `testOnlyHeadSha` es el head de la última
   clasificación (o, antes de la primera, el head previo a los primeros fixes del loop);
   `lastReviewedSha` es el head al postear el último; `reviewRequestedAt` (ISO-8601 UTC) es
   el momento en que se posteó el `@codex review` de la ronda en curso y
   `reviewTimeoutRetries` cuenta los reposts de esa ronda por vencimiento y `reviewTimedOut`
   queda en `true` cuando el loop se auto-canceló porque la ronda volvió a vencer (ver
   «Timeout de ronda»); `finalMergePending` queda en `true`
   cuando terminó la última ronda permitida y solo falta el merge final (ver «Tope de
   rondas»); `outcomes` es el registro de
   findings de la política de convergencia: `id -> {result, severity, round, path, sha?, reason?}`,
   con `result` en `fixed`, `rejected`, `pre-existing`, `nit-skipped`, `edge-case` o
   `failed`. Si falta alguna clave, el loop la trata como vacía o `0`.)
   Si el archivo ya existe (relanzar), conservalo. Solo si trae `reviewTimedOut: true`,
   ponelo en `false` y `reviewTimeoutRetries` en `0`: el loop se había auto-cancelado por el
   «Timeout de ronda» y relanzarlo es pedir un reintento más.
   (`.codex-autofix/` está gitignored: es estado de runtime, no se commitea.)
3. Lanzá el loop pegando el prompt con el intervalo `{{INTERVAL}}`:
   ```
   /loop {{INTERVAL}} <pegá acá el prompt ya completado>
   ```
   O, más simple, decile a Claude: «relanzá el loop de Codex para el PR {{PR}}
   usando el skill codex-autofix-loop» y completa la plantilla por vos (con el tope de
   rondas del paso 0).

> **Variables globales del loop** (única fuente de verdad — cambiá SOLO estos
> números y se propagan a todo el documento):
> - `{{INTERVAL_MIN}}` = `3` — minutos entre corridas del cron de respaldo (el disparador principal es el Monitor del PR).
> - Costo estimado de UN subagente (clone efímero + install + tests), usado para
>   calcular cuántos caben en paralelo según recursos libres:
>   - `{{CPU_PER_AGENT}}` = `1` — cores lógicos libres por subagente.
>   - `{{RAM_PER_AGENT_GB}}` = `2` — GB de RAM disponible por subagente.
>   - `{{DISK_PER_AGENT_GB}}` = `3` — GB de disco libre (en el tempdir) por subagente.
> - Reserva que nunca se reparte entre subagentes (queda para el sistema y la sesión):
>   - `{{RAM_RESERVE_GB}}` = `2`.
>   - `{{DISK_RESERVE_GB}}` = `5`.
> - `{{INFLIGHT_TTL_MIN}}` = `60` — minutos tras los cuales una entrada de
>   `inFlight` sin subagente vivo se considera huérfana y se libera.
> - `{{FIX_MODE}}` = `local` — `local`, `codex` o `auto` (ver «Modo de fix»). Usá
>   `codex` o `auto` solo si Codex tiene permiso de escritura en la rama del PR.
> - `{{CODEX_FIX_TTL_MIN}}` = `30` — minutos que se espera el commit de un pedido
>   `@codex fix` antes de darlo por fallido.
> - `{{CODEX_ACK_TIMEOUT_MIN}}` = `10` — minutos que se espera la reacción 👀 de Codex
>   sobre el pedido antes de darlo por no tomado.
> - `{{CODEX_FIX_MAX_ATTEMPTS}}` = `2` — pedidos `@codex fix` por comentario en modo
>   `codex` (en `auto` es siempre 1 antes de caer a local).
> - `{{CODEX_MAX_PARALLEL}}` = `2` — pedidos `@codex fix` simultáneos (no consumen
>   recursos locales, pero sí pushes concurrentes a la rama).
> - `{{MONITOR_POLL_SEC}}` = `30` — segundos entre consultas del `Monitor` que vigila
>   el PR mientras está abierto (30 s o más por rate limit).
> - `{{DEFAULT_MAX_REVIEW_ROUNDS}}` = `3` — tope de `@codex review` que usa el loop
>   cuando el pedido no indica otro.
> - `{{MAX_REVIEW_ROUNDS}}` = el que indica el pedido o, si no indica ninguno,
>   `{{DEFAULT_MAX_REVIEW_ROUNDS}}` (paso 0 de «Cómo relanzarlo»): un entero positivo o
>   `sin límite` — `@codex review` que el loop puede postear antes de cortar por falta de
>   convergencia (ver «Tope de rondas»).
> - `{{INITIAL_REVIEW_GRACE_MIN}}` = `5` — minutos desde que se abrió el PR que el loop
>   espera la review automática de Codex antes de pedirla con `@codex review` (paso 2-ter).
> - `{{REVIEW_ROUND_TIMEOUT_MIN}}` = `45` — minutos que el loop espera, desde el
>   `@codex review` de una ronda, a que Codex publique la review terminada de
>   `lastReviewedSha` (ver «Timeout de ronda»). Codex suele tardar entre 5 y 15 min. Los 45
>   dan margen para un PR grande o una cola lenta, y el timeout se evalúa en varias vueltas
>   del cron o del watcher antes de vencer.
> - `{{REVIEW_ROUND_TIMEOUT_RETRIES}}` = `1` — reposts de `@codex review` que el loop hace por
>   una ronda vencida antes de avisar y auto-cancelarse.
> - `{{MAX_TEST_ONLY_ROUNDS}}` = `3` — rondas consecutivas en las que los fixes solo tocan
>   tests o evals antes de dejar de pedir reviews y mergear (ver «Tope de rondas de solo
>   tests»). Aplica aunque se suba o se levante `{{MAX_REVIEW_ROUNDS}}`.
> - `{{TEST_PATH_PATTERNS}}` = `(^|/)(tests?|__tests__|evals?|e2e)/|\.(test|spec)\.[^/]+$|_test\.[^/]+$|\.bats$`
>   — regex extendida (`grep -E`) que identifica un archivo de tests o evals por su path.
>   Solo incluye convenciones inequívocas (`spec/` o `fixtures/` pueden ser contratos o datos
>   del producto); un repo puede ampliarla si sus convenciones lo justifican.
>
> Derivados (no los edites a mano; salen de `{{INTERVAL_MIN}}`):
> - `{{INTERVAL}}` = `{{INTERVAL_MIN}}m` (= `3m`) — intervalo de `/loop`.
> - `{{CRON}}` = `*/{{INTERVAL_MIN}} * * * *` (= `*/3 * * * *`) — cron equivalente
>   para identificar el job en `CronList`.

El disparador principal es un `Monitor` del PR (paso 0 del prompt): consulta GitHub cada
`{{MONITOR_POLL_SEC}}` s y corre una vuelta apenas hay un head nuevo, un comentario o review
de Codex o un cambio en los checks. El cron de `{{INTERVAL}}` queda como respaldo para los
timeouts y para rearmar el monitor si murió. Monitor y cron son session-only: si cerrás
Claude, hay que relanzarlo. El loop se
**auto-cancela** en estos casos: (a) cuando el PR deja de estar `OPEN`
(mergeado/cerrado/borrado); (b) cuando Codex responde con una **review limpia**
para el head actual, no quedan ítems pendientes y pasa el gate de CI (o se da el corte
por convergencia): ahí el loop **mergea el PR** sin esperar revisión humana y se corta
solo; (c) cuando termina la última ronda permitida (`{{MAX_REVIEW_ROUNDS}}`): ahí también
mergea sin preguntar tras el gate de CI; (d) cuando se alcanzan
`{{MAX_TEST_ONLY_ROUNDS}}` rondas seguidas que solo corrigen tests y el PR se mergea tras el
gate de CI; (e) cuando la review de una ronda vence por segunda vez (ver «Timeout de
ronda»): ahí avisa y corta **sin mergear**. La review limpia se reconoce por el estado JSON del resumen de Codex
(`<!-- codex-review-state:v1 {...} -->` sin hallazgos) o, en el formato viejo, por el
texto "Codex Review: Didn't find any major issues" (ver paso 5-bis).

## Prompt (plantilla parametrizable)

```text
Loop de auto-fix de comentarios de Codex en el PR #{{PR}} de {{OWNER}}/{{REPO}} (rama {{BRANCH}}).

GUARD DE AUTO-CANCELACIÓN (hacelo SIEMPRE primero). Obtené el estado del PR:
  estado=$(gh pr view {{PR}} --repo {{OWNER}}/{{REPO}} --json state -q .state 2>/dev/null)
- "OPEN" -> seguí. - "MERGED"/"CLOSED" -> auto-cancelá. - vacío/falla (404 PR o repo borrado) -> confirmá una vez con `gh api repos/{{OWNER}}/{{REPO}}/pulls/{{PR}} --jq .state 2>&1`; si vuelve a fallar o "closed", auto-cancelá; si "open", seguí (error transitorio).
Auto-cancelar = CronList, identificá el job de ESTE loop (cron `{{CRON}}`, auto-fix de Codex en PR #{{PR}}), borralo con CronDelete por id, detené con TaskStop el Monitor `Monitor codex-autofix PR #{{PR}}` si está vivo, PushNotification de una línea avisando el motivo, y terminá sin procesar.

Si OPEN, procesá:
(0) MONITOR DEL PR (disparador principal; el cron `{{CRON}}` es solo respaldo para timeouts y por si el monitor muere). Mientras el PR esté `OPEN` tiene que haber UN `Monitor` vivo con `description` = `Monitor codex-autofix PR #{{PR}}` (así lo reconocés entre tus tareas en background y no armás dos). Si no existe, armalo con `timeout_ms: 1800000` (el máximo) y este `command`:
   ```bash
   pr={{PR}}; repo={{OWNER}}/{{REPO}}; bot='chatgpt-codex-connector[bot]'
   count_bot_reviews() { gh api "repos/$repo/pulls/$pr/reviews" --paginate --jq "[.[] | select(.user.login==\"$bot\")] | length" 2>/dev/null | jq -s 'add // 0'; }
   checks_signature() { gh pr checks "$pr" --repo "$repo" --json bucket -q 'group_by(.bucket) | map("\(.[0].bucket)=\(length)") | join(",")' 2>/dev/null || true; }
   head=$(gh pr view "$pr" --repo "$repo" --json headRefOid -q .headRefOid 2>/dev/null)
   reviews=$(count_bot_reviews); checks=$(checks_signature)
   since=$(date -u +%Y-%m-%dT%H:%M:%SZ)
   while true; do
     sleep {{MONITOR_POLL_SEC}}
     now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
     snapshot=$(gh pr view "$pr" --repo "$repo" --json state,headRefOid -q '.state + " " + .headRefOid' 2>/dev/null) || continue
     state=${snapshot%% *}; current=${snapshot#* }
     if [ "$state" != "OPEN" ]; then echo "PR #$pr $state"; exit 0; fi
     if [ -n "$current" ] && [ "$current" != "$head" ]; then echo "PR #$pr head nuevo ${current:0:7}"; head=$current; fi
     for endpoint in "issues/$pr/comments" "pulls/$pr/comments"; do
       gh api "repos/$repo/$endpoint?since=$since" --jq ".[] | select(.user.login==\"$bot\") | \"PR #$pr comentario de Codex \(.id)\"" 2>/dev/null || true
     done
     current_reviews=$(count_bot_reviews)
     if [ "$current_reviews" -gt "$reviews" ]; then echo "PR #$pr review nueva de Codex"; fi
     reviews=$current_reviews
     current_checks=$(checks_signature)
     if [ -n "$current_checks" ] && [ "$current_checks" != "$checks" ]; then echo "PR #$pr checks $current_checks"; checks=$current_checks; fi
     since=$now
   done
   ```
   Cada línea que emite (head nuevo, comentario o review de Codex, cambio en los checks o PR que dejó de estar `OPEN`) es un evento: corré **una iteración inmediata** de este mismo prompt, sin esperar al cron. Si ya hay una iteración en curso, no lances otra: esa vuelta, o la siguiente, reconcilia el evento. El monitor no evalúa timeouts: los de ack (`{{CODEX_ACK_TIMEOUT_MIN}}`), commit (`{{CODEX_FIX_TTL_MIN}}`), `inFlight` huérfano (`{{INFLIGHT_TTL_MIN}}`) y ronda (`{{REVIEW_ROUND_TIMEOUT_MIN}}`, paso 2-quater), los reintentos de merge y el re-disparo de `@codex review` los resuelve el cron. Si Codex nunca publica la review, el monitor no emite nada y solo el cron hace vencer la ronda.
   - Al vencer (aviso de expiración), rearmalo con el mismo `command` si el PR sigue `OPEN`. Si al empezar una vuelta del cron no está vivo (se perdió el aviso o falló el rearme), rearmalo en ese momento.
   - Cuando el PR deja de estar `OPEN` el script termina solo; si el loop se auto-cancela por otro motivo, detenelo con `TaskStop` (ver «Auto-cancelar»).

(1) Leé `processedCommentIds` desde `.codex-autofix/processed-{{PR}}.json`. Los ids de comentarios (inline/generales) se guardan como número crudo; los ids de review-body se guardan namespaceados como `"review:<id>"` (evita colisión entre espacios de id distintos). `processedCommentIds` representa comentarios cerrados: fixes aplicados y los cerrados como «Sin cambios» (incluidos los bordes rebuscados del paso 3-pre). Leé también `inFlight` (mapa `id -> {label, startedAt}` con el mismo formato de id; si falta, tratalo como `{}`): son los comentarios que YA tienen un subagente trabajando, lanzado en esta vuelta o en una anterior. Las entradas delegadas a Codex llevan además `via: "codex"`, `triggerId` (id del comentario `@codex fix`), `triggerKind` (`inline` o `general`), `baseSha` (head del PR al pedir) y `groupIds` (todos los ids del grupo). Leé también `codexAttempts`, `delegationReplyIds`, `reviewRounds`, `testOnlyRounds`, `testOnlyHeadSha`, `lastReviewedSha`, `reviewRequestedAt`, `reviewTimeoutRetries`, `reviewTimedOut`, `finalMergePending` y `outcomes` (si faltan, `{}`, `[]`, `0`, `0`, `null`, `null`, `null`, `0`, `false`, `false` y `{}`). Modo de fix de esta corrida: `{{FIX_MODE}}`.

(1-bis) NO RELANCES COMENTARIOS CON UN SUBAGENTE TRABAJANDO. Una vuelta puede empezar mientras siguen corriendo subagentes de vueltas anteriores. Antes de armar grupos, reconciliá `inFlight`:
   - Si el subagente de una entrada sigue vivo (lo ves corriendo en tus tareas/agentes en background con ese label), el id queda BLOQUEADO: no lo agrupes, no lo spawnees de nuevo, no reacciones ni respondas. Esperá su resultado; el closeout lo hace el paso (4) cuando vuelva.
   - Si el subagente ya no existe (murió sin devolver resultado, la sesión se reinició) Y pasaron más de `{{INFLIGHT_TTL_MIN}}` min desde `startedAt`, sacá la entrada de `inFlight`: el comentario vuelve a ser elegible en esta vuelta. Si no pasó ese tiempo, dejalo bloqueado por las dudas.
   - Si un comentario nuevo cae en el mismo `path` (o zona) que un grupo en curso, tampoco lo spawnees en paralelo: esperá a que ese grupo termine y tomalo en una vuelta siguiente (evita dos clones pisando el mismo archivo).
   - Entradas con `via: "codex"` (no hay subagente local que mirar; se reconcilian contra GitHub):
     - **Ack**: `gh api repos/{{OWNER}}/{{REPO}}/pulls/comments/<triggerId>/reactions` (inline) o `issues/comments/<triggerId>/reactions` (general) con `select(.content=="eyes" and .user.login=="chatgpt-codex-connector[bot]")`. Sin 👀 pasados `{{CODEX_ACK_TIMEOUT_MIN}}` min desde `startedAt` → pedido no tomado: FALLA de delegación.
     - **Commit de Codex**: `gh api repos/{{OWNER}}/{{REPO}}/pulls/{{PR}}/commits --paginate --jq '[.[] | {sha, date: .commit.committer.date, files_url: .url}]'` y tomá los commits posteriores a `baseSha` con fecha posterior a `startedAt` que NO sean shas reportados por subagentes locales. Para un grupo inline, verificá con `gh api repos/{{OWNER}}/{{REPO}}/commits/<sha> --jq '[.files[].filename]'` que el commit toca el `path` del grupo. Si hay uno que cumple → ÉXITO con ese sha: closeout del paso (4) para todos los `groupIds` (en el resumen, describí el efecto a partir del diff del commit).
     - **Respuestas de Codex**: los comentarios del bot posteriores al pedido en ese hilo (inline con `in_reply_to_id` = primer comentario del grupo) o en el PR (general que no sea el resumen de review `<!-- codex-pull-request-review-summary -->` ni una review con `Codex Review:`) son respuestas a la delegación: agregá sus ids a `delegationReplyIds`. Si Codex respondió y pasaron 5 min sin commit que cumpla (típico cuando no tiene permiso para pushear o solo contestó), es FALLA de delegación.
     - Sin commit pasados `{{CODEX_FIX_TTL_MIN}}` min desde `startedAt` → FALLA de delegación.
     - **FALLA de delegación**: sacá la entrada de `inFlight` y sumá 1 a `codexAttempts[<id>]` de cada id del grupo. En `auto`, el grupo queda elegible y en la próxima armada de grupos va a subagente local. En `codex`, si `codexAttempts < {{CODEX_FIX_MAX_ATTEMPTS}}` se vuelve a pedir; si no, aplicá el paso (5) (reply `⚠️ No pude aplicar` en el hilo, sin reacción, sin marcar) y no lo pidas más en este loop. No borres el comentario `@codex fix`.

(2) Traé comentarios de chatgpt-codex-connector[bot] de las TRES fuentes:
   - inline: `gh api repos/{{OWNER}}/{{REPO}}/pulls/{{PR}}/comments --paginate` (cada uno trae `id`, `path`, `line`, `body` y `pull_request_review_id` = review padre).
   - generales: `gh api repos/{{OWNER}}/{{REPO}}/issues/{{PR}}/comments --paginate`.
   - review-bodies: `gh api repos/{{OWNER}}/{{REPO}}/pulls/{{PR}}/reviews --paginate --jq '[.[] | select(.user.login=="chatgpt-codex-connector[bot]") | {id, node_id, body, state}]'`.
   - Descartá como hallazgos: los inline del bot con `in_reply_to_id` no nulo (los hallazgos de Codex siempre abren el hilo; un reply suyo es respuesta a un `@codex fix`), y cualquier id que esté en `delegationReplyIds`. No los marques en `processedCommentIds`.
   - Descartá también el **resumen de review** de Codex: el comentario general cuyo body contiene `<!-- codex-pull-request-review-summary -->`. Es un único comentario que Codex edita en cada review (tabla de estado y marcador `codex-review-state:v1`), no un hallazgo: no reacciones, no respondas y no lo marques. Solo lo lee el paso (5-bis).
   - Descartá también los **receipts de review**: los comentarios generales del bot cuyo body contiene `<!-- codex-review-receipt:v1 -->` (por ejemplo «Codex Review: Didn't find any major issues» con `**Reviewed commit:**`). Codex los publica al terminar una review pedida con `@codex review`. No son hallazgos: no reacciones, no respondas y no los marques. Cuando la review tiene hallazgos, el mismo receipt va en el body de la review y lo filtra el paso (3b).

(2-bis) RE-DISPARO de un `@codex review` que el bot no leyó. Codex reacciona con 👀 (eyes) sobre el comentario apenas lo recibe; si el ÚLTIMO comentario general del PR es un `@codex review` y NO tiene esa reacción 👀 del bot, el trigger se cayó (Codex nunca lo tomó) → reposteá uno nuevo para que arranque la review.
   - Último comentario general (vienen ascendentes por fecha, `last` = el más nuevo): `LAST=$(gh api repos/{{OWNER}}/{{REPO}}/issues/{{PR}}/comments --paginate --jq 'last // empty')`. Si está vacío, salteá este paso.
   - `LAST_ID=$(printf '%s' "$LAST" | jq -r '.id'); LAST_BODY=$(printf '%s' "$LAST" | jq -r '.body')`.
   - Seguí SOLO si `LAST_BODY` es un trigger de review (matchea `^@codex review`); si no, salteá (el último comentario no es un trigger pendiente).
   - Reacción 👀 del bot sobre ese comentario: `HAS_EYES=$(gh api repos/{{OWNER}}/{{REPO}}/issues/comments/$LAST_ID/reactions --jq '[.[] | select(.content=="eyes" and .user.login=="chatgpt-codex-connector[bot]")] | length')`.
   - Si `HAS_EYES == 0` (sin ojitos del bot): reposteá el trigger → `gh pr comment {{PR}} --repo {{OWNER}}/{{REPO}} --body "@codex review"`. Si `HAS_EYES >= 1`, NO hagas nada: Codex ya lo está procesando.
   - Para no duplicar el trigger: si en ESTA misma vuelta vas a fixear ítems nuevos (vas a postear `@codex review` en el paso (6)), si el «Head avanzado sin review» del paso (6) va a pedir la review del head nuevo, o si vence la ronda (paso 2-quater), salteá el repost acá; ese paso ya re-dispara la review.
   - Este repost no toca `reviewRequestedAt` ni `reviewTimeoutRetries`: el reloj de la ronda sigue corriendo desde el pedido original.

(2-ter) REVIEW INICIAL. Codex suele revisar solo al abrir el PR, pero no siempre: puede tener las reviews automáticas apagadas o tomar una mención de `@codex` en el body del PR como pedido de tarea. Si `reviewRounds` es `0` y el PR no tiene ninguna review de Codex (ni comentario con `codex-review-state:v1`, ni review del bot, ni receipt `codex-review-receipt:v1`), ni ningún comentario general `@codex review`:
   - Si pasaron más de `{{INITIAL_REVIEW_GRACE_MIN}}` min desde `createdAt` del PR (`gh pr view {{PR}} --repo {{OWNER}}/{{REPO}} --json createdAt -q .createdAt`), posteá `gh pr comment {{PR}} --repo {{OWNER}}/{{REPO}} --body "@codex review"` y, en la misma unidad, guardá el head en `lastReviewedSha`, poné `reviewRequestedAt` en ahora y `reviewTimeoutRetries` en `0`. Es la review inicial (ronda 0): no sumes a `reviewRounds`. Desde ahí, el paso (2-bis) la re-dispara si Codex no le pone 👀 y el paso (2-quater) la hace vencer si nunca llega.
   - Si no pasó ese plazo, no hagas nada: la próxima vuelta lo vuelve a evaluar.

(2-quater) TIMEOUT DE RONDA (ver «Timeout de ronda» del skill; se evalúa en CADA vuelta, también en las que no fixean nada).
   - Review automática colgada: si `reviewRequestedAt` es `null`, `reviewRounds` es `0` y el estado `codex-review-state:v1` del PR sigue `running`, arrancá el reloj sin postear nada: `reviewRequestedAt` = `createdAt` del PR y `lastReviewedSha` = `code_review.commit_sha` de ese estado, y persistí el JSON. Así también vence la review que Codex dispara solo al abrir el PR.
   - Salteá el resto del paso si `reviewRequestedAt` es `null` o si Codex ya publicó una review terminada de `lastReviewedSha` (la misma evidencia del «Fin de la última ronda» del paso 6). Si no, calculá los minutos desde `reviewRequestedAt`:
   - Menos de `{{REVIEW_ROUND_TIMEOUT_MIN}}` → no hagas nada: la ronda sigue esperando.
   - Vencida y `reviewTimeoutRetries < {{REVIEW_ROUND_TIMEOUT_RETRIES}}` → `gh pr comment {{PR}} --repo {{OWNER}}/{{REPO}} --body "@codex review"` y, en la misma unidad, `reviewTimeoutRetries += 1`, `reviewRequestedAt` = ahora, `lastReviewedSha` = head actual y persistí el JSON. NO sumes a `reviewRounds`.
   - Vencida y `reviewTimeoutRetries >= {{REVIEW_ROUND_TIMEOUT_RETRIES}}` → NO postees otra review. Con ids en `inFlight`, esperá a que vuelvan (sus closeouts siguen el paso 4). Sin `inFlight`, PushNotification de una línea «PR #{{PR}}: Codex no publicó la review en X min» (X = `{{REVIEW_ROUND_TIMEOUT_MIN}}` × (`{{REVIEW_ROUND_TIMEOUT_RETRIES}}` + 1)), poné `reviewTimedOut: true`, persistí el JSON y auto-cancelá el loop como en el GUARD. El resto del estado queda como está para que relanzar retome la ronda.
   - Una ronda vencida NUNCA lleva al merge: no es review limpia (paso 5-bis) y no habilita el corte por convergencia, el tope de solo tests ni el fin de la última ronda (paso 6), aunque la CI esté verde.

(3) FAN-OUT EN PARALELO (por GRUPO de archivo, con concurrencia según recursos libres).

(3-pre) TRIAGE DE ALCANCE (lo decide el LOOP PRINCIPAL, antes de agrupar). Clasificá cada ítem elegible según la «Regla de alcance y convergencia» del skill: realista, borde razonable, borde rebuscado, preexistente o nit. Leé el badge de severidad de Codex (`P0`–`P3`) del body. Los **rebuscados**, **preexistentes** y **nits no fixeables** NO van a ningún grupo: cerralos directamente con la variante «ℹ️ Sin cambios» de `codex-comment-closeout`, con `**Motivo:**` de una línea (👎, reply, resolver el hilo inline, marcar el id en processedCommentIds y registrar en `outcomes` con `edge-case`, `pre-existing` o `nit-skipped`). Si un hallazgo repite uno ya registrado en `outcomes` (mismo `path`, misma clase de bug) y esas líneas no cambiaron desde entonces, cerralo igual con el mismo motivo, sin spawnear subagente. En el prompt de cada subagente pedí el **diff mínimo** que resuelva el comentario y **todas las apariciones de su clase de bug dentro del diff del PR**, sin ampliar el alcance a código fuera del PR ni a casos de borde vecinos; si el subagente concluye que el fix exige un rediseño, que devuelva «rebuscado» con el motivo en lugar de implementarlo, y cerralo como «Sin cambios».

(3a) ARMÁ LOS GRUPOS DE TRABAJO. Tomá los ítems accionables y elegibles (los que NO están en `processedCommentIds` NI en `inFlight` NI tienen en `outcomes` un `failed` con `terminal: true`; para review-bodies, además, pasá el filtro de accionabilidad de (3b)) y agrupalos así, porque dos fixes sobre el MISMO archivo/zona en clones paralelos se pisan o explotan en el rebase:
   - Los **inline** se agrupan por `path`; si dos inline del mismo `path` tienen `line` solapadas o cercanas, van en el MISMO grupo igual.
   - Cada **general** y cada **review-body accionable** es su propio grupo (no tienen `path`; asumí que pueden tocar cualquier archivo, así que no los mezcles con otros).
   - Un grupo = la unidad que toma UN subagente. Dentro del grupo, el subagente resuelve sus comentarios **secuencialmente en el mismo clone** (un solo push al final). Entre grupos de archivos DISJUNTOS sí hay paralelismo.

(3b) ACCIONABILIDAD DE REVIEW-BODIES (antes de agrupar/spawnear, la decide el LOOP PRINCIPAL). Evaluá si el body trae una **sugerencia accionable real** (un cambio concreto de código). Si es solo un resumen/observación no accionable ("revisé X, ver inline", aprobación, etc.), SALTEALO: no lo metas en ningún grupo, no reacciones, no respondas y NO lo marques como procesado (no ensucia el estado; igual entra en el paso de minimize si corresponde).

(3b-bis) RUTEO SEGÚN `{{FIX_MODE}}` (ver «Modo de fix» del skill). Si `testOnlyHeadSha` es `null`, antes de lanzar o delegar el primer grupo guardá en `testOnlyHeadSha` el head actual del PR (el que revisó Codex, todavía sin fixes de esta ronda) y persistí el JSON: así la primera clasificación de «Ronda de solo tests» no mezcla los commits de producto ya revisados. Por cada grupo:
   - `local` → cola local (pasos 3c y 3d).
   - `codex` → cola Codex, salvo que algún id del grupo ya agotó `{{CODEX_FIX_MAX_ATTEMPTS}}` (queda pendiente, no se rutea).
   - `auto` → cola Codex si ningún id del grupo tiene `codexAttempts >= 1`; si no, cola local.
   Cola Codex, hasta `{{CODEX_MAX_PARALLEL}}` pedidos vivos (contá las entradas `via: "codex"` de `inFlight`); el resto espera a la próxima vuelta:
   - Armá el texto según «Reglas del pedido a Codex» (sin la palabra `review`, diff mínimo, rama {{BRANCH}}; links a los otros comentarios del grupo o al comentario/resumen original).
   - INLINE → reply en el hilo del primer comentario del grupo: `TRIGGER_ID=$(gh api -X POST repos/{{OWNER}}/{{REPO}}/pulls/{{PR}}/comments/<id>/replies -f body="<pedido>" --jq .id)`.
   - GENERAL / REVIEW-BODY → comentario general: `TRIGGER_ID=$(gh api -X POST repos/{{OWNER}}/{{REPO}}/issues/{{PR}}/comments -f body="<pedido>" --jq .id)`.
   - En la misma unidad, registrá en `inFlight` cada id del grupo con `{label, startedAt, via: "codex", triggerId: TRIGGER_ID, triggerKind, baseSha: <headRefOid actual>, groupIds}`, agregá `TRIGGER_ID` a `delegationReplyIds` y persistí el JSON. El resultado se reconcilia en el paso (1-bis) de las vueltas siguientes.

(3c) CALCULÁ CUÁNTOS SUBAGENTES CABEN (`SLOTS`) según CPU, RAM y disco libres AHORA. Solo aplica a la cola local: los pedidos a Codex no consumen recursos locales. Los subagentes que ya corren están incluidos en la medición, así que no los restes aparte.
   - Medí (usá el bloque de tu plataforma; disco = unidad del tempdir donde se crean los clones):
     - Windows (PowerShell):
       `$cores = (Get-CimInstance Win32_Processor | Measure-Object NumberOfLogicalProcessors -Sum).Sum; $loadPct = (Get-CimInstance Win32_Processor | Measure-Object LoadPercentage -Average).Average; $busyCores = $cores * $loadPct / 100; $freeRamGb = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB; $freeDiskGb = (Get-PSDrive ((Split-Path $env:TEMP -Qualifier).TrimEnd(':'))).Free / 1GB`
     - Linux: `cores=$(nproc); busy_cores=$(cut -d' ' -f1 /proc/loadavg); free_ram_gb=$(awk '/MemAvailable/{print $(NF-1)/1048576}' /proc/meminfo); free_disk_gb=$(df -Pk "${TMPDIR:-/tmp}" | awk 'NR==2{print $(NF-2)/1048576}')`
     - macOS: `cores=$(sysctl -n hw.ncpu); busy_cores=$(sysctl -n vm.loadavg | awk '{print $(NF-3)}'); free_ram_gb=$(vm_stat | awk -v ps=$(pagesize) '/Pages (free|inactive|speculative)/{gsub(/\./,"",$NF); sum+=$NF} END{print sum*ps/1073741824}'); free_disk_gb=$(df -Pk "${TMPDIR:-/tmp}" | awk 'NR==2{print $(NF-2)/1048576}')`
   - Calculá (redondeando hacia abajo):
     - `cpu_slots  = floor((cores - busy_cores) / {{CPU_PER_AGENT}})`
     - `ram_slots  = floor((free_ram_gb - {{RAM_RESERVE_GB}}) / {{RAM_PER_AGENT_GB}})`
     - `disk_slots = floor((free_disk_gb - {{DISK_RESERVE_GB}}) / {{DISK_PER_AGENT_GB}})`
     - `SLOTS = max(0, min(cpu_slots, ram_slots, disk_slots, cantidad_de_grupos_pendientes))`
   - Si `SLOTS == 0` y NO hay ningún subagente en curso, usá `SLOTS = 1` para garantizar progreso. Si `SLOTS == 0` y SÍ hay subagentes en curso, no lances nada nuevo: los grupos pendientes esperan a que se liberen recursos.
   - Si la medición falla, usá `SLOTS = 1` y mencioná el fallo en la PushNotification de la vuelta.
   - Reportá en una línea del resumen de la vuelta qué recurso limitó (`cpu`, `ram` o `disk`) y el valor de `SLOTS`.

(3d) SPAWNEÁ HASTA `SLOTS` SUBAGENTES a la vez (herramienta `Agent`/`Task` en background, varios tool-uses en un mismo mensaje). **Antes de lanzar cada uno, registrá en `inFlight` todos los comment ids de su grupo** (`{label, startedAt: <ISO-8601 UTC>}`) y persistí el JSON: así la próxima vuelta, aunque este subagente siga trabajando, no vuelve a lanzar esos comentarios. Cuando un grupo termina, recalculá `SLOTS` (paso 3c) y arrancá los siguientes que quepan, hasta agotar la cola. **Etiquetá cada subagente con los comment ids de su grupo** (label), para mapear sin ambigüedad resultado→comentarios al cerrar y para reconocerlo como vivo en el paso (1-bis). Cada subagente:
   - Recibe en su prompt el **path absoluto al `SKILL.md` de `fix-in-ephemeral-clone`** como fuente de verdad del flujo de aislamiento (que lo lea), además de intentar invocarla por nombre vía la herramienta `Skill` (`/fix-in-ephemeral-clone`). NO reimplementa el clone/push a mano.
   - Recibe como "issue(s)" el contexto de los comentarios de su grupo: cuerpo, `path` y `line` (inline) o solo el body (general/review-body), y la rama objetivo {{BRANCH}}. No envíes un URL `#discussion_r...` o `#pullrequestreview-...` como target: este loop ya posee preflight y closeout agrupado; esos links pueden viajar solo como metadata no accionable.
   - Vía esa skill, hace el clone efímero depth-1, copia `.env*`, instala/linkea deps según plataforma, aplica el/los fix(es) de su grupo, valida, rebasea sobre el último remoto y pushea a {{BRANCH}}, y limpia el clone.

   **Push concurrente**: como varios subagentes pushean a la MISMA rama, ante un rechazo por non-fast-forward el subagente NO repushea a ciegas: corre un ciclo completo de re-integración —re-fetch → rebase sobre el nuevo remoto → resolver conflictos → revalidar que TANTO el fix recién hecho COMO los cambios que integró de los otros subagentes (fixes de otros comentarios que ya cayeron a la rama) siguen pasando sobre la nueva base → recién ahí pushea; si vuelve a rebotar, repite el ciclo entero hasta un máximo de 3 ciclos; al agotarlos devuelve fallo `CONCURRENT_PUSH_RETRY_EXHAUSTED`— (esa lógica y ese límite viven en `fix-in-ephemeral-clone`). Cada subagente DEVUELVE el sha COMPLETO del commit pusheado en éxito (uno por grupo), o un fallo explícito + el path del clone que quedó para inspección. Recogé los resultados; por cada comentario fixeado guardá su sha (para el closeout) y sumá 1 al contador de ítems fixeados esta vuelta.

(4) CLOSEOUT en ÉXITO (push hecho). Hacelo por cada comentario cuyo subagente volvió con éxito, usando el sha que ese subagente reportó (no esperes a que terminen todos: a medida que vuelven, cerrás), y por cada comentario cuyo pedido `@codex fix` se verificó como ÉXITO en el paso (1-bis), usando el sha del commit de Codex (cuenta como ítem fixeado de esta vuelta). El closeout es idéntico en ambos caminos: misma plantilla, mismo reply en el hilo del comentario original (no en el pedido `@codex fix`), misma reacción y resolución. Las acciones de closeout en GitHub (reacciones, replies, resolver hilos) son independientes por comentario; el ÚNICO recurso compartido es `.codex-autofix/processed-{{PR}}.json`, así que el loop principal es el único escritor y serializa esas escrituras (paso d) para no corromper el JSON cuando varios subagentes terminan casi a la vez. Definí el link al commit: COMMIT_URL=https://github.com/{{OWNER}}/{{REPO}}/commit/<sha>
   a. Reacción 👍:
      - INLINE: `gh api -X POST repos/{{OWNER}}/{{REPO}}/pulls/comments/<id>/reactions -f content=+1`.
      - GENERAL: `gh api -X POST repos/{{OWNER}}/{{REPO}}/issues/comments/<id>/reactions -f content=+1`.
      - REVIEW-BODY (no hay endpoint REST de reactions para reviews; va por GraphQL sobre el `node_id` de la review): `gh api graphql -f query='mutation($id:ID!){addReaction(input:{subjectId:$id,content:THUMBS_UP}){reaction{content}}}' -F id="<review_node_id>"`.
   b. Reply con la **plantilla de cierre** de `codex-comment-closeout` (los comandos de abajo la aplican; si cambia la plantilla, manda esa skill). Definí `<resumen>` = UNA línea de qué cambió y su efecto, y usá el sha corto de 7 chars como texto del link:
      - INLINE: `gh api -X POST repos/{{OWNER}}/{{REPO}}/pulls/{{PR}}/comments/<id>/replies -f body="$(printf '✅ **Resuelto** en [`%s`](%s).\n\n**Qué cambió:** %s\n\n<sub>🤖 Fix automático en respuesta a este comentario de Codex.</sub>' "<sha_corto>" "<COMMIT_URL>" "<resumen>")"`
      - GENERAL: `gh pr comment {{PR}} --repo {{OWNER}}/{{REPO}} --body "$(printf '✅ **Resuelto** en [`%s`](%s) (en respuesta a tu comentario).\n\n**Qué cambió:** %s\n\n<sub>🤖 Fix automático de Codex.</sub>' "<sha_corto>" "<COMMIT_URL>" "<resumen>")"`
      - REVIEW-BODY → **quote reply** (comentario general que CITA el body original). Construí la cita prefijando cada línea del body con `> ` (recortá a la parte saliente si el body es largo); guardala en QUOTED: `QUOTED=$(printf '%s\n' "<body_review>" | sed 's/^/> /')`. Después: `gh pr comment {{PR}} --repo {{OWNER}}/{{REPO}} --body "$(printf '%s\n\n✅ **Resuelto** en [`%s`](%s) (en respuesta a esta review).\n\n**Qué cambió:** %s\n\n<sub>🤖 Fix automático en respuesta a esta review de Codex.</sub>' "$QUOTED" "<sha_corto>" "<COMMIT_URL>" "<resumen>")"`
   c. SOLO INLINE — resolver el hilo vía GraphQL:
      THREAD_ID=$(gh api graphql -f query='query($owner:String!,$repo:String!,$pr:Int!){repository(owner:$owner,name:$repo){pullRequest(number:$pr){reviewThreads(first:100){nodes{id comments(first:100){nodes{databaseId}}}}}}}' -F owner={{OWNER}} -F repo={{REPO}} -F pr={{PR}} --jq "[.data.repository.pullRequest.reviewThreads.nodes[] | select(any(.comments.nodes[]; .databaseId == <id>)) | .id] | first // empty")
      si THREAD_ID no vacío: gh api graphql -f query='mutation($threadId:ID!){resolveReviewThread(input:{threadId:$threadId}){thread{isResolved}}}' -F threadId="$THREAD_ID"
   d. Agregá el id a processedCommentIds en .codex-autofix/processed-{{PR}}.json: número crudo para inline/generales; `"review:<id>"` para review-bodies. En la misma escritura, sacá el id de `inFlight` y registrá en `outcomes` `{result: "fixed", severity, round: reviewRounds, path, sha}`. **Invariante de idempotencia**: por cada comentario hacé el reply de cierre Y la escritura del id como una sola unidad apenas vuelve su subagente (no batchees al final). Si el loop se cae entre el push y esta escritura, la próxima vuelta re-fixearía el comentario (reply duplicado): cerrar+marcar de inmediato achica esa ventana al mínimo.

(4-bis) MINIMIZE de la review cuando esté COMPLETAMENTE resuelta (estado RESOLVED → queda oculta/colapsada). Para CADA review de Codex que tenga al menos 1 comment inline asociado y que NO esté ya minimizada, chequeá si está fully-resolved:
   - el review-body está cubierto: era no accionable (nada que fixear) O su id `"review:<id>"` ya está en processedCommentIds, **y**
   - TODOS sus threads inline (los que cuelgan de esa review) están `isResolved`.
   Detección en una query (devuelve `true` solo si hay ≥1 thread de esa review y todos resueltos):
     `gh api graphql -f query='query($owner:String!,$repo:String!,$pr:Int!){repository(owner:$owner,name:$repo){pullRequest(number:$pr){reviewThreads(first:100){nodes{isResolved comments(first:1){nodes{pullRequestReview{databaseId}}}}}}}}' -F owner={{OWNER}} -F repo={{REPO}} -F pr={{PR}} --jq '[.data.repository.pullRequest.reviewThreads.nodes[] | select(.comments.nodes[0].pullRequestReview.databaseId == <review_db_id>) | .isResolved] as $r | ($r|length>0) and ($r|all)'`
   Si da `true` (o si la review no tiene inline pero su body accionable ya fue fixeado y resuelto): minimizá la review:
     `gh api graphql -f query='mutation($id:ID!){minimizeComment(input:{subjectId:$id,classifier:RESOLVED}){minimizedComment{isMinimized minimizedReason}}}' -F id="<review_node_id>"`
   NO minimices reviews donde el loop no resolvió nada (sin inline resueltos por el loop y body no accionable): dejalas como están.

(5) Si FALLA (no se pudo aplicar el fix por una falla del loop/agente o de la delegación a Codex que ya no tiene reintento según `{{FIX_MODE}}`, no porque la sugerencia sea inválida; una falla de delegación en `auto` NO llega acá, cae a subagente local): NO marques el id, NO resuelvas, y NO cuentes ese comentario como fixeado. SÍ sacá sus ids de `inFlight` (el subagente ya terminó), para que la próxima vuelta pueda reintentarlo, y registrá en `outcomes` `{result: "failed", reason}` (se sobrescribe si un reintento posterior tiene éxito). Si `reviewRounds >= {{MAX_REVIEW_ROUNDS}}` (última ronda), la falla es terminal: registrá `{result: "failed", reason, terminal: true}` y no lo reintentes, así el paso (6) puede llegar al merge final. NO reacciones 👎 (content=-1): el 👎 es la señal de "sugerencia incorrecta/no útil" que Codex interpreta sobre su comentario, y acá el problema es el loop, no la sugerencia. No agregues reacción final; opcionalmente, dejá un reply con el motivo/link al error. Reservá el 👎 solo para cuando evaluaste la sugerencia y concluiste que no requería cambios.
   - **Clones huérfanos**: en fallo, `fix-in-ephemeral-clone` conserva el clone para inspección y reporta su path. Recolectá esos paths de los subagentes que fallaron y, al cerrar la vuelta, listalos en UNA línea de PushNotification (p. ej. "PR #{{PR}}: 2 fixes fallaron, clones en <paths>"). Si no los vas a inspeccionar, podés limpiarlos vos (`rm -rf <path>`) DESPUÉS de loguear el path, nunca antes. Con varios fallos en paralelo el tempdir se llena: no dejes los paths sin reportar.

(5-bis) TERMINACIÓN POR REVIEW LIMPIA (mergear + cortar). Chequealo cuando NO quedó ningún ítem accionable de Codex sin resolver esta vuelta (ni nuevos sin procesar, ni ids en `inFlight`, ni fallas pendientes del paso 5). Obtené el commit de la ÚLTIMA review limpia de Codex (REVIEWED) con estos dos formatos, en orden:
   - **Formato actual (resumen con estado JSON).** Codex mantiene un único comentario general con `<!-- codex-pull-request-review-summary -->` y un marcador `<!-- codex-review-state:v1 {...} -->`. Ese JSON trae `code_review` y `security_review`, cada uno con `commit_sha`, `status`, `has_any_findings` y `has_unresolved_findings`. Cuando la security review no corrió, sus campos vienen en `null`. Es limpia solo si `code_review.status == "completed"`, los dos flags de `code_review` son `false`, y `security_review` no corrió o también terminó `completed` sin hallazgos. La regex usa `[{]`/`[}]` en vez de llaves escapadas para que el comando sobreviva al quoting de cualquier shell:
     HAS_STATE=$(gh api repos/{{OWNER}}/{{REPO}}/issues/{{PR}}/comments --paginate --jq '[.[] | select(.user.login=="chatgpt-codex-connector[bot]") | select(.body | contains("codex-review-state:v1"))] | length' | jq -s 'add // 0')
     REVIEWED=$(gh api repos/{{OWNER}}/{{REPO}}/issues/{{PR}}/comments --paginate --jq '[.[] | select(.user.login=="chatgpt-codex-connector[bot]") | .body | capture("codex-review-state:v1 (?<state>[{].*[}]) -->")? | .state | fromjson?] | last // empty | select(.code_review.status=="completed" and .code_review.has_any_findings==false and .code_review.has_unresolved_findings==false and (.security_review.status==null or (.security_review.status=="completed" and .security_review.has_any_findings==false and .security_review.has_unresolved_findings==false))) | .code_review.commit_sha' | tail -1)
     Si hay estado pero no está limpio (por ejemplo, `has_any_findings: true` con hallazgos ya cerrados), esto NO es review limpia. Esa terminación es el «Corte por convergencia». Lo mismo si la review sigue `running`: con `HAS_STATE >= 1` y REVIEWED vacío no hay review limpia, NO corras el fallback y seguí al paso (6).
   - **Formato viejo (fallback)**, solo si `HAS_STATE` es `0` (ningún comentario del bot con el marcador `codex-review-state:v1`): el último comentario general del bot con el texto de review limpia, y su `**Reviewed commit:**`:
     CLEAN=$(gh api repos/{{OWNER}}/{{REPO}}/issues/{{PR}}/comments --paginate --jq '[.[] | select(.user.login=="chatgpt-codex-connector[bot]") | select(.body | test("Codex Review:.*([Dd]idn.t find any|[Nn]o (major )?issues|[Ff]ound no issues)"))] | last // empty')
     REVIEWED=$(printf '%s' "$CLEAN" | jq -r '.body' | grep -oiE 'Reviewed commit:\*\* `[0-9a-f]{7,}`' | grep -oiE '[0-9a-f]{7,}' | head -1)
     Mantené los dos formatos. Codex sigue publicando el texto viejo como receipt (`<!-- codex-review-receipt:v1 -->`) cuando la review limpia se pide con `@codex review`. En cambio, en la review limpia que se dispara al abrir el PR solo deja el resumen JSON y el 👍. Con `HAS_STATE >= 1`, el resumen JSON manda y el receipt se ignora, porque puede ser de una review anterior del mismo commit.
   Si REVIEWED sigue vacío con los dos formatos -> no hay review limpia reconocible: NO mergees, seguí al paso (6). No infieras la review limpia a mano desde la tabla del resumen ni desde la reacción 👍 del bot. Si no:
   HEAD=$(gh pr view {{PR}} --repo {{OWNER}}/{{REPO}} --json headRefOid -q .headRefOid)
   Solo continuá si REVIEWED es prefijo de HEAD (la review limpia corresponde al head actual; si no coincide, hay commits posteriores sin re-revisar -> NO mergees, seguí al paso 6 para disparar/esperar la nueva review).
   **GATE DE CI (obligatorio antes de CUALQUIER merge, también en el corte por convergencia).** Una review limpia de Codex no prueba que la CI pase, y un repo sin branch protection deja mergear con checks en rojo. Leé los checks del head: `gh pr checks {{PR}} --repo {{OWNER}}/{{REPO}}` (exit 0 = todos verdes; exit 8 = pendientes; otro = alguno falló).
   - Pendientes -> NO mergees; dejá el loop vivo y reintentá en la próxima vuelta.
   - Alguno falló -> NO mergees. Tratá el fallo como un hallazgo realista más: en `codex`/`auto`, delegalo primero con un comentario general `@codex fix las fallas de CI del run <run_url> con el diff mínimo` (registrado en `inFlight` con id `"ci:<run_id>"` y `via: "codex"`, mismo reconcile del paso 1-bis); en `local`, o si esa delegación falla en `auto`, leé el log (`gh run view <run_id> --repo {{OWNER}}/{{REPO}} --log-failed`), lanzá un subagente con `fix-in-ephemeral-clone` y el diff mínimo (registrado en `inFlight` con id `"ci:<run_id>"`), y cuando pushee, posteá `@codex review` como en el paso 6, salvo que `finalMergePending` sea `true`: ahí no se pide review y la vuelta siguiente vuelve a pasar el gate y reintenta el merge final. Mandá una PushNotification de una línea con el check que falló (una sola vez por run).
   - Sin checks configurados -> seguí, pero mencionalo en la PushNotification del merge.
   **SIN ESPERA DE REVISIÓN HUMANA.** No frenes el merge por los archivos que toca el PR ni por el tamaño del diff, y no esperes la aprobación de una persona.
   Solo con todos los checks verdes: MERGEÁ el PR (estrategia squash, borrando la rama; ajustá si tu repo usa otra): `gh pr merge {{PR}} --repo {{OWNER}}/{{REPO}} --squash --delete-branch`.
   - Si el merge tiene ÉXITO -> auto-cancelá el loop (mismo procedimiento del guard: CronList, identificá el job de ESTE loop por cron `{{CRON}}` y PR #{{PR}}, CronDelete por id, PushNotification de una línea avisando "PR #{{PR}} mergeado tras review limpia de Codex") y terminá. NO postees `@codex review`.
   - Si el merge FALLA (checks pendientes, no-mergeable, conflicto, branch protection): NO cortes el loop. PushNotification de una línea con el motivo (una sola vez) y dejá el loop vivo para reintentar en la próxima vuelta. No es trabajo del loop resolver conflictos de merge.

(6) AL FINAL:
   - **Merge final pendiente (en CADA vuelta, antes de lo demás)**: si `finalMergePending` es `true` y no quedan ids en `inFlight`, aunque esta vuelta no hayas fixeado nada, NO postees `@codex review`. Pasá el GATE DE CI del paso 5-bis sobre el head actual y, con todos los checks verdes, mergeá sin preguntar: `gh pr merge {{PR}} --repo {{OWNER}}/{{REPO}} --squash --delete-branch --match-head-commit <head>`. Antes del gate, corré el chequeo de «Commits ajenos con el tope agotado» del «Head avanzado sin review». Si sale, auto-cancelá el loop con la PushNotification del «Tope de rondas» (con los hallazgos `failed` listados) y terminá. Si quedan checks pendientes o el merge falla, dejá el loop vivo para reintentar, avisando el motivo una sola vez. Con checks en rojo, aplicá el manejo de CI fallida del gate, sin review. Mientras `finalMergePending` sea `true`, saltá los demás puntos de este paso.
   - **Tope de solo tests persistido (en CADA vuelta, antes de lo demás)**: si `testOnlyRounds >= {{MAX_TEST_ONLY_ROUNDS}}` y no quedan pendientes (ni ids en `inFlight`), aunque esta vuelta no hayas fixeado nada: si el head actual difiere de `testOnlyHeadSha`, clasificá el rango nuevo como en «Ronda de solo tests» (si entró algo fuera de los tests, `testOnlyRounds` vuelve a `0` y el head nuevo ya no coincide con la última review limpia: si esta vuelta fixeó algo (contador >= 1), seguí con el resto del paso; si no, NO apliques la regla de contador == 0: con `reviewRounds < {{MAX_REVIEW_ROUNDS}}` posteá `@codex review` como abajo, sumando 1 a `reviewRounds` y guardando el head en `lastReviewedSha` en la misma unidad, y si ya se agotó aplicá el «Tope de rondas»). Si el tope sigue alcanzado, NO postees `@codex review`: aplicá el «Tope de rondas de solo tests» (GATE DE CI del paso 5-bis, merge con squash atado al head clasificado y auto-cancelar). Mergeá con `gh pr merge {{PR}} --repo {{OWNER}}/{{REPO}} --squash --delete-branch --match-head-commit <testOnlyHeadSha>`, para que un push concurrente posterior a la clasificación haga fallar el merge en vez de mergear un commit sin clasificar, revisar ni pasar CI. Con checks pendientes, o si `gh pr merge` falla (por ejemplo porque el head ya no coincide), dejá el loop vivo y reintentá en la próxima vuelta, sin postear review: si el head cambió, la próxima vuelta lo reclasifica. Con checks en rojo no reintentes pasivamente: aplicá el manejo de CI fallida del GATE DE CI del paso 5-bis (delegar a Codex o lanzar el subagente con `fix-in-ephemeral-clone`); ese fix es un commit nuevo que se clasifica como cualquier otro, y si toca algo fuera de los tests vuelve `testOnlyRounds` a `0`.
   - **Fin de la última ronda (en CADA vuelta, aunque esta vuelta no haya fixeado nada)**: si `reviewRounds >= {{MAX_REVIEW_ROUNDS}}`, la review de Codex de `lastReviewedSha` ya terminó, no quedan ids en `inFlight` y todo hallazgo de esa review está cerrado o es `failed` con `terminal: true`, entonces esa fue la última ronda: NO postees otra review. Corré el chequeo de «Commits ajenos con el tope agotado» del punto siguiente y, si no frena, poné `finalMergePending: true`, persistí el JSON y aplicá en esta misma vuelta el «Merge final pendiente» de arriba (GATE DE CI y merge sin preguntar). Es el «Tope de rondas» del skill. Si quedan hallazgos sin intentar, esta vuelta los fixea primero. Qué cuenta como review terminada: con `HAS_STATE >= 1` (paso 5-bis) manda el último estado `codex-review-state:v1`, que tiene que tener `code_review.commit_sha` = `lastReviewedSha` y `code_review.status == "completed"`, y además `security_review` sin correr (`status` `null`) o también `completed`. Mientras ese estado siga `running`, o apunte a otro commit, la ronda no terminó, aunque haya una review o un receipt viejos del mismo commit. Solo con `HAS_STATE == 0` vale como evidencia una review o un receipt del bot cuyo `**Reviewed commit:**` sea prefijo de `lastReviewedSha`.
   - **Head avanzado sin review (en CADA vuelta, aunque esta vuelta no haya fixeado nada)**: el head puede avanzar por un commit ajeno al loop (por ejemplo, un merge de la rama base) después de una review terminada; el paso (5-bis) no mergea porque esa review ya no es del head, y sin este punto nadie pide la del head nuevo. Llamá REVISADO a `lastReviewedSha` (si es `null`, al commit de la última review terminada, con la evidencia del punto anterior).
     - **Pedido del head nuevo**: si esta vuelta no fixeó nada (contador == 0; con contador >= 1 el pedido de abajo ya cubre el head nuevo), `finalMergePending` es `false`, el «Tope de solo tests persistido» no actuó en esta vuelta (tiene su propio reset con review), no quedan pendientes (ni ids en `inFlight`), la review de REVISADO ya terminó y el head actual no es REVISADO: si el último estado `codex-review-state:v1` tiene `code_review.commit_sha` = head y `status` `running` (Codex ya revisa ese head, por ejemplo por un `@codex review` manual), NO postees otro: adoptá esa review como la ronda del head con la unidad de estado de abajo. La fecha del commit no sirve como evidencia, porque un commit creado antes de un pedido puede pushearse después. Si no, con `reviewRounds < {{MAX_REVIEW_ROUNDS}}`, posteá `@codex review` y aplicá la unidad de estado de abajo (`reviewRounds += 1`, `lastReviewedSha` = head, `reviewRequestedAt` = ahora, `reviewTimeoutRetries` = `0`). Con el tope agotado, aplicá el chequeo siguiente.
     - **Commits ajenos con el tope agotado** (lo corren también el «Fin de la última ronda» y el «Merge final pendiente», aunque el contador sea >= 1): si `reviewRounds >= {{MAX_REVIEW_ROUNDS}}` y el head no es REVISADO, listá los commits de `REVISADO...head` como en «Ronda de solo tests». Si alguno no figura con su `sha` en `outcomes` (los fixes del loop, también los de CI del paso 5-bis, que se tratan como un hallazgo más) o la lista no está completa, hay commits sin revisar: NO postees review ni mergees (los fixes de la última ronda pueden mergearse sin review; un commit ajeno, no). Mandá una PushNotification de una línea («PR #{{PR}}: el head avanzó con commits ajenos después de la última ronda (R/R); no se mergea sin review»), poné `finalMergePending: false` (así un relanzamiento con un tope mayor no mergea el head sin revisar desde el «Merge final pendiente»), persistí el JSON y auto-cancelá el loop como en el GUARD. Relanzarlo con un `{{MAX_REVIEW_ROUNDS}}` mayor pide la review del head. Si todos son fixes del loop, seguí con el «Fin de la última ronda».
   Si en esta vuelta fixeaste con éxito al menos 1 ítem nuevo (inline, general o review-body, por subagente local o por commit de Codex verificado; contador >= 1) y ya no quedan pendientes (ni ids en `inFlight`):
   - **Ronda de solo tests**: clasificá TODOS los commits que entraron desde la última clasificación, no solo los de `outcomes`, para que un commit ajeno al loop también cuente. Tomá como inicio `testOnlyHeadSha` (lo inicializa el paso (3b-bis) antes de los primeros fixes; si aun así es `null`, por un estado viejo, usá `lastReviewedSha` y, si también es `null`, la base del PR: `gh pr view {{PR}} --repo {{OWNER}}/{{REPO}} --json baseRefOid -q .baseRefOid`) y como fin el head actual; listá los commits del rango con `gh api 'repos/{{OWNER}}/{{REPO}}/compare/<inicio>...<head>?per_page=100' --paginate --jq '.commits[].sha'` (con `per_page`, `--paginate` recorre todas las páginas; si la cantidad listada no coincide con `.total_commits` del compare, no hay lista completa) y los archivos de cada uno con `gh api repos/{{OWNER}}/{{REPO}}/commits/<sha> --paginate --jq '.files[] | .filename, (.previous_filename // empty)'` (en un rename cuentan el path de origen y el de destino). Si TODOS matchean `{{TEST_PATH_PATTERNS}}` (`grep -Ev '<patrón>'` no devuelve nada), sumá 1 a `testOnlyRounds`; si alguno no matchea, o si algún listado falla o vuelve vacío (no hay lista completa), poné `testOnlyRounds` en `0`. Guardá el head clasificado en `testOnlyHeadSha` y persistí el JSON en la misma unidad. Si `testOnlyRounds >= {{MAX_TEST_ONLY_ROUNDS}}`, NO postees otra review: aplicá el «Tope de rondas de solo tests» del skill (GATE DE CI del paso 5-bis, merge con squash y auto-cancelar) y terminá; antes del merge, si el head avanzó desde `testOnlyHeadSha`, reclasificá ese rango y no mergees si entró algo fuera de los tests. Mergeá con `--match-head-commit <testOnlyHeadSha>` y manejá checks pendientes, en rojo o un merge fallido como en el «Tope de solo tests persistido». Este chequeo va antes que el tope general.
   - **Tope de rondas**: si `reviewRounds >= {{MAX_REVIEW_ROUNDS}}`, aplicá el «Fin de la última ronda» de arriba en vez de postear otra review.
   - Si no, posteá UN único comentario general con el trigger exacto `@codex review`, sin texto adicional y en todas las rondas: `gh pr comment {{PR}} --repo {{OWNER}}/{{REPO}} --body "@codex review"`. No uses `@codex review for …` ni otras instrucciones para enfocar la review en el delta: Codex las ignora y revisa el PR completo en el head actual. Los hallazgos repetidos los cierra el registro de `outcomes` (paso 3-pre), no el texto del pedido.
   - En la misma unidad, sumá 1 a `reviewRounds`, guardá el head actual en `lastReviewedSha`, poné `reviewRequestedAt` en ahora (ISO-8601 UTC) y `reviewTimeoutRetries` en `0`, y persistí el JSON. Vale para todo `@codex review` de ronda nueva, también el del reset del «Tope de solo tests persistido» y el que sigue a un fix de CI (paso 5-bis): cada ronda arranca su propio reloj (paso 2-quater).
   Si NO fixeaste nada nuevo esta vuelta (contador == 0), NO postees nada (evitá spam), salvo la review que pide el reset del «Tope de solo tests persistido» o el «Head avanzado sin review». Si los únicos cierres de la vuelta fueron «Sin cambios» y el head sigue siendo REVISADO (si avanzó, manda el «Head avanzado sin review»), aplicá el «Corte por convergencia» de la «Regla de alcance y convergencia»: sin `@codex review`, mergeá el PR (pasando antes el GATE DE CI del paso 5-bis) y auto-cancelá el loop.

(6-bis) RESUMEN DE LA VUELTA: en la PushNotification de cierre del loop (merge, tope o PR cerrado) incluí una línea con las rondas usadas (`reviewRounds`/`{{MAX_REVIEW_ROUNDS}}`), las rondas seguidas de solo tests (`testOnlyRounds`/`{{MAX_TEST_ONLY_ROUNDS}}`) y el conteo de `outcomes` por resultado (por ejemplo «3 fixed, 2 edge-case, 1 pre-existing»). Esa línea mide el ruido de Codex y alimenta las evals del reviewer.

(7) SIEMPRE que postees `@codex review`, asegurá que el loop siga vivo SIN que el usuario lo pida: si el cron del loop (`{{CRON}}`, este PR) fue cancelado o pausado, relanzalo (mismo prompt parametrizado) y corré una iteración; si el `Monitor` del PR (paso 0) no está vivo, rearmalo. `@codex review` dispara comentarios nuevos; el loop debe quedar escuchando para auto-procesarlos. Nunca dejes el loop cancelado justo después de disparar una review.
```

## Plantilla de comentario de cierre

Vive en [`codex-comment-closeout`](../codex-comment-closeout/SKILL.md), junto con su
regla de paridad con el step «Cerrar comentario» del Action
`.github/workflows/codex-autofix.yml`.

## Notas

- **Fan-out por grupo de archivo, con cap de concurrencia**: la unidad de trabajo
  no es el comentario suelto sino el GRUPO —inline del mismo `path` (o `line`
  cercanas) juntos; cada general/review-body es su propio grupo—. Un subagente por
  grupo; dentro del grupo resuelve secuencial en el mismo clone (un push). Así dos
  fixes sobre el mismo archivo no se pisan ni chocan en el rebase. La cantidad
  de subagentes simultáneos se calcula en cada vuelta (y al liberarse cada slot)
  como el mínimo entre lo que permiten los cores libres, la RAM disponible y el
  disco libre del tempdir, descontando una reserva (cada subagente es clone +
  install + tests). Cada subagente lleva como label los comment ids de su grupo, y
  recibe en el prompt el path al `SKILL.md` de `fix-in-ephemeral-clone` como
  fuente de verdad (además de invocarla por nombre).
- **Push con re-integración (clones aislados)**: el cómputo del fix está aislado
  por clone; el único punto compartido es el push a la rama del PR. Ante non-fast-forward,
  cada subagente NO repushea a ciegas: corre un ciclo completo de re-integración
  —fetch → rebase → resolver conflictos → revalidar que tanto el fix propio como
  los cambios integrados de los otros subagentes siguen pasando → push— y lo
  repite hasta el tope de ciclos de `fix-in-ephemeral-clone` (al agotarlo
  reporta `CONCURRENT_PUSH_RETRY_EXHAUSTED`). Eso evita el clobber y garantiza que ni el fix propio ni los
  fixes de los demás quedaron rotos al combinarse, sin perder el paralelismo del
  trabajo pesado. El closeout (reacciones, replies,
  resolver hilos) corre por comentario a medida que vuelve cada subagente; la
  escritura de `processed-<PR>.json` la serializa el loop principal (único
  escritor).
- **Sin relanzar trabajo en curso**: como el loop dispara cada `{{INTERVAL}}` y
  un subagente puede tardar más, `inFlight` marca los comentarios con un
  subagente trabajando. Se registran antes de spawnear y se liberan al volver
  (éxito o fallo); una vuelta nueva los saltea. Las entradas sin subagente vivo
  por más de `{{INFLIGHT_TTL_MIN}}` min se liberan para no bloquear para siempre.
- **Estado por PR**: un archivo `processed-<PR>.json` por cada PR en seguimiento;
  así un mismo loop o varios loops no reprocesan lo ya hecho. `processedCommentIds`
  contiene únicamente fixes aplicados/cerrados. Los review-bodies se guardan
  namespaceados (`"review:<id>"`) para no colisionar con ids de comentarios
  inline/generales (espacios de id distintos).
- **Tres fuentes**: inline (`pulls/{pr}/comments`), generales
  (`issues/{pr}/comments`) y review-bodies (`pulls/{pr}/reviews`). El review-body
  se procesa solo si trae una sugerencia accionable real; igual entra al paso de
  minimize cuando él y sus inline asociados están resueltos.
- **Reacción/minimize en reviews por GraphQL**: no hay endpoint REST de reactions
  ni de minimize para un `PullRequestReview`. Implementa `Reactable` y
  `Minimizable`, así que `addReaction` y `minimizeComment` operan sobre su
  `node_id`. El vínculo review↔inline lo da `pull_request_review_id` en cada
  comment inline (REST) o `comment.pullRequestReview.databaseId` (GraphQL).
- **Terminación por review limpia**: cuando el resumen de Codex
  (`codex-review-state:v1`) marca la code review `completed` sin hallazgos para
  el **head actual** (se valida `code_review.commit_sha` contra `headRefOid`; en el
  formato viejo, el texto "Codex Review: Didn't find any major issues" y su
  `**Reviewed commit:**`), no quedan pendientes y todos los
  checks de CI del head están en verde, el loop mergea el PR y se auto-cancela,
  sin esperar revisión humana.
  El check de sha evita mergear con commits posteriores aún sin re-revisar, y el
  gate de CI evita mergear en rojo cuando el repo no tiene branch protection (una
  review limpia de Codex no prueba que la CI pase); un check fallido se trata
  como un hallazgo más y se fixea. Estrategia de merge por defecto: `--squash
  --delete-branch` (alineado con el historial del repo, `feat: … (#NN)`); cambiá
  el flag si tu repo usa merge-commit o rebase. Si el merge falla (checks
  pendientes, conflicto, branch protection), el loop NO se corta y reintenta.
- **Re-disparo de `@codex review` caído**: Codex pone 👀 (eyes) sobre el comentario
  al recibirlo. Si en una vuelta el último comentario general del PR es un
  `@codex review` sin esa reacción del bot, el trigger no fue leído (caído) y el
  loop lo repostea (paso 2-bis). El chequeo corre una vez por iteración, así que
  el propio intervalo del loop lo rate-limitea y no spamea; si el comentario ya
  tiene 👀, no hace nada.
- **Convergencia**: el triage del paso 3-pre (realista / borde razonable / borde
  rebuscado / preexistente / nit) evita que cada review agregue fixes de casos cada vez
  más improbables o de código viejo. Los no fixeables se cierran como «Sin cambios» con
  motivo; si una review solo deja ese tipo de hallazgos, el loop deja de pedir reviews,
  mergea el PR si pasa el gate de CI, y se auto-cancela. Codex no acepta una review
  limitada al delta, así que cada ronda pide un `@codex review` liso y el registro de
  `outcomes` cierra los hallazgos repetidos; los fixes cubren la clase
  de bug dentro del PR y, al terminar la ronda `{{MAX_REVIEW_ROUNDS}}`, el loop deja de
  pedir reviews y mergea sin preguntar tras el gate de CI, avisando qué quedó `failed`. Si las rondas solo corrigen tests o evals, el loop corta antes:
  tras `{{MAX_TEST_ONLY_ROUNDS}}` rondas seguidas así, mergea si pasa el gate de CI, porque
  esos hallazgos suelen ser variantes de las mismas aserciones y no defectos del producto.
  La política completa es compartida con `review-fix-loop`.
- **Delegación a Codex (`@codex fix`)**: en `codex`/`auto` el loop pide el fix en el
  propio hilo del hallazgo (o en el PR si no hay hilo) y no lo cierra hasta verificar un
  commit nuevo en el head que toque el archivo del grupo. El pedido no reemplaza el
  closeout: el cierre con plantilla lo sigue publicando el loop en el hilo original.
  Codex solo pushea si tiene permiso de escritura en la rama; sin él contesta sin
  commit y, en `auto`, el grupo cae a subagente local. Las respuestas del bot al pedido
  se registran en `delegationReplyIds` para no tratarlas como hallazgos nuevos.
  El `Monitor` del PR (paso 0) detecta el push de Codex y dispara la vuelta que cierra.
- **Timeout de ronda**: si Codex no publica la review de una ronda en
  `{{REVIEW_ROUND_TIMEOUT_MIN}}` min, el loop repostea `@codex review` una vez sin consumir
  el tope de rondas; si vuelve a vencer, avisa y se auto-cancela sin mergear. Relanzarlo
  le da a esa ronda un reintento más (ver «Timeout de ronda»).
- **Head avanzado sin review**: si después de una review terminada entra un commit
  ajeno al loop, el loop pide `@codex review` del head nuevo aunque esa vuelta no haya
  fixeado nada (o adopta la review que Codex ya esté corriendo sobre ese head), para no quedar esperando una
  review que nadie pidió, como pasó en el PR #31 (paso 6).
- **Cancelar a mano**: `CronList` para ver el job y `CronDelete <id>`.
- **Persistencia real**: para correr sin sesión abierta, mergeá el workflow de CI
  a la rama default y usá el Action.
