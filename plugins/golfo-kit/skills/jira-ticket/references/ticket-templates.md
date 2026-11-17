# Templates de descripción por nivel

Leer antes de redactar o editar la descripción de una épica, una Story o una subtarea, y antes de agregar un hijo a un padre existente o reflejar el cambio de estado de un hijo. Este archivo define qué secciones lleva cada nivel. Cómo se escribe cada elemento (paneles, lozenges, expand, fechas), en qué formato se envía a Jira y cómo se edita una sección sin tocar el resto vive en [`rich-format.md`](rich-format.md); campos, labels y tipos, en [`jira-fields.md`](jira-fields.md); la sección `## Pull requests` y la concurrencia de escritura, en [`pr-traceability.md`](pr-traceability.md).

Los templates están en el Markdown enriquecido de `rich-format.md`: se compilan con `adf` (modo enriquecido) o `plain` (modo Markdown), nunca se envían tal cual.

## Reglas comunes

- **Poco texto.** Cada sección cabe en 1–3 líneas o hasta 4 bullets. Si hace falta más, el detalle va en un expand o en un hijo, no a la vista en el padre.
- **Sin repetir a Jira.** El panel de hijos de Jira ya muestra key, título, estado, responsable y barra de progreso. La tabla existe para leer el avance dentro de la descripción y suma lo que ese panel no da: emoji de estado, contador por estado, PR propio de cada hijo y un bloqueo en una línea.
- **Cada fila es un issue real.** Una fila sin key no es válida; la tabla es una vista de hijos existentes, nunca un checklist que los reemplace.
- **Estado leído de Jira.** El texto del estado es el nombre real que devuelve Jira para ese hijo; el emoji y el color del lozenge salen de su categoría (`statusCategory`), no del nombre:

  | Categoría | Emoji | Lozenge |
  |---|---|---|
  | `new` (To Do) | ⬜ | `neutral` |
  | `indeterminate` (In Progress, Review…) | 🔄 | `blue` |
  | `done` | ✅ | `green` |
  | Bloqueado (link `is blocked by` a un issue abierto, o lo indica el usuario) | 🚫, con el motivo en la columna `Nota` | `red` |

- **El estado se escribe `<emoji> <nombre>`** (por ejemplo `✅ Done`), en la tabla y al mostrarla al usuario. El lozenge lo agrega `tracking` cuando escribe en ADF: no usar `{status:…}` en la tabla de seguimiento.
- **Una fila por hijo, una celda por estado.** Cambiar el estado de un hijo es reescribir solo la celda `Estado` de su fila. La línea `Progreso` es derivada: la skill la recalcula desde las filas en la misma escritura; si una persona edita a mano una celda, la próxima sincronización corrige el contador. Formato exacto, el mismo que escribe `tracking`: `**Progreso:** <done>/<total> ✅ · <en curso> 🔄 · <pendientes> ⬜`, con las tres cifras siempre, aunque alguna sea 0. Un hijo bloqueado cuenta solo como 🚫 y, si hay alguno, se agrega al final `· <bloqueados> 🚫` (por ejemplo `**Progreso:** 2/3 ✅ · 0 🔄 · 0 ⬜ · 1 🚫`). Todas las filas llevan el emoji de su estado, también las que no cambiaron.
- **Orden estable** por key numérica, para que agregar un hijo sea insertar una fila sin mover las demás.
- **Responsable**: nombre visible que devuelve Jira, o `—` sin asignar. No usar emails, account ids ni menciones.
- **PR**: solo `owner/repo#n` como texto, sin URL ni estado GitHub. La URL canónica vive una sola vez en `## Pull requests` de la Story. Poner un PR en una fila solo cuando ese hijo tiene un PR propio; si un PR cubre toda la Story, la celda queda `—`. Si ningún hijo tiene PR propio, omitir la columna; cuando un hijo nuevo trae el primero, `tracking` agrega la columna antes de `Nota` con `—` en las filas existentes.
- **Marcadores.** Los headings de este template (`## Objetivo`, `## Stories`, `## Problema`, `## Tareas`…) delimitan secciones: la skill reescribe una sección desde su heading hasta el siguiente `##` y no toca nada más. Por eso todo elemento, también un panel, vive dentro de una sección con heading.
- **Secciones opcionales solo con evidencia.** `## Bloqueo` y `## Decisiones` se agregan cuando el pedido, el diff o Jira las respaldan, y se quitan cuando dejan de aplicar (`section` con `markdown` vacío).

## Épica

```markdown
## Objetivo
<problema y resultado esperado, 1–2 oraciones>

## Alcance
- ✅ Incluye: <qué entra>
- ❌ Fuera de alcance: <qué no entra; omitir la línea si no aplica>

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
- `## Decisiones` es opcional y va después de `## Alcance`, igual que en la Story.

