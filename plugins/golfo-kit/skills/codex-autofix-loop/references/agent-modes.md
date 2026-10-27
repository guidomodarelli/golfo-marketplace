# Modos de ejecución por capacidades del agente

El prompt del loop (`references/prompt-template.md`) está escrito para Claude Code: `Monitor` como disparador, cron de `/loop` como respaldo, `Agent` para subagentes y `PushNotification` para avisos. Este archivo define cómo correr **el mismo prompt** cuando faltan esas herramientas, con alternativas que conservan la escucha del PR siempre que el agente pueda esperar un comando acotado. Las equivalencias generales y el protocolo detectar → verificar → alternativa → desactivar y reportar viven en [`agent-capabilities.md`](../../../references/agent-capabilities.md).

## Elegir el modo (por capacidades, no por nombre del agente)

Antes del paso (0) del prompt, verificá en la lista de herramientas de la sesión:

| Modo | Requiere (todas verificadas en la sesión) | Típico en |
|---|---|---|
| **A. Monitor + cron** (original) | `Monitor`, `CronCreate`, `CronList`, `CronDelete`, `TaskStop` | Claude Code interactivo |
| **B. Watcher en background** | Un proceso en background que avisa al terminar (`terminal` con `background` + `notify`/`notify_on_complete`) y una herramienta para esperarlo o matarlo (`process`/`process_manage` con `wait` y `kill`) | Hermes |
| **C. Watcher en foreground dentro del turno** | Un shell que sostiene un comando de hasta `{{WATCH_TIMEOUT_SEC}}` s dentro del turno: bloqueante con timeout propio, o que devuelve el control y deja leer la salida después (`exec_command` con `yield_time_ms` + `write_stdin` vacío para seguir leyendo, en Codex) | Codex CLI y app, `claude -p`, otros agentes con terminal |
| **D. Una ronda por invocación** | Nada de lo anterior, o el usuario pidió explícitamente una sola ronda sin ocupar la sesión | Agentes sin shell para comandos largos |

Si falta una sola herramienta de un modo, ese modo no aplica: bajá al siguiente. No mezcles modos en una misma corrida.

## Garantías que se mantienen en todos los modos

Viven en el estado del PR (`.codex-autofix/processed-<PR>.json`) y en comprobaciones síncronas contra GitHub, así que no dependen del mecanismo de espera:

- **Dedup por PR**: `processedCommentIds`, `inFlight`, `delegationReplyIds` y `outcomes` se leen y escriben igual. El loop principal sigue siendo el único escritor.
- **Tope de rondas** (`reviewRounds` contra `{{MAX_REVIEW_ROUNDS}}`) y **tope de solo tests** (`testOnlyRounds`): persisten entre invocaciones, así que relanzar no los resetea.
- **Timeout de ronda** (`reviewRequestedAt`, `reviewTimeoutRetries` y `reviewTimedOut` contra `{{REVIEW_ROUND_TIMEOUT_MIN}}` y `{{REVIEW_ROUND_TIMEOUT_RETRIES}}`, paso 2-quater): el reloj es la hora guardada en el JSON, así que vence igual en cualquier modo, aunque el agente haya estado cerrado. Ningún modo mergea por una ronda vencida.
- **Gates de merge**: review limpia de Codex para el head actual (o un corte del loop: convergencia, tope de solo tests o fin de la última ronda) y GATE DE CI del paso (5-bis), evaluados en el momento del merge. Nunca se mergea con CI roja ni checks pendientes, y ningún merge se le consulta al usuario. Fuera del merge por fin de la última ronda, que tolera hallazgos `failed` y los reporta, tampoco se mergea con hallazgos abiertos. `finalMergePending` persiste entre invocaciones igual que los topes.
- **Guard de auto-cancelación**: el paso «GUARD» corre primero en cada vuelta.

## Modo A — Monitor + cron (Claude Code)

El prompt tal cual, sin cambios.

## Modo B — Watcher en background (Hermes)

Reemplaza el paso (0) y el cron de respaldo por ciclos de un watcher acotado:

1. **Armar**: lanzá en background, con aviso al terminar, el script de esta skill
   `bash <skill-dir>/scripts/wait-for-pr-event.sh --repo {{OWNER}}/{{REPO}} --pr {{PR}} --poll-seconds {{MONITOR_POLL_SEC}} --timeout-seconds {{WATCH_TIMEOUT_SEC}}`
   (en Hermes: `terminal(command=..., background=true, notify=true)`; usá el nombre de parámetro que muestre el schema). Guardá el `session_id` del proceso. Debe haber **un solo** watcher vivo por PR: antes de armar otro, listá los procesos y reutilizá el existente.
