---
name: stacked-pr
description: "Gestiona stacked Pull Requests de GitHub con ramas feature/*: divide PRs grandes por responsabilidad, crea un stack desde un PR normal, agrega capas o PRs existentes, propaga fixes de una capa intermedia a las de arriba, reordena capas, preserva un golden diff, valida CI por capa y mergea bottom-up con rebase post-squash. Usar siempre cuando el usuario mencione stacked PRs, stacked pull requests, dividir un PR, crear un stack, agregar un PR al stack, cambiar la base de un PR dependiente, actualizar las capas tras un fix o review, reordenar capas o mergear un stack. No usar para merge requests de GitLab ni de otros hosts."
allowed-tools: Bash Read Write Edit
license: MIT
metadata:
  version: "1.2.0"
  author: "Guido Modarelli"
  category: "git-workflow"
  tags: "git, pull-request, stacked-pr, stack"
  command: "/stacked-pr"
---

# Stacked PRs por responsabilidad

Divide cambios grandes en PRs pequeños y dependientes, manteniendo una cadena GitHub revisable. Prioriza árbol final correcto, CI por capa y trazabilidad sobre velocidad de cherry-pick: un stack que compila capa por capa y termina en el mismo árbol que el original se puede revisar y mergear sin sorpresas.

## Reglas de seguridad y alcance

- Ejecutá acciones remotas solo si el usuario pidió crear, actualizar, cerrar, mergear o publicar PRs.
- Antes de force-push, cerrar/recrear PRs o cambiar bases, confirmá la acción si no fue autorizada explícitamente.
- Nunca modifiques una branch sin crear primero su backup local (ver «Backups»).
- Nunca uses `git reset --hard`, `git checkout -- .` o `git clean` sin backup y alcance explícito.
- No uses `git push --force`; usá `git push --force-with-lease=<branch>:<oid-esperado>` únicamente en branches `feature/*` reescritas, para no pisar un push ajeno.
- No uses `git cherry-pick -X ours`, `-X theirs`, `--skip`, tests deshabilitados ni mocks artificiales para ocultar fallos.
- No declares CI verde si algún check está `pending`, `skipping` o no disponible.
- Mantené cuerpos, títulos y reportes visibles en español; conservá nombres técnicos, branches, comandos, paths y mensajes literales en inglés.

## Rama de integración

Nunca asumas `develop`. La rama de integración (`<integration-branch>`) es la base del PR inferior del stack. Si todavía no hay PR, resolvela como `feature-branch-pr`: la primera que exista entre `origin/develop`, `origin/master` y `origin/main`.

```bash
for candidate in develop master main; do
  git show-ref --verify --quiet "refs/remotes/origin/$candidate" && { echo "$candidate"; break; }
done
```

Si no existe ninguna, detenete y reportá que no hay base soportada. Todos los comandos de abajo usan `<integration-branch>`.

## Backups

Toda reescritura (split, rebase en cascada, reordenamiento, rebase post-squash, sumar un PR existente) crea antes un backup local condicional por branch afectada y lo conserva ante cualquier fallo. Antes de crear la primera ref y antes del cleanup final, leé [`references/backups.md`](references/backups.md): ahí está el procedimiento completo (naming scoped, `update-ref` con OID cero, transacción `update-ref --stdin` con OID esperado, worktrees).

Estados que siempre se reportan: `BACKUPS_CLEANED` (cleanup completo tras éxito total), `BACKUPS_PRESERVED_ON_FAILURE` (fallo en alguna etapa; refs retenidas, nunca se borran como recuperación) y `BACKUP_CLEANUP_FAILED` (la transacción de cleanup no pudo aplicarse; no hay borrado parcial).

## Tamaño de una capa

Cada capa debe poder revisarse en una sentada y tener una sola responsabilidad. Como guía, apuntá a ≤ ~400 líneas cambiadas de código revisable (sin lockfiles, catálogos generados ni snapshots). Si una capa supera eso, partila por subárea (por ejemplo, backend en modelos y endpoints). Si una capa queda trivial (≲ 30 líneas) y la revisa la misma persona que la vecina, uní ambas: cada PR extra cuesta un ciclo de CI y de review. Medí siempre contra la base inmediata, no contra `<integration-branch>`.

## Modos de operación

### A. Dividir un PR grande no stacked

Usá cuando el usuario pasa una URL/número de PR o pide dividir un PR existente.

