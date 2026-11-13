# Contrato de campos JIRA

Leer antes de crear, editar o validar cualquier issue de `jira-ticket`. Los valores entre `<...>` salen de la configuración (ver [configuración](config.md)): `<NOMBRE>` es el valor de `JIRA_TICKET_NOMBRE` que informa `scripts/jira-ticket.py config`.

## Configuración

| Dato | Valor |
|---|---|
| `cloudId` | `<CLOUD_ID>` |
| `projectKey` | `<PROJECT_KEY>` (`<PROJECT_NAME>` si está definido) |
| Tablero | `<BOARD_ID>`; sin tablero configurado no se gestiona sprint |
| `assignee_account_id` por defecto | `<ASSIGNEE_ACCOUNT_ID>`; sin valor configurado, preguntar responsable o crear sin asignar e informarlo |
| Tipo padre nuevo | `<STORY_TYPE>` (por defecto `Story`) |
| Padre existente compatible | `<STORY_TYPE>`; conservar `<TASK_TYPE>` legacy válido sin duplicar ni convertir automáticamente |
| Tipo subtarea | `<SUBTASK_TYPE>` (por defecto `Sub-task`) |
| Campo quarter | `<QUARTER_FIELD>`, opcional |
| Campo fecha de inicio | `<START_DATE_FIELD>`, opcional |
| Campo sprint | `<SPRINT_FIELD>` (tipo `com.pyxis.greenhopper.jira:gh-sprint`), opcional |
| Campo de vencimiento | `duedate` (`Due date`, fecha `YYYY-MM-DD`), campo de sistema |
| Label fija | Ninguna |

Los ids de tipo y las opciones de campos se resuelven con la metadata del proyecto en cada ejecución; nunca se recuerdan entre proyectos.
Un campo opcional no configurado no se envía, no se valida y se muestra como `➖ no configurado` en el gate.
Configuración del tablero, sprint o componente no se deriva del nombre del repositorio.
No afirmar visibilidad en tablero sin comprobar su filtro.

## Metadata y requisitos

Antes de escribir, consultar tipos y metadata de `<PROJECT_KEY>` para cada tipo afectado, con `requiredFieldsOnly=true` para requisitos y reducción con `slim` para campos puntuales; paginar si hace falta.
Verificar campos editables con metadata de edición cuando integración permita consultarla; no suponer que pantalla de creación autoriza edición.

- Exigir que `<STORY_TYPE>` y `<SUBTASK_TYPE>` existan en el proyecto; si no existen, detener e informar qué variable revisar.
- Task legacy puede reutilizarse si ya representa el alcance; no crear una Story duplicada ni convertir el tipo sin pedido explícito.
- Esta skill conserva quarter, fecha de inicio y sprint (cuando están configurados) y asignación como contrato de seguimiento para padre y subtareas. No confundir ese contrato con requisitos de Jira.
- Si metadata cambia, no enviar campos u opciones ausentes. Informar incompatibilidad y pedir decisión antes de escribir parcialmente o inventar valores.
- Si aparecen requisitos nuevos sin default ni valor aportado, preguntar antes de crear.
- Conservar reporter por defecto; no copiar responsable a reporter automáticamente.

## Labels

Usar unión deduplicada de labels existentes, labels solicitadas y todos los `PR_LABELS`.
No agregar label fija. Preservar labels ajenos; no renombrarlos por migración de skill.
Con PR asociados, padre y subtareas llevan todos los `PR_LABELS`.
Sin PR ni labels solicitadas, conservar labels existentes; en creación puede omitirse `labels`.
URLs de PR pertenecen solo a descripción del padre.

## Quarter

Solo si `<QUARTER_FIELD>` está configurado. Calcular trimestre desde fecha de sistema en cada ejecución (`jira-ticket.py quarter`):

| Mes | Quarter |
|---|---|
| `01`–`03` | `1` |
| `04`–`06` | `2` |
| `07`–`09` | `3` |
| `10`–`12` | `4` |

El valor visible sigue `<QUARTER_FORMAT>` (por defecto `Q{quarter}/{yy}`). Resolver la opción exacta en `allowedValues` de `<QUARTER_FIELD>` para proyecto y tipo actuales (`jira-ticket.py quarter --metadata`).
Enviar array de opciones según schema:

```json
[{ "id": "<allowed-value-id>", "value": "<valor de quarter>" }]
```

No usar `name` ni reutilizar option IDs de otro proyecto. Si no existe la opción esperada, detener antes de escribir.
Padre y subtareas usan mismo quarter esperado.

## Sprint

