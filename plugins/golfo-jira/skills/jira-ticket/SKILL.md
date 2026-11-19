---
name: jira-ticket
description: >
  Crea o actualiza una Story de JIRA con subtareas reales (Sub-task) en el proyecto configurado por variables de entorno
  JIRA_TICKET_* (sitio, proyecto, tablero, campos), a partir del pedido del usuario o de los cambios de cualquier repositorio Git.
  Construye el alcance desde el diff, sincroniza padre y subtareas, completa quarter, fecha de inicio y sprint activo cuando están
  configurados, pregunta si los tickets tienen Due date, enlaza uno o varios pull requests en ambos sentidos y mueve a Done el trabajo
  cuando todos sus PRs están fusionados. Usar cuando se pida crear, actualizar o sincronizar un ticket de Jira desde los cambios actuales
  o asociarlo con pull requests; también crea épicas, cuelga stories de una épica existente sin pisar su contenido y lleva en cada
  subtarea una tabla de pasos con su estado y leyenda de progreso. Usa formato enriquecido de Jira (paneles,
  estados) y emojis. Reutiliza tickets existentes, crea y asigna faltantes y agrega label jira-ticket al PR tras verificar
  vínculo.
metadata:
  plugin-dependencies: "golfo-github"
---

# Jira Ticket

Crear o actualizar **Stories con subtareas reales (`Sub-task`)** en el proyecto Jira configurado, desde pedido explícito o cambios del repositorio actual.
Crear padres nuevos como `<STORY_TYPE>`; reutilizar Stories existentes y Tasks legacy válidos sin duplicar ni convertir automáticamente. La épica es opcional: se crea solo cuando el pedido la pide, y una épica existente recibe Stories nuevas sin perder su contenido. Los hitos solicitados se gestionan como issues hijos, no como checklists textuales en la descripción. Épicas y Stories no llevan tabla de hijos ni de estados, porque el panel de hijos de Jira ya los muestra; la tabla de estados vive solo en la subtarea, la unidad más chica de Jira, para sus pasos.
Las descripciones se escriben para leerse de un vistazo: secciones cortas, emoji al inicio de todo lo que expresa un estado y los elementos enriquecidos de Jira (paneles, lozenges de estado, expand, decisiones, fechas) con un papel fijo cada uno, según [formato enriquecido](references/rich-format.md).
La skill no contiene datos de ninguna organización: sitio, proyecto, tablero, ids de campos, responsable y convenciones llegan por variables `JIRA_TICKET_*` ([configuración](references/config.md)). En este documento, `<NOMBRE>` es el valor de `JIRA_TICKET_NOMBRE`.
Requiere la integración Atlassian (MCP) y la memoria persistente disponible en el entorno; Git y GitHub CLI solo cuando hay cambios o PR asociados.
Crear en proyecto `<PROJECT_KEY>`; no inventar componente, equipo ni label para forzar visibilidad en tablero.
El sprint se descubre en Jira según `jira-fields.md`; nunca se calcula ni se inventa.

> **NUNCA ejecutar `git push`, `git push --force` ni otro comando de upload Git durante esta skill.**
> Gestión de tickets es independiente de publicación del repositorio.

## Mapa del flujo

| Paso | Qué resuelve | Referencia |
|---|---|---|
| 0 | Configuración y features activas | `config.md` |
| 1 | Modo (tarea explícita o repositorio), campos, Due date y PRs | `jira-fields.md` |
| 2 | Padre existente o creación, y épica | `pr-traceability.md` |
| 3 | Alcance desde el diff (solo modo repositorio) | — |
| 4 | Summary, descripción y subtareas deseadas | `ticket-templates.md`, `rich-format.md` |
| 5 | Crear o actualizar issues y los pasos de las subtareas | `jira-fields.md`, `ticket-templates.md` |
| 6 | Trazabilidad Jira ↔ PR | `pr-traceability.md` |
| 7 | Estado del padre | `status-transitions.md` |
| 8 | Gate final | — |
| 9 | Memoria y reporte | — |

## Alcance estricto

Ejecutar únicamente acciones necesarias para crear, actualizar, asociar, transicionar y validar ticket JIRA solicitado.

