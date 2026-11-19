# Template de cierre

Usar después de fix validado y commit pusheado/verificado en head de PR. Elegir variante según destino recibido.

## Comentario inline

```markdown
✅ **Resuelto** en [`{{sha_corto}}`]({{commit_url}}).

### 🔧 Qué cambió
> {{resumen_de_una_linea}}

<sub>🤖 Fix aplicado en respuesta a este comentario inline.</sub>

<!-- inline-thread-autofix: comment:{{comment_id}} -->
```

Usar `Resuelto` solo cuando reply fue creado en `in_reply_to` correcto y `resolveReviewThread` confirmó `isResolved: true`. El marker `comment:{{comment_id}}` va siempre, haya o no issue: es la señal que el fast path usa para reconocer el closeout del thread en una invocación posterior, también cuando la issue y el PR alternativo no aportan markers propios. Usar SHA de `implementation_pr`, aunque `source_pr` sea otro PR. Si existe issue asociada, agregar `Issue asociada: [{{owner}}/{{repo}}#{{issue_number}}]({{issue_url}})` al reply; con `issue: none`, omitir esa línea: reply y resolución del thread completan el closeout. El body debe enlazar SHA completo de implementación; GitHub puede conservar en metadata `commit_id` de comment de ancla para replies, lo que no justifica duplicar reply si `in_reply_to`, body, head remoto y thread están verificados.

## Comentario inline eliminado

Usar esta variante cuando el comentario original devuelve `404` o no aparece tras refrescar comentarios y threads, y el fix/head remoto están verificados:

```markdown
ℹ️ **Closeout realizado sin reply**

El comentario inline original fue eliminado o ya no está disponible.

### 🔧 Qué cambió
> {{resumen_de_una_linea}}

- Commit: [`{{sha_corto}}`]({{commit_url}})
- Reply `Resuelto`: omitido
- Thread: `{{resuelto|not_resolvable}}`
```

No publicar comentarios adicionales ni asumir identidad de otro thread. Si la issue asociada debe cerrarse sin comentario, exigir solicitud explícita del usuario y validación previa de la asociación.

## Issue asociada a inline comment

Solo con issue validada; con `issue: none` omitir esta sección y el cierre. Publicar en `repos/{{owner}}/{{repo}}/issues/{{issue_number}}/comments`, después de verificar reply y resolución del thread:

```markdown
✅ **Resuelto** en [PR #{{implementation_pr}}]({{implementation_pr_url}}), commit [`{{sha_corto}}`]({{commit_url}}).

Issue atendida a partir de este [comentario inline]({{source_comment_url}}).

### 🔧 Qué cambió
> {{resumen_de_una_linea}}

<sub>🤖 Fix aplicado y verificado; issue cerrada después de completar el thread.</sub>

<!-- inline-thread-autofix: issue:{{owner}}/{{repo}}#{{issue_number}}:comment:{{comment_id}} -->
```

Reglas:

- Verificar que issue pertenece a `{{owner}}/{{repo}}`, es issue y no pull request.
- No editar body ni reabrir issue; cerrar con `PATCH .../issues/{{issue_number}} -f state=closed` y releer `state == closed`.
- Si marker ya existe, reutilizar comentario verificado y no publicar otro.
- No afirmar issue cerrada si comentario, PATCH o releer estado falló.

## PR de implementación alternativo

Publicar como comentario general en `repos/{{owner}}/{{repo}}/issues/{{implementation_pr}}/comments`, sin `in_reply_to`, solo cuando `implementation_pr != source_pr`. Con issue validada:

```markdown
✅ **Issue resuelta**: [{{owner}}/{{repo}}#{{issue_number}}]({{issue_url}}).

El fix quedó aplicado en este [PR #{{implementation_pr}}]({{implementation_pr_url}}), commit [`{{sha_corto}}`]({{commit_url}}).

Origen: [comentario inline original]({{source_comment_url}}).

<!-- inline-thread-autofix: pr:{{implementation_pr}}:issue:{{issue_number}}:comment:{{comment_id}} -->
```

Con `issue: none`:

```markdown
✅ **Feedback resuelto** a partir del [comentario inline original]({{source_comment_url}}).

El fix quedó aplicado en este [PR #{{implementation_pr}}]({{implementation_pr_url}}), commit [`{{sha_corto}}`]({{commit_url}}).

<!-- inline-thread-autofix: pr:{{implementation_pr}}:comment:{{comment_id}} -->
```

Verificar que `html_url` pertenece al PR de implementación y contiene link al comment original y a la issue si existe. Este comentario completa la dirección `PR destino → issue → comment` (o `PR destino → comment` sin issue); no reemplaza reply/resolución del thread ni comentario/cierre de issue.

## Review body editada

Agregar este bloque al body original, sin reemplazarlo:

```markdown
---

✅ **Fix aplicado** en [`{{sha_corto}}`]({{commit_url}}).

### 🔧 Qué cambió
> {{resumen_de_una_linea}}

<sub>🤖 Fix aplicado en respuesta a esta review sin comentarios inline.</sub>

<!-- inline-thread-autofix: review:{{review_id}} -->
```

## Comentario general del PR

Publicar como comentario nuevo en `repos/{{owner}}/{{repo}}/issues/{{pull_request_number}}/comments`. La respuesta a un comentario general siempre empieza con el link explícito al original (primera línea, para verlo rápido) y sigue con un quote reply de su texto, como el botón *Quote reply* de GitHub: cada línea con `> `. Se cita el body completo; si es muy largo, solo las partes de cada pedido, marcando el recorte con `> …`. Del quote se quitan los comentarios HTML (markers de corridas anteriores) y los back-links agregados por esta skill. Después de verificar la respuesta, se edita el original para agregarle al final, sin tocar su texto, un back-link a la respuesta (variante `Back-link en el comentario original`). Una fila por pedido del comentario, en el mismo orden en que aparecen:

```markdown
↩️ En respuesta a [este comentario]({{source_comment_url}}) de {{mencion_autor}}:

> {{linea_1_del_comentario_original}}
> {{linea_2_del_comentario_original}}

✅ **Fix aplicado** en [`{{sha_corto}}`]({{commit_url}}).

### 📋 Pedidos
| # | Pedido | Estado |
|---|---|---|
| 1 | {{pedido_resumido}} | ✅ Aplicado |
| 2 | {{pedido_resumido}} | ℹ️ Sin cambios: {{motivo_breve}} |
| 3 | {{pedido_resumido}} | ⏸️ Pendiente: {{motivo_breve}} |

### 🔧 Qué cambió
> {{resumen_de_una_linea}}

<sub>🤖 Respuesta a un comentario general del PR.</sub>

<!-- inline-thread-autofix: issuecomment:{{comment_id}} -->
```

`{{mencion_autor}}` es `@{{autor_login}}` (por ejemplo `@octocat`), para que GitHub lo renderice como mención y notifique al autor que su comentario tiene respuesta. Excepción: si el autor es un bot (`user.type == "Bot"` o login terminado en `[bot]`), va su login como texto, sin `@`, porque mencionar a un bot revisor puede disparar otra corrida suya. Si ningún pedido llevó commit, cambiar `✅ **Fix aplicado** …` por `ℹ️ **Sin cambios de código**.`, quitar `### 🔧 Qué cambió` y conservar tabla y marker. `⏸️ Pendiente` se usa para pedidos que necesitan confirmación del usuario (labels, merge, otro PR) o que quedaron `FINDING_ANCHOR_AMBIGUOUS`. No usar la palabra `Resuelto` en el texto: no hay thread. Tras verificar la respuesta, el comentario original se oculta como resuelto (`minimizeComment`, `classifier: RESOLVED`), también con pedidos `⏸️ Pendiente` o `ℹ️ Sin cambios`, porque la tabla de la respuesta conserva su estado. Nunca se oculta un comentario del propio usuario autenticado.

### Respuesta ya publicada: se reemplaza, no se acumula

