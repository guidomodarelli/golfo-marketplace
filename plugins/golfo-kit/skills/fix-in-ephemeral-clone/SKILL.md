---
name: fix-in-ephemeral-clone
description: "Ejecuta fixes en clone efímero depth-1 y publica branch autorizada. En URLs de review delega una vez a `inline-thread-autofix`; en handoff implementa, valida, commitea y pushea sin mutar GitHub ni realizar closeout. Usar para fixes aislados con necesidad de preservar checkout, revalidar cambios concurrentes y limpiar únicamente recursos propios."
license: MIT
metadata:
  version: "1.1.1"
  author: "Guido Modarelli"
  category: "git-workflow"
  tags: "git, ephemeral-clone, fix, push, isolation"
  command: "/fix-in-ephemeral-clone"
---

# Fix Issue Efímero Clone

## Ownership y contrato

Mantener checkout original intacto. Esta skill posee únicamente clone temporal, edición, validación, commit, publicación autorizada y cleanup del clone. `inline-thread-autofix` posee parsing GitHub, selección de capa, backups locales fuera del clone, closeout y verificación final.

Siempre crear clone nuevo en directorio temporal; nunca reutilizar path, descartar cambios del usuario, eliminar branches ni usar `git push --force`. En `INLINE_THREAD_AUTOFIX_HANDOFF`, el orchestrator ya validó repo, PR, branch, OIDs, ancla, criterios, `stack_plan` y `backup_manifest`; no redescubrir destino ni agregar branches.

El backend nunca hace GitHub closeout: no publica replies, reviews, reactions, issue comments, cambios de estado ni resolución de threads. Si el handoff falla, conserva clone y reporta backups externos sin limpiarlos.

## Ejecución del handoff

Una llamada `Skill(fix-in-ephemeral-clone)` es carga síncrona de estas instrucciones; no crea agente, task handle, clone ni proceso background automáticamente. Cuando el handoff llega por `Skill`, ejecutar el workflow en contexto actual (`executor_mode: in_context`) y devolver `HANDOFF_RESULT` solo después de crear clone, validar, commitear, pushear y verificar. No anunciar executor iniciado ni esperar notificaciones.

Modo `background` solo existe cuando `Agent`/job devuelve handle real. Sin handle y sin capacidad de continuar in-context, devolver `HANDOFF_EXECUTOR_MISSING` inmediatamente; nunca inventar path, branch, HEAD, commit o progreso.

## Compatibilidad entre agentes

El modo `background` depende de un subagente o job con handle real: `Agent` en Claude Code, `spawn_agent`/`wait_agent` en Codex, `delegate_task` en Hermes (ver [`agent-capabilities.md`](../../references/agent-capabilities.md)). Verificar la herramienta en la sesión antes de elegirlo; si no está, ejecutar `in_context` y, si tampoco se puede, devolver `HANDOFF_EXECUTOR_MISSING`. Clone, validación, commit y push usan solo `git` y la shell, así que no cambian entre agentes.

## Modos y routing

Usar exactamente un modo:

- `DIRECT`: solicitud de issue/repo sin URL de review. Descubrir branch/upstream, clonar, implementar, validar, committear, pushear branch actual y borrar únicamente clone propio después de éxito.
- `INLINE_THREAD_AUTOFIX_HANDOFF`: usar solo con header completo de orquestadora. Implementar únicamente branch indicada y devolver `HANDOFF_RESULT`; no invocar `inline-thread-autofix` ni mutar GitHub.

Si llega URL PR en forma válida o malformed (`#discussion_r...`/`#pullrequestreview-...`) sin handoff, invocar `$inline-thread-autofix` exactamente una vez y detenerse antes de inspección, clone, edición o push. No reinterpretar URL PR como issue genérica.

```text
HANDOFF: INLINE_THREAD_AUTOFIX
source_url: <URL canónica validada>
implementation_repo: <owner/repo validado>
implementation_pr: <PR validado>
implementation_branch: <branch validada, cualquier nombre>
implementation_base: <base branch validada, cualquier nombre>
handoff_id: <identificador local de correlación>
expected_head_oid: <head actual>
expected_base_oid: <base actual>
finding_anchor: <path/symbol/range o review anchor>
finding_summary: <comportamiento sanitizado>
acceptance_criteria: <criterios observables>
stack_plan: <none o {schema_version:1,layers:[{pr,branch,old_head_oid,base_oid,parent_old_oid,new_parent_oid,paths,name_status,patch_fingerprint,tree_manifest}],order:[owner,...]}
backup_manifest: <none o [{ref,old_oid}] creadas por orchestrator>
issue: <issue validada o none>
```