- Leer diff solo como evidencia para redactar alcance, subtareas y cobertura del ticket; no tratarlo como pedido implícito de review.
- No iniciar code review, security audit, dependency audit, performance review ni análisis adicional salvo pedido explícito del usuario.
- No ejecutar tests, builds, linters, scanners ni comandos de validación del repositorio salvo pedido explícito.
- No invocar skills, agentes o workflows ajenos al flujo Jira salvo pedido explícito. Si una regla de mayor prioridad obliga una invocación, limitarla a determinar aplicabilidad y volver al flujo; no expandirla a auditoría o implementación.
- No modificar código, dependencias, configuración, comentarios de review, approvals ni estado del PR.
- Únicos writes externos permitidos: issues JIRA, transiciones JIRA, backlink Jira body-only y label `jira-ticket` sobre PR asociado al flujo solicitado, incluida creación de esa label en su repositorio si falta.
- Si una acción no es requisito directo para completar sincronización Jira pedida, omitirla.
- Pedidos laterales fuera de este alcance (push, cambiar título del PR, escribir archivos del repositorio, publicar en otros canales): declinarlos en una sola línea que los nombre por su efecto (por ejemplo «el push de la rama», no el comando literal), sin reproducir comandos ni listarlos como pasos, y continuar con el flujo Jira.

## Idioma obligatorio

Todo contenido visible para personas debe estar en español:

- Summary y description del padre.
- Summary y description de subtareas.
- Encabezados, bullets, tablas, validaciones, advertencias y respuesta final.
- Notas persistidas en memoria.

Conservar en inglés solo identificadores y valores técnicos que deban coincidir con sistemas externos:
paths, symbols, packages, endpoints, labels, field keys, estados/transiciones JIRA (`To Do`,
`In Progress`, `Create New Release`, `Done`) y estados GitHub (`OPEN`, `CLOSED`, `MERGED`).
`## Pull requests` es única excepción de heading: funciona como marker técnico canónico para trazabilidad.

Redactar contenido nuevo o modificado en español. Preservar texto existente fuera del alcance solicitado, aunque esté en otro idioma.
Antes de cualquier write, validar contenido redactado en español.

## Contrato de responsabilidades

| Artefacto | Responsabilidad |
|---|---|
| Épica JIRA (opcional) | Objetivo y alcance; sin tabla de Stories |
| Padre JIRA | Problema, solución breve (áreas técnicas y cobertura automática en modo repositorio), criterios de aceptación y links canónicos de PR; sin tabla de subtareas |
| Subtareas JIRA | Issues `<SUBTASK_TYPE>` para unidades del diff o hitos explícitamente solicitados; describen qué hacer, cómo se valida y, si los hay, sus pasos en una tabla de estados |
| Pull request | Resumen para reviewer, tipo de cambio, pruebas manuales, contratos HTTP y notas opcionales |
| Skill sobre PR | Agregar o normalizar backlink al padre JIRA y label `jira-ticket` |

Reglas de separación:

- No copiar descripción JIRA dentro del PR ni cuerpo PR dentro de JIRA.
- Cobertura automática pertenece al padre JIRA; validación manual pertenece al PR.
- Contratos HTTP orientados a reviewer pertenecen a `Cambios en la API` del PR; JIRA describe área técnica sin duplicar matriz de endpoints.
- La skill nunca regenera título o body con `pr-description-template`; aplica parche `traceability-only`.
- Subtareas nunca reciben sección de links PR.

## Referencias por fase

- Antes de cualquier consulta a Jira, leer [configuración](references/config.md) y ejecutar `scripts/jira-ticket.py config` (Paso 0).

- Antes de crear, editar o validar cualquier issue, leer
  [contrato de campos JIRA](references/jira-fields.md).
- Cuando existan asociaciones PR, y siempre durante update aunque no haya PR nuevo, leer
  [contrato de trazabilidad](references/pr-traceability.md).
- Antes de decidir o modificar estado del padre, leer
  [máquina de estados](references/status-transitions.md).
- Antes de redactar o editar la descripción de una épica, Story o subtarea, de agregar un hijo a un padre existente
  o de agregar o actualizar los pasos de una subtarea, leer [templates por nivel](references/ticket-templates.md).
- Antes de escribir o editar cualquier descripción, leer [formato enriquecido](references/rich-format.md): decide el modo de
  escritura (ADF o Markdown de respaldo), qué elemento de Jira corresponde a cada papel y cómo editar una sola sección.

## Consultas acotadas y helper