Un comentario general tiene una sola respuesta, y esa respuesta muestra solo el análisis actual. Si al retomarlo ya existe una respuesta propia con su marker (`issuecomment:`, `answer:issuecomment:` o `declined:issuecomment:` con el mismo `{{comment_id}}`), no publicar otra ni conservarla como está: rehacer el análisis de cada pedido contra el head actual del PR y reescribir esa respuesta en el lugar con `PATCH repos/{{owner}}/{{repo}}/issues/comments/{{reply_id}}`, usando el template vigente de esta sección (o de `Respuesta a una pregunta`). Quien lee el PR necesita saber qué estado tiene hoy cada pedido, no la crónica de corridas anteriores.

- El body nuevo reemplaza al anterior por completo: no conservar el texto previo, ni tachado, ni en `<details>`, ni como sección `Actualización` o `Historial`, ni la tabla vieja al lado de la nueva.
- Un formato viejo (sin link inicial, sin quote, sin tabla o sin emojis) se migra al template vigente en la misma edición.
- Para un pedido ya implementado en una corrida anterior, reutilizar su commit solo si se verifica que el cambio sigue en el head; no crear otro commit para reescribir la respuesta.
- Mantener el marker exacto: la URL de la respuesta no cambia, así que el back-link del original sigue válido.
- Releer la respuesta justo antes del `PATCH` y verificar después el body publicado (link, quote, tabla, SHA si hay commit y marker). Si hay más de una respuesta propia con el marker, reescribir la más antigua y reportar las otras sin borrarlas.
- Si el `PATCH` devuelve `403`/`404` o no verifica, no publicar una respuesta nueva y dejar el ítem en `CLOSEOUT_INCOMPLETE`: no agregar el back-link, no ocultar el original y no cerrar la issue que dependa de esa respuesta, porque un comentario oculto se descarta en las corridas siguientes y ya no se podría recuperar la respuesta vigente. Reportar `respuesta: no reescrita` y seguir solo con los demás ítems independientes.

## Back-link en el comentario original

Después de publicar y verificar la respuesta a un comentario general, editar el original con `PATCH repos/{{owner}}/{{repo}}/issues/comments/{{comment_id}}` enviando su body completo, tal como se leyó inmediatamente antes, más este bloque al final:

```markdown

---
↪️ Respondido en [este comentario]({{reply_url}}).

<!-- inline-thread-autofix: issuecomment-backlink:{{comment_id}} -->
```

Reglas:

- Releer el original justo antes del `PATCH`; si su body cambió desde que se citó, reconstruir con el body nuevo y no pisar la edición ajena.
- Si el marker `issuecomment-backlink:{{comment_id}}` ya está en el body, no agregar otro.
- Verificar después que el body empieza con el texto original completo y termina con el bloque.
- Si el `PATCH` devuelve `403`/`404` o no verifica, la respuesta publicada sigue valiendo: reportar `back-link: no agregado` y seguir; no reintentar en loop.
- Aplica también a comentarios del propio usuario y de bots; editar el original nunca reemplaza ocultarlo como resuelto.

## Respuesta a una pregunta

Para un thread inline o un comentario general que pregunta algo sin pedir cambios. En inline va como reply con `in_reply_to`, sin quote. En comentario general va como comentario nuevo con el mismo encabezado de link y quote reply de la variante anterior (y back-link en el original):

```markdown
💬 **Respuesta** a [este comentario]({{source_comment_url}}).

{{respuesta_breve}}

### 🔎 Evidencia
- {{path_y_linea_o_link_al_codigo}}

<sub>🤖 Sin cambios de código: el comentario hacía una pregunta.</sub>

<!-- inline-thread-autofix: answer:{{source_kind}}:{{source_id}} -->
```

`{{source_kind}}` es `comment`, `review` o `issuecomment`. Un comentario general con pregunta se oculta como resuelto tras responder (salvo que sea del propio usuario). Resolver el thread inline solo si la evidencia contesta la pregunta por completo; si la respuesta deja una decisión abierta, dejar el thread abierto y reportarlo.

## Sugerencia no aplicada

Para feedback que, tras revisar el código, no conviene aplicar (incorrecto, ya cubierto o contrario a una regla del repo):

```markdown
ℹ️ **Sin cambios** para [este comentario]({{source_comment_url}}).

{{motivo_breve}}

### 🔎 Evidencia
- {{path_y_linea_test_o_regla}}

<sub>🤖 La sugerencia no se aplicó; queda abierta para que decida quien la hizo.</sub>

<!-- inline-thread-autofix: declined:{{source_kind}}:{{source_id}} -->
```

