---
name: codex-autofix-loop
description: "Lanza y opera el loop que auto-fixea comentarios de Codex (chatgpt-codex-connector[bot]) en un PR: clone efímero → fix → push → closeout del hilo, o `@codex fix` en el propio hilo (modos `codex`/`auto` con fallback local), con dedup por PR, tope de rondas, timeout por ronda, guard de auto-cancelación y merge sin preguntar ni esperar revisión humana tras el gate de CI, también al terminar la última ronda. Lanzarlo solo, sin que lo pidan, apenas el agente abre un PR con `gh pr create`. Adapta la espera a cada agente (Monitor en Claude Code, watcher en background en Hermes, en foreground en Codex, o una ronda por invocación). Para un solo comentario de Codex alcanza con `codex-comment-closeout`. Use when the user asks to relaunch/start the Codex auto-fix loop for a PR, right after the agent opens a pull request (gh pr create) even if nobody asked, set up Codex comment auto-fixing, mentions docs/codex-autofix-loop.md, processed-PR.json, or the codex-autofix workflow."
license: MIT
metadata:
  version: "1.8.0"
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
rama si tiene permiso. Qué camino se usa lo decide `{{FIX_MODE}}` (ver «Modo de fix» y `references/fix-modes.md`).

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
`gh pr merge {{PR}} --repo {{OWNER}}/{{REPO}} {{MERGE_FLAG}} --delete-branch`. Si el merge tiene
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
- **Comando**: `gh pr merge {{PR}} --repo {{OWNER}}/{{REPO}} {{MERGE_FLAG}} --delete-branch
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

**Esperando al usuario:** cuando el loop queda frenado por algo que solo el usuario puede
resolver, por ejemplo un merge que el repo rechaza por su configuración, ninguna vuelta del
cron puede avanzar. Seguir corriéndolo cada `{{INTERVAL}}` solo gasta turnos y repite el mismo
aviso. Por eso, en ese caso:

- **Entrar**: poné `awaitingUser: {reason, since}` en el JSON (motivo en una línea, ISO-8601 UTC),
  mandá una PushNotification de una línea con el motivo y qué decisión hace falta, y borrá el
  cron del loop con `CronDelete`. El `Monitor` del PR sigue vivo (rearmalo al vencer): un head
  nuevo, un comentario o review de Codex, o el PR cerrado disparan una vuelta como siempre.
- **En cada vuelta con `awaitingUser`**: primero rearmá el `Monitor` si no está vivo (también
  cuando la vuelta es el aviso de que venció), porque sin cron es lo único que despierta al
  loop. Después reevaluá solo lo que lo frenó (por ejemplo, volvé a
  intentar el merge con el método que corresponda hoy). Si sigue igual, terminá la vuelta en
  silencio, sin otra notificación. Si se destrabó o el monitor trajo un evento con trabajo
  nuevo, borrá `awaitingUser`, recreá el cron (paso 3 de «Cómo relanzarlo») y seguí normal.
- **Respuesta del usuario**: si el usuario contesta (cambió la configuración, eligió una
  opción o pidió seguir), borrá `awaitingUser` y relanzá el loop con «Cómo relanzarlo».
- No cambies la configuración del repo para salir de este estado salvo que el usuario lo pida.

**Sin espera de revisión humana:** el loop no frena el merge para que una persona
apruebe, sin importar qué archivos toque el PR ni el tamaño del diff. Los únicos
requisitos para mergear son la review limpia de Codex (o el corte por convergencia, el
tope de solo tests o el fin de la última ronda) y el GATE DE CI. Ningún merge del loop
se consulta con el usuario. Si el repo tiene branch protection que exige una aprobación, `gh pr merge`
falla y el loop lo trata como cualquier merge fallido: avisa el motivo una vez y reintenta.

## Modo de fix: subagente local o `@codex fix`

`{{FIX_MODE}}` decide quién aplica cada fix: `local` (default, subagentes con
`fix-in-ephemeral-clone`), `codex` (`@codex fix` en el hilo) o `auto` (Codex primero y local si falla).
El triage, la agrupación y el cierre son iguales en los tres. Las reglas de `codex` y `auto` (dónde
se comenta, texto del pedido, respuestas y fallas) viven en
[references/fix-modes.md](references/fix-modes.md): leelo antes de usar uno de esos modos.

## Compatibilidad entre agentes

El prompt del loop (`references/prompt-template.md`) usa herramientas de Claude Code (`Monitor`, `CronCreate`/`CronList`/
`CronDelete`, `TaskStop`, `Agent`, `PushNotification`). Antes de lanzarlo, leé
[`references/agent-modes.md`](references/agent-modes.md) y elegí el modo según las
herramientas **realmente presentes en la sesión**, no según el nombre del agente
(protocolo común en [`agent-capabilities.md`](../../references/agent-capabilities.md)):

- **A. Monitor + cron** (Claude Code): el prompt de `references/prompt-template.md` tal cual.
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
0-bis. Definí `{{MERGE_FLAG}}` (`--squash`, `--merge` o `--rebase`) según lo que el repo
   permite de verdad, también **sin preguntar**. Un flag fijo rompe el merge final en repos que
   desactivan ese método, y el loop se entera recién al final.
   - Métodos del repo: `gh api repos/{{OWNER}}/{{REPO}} --jq '[(select(.allow_squash_merge) | "squash"), (select(.allow_merge_commit) | "merge"), (select(.allow_rebase_merge) | "rebase")] | join(" ")'`.
   - Reglas de la rama base: `gh api repos/{{OWNER}}/{{REPO}}/rules/branches/<base> --jq '[.[] | select(.type=="pull_request") | .parameters.allowed_merge_methods // empty] as $sets | {restricted: ($sets | length > 0), methods: (if ($sets | length) == 0 then [] else reduce $sets[1:][] as $set ($sets[0]; map(select(. as $method | $set | index($method)))) end), linear: any(.[]; .type=="required_linear_history")}'`. GitHub aplica todas las reglas que caen sobre la rama, así que los métodos permitidos son la **intersección** de cada `allowed_merge_methods` (no la unión). Con `restricted: true`, el método tiene que estar en `methods` (si queda vacía, ninguno vale). Con `linear: true`, `merge` no vale.
   - Elegí el primero válido en este orden: el que pida el usuario, las instrucciones del repo o
     una memoria de ese repo; si no, `squash`, `merge`, `rebase`.
   - Si ninguno vale, lanzá el loop igual y avisá en una línea que el PR no se va a poder mergear
     (con los métodos del repo y de las reglas). Al llegar al merge se trata como un merge
     fallido: aviso una vez y loop vivo. No cambies la configuración del repo sin que el usuario
     lo pida.
1. Reemplazá los placeholders del prompt de `references/prompt-template.md` (`{{OWNER}}`, `{{REPO}}`,
   `{{PR}}`, `{{BRANCH}}`, `{{MERGE_FLAG}}`) por los del PR objetivo.
2. Inicializá el estado de dedup del PR (vacío procesa todo el backlog; con ids
   ya cargados procesa solo los nuevos):
   ```
   .codex-autofix/processed-{{PR}}.json  ->  {"pr":{{PR}},"processedCommentIds":[],"inFlight":{},"codexAttempts":{},"delegationReplyIds":[],"reviewRounds":0,"testOnlyRounds":0,"testOnlyHeadSha":null,"lastReviewedSha":null,"reviewRequestedAt":null,"reviewTimeoutRetries":0,"reviewTimedOut":false,"finalMergePending":false,"awaitingUser":null,"outcomes":{}}
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
   rondas»); `awaitingUser` es `{reason, since}` mientras el loop espera una decisión del
   usuario y `null` el resto del tiempo (ver «Esperando al usuario»); `outcomes` es el registro de
   findings de la política de convergencia: `id -> {result, severity, round, path, sha?, reason?}`,
   con `result` en `fixed`, `rejected`, `pre-existing`, `nit-skipped`, `edge-case` o
   `failed`. Si falta alguna clave, el loop la trata como vacía o `0`.)
   Si el archivo ya existe (relanzar), conservalo. Solo si trae `reviewTimedOut: true`,
   ponelo en `false` y `reviewTimeoutRetries` en `0`: el loop se había auto-cancelado por el
   «Timeout de ronda» y relanzarlo es pedir un reintento más. Si trae `awaitingUser`, ponelo en
   `null`: relanzar es la respuesta del usuario.
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
> - `{{FIX_MODE}}` = `local` — `local`, `codex` o `auto` (ver «Modo de fix» y `references/fix-modes.md`). Usá
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
> - `{{MERGE_FLAG}}` = `--squash`, `--merge` o `--rebase`, el que permiten el repo y las reglas
>   de la rama base (paso 0-bis de «Cómo relanzarlo»).
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

La vuelta del loop, paso por paso (guard de auto-cancelación, monitor, triage, fan-out,
cierre, gate de CI, merge y pedido de review), vive en
[references/prompt-template.md](references/prompt-template.md). Leela entera antes de la primera
vuelta; el prompt del cron le pide al agente seguirla con los placeholders ya completados.

## Plantilla de comentario de cierre

Vive en [`codex-comment-closeout`](../codex-comment-closeout/SKILL.md), junto con su
regla de paridad con el step «Cerrar comentario» del Action
`.github/workflows/codex-autofix.yml`.

## Notas

Por qué el loop agrupa por archivo, reintegra antes de pushear, separa las tres fuentes de
comentarios o pide reviews sin texto extra: [references/design-notes.md](references/design-notes.md).