Toda consulta pide solo lo necesario. Escribir cada llamada en una sola línea, con sus parámetros:

```text
searchJiraIssuesUsingJql(jql: "project = <PROJECT_KEY> AND labels = \"<repository_id>/PR-<n>\"", fields: ["summary","status","labels","issuetype","parent","subtasks"], maxResults: <MAX_RESULTS>)
searchJiraIssuesUsingJql(jql: "project = <PROJECT_KEY> AND sprint in openSprints()", fields: ["<SPRINT_FIELD>"], maxResults: <MAX_RESULTS>)
getJiraIssue(issueIdOrKey: "<KEY>", fields: ["<solo los campos a verificar>"])
getJiraIssueTypeMetaWithFields(issueTypeId: "<id>", requiredFieldsOnly: true)
```

- Nunca omitir `fields`, pedir `*all` ni subir `maxResults` por encima de `<MAX_RESULTS>`; paginar con el token devuelto.
- Para un campo puntual de metadata (quarter, sprint, Due date), reducir la respuesta con `slim`.
- Releer por key (`getJiraIssue`), nunca por JQL, todo issue recién creado o editado: el índice de búsqueda demora y puede omitirlo.
- La lógica determinista la resuelve `scripts/jira-ticket.py` (salida JSON; exit `3` = no resuelto: preguntar o reportar, nunca suponer; exit `4` = configuración incompleta). No hace falta leer su código; este es su contrato:

| Subcomando | Uso |
|---|---|
| `config` | Configuración resuelta, origen de cada valor, features activas y variables obligatorias faltantes |
| `quarter [--date] [--metadata]` | Valor de quarter según `<QUARTER_FORMAT>`; con createmeta por stdin, opción exacta de `<QUARTER_FIELD>` |
| `sprint-pick [--date]` | Sprint activo de `<BOARD_ID>` desde la respuesta de `sprint in openSprints()` (`ok`, `none`, `ambiguous`) |
| `repo-id [--root]` | `repository_id` según `<REPO_ID_SOURCES>` y `<REPO_PREFIXES>` |
| `pr-normalize <n\|url>...` | `pull_requests`, `pr_labels` y `all_prs_merged` leídos de GitHub |
| `backlink apply\|verify --key <KEY>` | Parche `traceability-only` idempotente del body del PR (stdin → stdout) con links a `<SITE_URL>` |
| `adf` | Documento ADF desde Markdown enriquecido por stdin, para escribir con `contentFormat: "adf"` (`rich-format.md`); rechaza un expand con links, porque Jira no los vuelve clickeables ahí |
| `plain` | El mismo Markdown enriquecido sin elementos exclusivos de ADF, para el modo Markdown de respaldo |
| `section --heading <texto> [--before <heading>]` | Una sola sección reescrita, creada o quitada desde `{description, markdown}` por stdin; el resto de la descripción queda idéntico |
| `tracking [--create] [--list]` | Tabla `## Pasos` de una subtarea actualizada desde `{description, steps}` por stdin: celdas `Estado` y `Nota`, pasos nuevos y leyenda `Progreso`, sin tocar el resto (`ticket-templates.md`). `description` es el documento ADF o el texto Markdown releído; `--list` deja los pasos Markdown como lista anidada |
| `slim --fields <ids>` | Reduce respuestas grandes de JQL, createmeta o issue a los campos pedidos |

Si el script no puede ejecutarse, aplicar las mismas reglas de las referencias manualmente e informarlo.

## Paso 0 — Resolver configuración

Ejecutar `scripts/jira-ticket.py config`. Si informa `missing_required`, detener sin consultar Jira y decir al usuario qué variables definir y en qué archivo (`~/.config/jira-ticket/env` por defecto). Usar `features` para saber qué campos opcionales gestionar: un campo no configurado no se envía ni se valida.

## Invariantes bloqueantes

