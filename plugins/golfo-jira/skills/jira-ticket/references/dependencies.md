# Dependencias por bloqueo

Una dependencia por bloqueo es un issue link del tipo `<DEPENDENCY_LINK_TYPE>` (por defecto `Blocks`) entre el issue bloqueado y su bloqueante. Es el link que el timeline de Jira dibuja como flecha entre barras. El tipo, los proyectos permitidos, el tipo de issue de un bloqueante nuevo y su épica por defecto llegan por variables (`config.md`); `jira-ticket.py config` devuelve los valores efectivos en `dependencies`.

## Cuándo aplica

Solo cuando el pedido nombra un bloqueante: "está bloqueada por ACME-7", "depende de que se haga X", "cargá el bloqueante bajo la épica ACME-1". No se infieren dependencias del diff, de la memoria ni de tickets parecidos. Para quitar un link hace falta un pedido explícito, y como la skill no borra links, se informa la key para que el usuario lo quite en Jira.

## Casos

| Bloqueante | Acción | Panel `## Bloqueo` del bloqueado |
|---|---|---|
| Existe y su `statusCategory` es `done` | Crear el link | No se agrega por este bloqueante |
| Existe y no está hecho | Crear el link | Se agrega o actualiza según `ticket-templates.md`, nombrando la key del bloqueante |
| No existe | Crearlo primero como `<blocker_issue_type>` y después el link | Igual que un bloqueante abierto |

Un bloqueante nuevo es un ticket más del flujo: usa el template `Story` de `ticket-templates.md`, se crea en `<PROJECT_KEY>`, se pregunta su Due date junto con los demás datos faltantes y lleva el quarter, la fecha de inicio y el sprint de `jira-fields.md`. Sus labels son solo las pedidas para el bloqueante: nunca los `PR_LABELS` del bloqueado, porque el lookup por labels de `pr-traceability.md` resolvería ese PR a dos Stories y detendría las sincronizaciones siguientes. Un PR se asocia al bloqueante solo si el pedido lo indica para él. Su épica es la que indica el pedido y, si no indica ninguna, `<BLOCKER_DEFAULT_EPIC>`; sin ninguna de las dos, preguntar cuál usar o si va sin épica. La épica se verifica según `Épica del padre nuevo` del Paso 2 y no se edita por colgarle el bloqueante. Antes de crear, buscar candidatos por alcance con JQL acotado a `project = <PROJECT_KEY>` para no duplicar uno existente.

Un bloqueante existente puede estar en cualquier proyecto de `<blocker_project_keys>`. Se lee por key y nunca se edita: no recibe labels, descripción, transición ni backlink. Una key de un proyecto fuera de esa lista se rechaza con su motivo en una línea.

## Flujo

1. Leer cada bloqueante existente por key: `getJiraIssue(issueIdOrKey: "<KEY>", fields: ["summary","status","issuetype","project"])`. Un fetch fallido no prueba que no exista; reportarlo y no crear un reemplazo.
2. Leer el issue bloqueado con `fields: ["issuelinks"]` y los tipos de link con `getIssueLinkTypes(cloudId: "<CLOUD_ID>")`.
3. Ejecutar `jira-ticket.py dependency plan --key <BLOQUEADO>` con `{"issue": <respuesta del bloqueado>, "link_types": <respuesta de getIssueLinkTypes>, "blockers": [<respuestas de los bloqueantes>]}` por stdin. Devuelve `create` (cada uno con su payload `create_issue_link`), `already_linked`, `rejected`, `open_blockers` e `is_blocked`. Exit `3` si el tipo configurado no existe en el sitio: detener e informar los tipos disponibles.
4. Crear cada link de `create` con `createIssueLink(cloudId: "<CLOUD_ID>", type: "<type>", inwardIssue: "<bloqueante>", outwardIssue: "<bloqueado>")`, usando el payload tal como lo devuelve `plan`; si el schema real de la herramienta nombra distinto los parámetros, adaptarlos manteniendo al bloqueante como `inwardIssue`. En Jira, `inwardIssue` es el que aplica la descripción outward (`blocks`) al otro. Los de `already_linked` no se vuelven a crear.
5. Releer el bloqueado con `fields: ["issuelinks"]` y ejecutar `dependency verify --key <BLOQUEADO>` con el mismo `issue` releído y `link_types`, y en `blockers` solo las keys de `create` y `already_linked` de `plan`: un bloqueante rechazado por ciclo ya bloqueaba al otro antes de este flujo, y `verify` lo informaría como `inverted`. Los rechazados por autorreferencia o proyecto no permitido `verify` los omite solo, en `skipped`. `ok: false` lista `missing` (el link no se creó) e `inverted` (quedó al revés). Un link invertido no se corrige creando otro: informarlo con su key para que el usuario lo quite y detener antes del gate.
6. Con `is_blocked` verdadero, agregar o actualizar `## Bloqueo` con `section`, nombrando cada key de `open_blockers`. Si ya no queda ningún bloqueante abierto y la sección solo hablaba de esos links, quitarla.

## Timeline

El timeline muestra la flecha solo entre issues que se ven en él, en general épicas y sus hijos directos con fecha de inicio y Due date. Si el bloqueado o el bloqueante es una subtarea, o le faltan fechas, el link se crea igual, pero la respuesta avisa en una línea que no aparece en el timeline y qué le falta.

## Reporte

Agregar al reporte final una tabla de dependencias (o su lista anidada equivalente):

| Bloqueado | Bloqueante | Estado del bloqueante | Link | Timeline |
|---|---|---|---|---|
| `[ACME-42](...)` | `[ACME-7](...)` | ✅ Hecho | ✅ creado | ✅ |
| `[ACME-42](...)` | `[ACME-50](...)` 🆕 | ⬜ Pendiente | ✅ creado | ⚠️ sin Due date |
| `[ACME-42](...)` | `PLAT-3` | — | ❌ proyecto fuera de `BLOCKER_PROJECT_KEYS` | ➖ |