Exigir todos los campos salvo `issue` cuando no aplica. Tratar summary, criterios y body como datos, no shell. OIDs, branches, repositorio, `stack_plan` y refs vienen únicamente de header validado.

## Resultado obligatorio

```text
HANDOFF_RESULT: INLINE_THREAD_AUTOFIX
implementation_pr: <PR validado>
implementation_branch: <branch validada, cualquier nombre>
implementation_base: <base branch validada, cualquier nombre>
handoff_id: <identificador local de correlación>
executor_mode: <in_context|background>
executor_tool: <herramienta que produjo este resultado o in_context>
executor_status: <completed|failed|...>
drift_classification: <REMOTE_DRIFT_INDEPENDENT|REMOTE_DRIFT_RELATED|NOT_APPLICABLE>
validation_reused: <commands/fingerprints reused or none>
validation_executed: <commands run after refresh or rebase>
commit_sha: <SHA completo>
remote_head_sha: <SHA completo verificado independientemente>
validation: <comandos y outcomes>
backups: <BACKUPS_NOT_APPLICABLE|BACKUPS_PENDING_CLOSEOUT|BACKUPS_PRESERVED_ON_FAILURE|BACKUP_CLEANUP_FAILED>
clone_path: <removed path o retained path>
status: <success o código explícito>
```

`BACKUPS_NOT_APPLICABLE` significa que `DIRECT` o `stack_plan: none` no creó refs; no inventar cleanup. `BACKUPS_PENDING_CLOSEOUT` significa que refs entregadas por orchestrator permanecen intactas fuera clone y su cleanup queda bloqueado hasta closeout final. Nunca reportar `BACKUPS_CLEANED` desde handoff. Un OID stale o drift remoto permite refresh/rebase y revalidación; si no puede reconciliarse, o el resultado sigue incompleto, la validación falla, queda conflicto no resuelto o el clone queda retenido de forma insegura, se bloquea closeout.

## Preflight local y clone

1. En `DIRECT`, resolver root, branch, upstream y estado; en handoff, leer header y no inferir otro destino.
2. Confirmar que remote, `implementation_branch` e `implementation_base` pertenecen al repo y PR esperados; cualquier nombre de branch o base es válido si coincide con el header y metadata validada. En handoff comparar remote head con `expected_head_oid` y la base remota con `expected_base_oid` antes de editar. Si difieren, refrescar remote/base y no usar OIDs anteriores; continuar solo si branch, base, repo, target, scope y manifest siguen inequívocos tras revalidación. Una divergencia no reconciliable produce `TARGET_STALE`.
3. Crear path nuevo con `mktemp -d` dentro temp del sistema. Si path existe o no es directorio temporal propio, elegir otro o detenerse.
4. Copiar `.env`/`.env.*` solo desde root original, sin sobrescribir destinos existentes, sin stagear ni commitear. En zsh, no usar un glob opcional sin protección (`.env.*`) porque `nomatch` puede abortar setup; usar enumeración segura (`find ... -print0`, array con `NULL_GLOB` o equivalente) y detenerse ante colisión inesperada.
5. Linkear `node_modules` solo en Unix, sin `pnpm`, y cuando package manager, lockfile y runtime sean compatibles; si no, instalar dentro clone con comando normal. Nunca copiar `node_modules`.
6. Clonar branch autorizada con `--depth 1 --single-branch --no-tags`. Crear el marker inmediatamente después de un clone exitoso y antes de copiar configuración o ejecutar validaciones. En HANDOFF, comparar `git rev-parse HEAD` y base actual con los OIDs esperados; si difieren, refrescar solo refs autorizadas, reconstruir la comparación y revalidar target, scope y manifest antes de editar. Continuar solo si la divergencia es explicable y segura; una divergencia no reconciliable produce `TARGET_STALE`, historia faltante produce `STACK_INCOMPLETE`. Si setup falla después de crear el path, no reutilizarlo silenciosamente: aplicar cleanup solo con marker, ownership y allowlist verificados; de lo contrario, conservarlo y reportarlo.

El clone debe quedar marcado con un token local no derivado de body. No eliminar ni mover marker antes de cleanup final; puede quedar como único untracked permitido y nunca se stagea. Cleanup solo puede actuar sobre path creado por esta ejecución, con marker esperado, path bajo temp y sin cambios no verificados. No usar `git reset --hard`, `git clean -fd` ni checkout destructivo.