- No crear duplicado cuando ticket ya existe.
- No eliminar labels ajenos ni asociaciones previas porque el pedido no los mencione.
- Padre y cada subtarea terminan con labels, quarter, fecha de inicio y sprint verificados; el sprint se asigna solo al padre y las subtareas lo heredan.
- Ningún issue nuevo se crea sin preguntar antes por su Due date (o sin que el pedido lo indique); la respuesta se respeta tal cual, incluido "sin Due date".
- Todo PR normalizado produce label `<repository_id>/PR-<number>` en padre y subtareas.
- URLs canónicas viven solo en sección `## Pull requests` del padre.
- Identidad y estado PR siempre provienen de GitHub; nunca inferirlos.
- Lookup por labels precede memoria y conflictos de padre detienen flujo.
- Cierre automático requiere colección PR no vacía y todos verificados `MERGED`; cierre manual sin PR sigue confirmación y reglas de `status-transitions.md`.
- Cada PR asociado termina con label GitHub `jira-ticket` y backlink a un padre existente verificado.
- Asignación de padre y subtareas se verifica según `jira-fields.md`.
- Trazabilidad bidireccional debe pasar antes de transición.
- Gate final debe pasar antes de memoria y respuesta exitosa.
- En modo repositorio, checkout actual y diff contra base son fuente de verdad para alcance.
- En modo tarea explícita, pedido del usuario y contenido actual del issue son fuente de alcance; no exigir Git ni inventar implementación, tests o PR.
- Toda búsqueda JQL queda limitada a `project = <PROJECT_KEY>`; rechazar keys y padres de otros proyectos sin migrarlos.

## Paso 1 — Resolver contexto

Elegir modo según pedido:

- **Tarea explícita:** crear o editar desde descripción y key aportadas. Consultar issue existente, limitar edición a campos pedidos y conservar resto. Preguntar solo por datos imprescindibles ausentes. Sin repositorio, usar `<PROJECT_KEY>` como project de memoria y omitir prefijo de repositorio, análisis de diff y comandos Git/GitHub. Crear subtareas reales por unidades de trabajo o hitos solicitados; no sustituirlas por checklists. Si el pedido no contiene desglose, no inventarlo.
- **Repositorio:** si usuario pide derivar alcance desde cambios, resolver contexto siguiente. No incorporar diff incidental a una tarea explícita.

