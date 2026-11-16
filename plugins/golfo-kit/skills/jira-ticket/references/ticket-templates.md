# Templates de descripción por nivel

Leer antes de redactar o editar la descripción de una épica, una Story o una subtarea, y antes de agregar un hijo a un padre existente o reflejar el cambio de estado de un hijo. Campos, labels y tipos viven en [`jira-fields.md`](jira-fields.md); la sección `## Pull requests` y la concurrencia de escritura, en [`pr-traceability.md`](pr-traceability.md). Este archivo define solo el texto de la descripción.

## Qué renderiza Jira

La skill escribe con `contentFormat: "markdown"`; la integración Atlassian lo convierte a ADF. El formato se eligió por lo que sobrevive a esa conversión:

| Elemento | Decisión |
|---|---|
| Tabla Markdown (GFM) | Se usa. Tras escribir, releer la descripción: si la tabla quedó aplanada como texto, reemplazarla por la [lista de respaldo](#lista-de-respaldo) en la misma escritura correctiva |
| Emoji Unicode (`✅`, `🔄`) | Se usa: es texto plano y se ve igual en web, mobile y notificaciones |
| Mermaid | No se usa: Jira Cloud no lo renderiza sin una app del Marketplace y quedaría como bloque de código |
| Smart link con estado en vivo | No se usa: requiere nodos ADF `inlineCard` que el Markdown no genera; la key va como link común |
| Checklist `- [ ]` | No se usa para trabajo: los hijos son issues reales (ver `Subtareas reales` en `SKILL.md`) |

## Reglas comunes

- **Poco texto.** Cada sección cabe en 1–3 líneas o hasta 4 bullets. Si hace falta más, el detalle va en un hijo, no en el padre.
- **Sin repetir a Jira.** El panel de hijos de Jira ya muestra key, título, estado, responsable y barra de progreso. La tabla existe para leer el avance dentro de la descripción y suma lo que ese panel no da: emoji de estado, contador por estado, PR propio de cada hijo y un bloqueo en una línea.
- **Cada fila es un issue real.** Una fila sin key no es válida; la tabla es una vista de hijos existentes, nunca un checklist que los reemplace.
- **Estado leído de Jira.** El texto del estado es el nombre real que devuelve Jira para ese hijo; el emoji sale de su categoría (`statusCategory`), no del nombre:

  | Categoría | Emoji |
  |---|---|
  | `new` (To Do) | ⬜ |
  | `indeterminate` (In Progress, Review…) | 🔄 |
  | `done` | ✅ |
  | Bloqueado (link `is blocked by` a un issue abierto, o lo indica el usuario) | 🚫, con el motivo en la columna `Nota` |

- **Una fila por hijo, una celda por estado.** Cambiar el estado de un hijo es reescribir solo la celda `Estado` de su fila. La línea `Progreso` es derivada: la skill la recalcula desde las filas en la misma escritura; si una persona edita a mano una celda, la próxima sincronización corrige el contador. Un hijo bloqueado cuenta solo como 🚫, que se agrega al final del contador (`· 1 🚫`) cuando hay alguno.
- **Orden estable** por key numérica, para que agregar un hijo sea insertar una fila sin mover las demás.
- **Responsable**: nombre visible que devuelve Jira, o `—` sin asignar. No usar emails ni account ids.
- **PR**: solo `owner/repo#n` como texto, sin URL ni estado GitHub. La URL canónica vive una sola vez en `## Pull requests` de la Story. Poner un PR en una fila solo cuando ese hijo tiene un PR propio; si un PR cubre toda la Story, la celda queda `—`. Si ningún hijo tiene PR propio, omitir la columna.
- **Marcadores.** Los headings de este template (`## Objetivo`, `## Stories`, `## Problema`, `## Tareas`…) delimitan secciones: la skill reescribe una sección desde su heading hasta el siguiente `##` y no toca nada más.

## Épica

```markdown
## Objetivo
<problema y resultado esperado, 1–2 oraciones>

## Alcance
- Incluye: <qué entra>
- Fuera de alcance: <qué no entra; omitir la línea si no aplica>

## Stories
**Progreso:** 1/3 ✅ · 1 🔄 · 1 ⬜

| Key | Story | Estado | Responsable | Nota |
|---|---|---|---|---|
| [ACME-10](<SITE_URL>/browse/ACME-10) | Alta de proveedores | ✅ Done | Ana Pérez | — |
| [ACME-14](<SITE_URL>/browse/ACME-14) | Guía de registro | 🔄 In Progress | — | — |
| [ACME-17](<SITE_URL>/browse/ACME-17) | Copy de errores | ⬜ To Do | Luis Gómez | — |
```

- La épica no lleva `## Pull requests`: los PR viven en sus Stories.
- Épica nueva sin Stories todavía: dejar `## Stories` con la línea `_Sin stories todavía._` en lugar de la tabla.

## Story

```markdown
## Problema
<qué pasa hoy y a quién afecta, 1–2 oraciones>

## Solución
<qué resuelve este ticket, 1–2 oraciones; en modo repositorio, hasta 4 bullets con las áreas técnicas y la cobertura automática>

## Criterios de aceptación
- <resultado verificable>
- <resultado verificable>

## Tareas
**Progreso:** 2/4 ✅ · 1 🔄 · 1 ⬜

| Key | Tarea | Estado | Responsable | PR | Nota |
|---|---|---|---|---|---|
| [ACME-21](<SITE_URL>/browse/ACME-21) | Migrar templates | ✅ Done | Ana Pérez | acme/payments-api#88 | — |
| [ACME-22](<SITE_URL>/browse/ACME-22) | PR creado | ✅ Done | Ana Pérez | — | — |
| [ACME-23](<SITE_URL>/browse/ACME-23) | PR testeado | ⬜ To Do | — | — | — |
| [ACME-24](<SITE_URL>/browse/ACME-24) | Revisar con producto | 🔄 In Progress | Luis Gómez | — | — |

## Pull requests
- [acme/payments-api#88](https://github.com/acme/payments-api/pull/88)
```

- Criterios de aceptación como bullets simples, no `- [ ]`: describen el resultado esperado, no el trabajo pendiente.
- `## Pull requests` sigue `pr-traceability.md` y va siempre al final.
- Story sin subtareas: omitir `## Tareas` hasta que exista el primer hijo.
- Story sin épica: es el nivel más alto; usa el mismo template y no se inventa una épica para colgarla.

## Subtarea (task)

```markdown
## Qué hacer
<1–3 bullets con el alcance>

## Cómo se valida
- <criterio de finalización verificable>
```

Sin tabla, sin URLs de PR (puede nombrar el número y remitir a la Story) y sin repetir el problema de la Story.

## Lista de respaldo

Si la relectura muestra que la tabla no se renderizó, usar una línea por hijo con el mismo orden y los mismos campos:

```markdown
## Tareas
**Progreso:** 2/4 ✅ · 1 🔄 · 1 ⬜

- ✅ [ACME-21](<SITE_URL>/browse/ACME-21) Migrar templates · Done · Ana Pérez · acme/payments-api#88
- ⬜ [ACME-23](<SITE_URL>/browse/ACME-23) PR testeado · To Do · —
```

Cambiar un estado sigue siendo tocar una sola línea.

## Operaciones

Toda escritura de la descripción de un padre (épica o Story) usa la relectura, `version` y el único retry de `Concurrencia de descripción padre` en `pr-traceability.md`.

La sección de seguimiento no se redacta a mano: se calcula con `scripts/jira-ticket.py tracking --level story|epic`, pasando por stdin `{"description": "<descripción releída>", "children": [...]}` con cada hijo releído en Jira (`key`, `summary`, `status`, `category` = `statusCategory.key`, y opcionales `assignee`, `pr`, `blocked`, `note`). El helper cambia solo la celda `Estado` (y `Nota` al bloquear o desbloquear) de los hijos que cambiaron, inserta las filas que faltan por key, recalcula `Progreso` y deja idéntico todo lo demás, también en la lista de respaldo. Devuelve `description`, `changed`, `added`, `updated` y `rows_without_child` (filas cuyo hijo no vino en la entrada: se conservan y se informan). Con `changed: false` no se escribe. Sin sección devuelve `section: missing` y no la crea salvo `--create`. Si el helper no puede ejecutarse, aplicar estas mismas reglas a mano e informarlo.

### Crear

Redactar la variante del nivel con los hijos que se crean en la misma ejecución. Releer después de crear los hijos y escribir la tabla con sus keys reales; nunca publicar filas con keys supuestas.

### Agregar un hijo a un padre existente

Aplica a una Story nueva bajo una épica existente y a una subtarea nueva bajo una Story existente.

1. Releer el padre por key. No reescribir, traducir ni reordenar ningún contenido fuera de la sección de seguimiento (`## Stories` en la épica, `## Tareas` en la Story), aunque no siga este template.
2. Si la sección existe, correr `tracking` con los hijos actuales: inserta la fila del hijo en su posición por key y recalcula `Progreso`.
3. Si la sección no existe, agregarla al final de la descripción (antes de `## Pull requests` en una Story), con una fila por cada hijo real del padre, consultados con `parent = <KEY>` y solo los campos `summary`, `status`, `assignee` e `issuelinks` (este último solo para detectar bloqueos). El índice de búsqueda puede omitir issues recién creados: unir ese resultado, deduplicado por key, con los hijos creados en esta ejecución releídos por key, y pasar esa unión a `tracking --create`. Si el padre tiene más hijos que `<MAX_RESULTS>`, no crear la tabla: informar que el panel de hijos de Jira ya cubre ese seguimiento.
4. No tocar los campos de la épica (fechas, sprint, labels, responsable) por agregar una Story.

### Actualizar el estado de un hijo

Cuando la skill cambia o verifica el estado de un hijo:

1. Releer el estado real del hijo en Jira.
2. Correr `tracking` (sin `--create`) con los hijos releídos: reescribe solo la celda `Estado` de su fila (o su línea en la lista de respaldo), la celda `Nota` si se bloqueó o desbloqueó, y `Progreso`.
3. Si el hijo es una Story con épica, actualizar también su fila en la tabla de la épica solo cuando cambia el estado de la Story, no el de sus subtareas.
4. Si la sección existe pero falta la fila del hijo, insertarla como en `Agregar un hijo a un padre existente`. Si el padre no tiene sección de seguimiento, no crearla solo por un cambio de estado, salvo pedido explícito.

El estado de un hijo en la tabla no decide el estado del padre: eso sigue `status-transitions.md`.