2. **Al recibir el aviso** (o con `process wait` y `timeout` ≤ `{{WATCH_TIMEOUT_SEC}}`), leé el código de salida:
   - `0` (evento) o `3` (timeout): corré **una** iteración completa del prompt desde el GUARD. El timeout cumple el rol del cron de respaldo: en esa vuelta se evalúan los TTL (`{{CODEX_ACK_TIMEOUT_MIN}}`, `{{CODEX_FIX_TTL_MIN}}`, `{{INFLIGHT_TTL_MIN}}`), el timeout de ronda (`{{REVIEW_ROUND_TIMEOUT_MIN}}`) y los reintentos de merge. Si Codex nunca publica la review, el watcher solo sale con `3`, y es esa vuelta la que hace vencer la ronda.
   - `5` (PR no `OPEN`): auto-cancelá (el GUARD lo confirma) y terminá.
   - `4` (GitHub no disponible) o `2` (uso inválido): no rearmes; reportá el error con la salida del script y terminá.
3. **Rearmar** tras cada iteración mientras el loop siga vivo, contando ciclos. Tope: `{{MAX_WATCH_CYCLES}}` ciclos por sesión. Al alcanzarlo, terminá con un mensaje «loop detenido por tope de ciclos: relanzá la skill para seguir» (el estado del JSON se conserva).
4. **Auto-cancelar** = matar el watcher vivo (`process kill`) y avisar en el chat. No hay cron que borrar. Vale también para el segundo vencimiento del timeout de ronda: no se rearma el watcher.
5. **Subagentes**: `delegate_task` (en paralelo con `tasks[]`) en lugar de `Agent`. Mueren con la sesión padre: antes de terminar, esperá a los que estén vivos o detenelos y dejá sus ids en `inFlight` para que el TTL los libere.
6. **Avisos**: cada `PushNotification` del prompt se reemplaza por una línea en el mensaje del chat.

No uses `cronjob` como respaldo: cada disparo corre en una sesión nueva sin acceso a los subagentes ni al watcher de esta sesión, así que no puede reconciliar `inFlight` ni cancelar el loop.

## Modo C — Watcher en foreground dentro del turno (Codex y otros agentes con terminal)

Mismo watcher que el modo B, pero esperado en primer plano: el turno queda ocupado por el loop y nada sobrevive al turno.

1. **Esperar el evento**: corré en foreground
   `bash <skill-dir>/scripts/wait-for-pr-event.sh --repo {{OWNER}}/{{REPO}} --pr {{PR}} --poll-seconds {{MONITOR_POLL_SEC}} --timeout-seconds {{WATCH_TIMEOUT_SEC}}`.
   En Codex, con `exec_command` y un `yield_time_ms` corto: si devuelve un `session_id` porque sigue corriendo, seguí leyendo con `write_stdin` (entrada vacía) hasta obtener el código de salida, sin lanzar otro watcher. Un solo watcher vivo por PR.