1. Obtené PR, repositorio, base, head y SHA:

   ```bash
   gh pr view <PR> --json number,url,title,baseRefName,baseRefOid,headRefName,headRefOid,state
   git fetch origin --prune
   git status --short --branch
   ```

2. Exigí árbol limpio y creá el backup del head original (ver «Backups»).
3. Usá `base-sha` y `head-sha` como oráculos; `head-sha` es el golden. Calculá el alcance sin confiar solo en commits:

   ```bash
   git diff --name-status <base-sha> <head-sha>
   git diff --stat <base-sha> <head-sha>
   ```

4. Definí manifests explícitos por responsabilidad. Default recomendado, ajustado al grafo real del repo:

   ```text
   contracts-dependencies: manifests de dependencias (package*.json, go.mod, pom.xml…),
                           constantes, interfaces, schemas y utils compartidas
   backend:                API, middlewares, servicios y sus tests
   frontend:               páginas, componentes, client services, estilos, assets y tests UI
   mocks-tests:            mocks, setup de tests, fixtures y tests que dependan
                           exclusivamente de esos fixtures
   generated:              catálogos de traducción, clientes o tipos generados
   cleanup:                shims legacy, renames finales, .gitignore y paths obsoletos
   ```

   Un path compartido va con su consumer o en la capa fundacional; nunca lo dupliques sin explicarlo. Revisá el tamaño de cada capa (ver «Tamaño de una capa»).

5. Reconstruí cada branch desde la base inmediata, aplicando solo su manifest:

   ```bash
   git switch -c feature/<slug>-<layer> <parent-branch>
   git diff --binary <base-sha> <golden-sha> -- <manifest> | git apply --index
   git diff --cached --check
   git commit -m "<type>(<scope>): <summary>"
   ```

   Si un rename o conflicto exige contexto completo, usá `git cherry-pick --no-commit` y resolvé semánticamente. Creá commit nuevo con los hashes fuente en el body.

6. Nombrá las branches `feature/<slug>-<layer>` y publicá cada PR con base en la branch inmediatamente inferior (ver «Publicar cada PR»).

### B. Crear stack desde un PR normal

Usá cuando existe un PR normal y el usuario quiere agregarle capas.

1. Tratá su `head` como primera capa y no lo reescribas sin autorización. Verificá con `gh pr view <PR> --json headRefName,headRefOid,isCrossRepository` que su head esté en el mismo repositorio (`isCrossRepository: false`): un PR no puede tener como base una branch de un fork.
2. Creá la child branch desde el head del PR y publicala:

   ```bash
   git switch -c feature/<slug>-<layer> <pr-head-sha>
   git push --set-upstream origin feature/<slug>-<layer>
   ```

3. Abrí el PR con base `<pr-head-branch>` (ver «Publicar cada PR»).
4. Repetí usando siempre el head de la última capa como base de la siguiente.
5. Si hay cambios ya mezclados en el child, calculá diff contra la base inmediata.

### C. Agregar una capa o un PR existente a un stack

1. Inspeccioná cada PR abierto y construí la cadena `baseRefName -> headRefName`:

   ```bash
   gh pr list --state open --json number,title,baseRefName,headRefName,headRefOid,isCrossRepository,url
   ```

2. Verificá que todas las branches estén en el mismo repositorio (`isCrossRepository: false`; GitHub no permite base en un fork ajeno) y que no haya ciclos.
3. Identificá el top layer: el head que no es base de ningún otro PR. Si hay más de uno, el stack está bifurcado: preguntá cuál extender.
4. **Capa nueva**: creá la branch desde el top y publicá el PR con el top como base:

   ```bash
   git switch -c feature/<slug>-<new-layer> <top-head-sha>
   git push --set-upstream origin feature/<slug>-<new-layer>
   ```

5. **PR existente** (hoy apuntando a otra base): su diff propio es `git diff <old-base>...<pr-head>`. Hacé backup, movelo encima del top y verificá que sus commits no cambiaron:

   ```bash
   old_head=$(gh pr view <PR> --json headRefOid -q .headRefOid)
   merge_base=$(git merge-base origin/<old-base> "$old_head")
   git rebase --onto <top-branch> "$merge_base" <pr-branch>
   git range-diff "$merge_base".."$old_head" <top-branch>..<pr-branch>
   git push --force-with-lease=<pr-branch>:"$old_head" origin <pr-branch>
   gh pr edit <PR> --base <top-branch>
   ```

   Si `range-diff` muestra commits alterados más allá del contexto, o el rebase tiene conflictos semánticos, detenete y reportalo: el PR depende de algo que el stack cambió.