No resolver el thread de una persona con esta variante: lo decide quien hizo el comentario. En un comentario general, la respuesta va en la tabla del template `Comentario general del PR` y el comentario se oculta igual, salvo que sea del propio usuario. Para comentarios de Codex (`chatgpt-codex-connector[bot]`) o Claude (`claude[bot]`), usar las variantes de `codex-comment-closeout` en lugar de las de este archivo.

## Hallazgo ya resuelto en otra capa

Usar solo después de confirmar explícitamente closeout del destino indicado por URL. No afirmar `Fix aplicado` ni `Resuelto` en PR que no recibió patch:

```markdown
ℹ️ **Sin cambios en esta capa**

El hallazgo ya está corregido en [PR #{{pull_request_number}}]({{pull_request_url}}), commit [`{{sha_corto}}`]({{commit_url}}).

### Evidencia
> {{resumen_de_la_evidencia}}

<sub>🤖 Corrección verificada en otra capa del stack; no se aplicó patch duplicado aquí.</sub>

<!-- inline-thread-autofix: finding:{{finding_key}} -->
```

Para `review_body`, este bloque solo puede publicarse como comentario fallback; no usar `Review body: actualizada` si body no fue editado y nunca llamar `resolveReviewThread`.

## Comentario general fallback

Usar misma variante review-body, precedida por referencia inequívoca:

```markdown
En respuesta a la [review original]({{review_url}}):

{{bloque_review_body}}
```

No usar `in_reply_to` para fallback. Mantener marcador estable `review:{{review_id}}` para evitar duplicados.

## Estado local de backups

Las refs `backup/*` son estado local y nunca deben aparecer en comentarios de GitHub. Ejecutar su cleanup solo después de verificar todos los destinos remotos y el estado final:

- `BACKUPS_NOT_APPLICABLE`: no hubo stack ni refs propias; no inventar cleanup.
- `BACKUPS_PENDING_CLOSEOUT`: backend terminó implementación/publicación, pero orchestrator conserva refs fuera clone hasta completar destinos.
- `BACKUPS_CLEANED`: refs creadas por esta ejecución fueron eliminadas con OID esperado y las preexistentes permanecen intactas.
- `BACKUPS_PRESERVED_ON_FAILURE`: una fase anterior falló; conservar refs para rollback e informar etapa y refs retenidas.
- `BACKUP_CLEANUP_FAILED`: una ref cambió, faltó o la transacción no pudo completarse; no borrar otras refs ni publicar comentario compensatorio. Informar URLs remotas ya publicadas, estado pendiente y refs retenidas.

## Reglas

- `{{sha_corto}}` tiene 7 caracteres y apunta a commit completo en mismo repo.
- `{{resumen_de_una_linea}}` describe efecto observable, no repite diff.
- Mantener `### 🔧 Qué cambió` y resumen en blockquote (`>`).
- Texto visible va en español; conservar en inglés solo identifiers, paths, comandos y nombres técnicos.
- `Resuelto` queda reservado para inline threads; review-body y comentario general usan `Fix aplicado`.
- Toda respuesta publicada usa una variante de este archivo (o de `codex-comment-closeout` para bots revisores): encabezado con emoji, secciones `###` con emoji, `<sub>🤖 …</sub>` y marker. Nunca escribir una respuesta libre.
- No publicar hasta confirmar push y head remoto.
- No incluir stack, `cause`, tokens, secrets, cookies, headers, payloads, PII ni logs raw.
- Review editada debe conservar body original completo; fallback debe enlazar review original.
- `finding:{{finding_key}}` es opcional, determinístico y no reemplaza evidencia de código.
- No publicar template de éxito ante tests fallidos, fix no aplicado o closeout ambiguo.

## Falla del flujo

Si fix no pudo aplicarse o validación falló, no responder ni resolver automáticamente. Si hace falta diagnóstico, usar comentario separado y seguro, sin atribuir éxito a sugerencia ni publicar datos sensibles.