2. **Según el código de salida**, igual que el modo B: `0` o `3` → **una** iteración completa del prompt desde el GUARD (el `3` cumple el rol del cron de respaldo y evalúa TTLs, timeout de ronda y reintentos de merge); `5` → auto-cancelar y terminar; `4` o `2` → reportar la salida del script y terminar.
3. **Repetir** tras cada iteración, contando ciclos, hasta `{{MAX_INTURN_CYCLES}}`. Así se cubre el relanzado tras `@codex review` (paso 7): el ciclo siguiente detecta la respuesta de Codex y sigue sin intervención. Con checks pendientes, el merge espera al ciclo en que la CI termine; nunca se mergea antes.
4. **Terminar** cuando el GUARD auto-cancela, se mergea, la ronda vence por segunda vez (paso 2-quater, con la línea «PR #N: Codex no publicó la review en X min»), se llega al tope de ciclos («loop detenido por tope de ciclos: relanzá la skill para seguir») o el usuario interrumpe el turno. El estado del JSON se conserva siempre, así que relanzar retoma donde quedó.
5. **Subagentes**: `spawn_agent` + `wait_agent` esperados dentro de la iteración; si no hay, `fix-in-ephemeral-clone` en contexto, grupo por grupo. Ninguno queda vivo al terminar el turno.
6. **Avisos**: cada `PushNotification` se reemplaza por una línea en el chat (y en el mensaje final).

Bloqueado en este modo: `sleep` en bucle fuera del script, procesos en background que sobrevivan al turno y crons. El único mecanismo de espera es el script, que siempre termina.

## Modo D — Una ronda por invocación

Corré el prompt **una sola vez**, sin el paso (0) ni el paso (7):

- **Bloqueado en este modo**: armar monitores o crons, `/loop`, `sleep` en bucle, procesos en background que sobrevivan al turno, y frases como «sigo escuchando». Si te descubrís a punto de esperar un evento futuro, cortá la ronda.
- **Subagentes**: si la sesión tiene subagentes con espera (`spawn_agent` + `wait_agent` en Codex), lanzalos y **esperalos dentro del turno**; si no, aplicá `fix-in-ephemeral-clone` en contexto, grupo por grupo. Ningún subagente local queda vivo al terminar. Los pedidos `@codex fix` sí quedan en `inFlight`, porque se reconcilian contra GitHub en la próxima invocación.
- **Merge**: igual que el original, solo si en esta ronda se cumplen la review limpia del head (o un corte del loop, como el fin de la última ronda con `finalMergePending`) y el GATE DE CI. Con checks pendientes no esperes: terminá y dejalo para la próxima invocación.
- **Timeout de ronda**: no hay espera, así que el paso (2-quater) compara `reviewRequestedAt` con la hora de cada invocación. Vencida por primera vez, repostea `@codex review` y reinicia el reloj. Vencida por segunda vez, no repostea ni mergea, marca `reviewTimedOut: true` y termina con la línea «PR #N: Codex no publicó la review en X min», explicando que volver a invocar la skill le da a la ronda un reintento más (paso 2 de «Cómo relanzarlo»). Una invocación normal entre medio no resetea nada: el reintento ya hecho sigue contando.
- **Cierre**: el mensaje final incluye la línea de resumen del paso (6-bis), qué quedó pendiente (por ejemplo «`@codex review` posteado, esperando a Codex») y cómo relanzar: «volvé a invocar `codex-autofix-loop` para el PR {{PR}} cuando Codex responda».
- **Avisos**: cada `PushNotification` se reemplaza por una línea del mensaje final.

## Variables de los modos B, C y D

- `{{WATCH_TIMEOUT_SEC}}` = `300` — presupuesto de cada ciclo del watcher (también marca cada cuánto se evalúan los TTL).
- `{{MAX_WATCH_CYCLES}}` = `72` — ciclos por sesión en el modo B (≈ 6 h con el timeout por defecto).
- `{{MAX_INTURN_CYCLES}}` = `36` — ciclos por turno en el modo C (≈ 3 h con el timeout por defecto); más corto que el modo B porque ocupa el turno del usuario.

## Limitaciones del agente (reportar al cierre)

| Modo | Desactivado | Motivo | Alternativas evaluadas |
|---|---|---|---|
| B | Cron de respaldo | No hay cron de sesión; `cronjob` corre en sesiones nuevas | Watcher con timeout como respaldo |
| B | Supervisión después de cerrar la sesión | El watcher y los subagentes mueren con la sesión (igual que en Claude Code) | Workflow `codex-autofix.yml` del repo |
| C | Uso del turno mientras el loop corre | El watcher ocupa el turno; el usuario puede interrumpirlo y relanzar sin perder estado | Automatizaciones de la app de escritorio de Codex (`codex_app`, `automation_update`): solo existen en la app (las herramientas las sirve la app por `CODEX_APP_TOOLS_PIPE_PATH`) y no se verificaron; `codex exec resume` + cron del SO o GitHub Actions (`codex-autofix.yml`): viables, pero crean un scheduler persistente fuera de la sesión, así que solo se arman si el usuario lo pide |
| C | Supervisión después del turno o tras `{{MAX_INTURN_CYCLES}}` ciclos | Nada sobrevive al turno | Ídem |
| D | Escucha continua del PR y relanzado automático (paso 7) | Modo elegido por el usuario o sin shell para comandos largos | Modo C si el shell lo permite; relanzar a mano o el workflow `codex-autofix.yml` |
