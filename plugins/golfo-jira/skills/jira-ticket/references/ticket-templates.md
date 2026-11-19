# Templates de descripción por nivel

Leer antes de redactar o editar la descripción de una épica, una Story o una subtarea, y antes de agregar o actualizar los pasos de una subtarea. Este archivo define qué secciones lleva cada nivel. Cómo se escribe cada elemento (paneles, lozenges, expand, fechas), en qué formato se envía a Jira y cómo se edita una sección sin tocar el resto vive en [`rich-format.md`](rich-format.md); campos, labels y tipos, en [`jira-fields.md`](jira-fields.md); la sección `## Pull requests` y la concurrencia de escritura, en [`pr-traceability.md`](pr-traceability.md).

Los templates están en el Markdown enriquecido de `rich-format.md`: se compilan con `adf` (modo enriquecido) o `plain` (modo Markdown), nunca se envían tal cual.

## Reglas comunes

- **Poco texto.** Cada sección cabe en 1–3 líneas o hasta 4 bullets. Si hace falta más, el detalle va en un expand o en un hijo, no a la vista en el padre.
- **Sin repetir a Jira.** El panel de hijos de Jira ya muestra key, título, estado, responsable y barra de progreso de las Stories de una épica y de las subtareas de una Story. Por eso épicas y Stories **no llevan tabla de hijos ni de estados**: la descripción cuenta el porqué y el qué, y el avance se lee en ese panel.
- **La tabla de estados vive solo en la subtarea.** La subtarea es la unidad más chica de Jira: sus pasos no tienen issue propio que muestre su estado, así que ahí sí se lleva una tabla `## Pasos` con el estado de cada uno. Nunca crear una subtarea de una subtarea para eso.
- **Un paso no es un hito pedido.** Los hitos que el pedido nombra (`PR creado`, `PR testeado`…) siguen siendo subtareas reales de la Story. `## Pasos` desglosa el trabajo de una sola subtarea en tareas más chicas, y solo cuando el pedido, el diff o la subtarea las respaldan; no se inventan pasos.
- **Marcadores.** Los headings de este template (`## Objetivo`, `## Problema`, `## Qué hacer`, `## Pasos`…) delimitan secciones: la skill reescribe una sección desde su heading hasta el siguiente `##` y no toca nada más. Por eso todo elemento, también un panel, vive dentro de una sección con heading.
- **Secciones opcionales solo con evidencia.** `## Bloqueo`, `## Decisiones` y `## Pasos` se agregan cuando el pedido, el diff o Jira las respaldan, y `## Bloqueo` se quita cuando deja de aplicar (`section` con `markdown` vacío).
- **Seguimiento heredado.** Una épica o Story creada con una versión anterior de la skill puede tener una tabla `## Stories` o `## Tareas`. No se actualiza ni se borra sola: se deja como está y se quita solo si el usuario lo pide (`section` con `markdown` vacío).

## Épica

```markdown
## Objetivo
<problema y resultado esperado, 1–2 oraciones>

## Alcance
- ✅ Incluye: <qué entra>
- ❌ Fuera de alcance: <qué no entra; omitir la línea si no aplica>
```

- La épica no lleva `## Pull requests`: los PR viven en sus Stories.
- Sin tabla de Stories: el panel de hijos de la épica ya las muestra con su estado.
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

