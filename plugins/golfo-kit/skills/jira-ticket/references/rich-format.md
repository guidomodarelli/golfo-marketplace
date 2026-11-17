# Formato enriquecido de las descripciones

Leer antes de escribir o editar cualquier descripción en Jira. Define en qué formato se escribe, qué elemento de Jira se usa para cada papel y cómo se edita una descripción existente sin romper lo ajeno. Qué secciones lleva cada nivel vive en [`ticket-templates.md`](ticket-templates.md).

El objetivo es que el ticket se entienda de un vistazo: un ✅ o un 🚫 se ve antes de leer una palabra, un lozenge de color dice el estado sin leer la fila, y el detalle largo queda plegado para que no tape lo importante.

## Fuente única: Markdown enriquecido

Toda descripción nueva se redacta una sola vez, en Markdown con estas extensiones. El helper la convierte al formato que acepte Jira.

| Elemento de Jira | Cómo se escribe |
|---|---|
| Heading, negrita, cursiva, código, link | Markdown común |
| Lista y lista anidada | `- item` y sub-items con 2 espacios; `1.` para numeradas |
| Tabla | Tabla GFM |
| Divisor | `---` |
| Cita | `> texto` |
| Panel | `> [!INFO]`, `> [!NOTE]`, `> [!SUCCESS]`, `> [!WARNING]` o `> [!ERROR]`, con título opcional en la misma línea y el contenido en las líneas `>` siguientes |
| Decisión | `> [!DECISION]` y una línea `> - <decisión>` por cada una |
| Expand | `<details><summary>Título</summary>`, línea en blanco, contenido, línea en blanco y `</details>` |
| Status (lozenge) | `{status:<color>:<texto>}`; colores `neutral`, `blue`, `green`, `yellow`, `red`, `purple` |
| Fecha | `{date:YYYY-MM-DD}` |

## Modo de escritura

Jira guarda las descripciones en ADF (Atlassian Document Format). Paneles, lozenges, expand, decisiones y fechas solo existen ahí: el Markdown que convierte la integración no los genera. Por eso el modo se decide una vez por ejecución, mirando el schema real de las herramientas de escritura de Jira (`createJiraIssue`, `editJiraIssue`):

| Modo | Cuándo | Cómo se escribe |
|---|---|---|
| **Enriquecido** (preferido) | El parámetro de formato de la descripción (`contentFormat`) admite `adf` y el helper se puede ejecutar | `jira-ticket.py adf` (Markdown enriquecido por stdin) devuelve el documento ADF; enviarlo como `description` con `contentFormat: "adf"` |
| **Markdown** (respaldo) | La herramienta no admite `adf`, o el helper no se puede ejecutar | `jira-ticket.py plain` (mismo Markdown enriquecido por stdin) devuelve Markdown sin elementos exclusivos de ADF; enviarlo con `contentFormat: "markdown"` |

- Leer en el mismo formato en que se escribe: en modo enriquecido, pedir la descripción en ADF (el parámetro de formato de respuesta de `getJiraIssue`, si existe) y pasar ese documento tal cual al helper. Leer en Markdown y reescribir ese texto borra paneles, lozenges y expands que ya estaban.
- Si Jira rechaza el documento ADF por un nodo, quitar ese elemento según la columna `Respaldo` de la tabla siguiente y reintentar una sola vez. Si vuelve a fallar, pasar a modo Markdown para esa ejecución e informarlo.
- En modo Markdown, releer después de escribir: si la tabla de seguimiento quedó aplanada como texto, convertirla a lista anidada con `tracking --list` (ver `ticket-templates.md`).
- Informar el modo usado en la respuesta final solo cuando fue el de respaldo, con el motivo en una línea.

## Un elemento por papel

Cada elemento tiene un único uso. Mezclarlos o usarlos de adorno le quita valor a la señal.