Solo si `<SPRINT_FIELD>` y `<BOARD_ID>` están configurados. Nunca calcular nombre ni id del sprint: descubrirlo en Jira.
`<SPRINT_NAME_REGEX>` (opcional) describe el nombre de los sprints del tablero. Si define los grupos `year` y `quarter`, el sprint además debe coincidir en año y quarter con la fecha de sistema. Ejemplo de convención año, quarter, release y sprint: `^(?P<year>[0-9]{4})\.Q(?P<quarter>[1-4])\.R[0-9]+\.S[0-9]+$`.

### Descubrimiento

1. Consultar `project = <PROJECT_KEY> AND sprint in openSprints()` pidiendo solo `<SPRINT_FIELD>`; paginar hasta obtener resultados suficientes.
2. Pasar la respuesta a `jira-ticket.py sprint-pick`: conserva sprints únicos con `boardId` `<BOARD_ID>`, estado `<SPRINT_ACTIVE_STATE>` (por defecto `active`), nombre que cumpla `<SPRINT_NAME_REGEX>` si existe y año/quarter coincidentes si la regex los define.
3. Si queda exactamente uno (`ok`), usar su `id`. Si no queda ninguno o quedan varios (`none` o `ambiguous`), no elegir: informar candidatos y pedir sprint al usuario, o dejar el padre sin sprint si el usuario lo indica.
4. Un sprint aportado por el usuario (nombre o id) se verifica con el mismo tablero y formato. Aceptar un sprint `future` solo si el usuario lo pide explícitamente; nunca usar uno `closed` para trabajo nuevo.

Un fallo de la consulta no equivale a ausencia de sprint: reportar la causa y no escribir el campo con un valor supuesto ni recordado.
No crear, iniciar ni cerrar sprints.

### Asignación

| Operación | Valor |
|---|---|
| Crear padre | Sprint resuelto en el descubrimiento |
| Actualizar padre con sprint | Preservar sprint existente, incluso si quedó cerrado, salvo cambio explícito solicitado |
| Actualizar padre sin sprint | Sprint resuelto en el descubrimiento |
| Crear o actualizar subtarea | No enviar el campo: Jira asocia la subtarea al sprint del padre |

Enviar el `id` numérico del sprint (`"<SPRINT_FIELD>": <sprint-id>`), no el nombre ni un array.
No mover de sprint un padre en categoría `done`.
Después de escribir, releer padre y subtareas por key y verificar que muestren el sprint esperado. Si una subtarea no lo hereda, reportar key y estado sin forzar el campo.
Si Jira rechaza el campo, reportar el error y no reintentar con otro formato inventado.

## Fecha de inicio

Solo si `<START_DATE_FIELD>` está configurado.


| Operación | Valor |
|---|---|
| Crear padre desde diff | Fecha del primer commit desde base, `YYYY-MM-DD` |
| Crear tarea explícita | Fecha aportada; si falta, preguntar, sin asumir inicio hoy |
| Crear subtarea | Misma fecha del padre |
| Actualizar padre | Preservar fecha existente salvo cambio explícito solicitado |
| Completar fecha faltante | Fecha aportada, primer commit verificable en modo repositorio o fecha de seguimiento común de todas las subtareas existentes, según reglas siguientes |
| Actualizar subtarea | Misma fecha esperada del padre |

Para completar fecha faltante de un padre existente, priorizar fecha aportada por el usuario y después primer commit verificable en modo repositorio. Si ninguna está disponible, consultar todas las subtareas reales del padre directamente en Jira y verificar sus relaciones y fechas. Usar la fecha común como fecha de seguimiento del padre únicamente si existe al menos una subtarea, todas tienen fecha válida y todas coinciden. Informar que proviene de las subtareas y no afirmar que demuestra el inicio real del trabajo. Releer padre y subtareas antes de escribir, no reemplazar una fecha del padre agregada concurrentemente y verificar el campo después de actualizar.

Si no hay subtareas, alguna fecha falta, difieren o no se pueden consultar todas, no elegir una fecha ni asumir la actual: dejar el campo pendiente y solicitar fecha al usuario. Una fecha existente del padre se preserva salvo pedido explícito de cambio; nunca alterar fechas de subtareas para crear consenso.

## Fecha de vencimiento (Due date)

Campo de sistema `duedate`, opcional en Story y Sub-task. Nunca se deriva ni se asume: lo define el usuario.

### Cuándo preguntar

- Antes de crear cualquier issue (padre o subtareas nuevas), si el pedido no indica la fecha de vencimiento, preguntar al usuario si el ticket o los tickets tienen Due date. Hacer una sola pregunta, junto con los demás datos faltantes, que cubra:
  - Due date del padre: fecha concreta o sin Due date.
  - Due date de las subtareas: la misma del padre, una por subtarea o sin Due date.