## Pull requests
- [acme/payments-api#88](https://github.com/acme/payments-api/pull/88)
```

- `## Bloqueo` va primero y solo mientras la Story esté frenada: un link `is blocked by` a un issue abierto (`open_blockers` de `dependency plan`, ver `dependencies.md`), o lo indica el usuario. Al destrabarse se quita la sección entera.
- El expand `Detalle técnico` se usa en modo repositorio, con hasta 4 bullets de áreas técnicas y cobertura automática. En una tarea planificada sin diff se omite. Nunca lleva links: ver `Links fuera del expand` en `rich-format.md`.
- Criterios de aceptación como bullets simples, no `- [ ]`: describen el resultado esperado, no el trabajo pendiente. Cuando el pedido indica cuáles ya se verificaron y cuáles no, anteponer ✅ o ⬜ a cada uno.
- `## Decisiones` solo cuando el pedido o el diff traen una decisión con su motivo (por ejemplo, la alternativa que se descartó).
- `## Pull requests` sigue `pr-traceability.md` y va siempre al final.
- Sin tabla de subtareas: el panel de subtareas de la Story ya las muestra con su estado y responsable.
- Story sin épica: es el nivel más alto; usa el mismo template y no se inventa una épica para colgarla.

## Subtarea (task)

```markdown
## Qué hacer
<1–3 bullets con el alcance>

## Cómo se valida
- <criterio de finalización verificable>

## Pasos
**Progreso:** 1/4 · ✅ 1 hecho · 🔄 1 en curso · ⬜ 1 pendiente · 🚫 1 bloqueado

| Paso | Estado | Nota |
|---|---|---|
| Copiar los templates al servicio nuevo | ✅ Hecho | — |
| Probar el envío en staging | 🔄 En curso | — |
| Revisar el copy con producto | 🚫 Bloqueado | espera la versión final del copy |
| Avisar a soporte | ⬜ Pendiente | — |
```

Sin URLs de PR (puede nombrar el número y remitir a la Story) y sin repetir el problema de la Story. Una dependencia que frena la subtarea entera va como panel `WARNING` dentro de `## Qué hacer`; un paso frenado se marca 🚫 en su fila, con el motivo en `Nota`.

`## Pasos` es opcional: va solo cuando la subtarea tiene tareas más chicas respaldadas por el pedido, el diff o la propia subtarea, y siempre al final. Una subtarea de un solo paso no la lleva.

### Estados de un paso y leyenda

Un paso no es un issue de Jira: su estado no se lee de Jira, se decide con la misma evidencia que un hito (`Subtareas reales` en `SKILL.md`). Sin evidencia, el paso queda ⬜ Pendiente. Que la subtarea esté en Done no marca solos sus pasos como hechos.

| `state` | Celda `Estado` | Lozenge (ADF) | Cuándo |
|---|---|---|---|
| `done` | ✅ Hecho | `green` | Hay evidencia de que se terminó |
| `in_progress` | 🔄 En curso | `blue` | Empezado, sin terminar |
| `todo` | ⬜ Pendiente | `neutral` | Sin empezar o sin evidencia |
| `blocked` | 🚫 Bloqueado | `red` | Frenado; el motivo va en `Nota` |

La línea `Progreso` es la leyenda de la tabla: cada número lleva su emoji y su nombre, para que se entienda sin conocer los emojis. Formato exacto, el mismo que escribe `tracking`:

`**Progreso:** <hechos>/<total> · ✅ <n> hecho(s) · 🔄 <n> en curso · ⬜ <n> pendiente(s)`

- Las tres cifras van siempre, aunque alguna sea 0, en singular con 1 y en plural con cualquier otro número (`✅ 1 hecho`, `✅ 0 hechos`, `⬜ 2 pendientes`).
- Si hay pasos bloqueados se agrega al final `· 🚫 <n> bloqueado(s)`; un paso bloqueado cuenta solo ahí.
- La línea es derivada: `tracking` la recalcula desde las filas en cada escritura; si una persona edita a mano una celda, la próxima sincronización corrige el contador.

Reglas de la tabla:

- **Una fila por paso, una celda por estado.** Cambiar el estado de un paso es reescribir solo su celda `Estado` (y `Nota` al bloquearlo o desbloquearlo).
- **El título identifica el paso.** Se compara sin mayúsculas ni espacios repetidos; renombrar un paso es una edición de la sección, no un cambio de estado.
- **Orden estable.** Los pasos nuevos se agregan al final; las filas existentes no se mueven.
- **Sin key ni responsable.** Un paso no tiene issue propio: si necesita key, responsable o PR propio, es una subtarea, no un paso.

## Lista de respaldo

Solo en modo Markdown, cuando la relectura muestra que la tabla no se renderizó: `tracking --list` la convierte en una lista anidada con el mismo orden y los mismos datos. Cada paso es una línea con su emoji y su título, con un sub-item `Estado` siempre y `Nota` si tiene.

```markdown
## Pasos
**Progreso:** 1/3 · ✅ 1 hecho · 🔄 0 en curso · ⬜ 1 pendiente · 🚫 1 bloqueado

- ✅ Copiar los templates al servicio nuevo
  - Estado: Hecho
- 🚫 Revisar el copy con producto
  - Estado: Bloqueado
  - Nota: espera la versión final del copy
- ⬜ Avisar a soporte
  - Estado: Pendiente
```

Cambiar un estado es tocar el emoji de la línea del paso y su sub-item `Estado`.

## Operaciones

La sección `## Pasos` no se redacta a mano: se calcula con `scripts/jira-ticket.py tracking`, pasando por stdin `{"description": <descripción releída de la subtarea>, "steps": [...]}` con cada paso (`title`, `state` = `done|in_progress|todo|blocked` y, opcional, `note`). `description` es el documento ADF en modo enriquecido o el texto en modo Markdown, y el helper devuelve el mismo tipo. Cambia solo las celdas `Estado` y `Nota` de los pasos que cambiaron, agrega al final los que faltan, recalcula `Progreso` y deja idéntico todo lo demás. Sin `note`, la nota actual se conserva, salvo al salir de 🚫, que vuelve a `—`. Devuelve `description`, `changed`, `added`, `updated`, `progress` y `rows_without_step` (filas cuyo paso no vino en la entrada: se conservan y se informan). Con `changed: false` no se escribe. Sin sección devuelve `section: missing` y no la crea salvo `--create`, que la agrega al final (en ADF, después de un divisor).

Si el helper no puede ejecutarse, aplicar estas mismas reglas a mano en modo Markdown e informarlo.

### Crear

- Épica y Story: redactar la variante del nivel, compilarla y crear el issue. No llevan sección de seguimiento.
- Subtarea con pasos: redactar `## Qué hacer` y `## Cómo se valida`, crear el issue y agregar los pasos con `tracking --create` sobre su descripción releída.

### Agregar un hijo a un padre existente

Aplica a una Story nueva bajo una épica existente y a una subtarea nueva bajo una Story existente: el hijo se cuelga con `parent` y **la descripción del padre no se toca**, ni sus campos (fechas, sprint, labels, responsable). El panel de hijos de Jira lo muestra solo.

### Actualizar el estado de un paso

1. Releer la descripción de la subtarea por key.
2. Decidir el `state` de cada paso con su evidencia.
3. Correr `tracking` (sin `--create`) con los pasos: reescribe solo las celdas que cambiaron y `Progreso`.
4. Si la subtarea no tiene `## Pasos`, no crearla solo por un cambio de estado, salvo pedido explícito o pasos respaldados por evidencia nueva.

El estado de los pasos no decide el estado de la subtarea ni el del padre: eso sigue `status-transitions.md` y los criterios de hitos de `SKILL.md`.