| Papel | Elemento | Respaldo en modo Markdown |
|---|---|---|
| Seguimiento de hijos (stories, subtareas) | Tabla con emoji y lozenge de estado | Tabla GFM; si no renderiza, lista anidada con emoji |
| Estado de un hijo | Emoji por categoría más lozenge con el nombre real del estado: ⬜ `neutral`, 🔄 `blue`, ✅ `green`, 🚫 `red` | Emoji y nombre del estado como texto |
| El ticket está frenado | Panel `ERROR` arriba de todo, en su sección `## Bloqueo` | Cita `> 🚫 **Bloqueado**` |
| Algo que el lector debe saber antes de actuar (dependencia, ventana de despliegue, riesgo) | Panel `WARNING` dentro de la sección que afecta | Cita `> ⚠️ **<título>**` |
| Contexto útil que no cambia la acción | Panel `INFO` | Cita `> ℹ️ **<título>**` |
| Decisión tomada y su motivo | Decisión (`[!DECISION]`) | Cita `> 🧭 **Decisiones**` con una viñeta por decisión |
| Detalle largo o técnico (áreas de código, cobertura, pasos) | Expand con título que diga qué hay adentro | Título en negrita y el contenido debajo |
| Cita textual del pedido o de una persona | Cita | Cita |
| Fecha comprometida dentro del texto | Fecha (`{date:}`) | Fecha `YYYY-MM-DD` como texto |
| Lo que entra y lo que no | Lista con ✅ y ❌ al inicio de cada línea | Igual |
| Separar el relato del seguimiento | Divisor; lo agrega `tracking --create`, no se escribe a mano | Sin divisor |

Reglas de uso:

- **Emoji primero.** En cualquier lista o celda que exprese un estado o un sí/no, el emoji va al inicio: ✅ hecho o incluido, ❌ no o fuera de alcance, ⬜ pendiente, 🔄 en curso, 🚫 bloqueado, ⚠️ atención, ➖ no aplica. El emoji es texto y se ve igual en web, mobile y notificaciones; el lozenge suma color donde se renderiza.
- **Tabla o lista anidada.** Para seguir varios ítems con tres o más datos cada uno, tabla. Si la tabla no es posible, lista anidada: una línea con emoji y nombre del ítem, y un sub-item `Campo: valor` por dato. No comprimir varios datos en una sola línea separada por símbolos.
- **Como máximo dos paneles por ticket.** Si todo está resaltado, nada lo está. Un panel lleva 1–3 líneas.
- **El expand no esconde lo necesario.** Problema, solución, criterios y seguimiento quedan a la vista; se pliega lo que solo consulta quien implementa o revisa.
- **Las fechas de los campos no se repiten.** Fecha de inicio, Due date y sprint viven en sus campos; `{date:}` es para fechas que solo existen en el texto (hasta cuándo dura un bloqueo, un hito intermedio).
- **Solo con evidencia.** Un panel de bloqueo, una decisión o una fecha se escriben cuando el pedido, el diff o Jira los aportan. No se inventan para completar el template.

## Qué no se usa

| Elemento | Motivo |
|---|---|
| Lista de tareas con casillas (`- [ ]`, action items) | El trabajo son issues hijos reales; una casilla no tiene estado, responsable ni historial |
| Mención (`@persona`) | Notifica a la persona; el responsable va como nombre visible en la tabla |
| Smart link con estado en vivo | La tabla ya trae el estado releído de Jira; en notificaciones y exports queda como URL |
| Mermaid | Jira Cloud no lo renderiza sin una app del Marketplace |
| Bloques sincronizados, listas de Confluence, layouts en columnas | Son de Confluence o dependen de contenido que vive fuera del ticket |
| Colores de texto o de fondo de celda | El color con significado lo dan el lozenge y el panel |

## Editar una descripción existente

Nunca se recompila la descripción entera: eso pierde nodos que escribió una persona (imágenes, menciones, texto con otro formato). Se cambia solo la sección pedida, sobre la descripción releída:

| Cambio | Comando |
|---|---|
| Seguimiento de hijos | `jira-ticket.py tracking --level story\|epic [--create]`, con `{"description": <releída>, "children": [...]}` por stdin |
| Reescribir, crear o quitar una sección | `jira-ticket.py section --heading "<texto del heading>" [--before "<heading>"]`, con `{"description": <releída>, "markdown": "<contenido en Markdown enriquecido, sin el heading>"}` por stdin; `markdown` vacío quita la sección |

- `description` es el documento ADF en modo enriquecido o el texto en modo Markdown; el helper devuelve el mismo tipo en `description` y `changed: false` cuando no hay nada que escribir.
- Una sección va de su heading de nivel 2 hasta el siguiente heading de nivel 1 o 2. Todo lo que está fuera queda idéntico.
- En modo Markdown, pasar por `plain` el contenido de `markdown` antes de enviarlo a `section`.
- Contenido sin headings, o un cambio dentro de un párrafo ajeno: editar a mano el nodo o la línea mínima y dejar el resto igual.
- La concurrencia de la escritura (relectura, `version` y único retry) sigue `Concurrencia de descripción padre` en [`pr-traceability.md`](pr-traceability.md).