- Se puede ofrecer como opción la fecha de fin del sprint resuelto, pero solo se usa si el usuario la elige.
- En issues existentes, preservar el Due date actual y cambiarlo solo por pedido explícito. Sin Due date existente, no preguntar salvo que se creen issues nuevos o el usuario lo pida.
- "Sin Due date" es una respuesta válida: omitir el campo y registrarlo como confirmado en el gate.

### Validación

- Aceptar solo fechas reales en formato `YYYY-MM-DD`.
- Si la fecha es anterior a la fecha de inicio del issue, o si la de una subtarea es posterior a la del padre, advertirlo y pedir confirmación antes de escribir.
- Enviar `"duedate": "<YYYY-MM-DD>"` solo cuando haya fecha confirmada; nunca enviar un valor vacío para "limpiar" una fecha existente salvo pedido explícito.
- Releer después de escribir y verificar la fecha de cada issue.

## Payloads conceptuales

Leer schema real de herramientas antes de invocarlas. Ejemplo de creación del padre:

```text
createJiraIssue(
  cloudId: "<CLOUD_ID>",
  projectKey: "<PROJECT_KEY>",
  issueTypeName: "<STORY_TYPE>",
  summary: "<resumen en español; prefijo repository_id cuando corresponda>",
  description: "<alcance solicitado en español>",
  contentFormat: "markdown",
  assignee_account_id: "<responsable solicitado o configurado>",
  additional_fields: {
    "labels": ["<labels solicitadas o existentes>", ...PR_LABELS],
    "<QUARTER_FIELD>": [{"id": "<quarter-option-id>", "value": "<valor de quarter>"}],   # solo si está configurado
    "<START_DATE_FIELD>": "<verified-start-date>",   # solo si está configurado
    "<SPRINT_FIELD>": <resolved-sprint-id>,   # solo si está configurado
    "duedate": "<due-date-confirmada, omitir si el usuario indicó sin Due date>"
  }
)
```

Para subtarea usar `issueTypeName: "<SUBTASK_TYPE>"`, `parent: "<story-key>"` y campos heredados del padre, sin `<SPRINT_FIELD>`. Verificar que padre pertenece a `<PROJECT_KEY>` y es Story, o Task legacy válido reutilizado. Cada hito solicitado necesita un issue hijo real: no publicar un checklist en su lugar.

Al editar, enviar solo campos con drift o correcciones del contrato. Preservar labels ajenos y contenido no relacionado.
Coordinar versión, relectura y merge según `pr-traceability.md`, incluso sin PR.
No mover issues entre proyectos ni cambiar su tipo como efecto lateral.

## Asignación

Crear con responsable configurado salvo responsable explícito distinto solicitado.
En issues existentes preservar responsable; si falta, asignar cuenta configurada mediante `assignee.accountId`.
Cambiar responsable existente solo por pedido explícito. No reasignar automáticamente para que aparezca bajo filtro del tablero.
Re-fetch y verificar cuenta esperada. Si cuenta no es asignable o faltan permisos, informar key y operación pendiente.
Conservar ticket creado y reanudar desde asignación; no crear alternativa ni afirmar éxito completo.

## Checklist bloqueante

Releer por key padre y subtareas y verificar:

- [ ] Proyecto `<PROJECT_KEY>`; nuevos padres `Story` y subtareas `Sub-task` con relación `parent` verificada.
- [ ] Padres existentes compatibles reutilizados sin duplicación; cada hito solicitado representado por issue hijo real, no checklist textual.
- [ ] Requisitos actuales de metadata cubiertos.
- [ ] Responsable previo preservado o responsable solicitado/configurado verificado.
- [ ] Todos los `PR_LABELS` y labels solicitadas presentes; labels ajenos preservados.
- [ ] Quarter contiene opción válida del trimestre esperado (si está configurado).
- [ ] Fecha de inicio (si está configurada) coincide con valor aportado, heredado o verificado; no reemplazar fecha existente por fecha actual.
- [ ] Si sprint está configurado, padre tiene sprint resuelto o preservado según sección Sprint, y cada subtarea muestra el sprint del padre.
- [ ] Due date de padre y subtareas coincide con lo confirmado por el usuario (fecha o sin Due date) o se preservó el existente.
- [ ] Subtareas contienen campos heredados correspondientes.

En tablas finales, columna Label significa labels solicitadas; mostrar `➖ no aplica` si no existen.
Corregir discrepancias y revalidar entidad afectada. No finalizar mientras contrato quede incumplido.
