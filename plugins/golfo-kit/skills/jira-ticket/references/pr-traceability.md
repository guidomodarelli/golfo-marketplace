# Contrato de trazabilidad JIRA ↔ pull requests

Leer esta referencia cuando existan asociaciones PR y siempre al actualizar ticket existente, aunque prompt no aporte PR nuevo. Descripción del padre puede contener asociaciones persistidas que deben redescubrirse antes de calcular labels, estado o drift.

## Responsabilidad

- Labels JIRA permiten lookup determinista y prevención de duplicados.
- Sección `## Pull requests` en padre permite navegación humana Jira→PR.
- Backlink canónico en cada PR permite navegación PR→Jira.
- Label GitHub `jira-ticket` señala vínculo verificado; no sustituye key ni labels JIRA.
- `jira-ticket` agrega o normaliza backlink en cuerpo PR y agrega label GitHub `jira-ticket`. Nunca regenera plantilla, título, tipo, pruebas manuales, API, opcionales ni notas.
- `pr-description-template` conserva responsabilidad sobre composición completa del PR.

Labels y links no son duplicación editorial: sirven a consumidores distintos.

## Normalización de entradas PR

Aceptar únicamente:

- Número decimal para PR del repositorio actual.
- URL con forma exacta `https://github.com/<owner>/<repo>/pull/<number>`.

Rechazar otras formas. Pasar input validado como argumento quoted:

```bash
gh pr view "<validated-number-or-url>" --json number,url,headRefName,baseRefName,state
```

Construir `PULL_REQUESTS` con:

- `number`
- canonical `url`
- `owner/repo`
- `repository_id`
- `headRefName`
- `baseRefName`
- `state`: `OPEN`, `CLOSED` o `MERGED`

Reglas:

- Número solo pertenece al repositorio actual.
- URL canónica devuelta por GitHub es fuente de verdad.
- Para PR cross-repository, derivar `repository_id` con las mismas reglas de repositorio (`<REPO_ID_SOURCES>`); si el repositorio no está disponible localmente, usar su nombre sin `<REPO_PREFIXES>` (`jira-ticket.py pr-normalize`).
- Deduplicar por URL canónica; número solo no es globalmente único.
- Ordenar por `owner/repo` y número para output estable.
- Si `gh pr view` falla, usar API solo con owner, repo y número validados; verificar `html_url`, repository y number antes de aceptar respuesta.
- Nunca inferir identidad o estado desde branches, commits, refs locales, JIRA, labels, descripción o memoria.

Derivar:

```text
PR_LABELS = unique("<repository_id>/PR-<number>" for each PULL_REQUEST)
ALL_PRS_MERGED = PULL_REQUESTS is not empty and every state == "MERGED"
```

Reconsultar estado de cada PR inmediatamente antes de transición del padre.

## Lookup JIRA por labels

Ejecutar lookup JQL para cada `PR_LABELS` antes de memoria, siempre acotado con `project = <PROJECT_KEY>`. Solicitar al menos `summary`, `description`, `status`, `labels`, `issuetype`, `parent` y `subtasks`. Verificar que cada padre resuelto pertenece a `<PROJECT_KEY>`; referencias de otros proyectos no autorizan edición ni migración.

Antes de evaluar resultados, agrupar cada match por Story padre o Task legacy compatible:

- Una `Story` se agrupa bajo su propia key.
- Un `Task` legacy válido se agrupa bajo su propia key; no crear una Story duplicada ni convertirlo automáticamente.
- Una `Sub-task` se agrupa bajo key de su parent, tras verificar que sea `Story` o `Task` legacy de <PROJECT_KEY>.
- Otros tipos no son padres compatibles; informar el tipo encontrado sin convertirlo ni crear un duplicado.
- Padre y subtareas con mismo label representan una sola asociación, no candidatos distintos.

Resolver colección agrupada:

- Ningún label tiene matches: continuar con ticket explícito, memoria o creación según intención.
- Todos los labels con match resuelven al mismo padre: reutilizarlo.
- Algunos labels resuelven al mismo padre y otros no tienen match: reutilizar ese padre y agregar PR sin match durante sincronización; nunca crear otro ticket.
- Labels resuelven a padres distintos: detener y reportar conflictos; nunca elegir arbitrariamente ni crear tercer ticket.
- Un mismo label resuelve a varios padres agrupados: detener y reportar asociación duplicada.
- Confirmar URL canónica en description del padre o key explícita antes de aceptar match ambiguo.
- Key explícita tiene precedencia sobre memoria, pero no sobre conflicto: cada label con match debe resolver al mismo padre explícito; labels sin match se agregan a ese padre.
- Si no hay match, verificar referencias JIRA estructuradas del body y luego memoria según paso 2. Si búsquedas terminan sin padre, crear y asignar salvo prohibición explícita de creación. Un error de búsqueda bloquea creación; no significa ausencia de ticket.

Memoria funciona solo como fallback cuando ningún PR label produce padre válido.

## Asociaciones persistidas durante updates

Antes de comparar drift:

1. Parsear sección existente `## Pull requests` del padre.
2. Agregar cada URL encontrada a input nuevo.
3. Resolver nuevamente todas las URLs con GitHub.
4. Deduplicar y ordenar colección completa.
5. Regenerar `PR_LABELS` y `ALL_PRS_MERGED`.
6. Repetir lookup JQL/conflict check con colección completa.
7. Detener si asociación descubierta tarde pertenece a otro padre.

Input nuevo aumenta asociaciones; nunca reemplaza ni elimina asociaciones previas solo porque prompt no las menciona.

Si label legacy no tiene URL, reconstruirla únicamente cuando identifica sin ambigüedad PR del repositorio actual. Si no, pedir URL canónica.

## Sección canónica Jira→PR

Solo descripción del padre puede contener:

```markdown
## Pull requests

- [owner/repository#123](https://github.com/owner/repository/pull/123)
```

Reglas:

- Agregar sección solo cuando `PULL_REQUESTS` no esté vacío.
- Una lista item por URL canónica.
- Mostrar `owner/repo#number`.
- Orden estable por repository y número.
- No persistir estado GitHub en descripción; puede quedar obsoleto.
- Máximo una sección canónica.
- Subtareas nunca reciben sección ni URLs PR.

## Concurrencia de descripción padre

Aplicar este contrato a todo update del padre, incluso cuando no haya PR asociados. Description padre puede cambiar entre fetch y write; nunca sobrescribir edición concurrente.

Cuando existan asociaciones, description también es fuente persistente de URLs PR. Combinar sección canónica con cualquier actualización de summary, description, labels o campos obligatorios en una sola escritura.

Antes de write:

1. Leer `version`, `updated` y descripción completa actual.
2. Fusionar sección canónica sobre versión más reciente.
3. Preservar contenido no relacionado.
4. Incluir `version` como precondición optimista cuando API lo soporte.
5. Nunca ejecutar writes concurrentes sobre mismo padre.
6. Ante conflicto, re-fetch, merge sobre body nuevo y retry una vez.
7. Si MCP/API no puede aplicar precondición y descripción cambió concurrentemente, detener; no sobrescribir.

Edits de issues independientes pueden ejecutarse en paralelo después de fijar payload final de cada uno.

## Backlink canónico PR→Jira

Formato exacto:

```markdown
🎫 Jira: [<KEY>](<SITE_URL>/browse/<KEY>)
```

Ejemplo:

```markdown
🎫 Jira: [PROJ-1234](<SITE_URL>/browse/PROJ-1234)
```

### Posición

Aplicar esta prioridad:

1. Si existe línea exacta `## 📝 Descripción`, insertar backlink como primer contenido no vacío debajo y antes de `### ❓ ¿Qué problema resuelve?`.
2. Si no existe, insertar debajo de primer heading ATX (`#`–`######`).
3. Si cuerpo no tiene heading, anteponer backlink y separación Markdown.

No crear heading o bloque `Referencia`.

### Normalización limitada al key objetivo

Normalizar solo padre objetivo:

- Eliminar backlinks canónicos duplicados del mismo key.
- Reemplazar variantes estructuradas del mismo backlink.
- Reemplazar línea legacy `> **Referencia:** ...` solo cuando URL o key identifica exactamente mismo ticket.
- Usar límites exactos: `PROJ-1234` no coincide con `PROJ-12345`.
- Preservar backlinks y referencias a otros tickets.
- Preservar menciones del key objetivo dentro de prosa normal.
- No borrar líneas genéricas de referencias si no identifican inequívocamente mismo ticket.

### Superficie protegida

Al aplicar parche:

- Leer `title`, `body` y `url` con `gh pr view`.
- No pasar `--title` a `gh pr edit`.
- No invocar composición completa de `pr-description-template`.
- No cambiar selección `[x]` de `Tipo de Cambio`.
- No agregar, eliminar o reordenar secciones opcionales.
- No modificar `Pruebas Manuales`, `Cambios en la API` ni `Notas para el Revisor`.
- Preservar estilo de fin de línea (`LF`/`CRLF`) y presencia/ausencia de newline final.
- Limitar diff a eliminar variantes estructuradas del mismo ticket e insertar backlink canónico.

### Concurrencia e idempotencia

Para cada PR:

1. Leer `title`, `body`, `url` y estado requerido.
2. Calcular transformación sobre body actual.
3. Releer body inmediatamente antes de write.
4. Si cambió, recalcular sobre body más reciente y permitir un solo retry.
5. Si transformación produce body idéntico, omitir write.
6. Escribir multiline body mediante archivo temporal:

```bash
gh pr edit "<canonical-url>" --body-file "<temporary-file>"
```

7. Releer `title` y `body`.
8. Verificar backlink objetivo exactamente una vez en posición canónica.
9. Verificar título idéntico.
10. Verificar otros tickets y contenido protegido idénticos.
11. Eliminar archivo temporal.

Segunda ejecución sobre body normalizado debe producir diff vacío.

## Label GitHub `jira-ticket`

Aplicar por cada PR después de verificar existencia del padre en JIRA y backlink canónico:

1. Leer labels actuales con `gh pr view "<canonical-url>" --json labels`.
2. Si `jira-ticket` ya existe en PR, conservarlo y omitir escritura.
3. Si falta, consultar labels del repositorio GitHub resuelto. Si definición no existe, crearla:

```bash
gh label create jira-ticket --repo "<owner/repo>" --description "PR vinculado a ticket JIRA verificado"
```

4. Agregar sin reemplazar labels ajenos:

```bash
gh pr edit "<canonical-url>" --add-label jira-ticket
```

5. Releer labels del PR y confirmar `jira-ticket` y conservación de labels previos.

Si creación de label compite con otra ejecución y GitHub informa que ya existe, releer definición y continuar.
Ante permisos insuficientes u otro fallo, reportar PR, ticket y operación pendiente; no afirmar gate exitoso.
Si creación o asignación de ticket falla, no agregar label nuevo. Conservar label previo y reportar inconsistencia
cuando vínculo no pueda verificarse. No revertir operaciones ya confirmadas.

## Gate bidireccional

Antes de transicionar padre, verificar:

### En JIRA

- [ ] Padre contiene todos los `PR_LABELS`.
- [ ] Cada subtarea contiene todos los `PR_LABELS`.
- [ ] Padre contiene exactamente una sección `## Pull requests` cuando hay asociaciones.
- [ ] Cada canonical URL aparece exactamente una vez.
- [ ] URLs persistidas previamente permanecen.
- [ ] Ninguna subtarea contiene sección o URL PR.

### En GitHub

- [ ] Cada PR contiene backlink exacto al padre una vez.
- [ ] Cada PR contiene label GitHub `jira-ticket`; labels ajenos permanecen.
- [ ] Backlink ocupa posición canónica.
- [ ] Título permanece sin cambios.
- [ ] Contenido protegido permanece sin cambios.
- [ ] Estado fue obtenido nuevamente desde GitHub.

Si cualquier PR no puede actualizarse o verificarse, reportar URL y detener antes de transición. No hacer rollback de PR ya normalizados y no duplicar links durante retry.

Gate final debe reportar una fila por PR con URL canónica, estado GitHub, label JIRA, label GitHub `jira-ticket`, resultado Jira→PR y resultado PR→Jira.