Resolver root y base branch en modo repositorio:

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
BASE_BRANCH=$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null)
```

Conservar ref remoto (`origin/main`): puede no existir branch local. Si remote HEAD falta, elegir primer ref existente según `git rev-parse --verify --quiet`: `origin/develop`, `origin/main`, `origin/master` y después `develop`, `main`, `master`. Preguntar solo si ninguno existe.

Resolver `repository_id` con `scripts/jira-ticket.py repo-id`: recorre `<REPO_ID_SOURCES>` en orden (por defecto `name` de `package.json` sin scope npm y después basename de root) y quita `<REPO_PREFIXES>` del basename.

Usar `repository_id` en prefix de summary (`[<repository_id>]`) y como project de memoria. No hardcodear nombre de repositorio.

Leer `jira-fields.md` y, para cada campo opcional activo en `features`, derivar quarter y su option id y descubrir el sprint activo del tablero según sus secciones antes de cualquier write. Si el sprint no se resuelve sin ambigüedad, preguntar antes de crear.

Si se van a crear issues y el pedido no indica la fecha de vencimiento, preguntar al usuario si el padre y las subtareas tienen Due date según la sección `Fecha de vencimiento (Due date)` de `jira-fields.md`. Agrupar esa pregunta con los demás datos faltantes en una sola consulta.

Recolectar números/URLs PR explícitos y PR identificable sin ambigüedad desde branch actual. Si hay PR, leer
`pr-traceability.md`, validar inputs y construir `PULL_REQUESTS`, `PR_LABELS` y `ALL_PRS_MERGED`.

## Paso 2 — Descubrir padre existente

Aplicar precedencia:

1. **Key JIRA explícita:** fetch primero; exigir project `<PROJECT_KEY>` y tipo `<STORY_TYPE>`, o `<TASK_TYPE>` legacy válido para reutilización. Si es `<SUBTASK_TYPE>`, resolver y verificar su padre. Rechazar otros tipos como padre sin convertirlos ni crear duplicados.
2. **Lookup JQL por cada `PR_LABELS`:** preferido cuando hay PR. Todos deben resolver al mismo padre; conflicto detiene flujo.
3. **Referencias del PR:** verificar referencias JIRA estructuradas del body y resolver padre antes de memoria.
4. **Memoria:** fallback cuando labels y referencias no encuentran ticket.
5. **Creación:** si no existe padre después de búsquedas exitosas, crear y asignar según `jira-fields.md`, también cuando solicitud sea asociar PR. Respetar pedido explícito de no crear.

Épica del padre nuevo: si el pedido indica una épica, verificarla por key (tipo `Epic`, proyecto `<PROJECT_KEY>`) y enviarla como `parent` de la Story. Rechazar épicas de otro proyecto e informarlo en una sola línea con la key y el motivo. Sin épica indicada, no inventarla: si hay candidatas plausibles, preguntar cuál usar; si no hay, crear sin épica e informarlo. Si el pedido pide una épica nueva, crearla primero según `Épica` de `jira-fields.md` y colgar de ella las Stories. Al colgar una Story de una épica existente, la descripción y los campos de la épica no se tocan (`Agregar un hijo a un padre existente` de `ticket-templates.md`).

Para memoria:

```text
mem_search(
  query="<PROJECT_KEY> <issue-key-or-feature-name>",
  project="<repository_id-or-<PROJECT_KEY>>",
  scope="project"
)
```

Antes de crear, inspeccionar también referencias JIRA estructuradas en body del PR y verificar cada candidato
con fetch de JIRA. Reutilizar padre <PROJECT_KEY> válido; si referencia es subtarea, resolver su padre.
Ejecutar control de conflictos entre key explícita, labels y referencias del PR antes de aceptar memoria.
Label GitHub `jira-ticket` no identifica padre por sí mismo. Referencias múltiples o contradictorias
requieren resolver conflicto; no crear otro ticket ni elegir arbitrariamente.
Una referencia del body a otro ticket que describe un alcance distinto (por ejemplo, trabajo consolidado de otro PR con su propio ticket) no es conflicto cuando hay key explícita o el usuario eligió el padre: preservarla tal cual y no agregar a ese otro ticket labels ni backlinks salvo pedido.

Lookup fallido por permisos, conexión o dependencia ausente no equivale a ausencia de ticket.
Si no se puede completar discovery, obtener campos obligatorios o crear/asignar, reportar causa concreta,
PR afectado y acción pendiente. No afirmar éxito ni agregar label nuevo hasta verificar vínculo.
Si creación devuelve timeout o resultado incierto, buscar ticket creado antes de reintentar;
si no se puede confirmar resultado, detener sin repetir creación.

Durante update, leer siempre `pr-traceability.md`, fetch padre y subtareas, redescubrir URLs persistidas,
renormalizar colección completa y repetir control de conflictos antes de editar.

Antes de crear sin PR ni key, buscar también candidatos por alcance y responsable con JQL acotado a `project = <PROJECT_KEY>`; verificar candidatos con fetch. Si hay varios plausibles, preguntar en vez de duplicar.

## Paso 3 — Analizar diff

Omitir en modo tarea explícita. En modo repositorio, ejecutar contra `BASE_BRANCH`:

```bash
git log "$BASE_BRANCH"..HEAD --oneline
git diff "$BASE_BRANCH"...HEAD --stat
git diff "$BASE_BRANCH"...HEAD --name-only
git log "$BASE_BRANCH"..HEAD --reverse --format="%aI" | head -1
test -f package.json && grep -E '"[a-z-]+":\s*"[0-9]' package.json | head -20
```

Usar fecha del primer commit (`YYYY-MM-DD`) como start date de padre nuevo. Commits sirven solo para comprender alcance; no copiar lista a JIRA.

Leer archivos representativos por responsabilidad:

- Producción: components, routes, controllers, services, hooks, utilities, config.
- Presentación: styles, templates, stories, assets, copy.
- Contratos: types públicos, schemas, API definitions, manifests, migrations.
- Validación: unit, integration, E2E, fixtures, snapshots.
- Documentación y release metadata cuando cambien.

No asumir framework, lenguaje, layout o package manager desde nombre de repositorio.

## Paso 4 — Construir modelo deseado

### Summary padre

```text
[<repository_id>] <descripción imperativa y concisa en español>
```

Ejemplo: `[payments-api] Corrige validación de registro`.
Sin repositorio, usar resumen conciso sin prefijo. Para tareas planificadas, describir trabajo esperado y criterios de aceptación; no afirmar cambios implementados ni cobertura ejecutada. Omitir secciones sin evidencia. En edición explícita, conservar estructura y contenido ajenos al pedido; no traducir ni regenerar texto ajeno sin autorización.

### Description padre

Usar la variante `Story` de [`ticket-templates.md`](references/ticket-templates.md) (y `Épica` cuando se crea una), redactada en el Markdown enriquecido de [`rich-format.md`](references/rich-format.md) y compilada con `adf` o `plain` según el modo de escritura resuelto. Los elementos enriquecidos se usan solo en su papel y con evidencia: panel de bloqueo si el ticket está frenado, expand para el detalle técnico (sin links adentro: Jira no los vuelve clickeables), decisiones cuando el pedido o el diff las traen. La Story no lleva tabla de subtareas ni la épica tabla de Stories. `## Pull requests` se agrega solo cuando hay asociaciones y sigue contrato de `pr-traceability.md`. En una edición, una descripción existente con otra estructura no se migra a este template: los cambios de contenido pedidos y el drift del diff se corrigen dentro de su estructura, preservando el contenido ajeno al pedido. Agregar un hijo no toca la descripción del padre. Toda edición parte de la descripción releída y cambia una sección por vez con `section` (o `tracking` para los pasos de una subtarea); nunca se recompila la descripción entera.