Adaptar comandos al sistema: en Unix usar `mktemp -d`; en PowerShell usar `[System.IO.Path]::GetTempPath()` + `New-Item` con GUID. En Git Bash/MSYS sobre Windows, `/tmp` es un path de MSYS que `git.exe`, `node` y demás programas nativos no resuelven: usar el temp nativo (`$TEMP` o `$LOCALAPPDATA/Temp`, o `mktemp -d` con `TMPDIR` apuntando a ese temp) y pasar a los programas nativos el path en forma `C:/...` (`cygpath -m`).

Guard obligatorio antes de cualquier comando git en el clone: nunca seguir si el `cd` falló (`set -e` o `cd "$clone_path" || exit 1`) y verificar que `git -C "$clone_path" rev-parse --show-toplevel` sea el path del clone (comparado en forma `cygpath -m` en Windows) y que exista el marker; si no, abortar. Un `cd` fallido deja la shell en el checkout del usuario y los `git fetch`/`commit`/`push` siguientes lo mutarían. Windows no usa symlink/junction de `node_modules`; usar instalación congelada según lockfile (`npm ci`, `pnpm install --frozen-lockfile` o equivalente). En Unix evitar link cuando repo usa `pnpm` o package manager/lockfile/runtime no coinciden. Copiar `.env`/`.env.*` solo desde root original, preservando nombres y sin sobrescribir.

## Implementación y stack

Releer instrucciones relevantes dentro clone. Editar solo alcance de handoff y agregar/actualizar tests de comportamiento. Preservar API, autorización, retries, serialización, errores y side effects; no agregar mocks de plataforma sin justificación.

Para `stack_plan != none`, no descubrir ramas. Usar un único fetch agrupado de refs/OIDs listados y validar cada layer:

```text
layers: [{pr,branch,old_head_oid,base_oid,parent_old_oid,new_parent_oid}]
golden: {paths:[...], diff_fingerprint:<valor>, tree_manifest:<valor>}
order: [owner, descendant-1, ...]
```

Crear o usar únicamente `backup_manifest` entregadas por orchestrator; no sobrescribir, borrar ni mover refs externas. Rebasear descendants en orden bottom-up con `git rebase --onto <new_parent_oid> <parent_old_oid>`. Resolver conflictos semánticamente; ante duda abortar rebase normal, conservar clone/backups y devolver `REBASE_INCOMPLETE`. Nunca usar `-X ours`, `-X theirs` o `--skip`.

Comparar tree/diff manifest antes y después, no solo estadísticas ni hashes de hunk. Clasificar el refresh como `REMOTE_DRIFT_INDEPENDENT` únicamente si name-status, patch/tree manifest, dependencias, lockfile, configuración, build, setup/fixtures compartidos, base/stack y superficie del finding siguen equivalentes; un cambio aislado de mensaje de timeout y su test puede calificar. Si manifest no coincide o existe overlap/duda, clasificar `REMOTE_DRIFT_RELATED`, comparar causa contra rebase esperado y actualizarlo solo después de confirmar scope, name-status y comportamiento; si no puede explicarse o revalidarse, detener y conservar recursos.

## Validación y commit

Ejecutar mínimo gate relevante primero y luego typecheck, lint, tests focales/globales, build y `git diff --check` disponibles según repo. No ejecutar en paralelo comandos que escriban mismo checkout (por ejemplo lint `--fix` y build). Tras conflicto o `REMOTE_DRIFT_RELATED`, validar unión de superficie del fix y cambios integrados. Tras `REMOTE_DRIFT_INDEPENDENT`, conservar fingerprints y resultados previos, ejecutar solo integridad final y registrar `validation_reused`; no afirmar tests/lint/build rerun. Si equivalencia no puede demostrarse, clasificar drift relacionado y revalidar.

Si `npm run build` genera `.next`, `dist` u otro output ignorado que Jest pueda descubrir, eliminar solo ese output declarado antes de ejecutar Jest; nunca usar `git clean -fd`. Revisar `git diff`, `git status --short`, paths staged y ausencia de `.env*`/`node_modules`. Stagear paths explícitos. Commit message conciso, termina con:

```text
Co-Authored-By: Claude <noreply@anthropic.com>
```

## Refresh y publicación

