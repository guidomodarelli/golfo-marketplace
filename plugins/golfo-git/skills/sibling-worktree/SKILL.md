---
name: sibling-worktree
description: "Gestiona worktrees hermanos persistentes reutilizando ramas existentes, locales o remotas, sin crear ramas derivadas. Usar cuando pidan crear, listar, remover o migrar una branch a otro worktree hermano, mantener misma branch en otro checkout, liberar branch ocupada cambiando worktree actual a develop o mover principal a develop con confirmación explícita. No usar para clones efímeros, commits, pushes ni fixes aislados."
license: MIT
metadata:
  version: "1.0.0"
  author: "Guido Modarelli"
  category: "git-workflow"
  tags: "git, worktree, branch, checkout"
  command: "/sibling-worktree"
---

# Worktree hermano

Gestiona worktrees Git persistentes en rutas hermanas. Cada `create` debe partir de snapshot remoto actualizado de rama origen mediante helper bundled; no reimplementar comandos Git manualmente.

## Helper

Invocar siempre `scripts/sibling-worktree` relativo al directorio de esta skill (el directorio base que informa el runtime al cargarla, por ejemplo `~/.claude/skills/sibling-worktree` o `~/.agents/skills/...`). No hardcodear rutas absolutas de otra máquina; en Windows ejecutarlo desde Git Bash.

```bash
SCRIPT="<directorio-de-la-skill>/scripts/sibling-worktree"
```

## Ubicación obligatoria

Todo worktree nuevo debe quedar como hermano inmediato del repo principal, nunca dentro del repo principal ni dentro de cualquier directorio de worktrees.

- Resolver `primary_path` desde primer registro de `git worktree list --porcelain`; resolver `source_parent` como `dirname` de ruta canónica de `primary_path`.
- Destino válido: `${source_parent}/${repository_name}-${suffix}`. `dirname` de destino debe ser exactamente `source_parent`.
- Destinos inválidos: `${repository_root}/.worktrees/...`, `${repository_root}/.git/worktrees/...`, `${repository_root}/.claude/worktrees/...`, `${repository_root}/worktrees/...`, cualquier subdirectorio anidado, cualquier ruta bajo otro repo y cualquier ruta fuera de `source_parent`.
- `--name` y destino automático siempre deben generar ruta hermana inmediata. `--path` solo puede aceptar ruta absoluta o relativa que resuelva a esa misma ubicación hermana.
- Si `--path` no cumple esta regla, bloquear operación antes de ejecutar `git worktree add`; no corregir, reinterpretar ni mover ruta silenciosamente.
- Ejemplo válido: repo principal `/workspace/app` y worktree `/workspace/app-feature`. Ejemplo inválido: `/workspace/app/.claude/worktrees/feature`.

## Flujo

1. Identificar intención: `create`, `list` o `remove`.
2. Ejecutar primero `--dry-run` para `create` o `remove`.
3. Mostrar al usuario ruta, rama, tracking, operación y bloqueos detectados.
4. Si helper termina con código `3`, tratarlo como bloqueo de seguridad; no repetir operación cambiando flags por iniciativa propia.
5. Si branch solicitada está checkout en worktree principal, explicar que misma branch no puede estar checkout dos veces. Pedir confirmación explícita para mover principal a `develop`.
6. Si solicitud es migrar branch checkout en worktree hermano actual, no remover ese worktree ni ejecutar `git worktree remove`. Preservar archivos ignorados y cambiar worktree actual a branch de reemplazo solo después de confirmar que `git status --short --untracked-files=all` está vacío. Usar `develop` como reemplazo únicamente cuando usuario lo confirme o lo haya indicado; no ejecutar `git clean`, reset ni stash.
7. Después de liberar branch, ejecutar `create --branch BRANCH --name/path DESTINO --dry-run`, mostrar OID y destino, solicitar confirmación y repetir `create` sin `--dry-run`.
8. Tras creación exitosa, cambiar sesión al nuevo checkout mediante mecanismo de entrada de worktree disponible; verificar ruta, branch, upstream, HEAD y estado. Worktree origen queda en branch de reemplazo, sin cambios de archivos intencionales.
9. Solo después de confirmación afirmativa para mover principal, repetir `create` agregando `--confirm-primary-switch-to-develop`.
10. Informar resultado final con ruta, branch, commit y estado.

## Migrar branch checkout actual a otro worktree hermano

Usar cuando usuario quiere conservar worktree actual y mover su branch a un sibling, no eliminar checkout actual.

1. Listar worktrees y capturar `source_worktree`, `source_branch`, `source_head`, upstream y estado.
2. Confirmar branch destino para worktree origen. Si usuario no indica branch y `develop` está libre, proponer `develop`; no cambiar silenciosamente si branch destino está ocupada, tiene cambios o hay ambigüedad.
3. Ejecutar desde worktree origen:

```bash
git status --short --untracked-files=all
git switch develop
```