No incluir:

- Pasos de pruebas manuales.
- Sección JIRA `Cambios en la API` o matriz de endpoints del PR.
- Lista de commits.
- Texto copiado literalmente del PR.

### Subtareas reales

Crear issues `<SUBTASK_TYPE>` relacionados mediante `parent` con la Story, no checklists `- [ ]` o `- [x]` que pretendan reemplazarlos. Checklists internos de esta guía son controles del agente, no subtareas publicadas.

Derivar cada subtarea de una unidad cohesiva real o de un hito pedido explícitamente:

- Área independiente de código o comportamiento público.
- Contrato, configuración, migración o dependencia sustancial.
- Cobertura/documentación cuando formen unidad significativa.
- Hitos solicitados, como `Migración de templates`, `PR creado` y `PR testeado`: crear una subtarea por hito y por Story, aunque sean hitos de seguimiento.

Antes de crear, leer subtareas existentes y comparar alcance, no solo título. Reutilizar equivalentes y crear únicamente faltantes. No inventar hitos no pedidos.

Al reemplazar un checklist existente, trasladar alcance, evidencia y pendientes a subtareas; retirar únicamente el checklist solicitado después de verificar su creación. Preservar contenido ajeno y links canónicos de PR en el padre. Si falla una creación, conservar seguimiento pendiente y reportar claves confirmadas, sin duplicarlas al reanudar.

Description de cada subtarea sigue la variante `Subtarea` de `ticket-templates.md` (qué hacer, cómo se valida y, si tiene tareas más chicas respaldadas por evidencia, la tabla `## Pasos` con su estado) en español; no reproduce estructura completa del padre ni incluye URLs PR. Puede mencionar número de PR y remitir al padre. Los pasos no reemplazan subtareas: un hito pedido sigue siendo una subtarea real.

Estados de hitos se determinan por su propio criterio, no por el estado de la Story:

- Migración: distinguir template migrado en panel, integración implementada, merge y despliegue; completar solo el alcance acreditado.
- `PR creado`: existencia verificada en GitHub cumple ese hito sin exigir merge.
- `PR testeado`: requiere evidencia de validación funcional del flujo y resultado esperado; para emails, recepción de correos. CI y cobertura no bastan.
- Mantener pendiente aquello sin evidencia; `[x]` previo, estado Done del padre y memoria no acreditan finalización por sí mismos.

Consultar transiciones por subtarea antes de cambiar estado y verificar resultado. Completar un hito no cierra ni reabre automáticamente la Story; reglas de cierre por merge se aplican al padre, no al hito `PR creado`.

## Paso 5 — Sincronizar JIRA

### Crear

1. Leer payloads en `jira-fields.md`.
2. Crear padre con `issueTypeName: "<STORY_TYPE>"`, description deseada en el modo de escritura resuelto (`rich-format.md`), campos obligatorios, sprint resuelto y Due date confirmado, si lo tiene.
3. Crear issues `<SUBTASK_TYPE>` independientes con `parent` igual a la key de la Story; heredar labels, quarter y start date, sin enviar sprint, con el Due date que confirmó el usuario para cada una. Verificar que cada hito solicitado tenga un issue hijo real.
4. Releer por key padre y subtareas; verificar asignación, sprint y Due date. Si alguna escritura falla, reportar claves creadas, causa y pasos pendientes; reutilizarlas al reanudar, sin recrear padre.
5. A cada subtarea con pasos, agregarle la tabla `## Pasos` con `tracking --create` sobre su descripción releída, según `ticket-templates.md`. El padre y la épica no reciben tabla de hijos.
6. Mostrar:

| # | Clave | Tipo | Resumen |
|---|---|---|---|
| 1 | `[PROJ-1234](...)` | 📋 Padre | `<summary>` |
| 2 | `[PROJ-1235](...)` | 📎 Subtarea | `<summary>` |

### Actualizar

1. Leer el padre por su key (`getJiraIssue <KEY>`) y cada subtarea por key, en paralelo.
2. Releer diff actual en modo repositorio; en tarea explícita, usar pedido y contenido actual sin incorporar cambios locales.
3. Comparar summary, description, áreas, subtareas, cobertura, idioma y campos.
4. Preservar labels y contenido no relacionado.
5. Actualizar solo drift real; corregir siempre campos obligatorios faltantes. Si falta fecha de inicio del padre, aplicar la precedencia y el fallback de consenso entre subtareas de `jira-fields.md` antes de pedirla. Una fecha inferida así es de seguimiento: decir siempre en la respuesta que proviene de las subtareas y que no prueba el inicio real del trabajo. Si el padre no tiene sprint, asignar el sprint activo resuelto; preservar uno existente salvo pedido explícito.
6. Ejecutar edits de issues independientes en paralelo; nunca writes concurrentes sobre mismo padre.
7. Crear subtareas faltantes con campos heredados; antes, preguntar por su Due date si el pedido no lo indica. Preservar el Due date de issues existentes salvo pedido explícito.
8. Mantener la tabla `## Pasos` de cada subtarea según `ticket-templates.md`: estado de cada paso con su evidencia, pasos nuevos al final y leyenda `Progreso` recalculada. Crear un hijo o cambiar su estado no toca la descripción del padre ni de la épica.
9. Mostrar:

| # | Clave | Tipo | Acción | Resumen |
|---|---|---|---|---|
| 1 | `[PROJ-1234](...)` | 📋 Padre | ✏️ Actualizado | `<summary>` |
| 2 | `[PROJ-1235](...)` | 📎 Subtarea | — Sin cambios | `<summary>` |
| 3 | `[PROJ-1236](...)` | 📎 Subtarea | 🆕 Creada | `<summary>` |

Para cualquier update del padre, tenga PR asociados o no, usar `version`, `updated`, relectura inmediata y un solo retry según `pr-traceability.md`. Nunca sobrescribir description concurrentemente.

### Formato de los reportes

Las tablas de este paso y del gate final son la forma por defecto de mostrar resultados al usuario. Si la superficie donde se responde no renderiza tablas, usar una lista anidada con los mismos datos: una línea por ticket con su emoji y su key, y un sub-item `Campo: valor` por columna. En los dos formatos, cada resultado empieza con su emoji (✅, ❌, ➖, 🆕, ✏️) para que se lea sin recorrer el texto.

## Paso 6 — Sincronizar trazabilidad bidireccional

Si hay PR, ejecutar `pr-traceability.md` en este orden:

1. Normalizar sección `## Pull requests` del padre con `section --heading "Pull requests"`.
2. Confirmar labels en padre y subtareas.
3. Aplicar parche `traceability-only` a cada PR:
   - backlink bajo `## 📝 Descripción`;
   - fallback primer heading;
   - fallback prepend;
   - no tocar título ni contenido protegido.
4. Verificar padre y backlink; agregar label GitHub `jira-ticket` según `pr-traceability.md`.
5. Re-fetch Jira y GitHub.
6. Verificar Jira→PR, PR→Jira y label GitHub.

Si cualquier asociación falla, detener antes de transición y reportar URL/issue exacto. No afirmar trazabilidad completa.

## Paso 7 — Resolver estado padre

1. Reconsultar estado de cada PR desde GitHub.
2. Recalcular `ALL_PRS_MERGED`.
3. Re-fetch status padre.
4. Leer y ejecutar `status-transitions.md`.
5. Verificar status real después de cada transición.

No continuar al gate final si máquina devuelve bloqueo.

## Paso 8 — Gate final

Releer por key padre y subtareas, y releer todos los PR en GitHub. Validar:

- Padre nuevo de tipo `<STORY_TYPE>`; padre existente compatible reutilizado sin duplicación ni conversión implícita.
- Cada unidad o hito solicitado tiene una `<SUBTASK_TYPE>` real con `parent` correcto, sin equivalentes duplicados; checklist textual no cuenta como issue.
- Estados de subtareas respaldados por evidencia específica; `PR testeado` no se completa por CI ni por estado del padre.
- Campos obligatorios según `jira-fields.md`.
- Contenido nuevo o modificado en español; contenido ajeno preservado.
- Alcance solicitado cubierto sin puntos obsoletos ni afirmaciones sin evidencia; diff completo solo en modo repositorio.
- Labels y sección Jira→PR según `pr-traceability.md`.
- Backlink PR→Jira único, label GitHub `jira-ticket` y contenido PR protegido.
- Responsable de padre y subtareas verificado según `jira-fields.md`.
- Sprint del padre resuelto o preservado y heredado por cada subtarea, según `jira-fields.md`.
- Due date de cada issue igual a lo confirmado por el usuario o preservado, según `jira-fields.md`.
- Estado individual actualizado de cada PR.
- Ni el padre ni la épica recibieron una tabla de hijos nueva; cada tabla `## Pasos` de subtarea tiene estados respaldados por evidencia y su leyenda `Progreso` coincide con las filas, según `ticket-templates.md`.
- Descripciones escritas en el modo resuelto según `rich-format.md`: elementos enriquecidos solo en su papel y con evidencia, ningún link dentro de un expand, sin sintaxis de Markdown enriquecido (`[!…]`, `{status:…}`, `<details>`) visible como texto, y contenido ajeno intacto.
- Status padre coherente con `status-transitions.md`.

Corregir mismatch local y revalidar elemento. No reiniciar flujo ni repetir transición ya verificada.

Tabla de campos:

| Ticket | Tipo | Label | Labels PR | Links PR | Quarter | Fecha inicio | Sprint | Due date |
|---|---|---|---|---|---|---|---|---|
| `[PROJ-1234](...)` | padre | ✅ | ✅ 2/2 | ✅ 2/2 | ✅ Q3/26 | ✅ 2026-07-07 | ✅ Sprint 34 | ✅ 2026-07-21 |
| `[PROJ-1235](...)` | subtarea | ✅ | ✅ 2/2 | ➖ solo padre | ✅ Q3/26 | ✅ 2026-07-07 | ✅ heredado | ➖ sin Due date (confirmado) |

Tabla por PR:

| Pull request | Estado | Label JIRA | Label GitHub `jira-ticket` | Jira→PR | PR→Jira |
|---|---|---|---|---|---|
| `[owner/repo#123](...)` | `MERGED` | ✅ | ✅ | ✅ | ✅ |

Usar ✅ correcto, ❌ incorrecto, `➖ sin asociaciones` cuando colección vacía, `➖ no aplica: solo padre` para links de subtarea `➖ sin Due date (confirmado)` cuando el usuario indicó que no tiene y `➖ no configurado` para campos opcionales sin variable.

## Paso 9 — Guardar memoria y reportar

Solo después de gate exitoso:

1. Consultar la memoria persistente (por ejemplo Engram con `mem_search`) por key y scope `project`; leer candidatos completos. Si `<MEMORY_ORG>` está configurado, guardar dentro de esa organización (en Engram, `--org <MEMORY_ORG>` del CLI si la herramienta MCP no lo admite).
2. Para mismo tema, `mem_update` por ID conservando hechos vigentes; para tema nuevo, `mem_save` con `topic_key` deliberado `jira/<KEY>`. Si búsqueda falla o identidad es ambigua, no sobrescribir ni duplicar memoria.
3. Título estable: `Ticket JIRA <KEY> para <feature>`.
4. Project: `repository_id` o `<PROJECT_KEY>` cuando no haya repositorio.
5. Content con **What**, **Why**, **Where**, **Learned**: key, summary, subtareas, status verificado y asociaciones relevantes, sin secretos ni paths absolutos.
6. Si la memoria no está disponible o el guardado falla, informar limitación; no usar otro sistema de memoria ni afirmar persistencia no verificada.

Memoria sirve para discovery; nunca como fuente de identidad, estado o contenido actual: no actualizar desde memoria sin fetch de Jira y GitHub.