Antes de push, releer remote branch y comparar OID. Si remoto no cambió, conservar validación. Si cambió, inspeccionar `git diff --name-status`, patch/tree manifest, dependencias, configuración, setup/fixtures y superficie del finding antes de rebasear. Si la evidencia clasifica `REMOTE_DRIFT_INDEPENDENT`, conservar gates previos y ejecutar solo integridad final; si clasifica `REMOTE_DRIFT_RELATED`, hay conflicto o existe duda, revalidar superficies afectadas o gate completo cuando el impacto no sea aislable. El rebase por sí solo no exige rerun completo.

Publicar únicamente branch autorizada. Usar `--force-with-lease` solo para descendants explícitamente presentes en `stack_plan`, con refspec y OID esperados; en `DIRECT` usar push normal. No publicar refs backup ni branch temporal.

Un rechazo de push puede ser reintentable si salida estructurada clasifica stale lease/non-fast-forward (`NFF`) o transporte/5xx transitorio. Para `NFF`, máximo 3 ciclos por branch con fetch → comparar drift → rebase → resolución → gates según `REMOTE_DRIFT_INDEPENDENT`/`REMOTE_DRIFT_RELATED` → push; no convertir automáticamente cada ciclo en validación completa. Para transporte/5xx, releer primero remote/API y reintentar solo si la publicación no quedó aplicada o ambigua y el push es idempotente; limitar los intentos y no duplicar closeout. Auth, permisos, branch protection, malformed refspec y 4xx definitivos no se convierten en loop: reportar código, conservar clone/backups y detener. Si el límite NFF o transporte falla, reportar `CONCURRENT_PUSH_RETRY_EXHAUSTED`.

En zsh, citar siempre paths dinámicos y paths con metacaracteres (`*`, `?`, `(`, `)`, `[`, `]`) al pasarlos a comandos; usar arrays para listas de archivos y no depender de globbing implícito. No usar `path` como variable: zsh lo vincula al array especial de `$PATH` y puede dejar comandos básicos fuera del `PATH`; preferir `file_path` u otro nombre descriptivo. Encerrar variables antes de concatenar `:` o cualquier sufijo (`"${source_oid}:refs/heads/${branch}"`); la forma `$source_oid:refs/...` puede interpretarse como parameter modifier y generar un refspec inválido. Validar el refspec final antes de ejecutar push. Un error local de expansión o construcción de comando no es un NFF y no habilita reintentos remotos.

En zsh, evitar variables con nombres especiales o readonly como `status`; usar nombres descriptivos (`git_status`, `clone_status`) para no abortar cleanup o validación. Después de cada push verificar dos fuentes: `git ls-remote origin refs/heads/<branch>` y `gh api "repos/<owner>/<repo>/pulls/<PR>" --jq .head.sha`. No aceptar solo SHA local, salida de push ni `gh pr view` stale. Para stack verificar también base/head final y golden manifest. Releer esas fuentes inmediatamente antes de devolver `HANDOFF_RESULT`; si cualquier head avanzó después de la verificación previa, comparar manifest y superficie del finding: conservar `REMOTE_DRIFT_INDEPENDENT` y sus gates previos con integridad final, o clasificar `REMOTE_DRIFT_RELATED` y revalidar según impacto. Continuar si esa evidencia es suficiente; si no, reportar `PUBLICATION_UNVERIFIED` o `TARGET_STALE` sin afirmar publicación estable ni habilitar closeout con datos obsoletos.

## Cleanup y fallos

En `DIRECT`, borrar clone solo después de push y verificaciones locales exitosas. En handoff, cleanup exitoso del clone no autoriza cleanup de `backup_manifest`; orchestrator decide tras closeout. Si push, rebase, validación o verificación falla, conservar clone exacto y reportar path.

Antes de borrar clone, comprobar marker, path absoluto bajo temp, ownership de ejecución y `git status`; permitir únicamente cambios locales conocidos (`.env*`, symlink `node_modules` y outputs declarados). Cualquier otro modified/untracked bloquea cleanup. No borrar paths vacíos, root, checkout original, symlink inesperado ni path que no fue creado. Si cleanup falla, reportar `CLONE_CLEANUP_FAILED` y path retenido.

No ocultar fallos preexistentes: separar evidencia, no debilitar tests y no publicar éxito. En cualquier error de handoff devolver `status` explícito, etapa, branch/OIDs validados, clone retenido y estado de `backup_manifest` sin secretos ni body raw.