`git switch` puede conservar directorios ignorados (`node_modules`, `build`, `coverage`, `.next`) sin modificarlos. No exigir worktree vacío de archivos ignorados para este patrón; sí detener si hay cambios tracked o archivos untracked. Nunca usar `git clean`, reset, stash o remover worktree.

4. Ejecutar helper desde worktree que no sea destino actual para validar y crear nuevo sibling:

```bash
SCRIPT="<directorio-de-la-skill>/scripts/sibling-worktree"
"$SCRIPT" create --branch feature/example --name example-migrated --dry-run
# pedir confirmación
"$SCRIPT" create --branch feature/example --name example-migrated
```

Si helper se ejecuta desde branch que se quiere liberar, primero completar `git switch` y volver a ejecutar dry-run. No interpretar bloqueo `no se permite remover worktree desde sí mismo` como motivo para remover; `remove` no es operación necesaria en migración.

5. Entrar al path nuevo, verificar branch/HEAD/upstream/estado y reportar OID original versus OID creado. Si destino ya existe, es symlink, está registrado o branch sigue ocupada, detener sin sobrescribir.

## Operaciones

### Crear

```bash
SCRIPT="<directorio-de-la-skill>/scripts/sibling-worktree"
"$SCRIPT" create --branch feature/example --dry-run
"$SCRIPT" create --branch feature/example
```

Opciones:

- `--branch BRANCH`: obligatorio. Acepta rama local, `origin/branch` o ref completa.
- `--name NAME`: nombre seguro para ruta hermana; mutuamente excluyente con `--path`.
- `--path PATH`: ruta hermana explícita.
- `--dry-run`: valida sin modificar Git ni filesystem; muestra fetch y fast-forward previstos sin confirmar snapshot remoto mediante refs locales.
- `--confirm-primary-switch-to-develop`: autoriza mover worktree principal limpio a rama local `develop` cuando rama solicitada está ocupada allí.

Rama remota se materializa como rama local con mismo nombre y upstream. Cada `create` ejecuta fetch dirigido únicamente a remoto y branch origen antes de crear worktree. Rama local con upstream se actualiza solo mediante fast-forward; rama adelantada se conserva. Rama sin upstream, divergente, remoto inaccesible o cambio concurrente de ref bloquea operación. Nunca usar `pull`, `fetch --all`, `fetch --prune`, `reset` o `--force`.

### Sincronización obligatoria de fuente

- Resolver fuente remota desde ref explícita (`origin/branch`, `refs/remotes/...`) o upstream remoto de rama local.
- Actualizar solo ref remota necesaria antes de `git worktree add`; no usar snapshot stale.
- Si rama local está detrás, aplicar fast-forward; si está igual, continuar; si está delante, conservar commits locales; si diverge, bloquear.
- Si rama local no tiene upstream y no se indicó ref remota explícita, bloquear; no inventar remoto ni asumir `main`, `master` o `develop`.
- Verificar HEAD creado contra OID sincronizado y reportar remoto, estado, OID fuente y OID local anterior.
- `--dry-run` no modifica refs, `FETCH_HEAD`, worktrees ni filesystem; solo muestra operaciones previstas y no afirma actualidad garantizada.

### Listar

```bash
"$SCRIPT" list
```

Operación solo lectura. Mostrar worktree principal, hermanos, ramas, HEAD y registros stale si existen.

### Remover

```bash
"$SCRIPT" remove --branch feature/example --dry-run
"$SCRIPT" remove --branch feature/example
```

Usar exactamente uno de `--branch BRANCH` o `--path PATH`. Solo remover worktree no principal y completamente limpio. No borrar rama local.

## Invariantes

- Reutilizar rama solicitada; nunca crear rama derivada para resolver conflicto.
- En `create`, ejecutar solo fetch dirigido a fuente remota y permitir únicamente fast-forward seguro de rama local; en `list` y `remove`, no ejecutar fetch.
- No usar `pull`, `push`, `commit`, `reset`, `clean`, `stash`, `prune` ni `--force`.
- No sobrescribir rutas existentes, symlinks, rutas registradas, rutas anidadas o rutas fuera del directorio hermano.
- No borrar worktree principal ni worktree con archivos trackeados, no trackeados o ignorados.
- No modificar archivos del proyecto fuera de operaciones propias de Git worktree.
- Helper mantiene compatibilidad Bash 3.2 y usa argumentos quoted; no usar `eval`.

## Códigos de salida

- `0`: éxito, ayuda o dry-run válido.
- `1`: error Git/runtime.
- `2`: argumentos inválidos.
- `3`: bloqueo de seguridad o confirmación requerida.

## Cierre

Reportar siempre:

- operación ejecutada;
- ruta absoluta del worktree;
- rama checkout y upstream cuando exista;
- fuente remota, estado de sincronización y OID fuente;
- OID local anterior cuando aplique;
- HEAD inicial/final;
- si principal fue movido a `develop`;
- validaciones omitidas o errores literales de Git.

No afirmar creación o remoción si helper no terminó exitosamente.
