# Configuración de jira-ticket

Toda la información de la organización llega por variables de entorno `JIRA_TICKET_*`. La skill no contiene datos de ningún equipo ni empresa: cambiar de equipo o de organización es cambiar estas variables.

## Dónde viven

1. Variables de entorno del proceso (tienen prioridad).
2. Archivo de perfil `JIRA_TICKET_ENV_FILE`, por defecto `~/.config/jira-ticket/env`, con líneas `export NOMBRE=valor`. No se versiona. El script lo lee sin ejecutarlo, así que funciona aunque el shell del agente no lo haya cargado.
3. Defaults del script para las variables opcionales que los tienen.

Para empezar: copiar [`../env.example`](../env.example) a `~/.config/jira-ticket/env` y completar los valores del equipo.

## Resolver la configuración

Antes de cualquier lectura o escritura en Jira, ejecutar:

```bash
python3 <skill-dir>/scripts/jira-ticket.py config
```

En Windows, si `python3` no existe, usar `python` o `py -3`.

Devuelve JSON con `settings` (valor y origen: `env`, `file` o `default`), `features` (qué campos opcionales están activos) y `missing_required`. Si `missing_required` no está vacío (exit `4`), detener sin consultar Jira e indicar al usuario qué variables definir y en qué archivo. No inventar ni recordar valores de otra ejecución.

## Variables

| Variable | Obligatoria | Uso | Default |
|---|---|---|---|
| `JIRA_TICKET_SITE_URL` | Sí | URL del sitio Jira; se usa para links `browse` y backlinks | — |
| `JIRA_TICKET_CLOUD_ID` | Sí | `cloudId` de las herramientas Atlassian | — |
| `JIRA_TICKET_PROJECT_KEY` | Sí | Proyecto donde se crean y buscan issues; toda JQL queda acotada a él | — |
| `JIRA_TICKET_PROJECT_NAME` | No | Nombre visible del proyecto en reportes | — |
| `JIRA_TICKET_BOARD_ID` | No | Tablero de sprints; sin él no se gestiona sprint | — |
| `JIRA_TICKET_ASSIGNEE_ACCOUNT_ID` | No | Responsable por defecto de issues nuevos | — |
| `JIRA_TICKET_STORY_TYPE` | No | Tipo de padre nuevo | `Story` |
| `JIRA_TICKET_TASK_TYPE` | No | Tipo legacy reutilizable como padre | `Task` |
| `JIRA_TICKET_SUBTASK_TYPE` | No | Tipo de subtarea | `Sub-task` |
| `JIRA_TICKET_QUARTER_FIELD` | No | Id del campo de quarter (`customfield_…`); sin él no se completa quarter | — |
| `JIRA_TICKET_QUARTER_FORMAT` | No | Formato del valor de quarter con `{quarter}`, `{yy}`, `{yyyy}` | `Q{quarter}/{yy}` |
| `JIRA_TICKET_START_DATE_FIELD` | No | Id del campo de fecha de inicio; sin él no se completa | — |
| `JIRA_TICKET_SPRINT_FIELD` | No | Id del campo Sprint; requiere `BOARD_ID` | — |
| `JIRA_TICKET_SPRINT_NAME_REGEX` | No | Regex del nombre de sprint; con grupos `year` y `quarter` exige coincidir con la fecha | — |
| `JIRA_TICKET_SPRINT_ACTIVE_STATE` | No | Estado de sprint en curso | `active` |
| `JIRA_TICKET_REPO_ID_SOURCES` | No | Orden para resolver `repository_id`: `archivo:clave` (YAML/`clave=valor`), `archivo.json:clave` o `basename` | `package.json:name,basename` |
| `JIRA_TICKET_REPO_PREFIXES` | No | Prefijos que se quitan al basename del repositorio, separados por coma | — |
| `JIRA_TICKET_MEMORY_ORG` | No | Organización para la memoria persistente (por ejemplo `--org` de Engram) | — |
| `JIRA_TICKET_MAX_RESULTS` | No | Tope de `maxResults` por consulta | `50` |

Los valores no son secretos, pero son datos del equipo: no copiarlos a la skill, a memorias compartidas ni a issues públicos. Nunca guardar tokens ni credenciales en este archivo; la autenticación es de la integración Atlassian.