## Story

```markdown
## Bloqueo
> [!ERROR] Bloqueado
> <qué la frena y qué la destraba; si hay fecha, {date:YYYY-MM-DD}>

## Problema
<qué pasa hoy y a quién afecta, 1–2 oraciones>

## Solución
<qué resuelve este ticket, 1–2 oraciones>

<details><summary>Detalle técnico</summary>

- Áreas: <áreas de código o comportamiento que cambian>
- Cobertura automática: <qué prueban los tests>

</details>

## Criterios de aceptación
- <resultado verificable>
- <resultado verificable>

## Decisiones
> [!DECISION]
> - <decisión tomada y su motivo, en una línea>

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

- `## Bloqueo` va primero y solo mientras la Story esté frenada: un link `is blocked by` a un issue abierto, o lo indica el usuario. Al destrabarse se quita la sección entera.
- El expand `Detalle técnico` se usa en modo repositorio, con hasta 4 bullets de áreas técnicas y cobertura automática. En una tarea planificada sin diff se omite.
- Criterios de aceptación como bullets simples, no `- [ ]`: describen el resultado esperado, no el trabajo pendiente. Cuando el pedido indica cuáles ya se verificaron y cuáles no, anteponer ✅ o ⬜ a cada uno.
- `## Decisiones` solo cuando el pedido o el diff traen una decisión con su motivo (por ejemplo, la alternativa que se descartó).
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

Sin tabla, sin URLs de PR (puede nombrar el número y remitir a la Story) y sin repetir el problema de la Story. Una dependencia que frena la subtarea va como panel `WARNING` dentro de `## Qué hacer`.

## Lista de respaldo

Solo en modo Markdown, cuando la relectura muestra que la tabla no se renderizó: `tracking --list` la convierte en una lista anidada con el mismo orden y los mismos datos. Cada hijo es una línea con su emoji, su key y su título, y un sub-item por dato: `Estado` y `Responsable` siempre, `PR` si el hijo tiene PR propio y `Nota` si está bloqueado.

```markdown
## Tareas
**Progreso:** 1/3 ✅ · 0 🔄 · 1 ⬜ · 1 🚫

- ✅ [ACME-21](<SITE_URL>/browse/ACME-21) Migrar templates
  - Estado: Done
  - Responsable: Ana Pérez
  - PR: acme/payments-api#88
- 🚫 [ACME-22](<SITE_URL>/browse/ACME-22) Revisar con producto
  - Estado: To Do
  - Responsable: Luis Gómez
  - Nota: espera ACME-30
- ⬜ [ACME-23](<SITE_URL>/browse/ACME-23) PR testeado
  - Estado: To Do
  - Responsable: —
```

Cambiar un estado es tocar el emoji de la línea del hijo y su sub-item `Estado`. Una lista de respaldo de una versión anterior, con todos los datos en una línea (`<título> · <estado> · <responsable>`), se sigue actualizando en ese formato: no se migra sola.

## Operaciones

Toda escritura de la descripción de un padre (épica o Story) usa la relectura, `version` y el único retry de `Concurrencia de descripción padre` en `pr-traceability.md`.

La sección de seguimiento no se redacta a mano: se calcula con `scripts/jira-ticket.py tracking --level story|epic`, pasando por stdin `{"description": <descripción releída>, "children": [...]}` con cada hijo releído en Jira (`key`, `summary`, `status`, `category` = `statusCategory.key`, y opcionales `assignee`, `pr`, `blocked`, `note`). `description` es el documento ADF en modo enriquecido o el texto en modo Markdown, y el helper devuelve el mismo tipo. En los dos casos cambia solo la celda `Estado` (y `Nota` al bloquear o desbloquear) de los hijos que cambiaron, inserta las filas que faltan por key, recalcula `Progreso` y deja idéntico todo lo demás. Devuelve `description`, `changed`, `added`, `updated` y `rows_without_child` (filas cuyo hijo no vino en la entrada: se conservan y se informan). Con `changed: false` no se escribe. Sin sección devuelve `section: missing` y no la crea salvo `--create`.

Sobre un documento ADF, `tracking` escribe cada estado como emoji más lozenge, separa la sección nueva del relato con un divisor y reemplaza por la tabla una lista de seguimiento de viñetas, porque en ADF la tabla siempre se renderiza; para eso necesita todos los hijos de la lista en `children`.

Si el helper no puede ejecutarse, aplicar estas mismas reglas a mano en modo Markdown e informarlo.

### Crear

Redactar la variante del nivel sin la sección de seguimiento, compilarla y crear el issue. Después de crear los hijos, releerlos y agregar la sección con `tracking --create` y sus keys reales; nunca publicar filas con keys supuestas.

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