### D. Propagar un cambio de una capa intermedia

Usá cuando un review, un fix o un rebase obliga a cambiar la capa N y las capas N+1…top deben recibirlo.

1. Capturá el tip de cada capa antes de tocar nada y hacé backup de todas (ver «Backups»):

   ```bash
   old_n_tip=$(git rev-parse feature/<slug>-<layer-n>)
   ```

2. Commiteá el cambio en la capa N (commit nuevo; no reescribas commits ya revisados salvo pedido).
3. Rebaseá el resto del stack de una sola vez. `--update-refs` (git ≥ 2.38) mueve también cada branch intermedia que apuntaba a un commit reescrito:

   ```bash
   git rebase --update-refs --onto feature/<slug>-<layer-n> "$old_n_tip" feature/<slug>-<top-layer>
   ```

   Con git más viejo, rebaseá capa por capa de abajo hacia arriba con `git rebase --onto <parent-nuevo> <parent-tip-viejo> <child>`, usando los tips capturados en el paso 1.

4. Si aparece un conflicto que no se resuelve con seguridad, `git rebase --abort`, conservá backups y reportá `BACKUPS_PRESERVED_ON_FAILURE` con la capa afectada.
5. Revalidá cada capa (ver «Dependencias y CI») y pusheá cada branch con su OID esperado:

   ```bash
   git push --force-with-lease=<branch>:<old-tip-de-esa-branch> origin <branch>
   ```

6. El nuevo golden es el tip previo del top más el cambio: verificá con `git diff <old-top-tip> <new-top-tip>` que la única diferencia es el cambio de la capa N.

### E. Reordenar capas

Usá cuando una capa debe ir antes que otra (por ejemplo, para mergear primero algo urgente).

1. Golden = tip actual del top. Hacé backup de todas las capas.
2. Comprobá dependencias: una capa solo puede bajar si no importa nada de las capas que salta. Si depende, explicalo y proponé mover también lo que necesita o un bridge temporal.
3. Reconstruí las capas en el nuevo orden desde `<integration-branch>` con los manifests (o `git cherry-pick` de los commits de cada capa) sobre las mismas branches.
4. Pusheá con `--force-with-lease=<branch>:<old-tip>` y actualizá bases de abajo hacia arriba con `gh pr edit <PR> --base <nueva-base>`, capturando `baseRefName` antes y después.
5. Verificá que el árbol del nuevo top sea igual al golden (ver «Golden diff y cierre») y revalidá CI por capa.

## Publicar cada PR

Antes de cada `gh pr create` o `gh pr edit --body`, cargá `pr-description-template` (este mismo plugin) y armá título y body con esa plantilla a partir del diff de la capa contra su base inmediata. En **Notas para el Revisor** agregá la navegación del stack, porque es lo primero que necesita quien revisa:

```markdown
**Stack** (capa 2/4) · base: #201 · sigue: #203
1. #201 contracts-dependencies
2. 👉 este PR: backend
3. #203 frontend
4. #204 cleanup
```

```bash
gh pr create --base <parent-branch> --head feature/<slug>-<layer> --title "<título>" --body-file <body.md>
```

Cuando se crean, reordenan o mergean capas, actualizá ese bloque en los PRs ya publicados con un patch body-only propio de esta skill (el modo traceability-only de la plantilla no cubre **Notas para el Revisor**):

1. Releé el body justo antes de escribir: `gh pr view <url> --json body -q .body > <body.md>`.
2. Reemplazá solo el bloque que empieza en `**Stack**` hasta la última línea de la lista numerada; si no existe, agregalo al final de **Notas para el Revisor** (o creá esa sección antes de la línea de atribución). No toques título ni otras secciones.
3. Aplicá con `gh pr edit <url> --body-file <body.md>`, sin `--title`.
4. Releé con `gh pr view <url> --json title,body` y verificá que el bloque es el nuevo y que el resto del body quedó idéntico.

## Dependencias y CI

