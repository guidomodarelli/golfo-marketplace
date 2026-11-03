# Template de cierre

Usar después de fix validado y commit pusheado/verificado en head de PR. Elegir variante según destino recibido.

## Comentario inline

```markdown
✅ **Resuelto** en [`{{sha_corto}}`]({{commit_url}}).

### 🔧 Qué cambió
> {{resumen_de_una_linea}}

<sub>🤖 Fix aplicado en respuesta a este comentario inline.</sub>
```

Usar `Resuelto` solo cuando reply fue creado en `in_reply_to` correcto y `resolveReviewThread` confirmó `isResolved: true`. Usar SHA de `implementation_pr`, aunque `source_pr` sea otro PR. Si existe issue asociada, agregar `Issue asociada: [{{owner}}/{{repo}}#{{issue_number}}]({{issue_url}})` al reply; con `issue: none`, omitir esa línea: reply y resolución del thread completan el closeout. El body debe enlazar SHA completo de implementación; GitHub puede conservar en metadata `commit_id` de comment de ancla para replies, lo que no justifica duplicar reply si `in_reply_to`, body, head remoto y thread están verificados.

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
- `Resuelto` queda reservado para inline threads; review-body usa `Fix aplicado`.
- No publicar hasta confirmar push y head remoto.
- No incluir stack, `cause`, tokens, secrets, cookies, headers, payloads, PII ni logs raw.
- Review editada debe conservar body original completo; fallback debe enlazar review original.
- `finding:{{finding_key}}` es opcional, determinístico y no reemplaza evidencia de código.
- No publicar template de éxito ante tests fallidos, fix no aplicado o closeout ambiguo.

## Falla del flujo

Si fix no pudo aplicarse o validación falló, no responder ni resolver automáticamente. Si hace falta diagnóstico, usar comentario separado y seguro, sin atribuir éxito a sugerencia ni publicar datos sensibles.
