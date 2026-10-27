# Notas de diseño del loop

Por qué el loop funciona como funciona: útil para cambiar la skill, no para correr una vuelta.

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
  como un hallazgo más y se fixea. El método de merge (`{{MERGE_FLAG}}`) sale de lo que
  permiten el repo y las reglas de la rama base (paso 0-bis de «Cómo relanzarlo»), siempre con
  `--delete-branch`. Si el merge falla (checks
  pendientes, conflicto, branch protection), el loop NO se corta y reintenta.
- **Re-disparo de `@codex review` caído**: Codex pone 👀 (eyes) sobre el comentario
  al recibirlo. Si en una vuelta el último comentario general del PR es un
  `@codex review` sin esa reacción del bot, el trigger no fue leído (caído) y el
  loop lo repostea (paso 2-bis). El chequeo corre una vez por iteración, así que
  el propio intervalo del loop lo rate-limitea y no spamea; si el comentario ya
  tiene 👀, no hace nada.
- **Sin `@codex` en el cuerpo del PR**: una mención `@codex` en el body hace que Codex
  conteste «create an environment» en vez de revisar; por eso la review inicial se pide
  con un comentario aparte (paso 2-ter). La regla vive en «Full-composition rules» de
  [`pr-description-template`](../../pr-description-template/SKILL.md).
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