- Contracts/dependencies precede consumers backend/frontend.
- Un import nuevo exige que módulo, tipos, configuración y dependencia estén presentes en la misma capa o en una anterior.
- Tests y fixtures necesarios para ejecutar una capa viajan con esa capa; fixtures puramente adicionales pueden ir en `mocks-tests`.
- Los artefactos generados (catálogos de traducción, clientes OpenAPI, tipos) nunca se editan a mano: regeneralos con el comando que define el repo y descartá churn ajeno a la capa (locales que no cambiaste, reordenamientos).
- Si una capa falla porque depende de una capa posterior, mové el consumer/contrato hacia arriba o agregá un bridge temporal documentado que cleanup eliminará. No debilites assertions.
- Validá cada branch con los comandos que define el repositorio (scripts del package manager, Makefile, CI, `AGENTS.md`/`CONTRIBUTING`): instalación limpia, typecheck, lint, tests, build y `git diff --check`, en la medida en que el repo los tenga, para que cada capa se pruebe igual que la probará CI. Por ejemplo, en un proyecto Node: `npm ci && npx tsc --noEmit && npx eslint . && npm test && npm run build && git diff --check`.
- Consultá los checks reales y esperá a que termine CI externo:

  ```bash
  gh pr checks <PR>
  ```

  Reportá por PR `pass`, `fail`, `pending` o `logs unavailable`; nunca confundas un `workflow` verde con CI completo.

## Golden diff y cierre

Antes de publicar cada capa, verificá el diff incremental:

```bash
git diff --name-status <base-branch>...<head-branch>
git diff --stat <base-branch>...<head-branch>
git status --short --untracked-files=all
```

Después de la última capa, compará árboles:

```bash
golden_tree=$(git rev-parse '<golden-sha>^{tree}')
stack_tree=$(git rev-parse '<last-stack-branch>^{tree}')
test "$golden_tree" = "$stack_tree"
```

El último PR debe contener todo el cambio intencional y ningún archivo fuera del golden. Si se excluye churn generado, documentá la exclusión y no la llames equivalencia exacta.

## Merge y rebase posterior

- Lanzá el loop de [`codex-autofix-loop`](../codex-autofix-loop/SKILL.md) («Arranque automático al abrir un PR») recién cuando todas las capas estén publicadas y el golden diff validado, no al abrir cada PR: el loop mergea sin preguntar y borra la rama, que las capas siguientes necesitan como base. Ahí lo lanza solo la capa cuya base es `<integration-branch>`; cada capa superior lo lanza cuando, tras el squash de su parent, pasa a apuntar a `<integration-branch>`.
- Fusioná bottom-up y nunca un child antes que su parent.
- **Antes** de mergear un parent, guardá su tip: después del squash ese commit ya no está en `<integration-branch>` y lo necesitás para recortar el child.

  ```bash
  old_parent_tip=$(gh pr view <parent-pr> --json headRefOid -q .headRefOid)
  ```

  Si el merge ya ocurrió, `gh pr view <parent-pr> --json headRefOid` sigue devolviendo el último head del PR mergeado.

- Cuando GitHub borra la rama del parent, cambia solo la base del child a `<integration-branch>`, pero el diff del child sigue mostrando los commits del parent hasta que lo rebasees. Tras el squash:

  ```bash
  git fetch origin <integration-branch>
  git switch <child-branch>
  child_tip=$(git rev-parse HEAD)
  git rebase --onto origin/<integration-branch> "$old_parent_tip"
  git push --force-with-lease=<child-branch>:"$child_tip" origin <child-branch>
  gh pr edit <child-pr> --base <integration-branch>
  ```

  Si quedan más capas encima, usá `--update-refs` desde el top para moverlas todas en el mismo rebase (ver modo D).

- Revalidá CI, conflictos y golden después de cada squash.
- Eliminá branches del stack solo cuando todos los PRs estén fusionados y el golden final verificado; las refs `backup/*` siguen el cleanup de [`references/backups.md`](references/backups.md).

## Reporte final

Entregá una tabla:

| Orden | PR | Branch | Base | Scope | Archivos | CI |
|---|---|---|---|---:|---:|---|

Incluí:

- URLs de PRs y cadena de bases, con `<integration-branch>` resuelta.
- SHA original/golden y SHA final.
- Resultado de comparación de árbol/patch (o `range-diff` en el modo C).
- Tests, build y lint ejecutados.
- Checks remotos aún pending o con logs unavailable.
- Branch original preservada.
- Estado de backups: `<BACKUPS_CLEANED|BACKUPS_PRESERVED_ON_FAILURE|BACKUP_CLEANUP_FAILED>` y refs retenidas si aplica.
