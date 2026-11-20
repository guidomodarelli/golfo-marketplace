# Configurar equipo

Flujo para completar o cambiar las variables `JIRA_TICKET_*` de [configuración](config.md) consultando Jira, en vez de buscar a mano el `cloudId`, el tablero y los ids de los custom fields. Se usa cuando el usuario pide «configurar equipo» o dice que cambió de equipo, o cuando `config` informa `missing_required` y el usuario quiere completarlas.

Este flujo solo lee Jira. Su único write es el archivo env del usuario, mediante `env-save`, después de que confirme los valores.

## 1. Descubrir

Pedir solo los campos necesarios en cada consulta, como en el resto de la skill.

| Variable | Cómo se descubre |
|---|---|
| `SITE_URL`, `CLOUD_ID` | `getAccessibleAtlassianResources`; con varios sitios, preguntar cuál |
| `PROJECT_KEY`, `PROJECT_NAME` | El proyecto que indica el usuario, verificado con `getVisibleJiraProjects`; nunca deducido del repositorio |
| `STORY_TYPE`, `SUBTASK_TYPE`, `TASK_TYPE` | `getJiraProjectIssueTypesMetadata`; proponer solo si difieren de los defaults (`Story`, `Sub-task`, `Task`) |
| `SPRINT_FIELD` | Campo con schema `com.pyxis.greenhopper.jira:gh-sprint` en `getJiraIssueTypeMetaWithFields` del tipo Story, reducido con `slim` |
| `QUARTER_FIELD`, `START_DATE_FIELD` | Por nombre del campo en esa misma metadata, solo si el usuario confirma que su equipo los usa |
| `BOARD_ID` | `boardId` de los sprints de `project = <KEY> AND sprint in openSprints()`, pidiendo solo el campo sprint; con varios, preguntar |
| `SPRINT_NAME_REGEX` | Solo si los nombres de esos sprints siguen un patrón claro; mostrar el patrón |
| `ASSIGNEE_ACCOUNT_ID` | Preguntar; no tomarlo de issues ajenos |

Un dato que no se pudo descubrir sin ambigüedad se pregunta; no se inventa ni se recuerda de otra ejecución.

## 2. Confirmar y guardar

1. Correr `scripts/jira-ticket.py env-save --dry-run` con las variables descubiertas por stdin (`{"JIRA_TICKET_NOMBRE": "valor"}`). Devuelve `added`, `changed` (con el valor anterior) y `unchanged`.
2. Mostrar ese plan como tabla (variable, valor anterior, valor nuevo) y pedir confirmación. Al cambiar de equipo, señalar las variables del equipo anterior que no se reemplazan (por ejemplo `QUARTER_FIELD` cuando el nuevo equipo no lo usa) y preguntar si se borran; `env-save` no borra, así que borrarlas es una edición que se le indica al usuario.
3. Tras la confirmación, correr `env-save` sin `--dry-run`. Actualiza las líneas existentes en su lugar, agrega las nuevas al final y conserva comentarios y otras líneas. Solo acepta variables de [configuración](config.md#variables), así que nunca escribe tokens ni nombres mal escritos.
4. Verificar con `scripts/jira-ticket.py config` que `missing_required` esté vacío y que cada valor tenga `source: file`. Si una variable del entorno del proceso pisa el archivo (`source: env`), decirlo: el valor guardado no rige hasta que se quite del entorno.

## Reporte

Responder con el archivo escrito, las variables agregadas o cambiadas y lo que quedó sin resolver. No afirmar que el equipo quedó configurado si `config` todavía informa faltantes.
