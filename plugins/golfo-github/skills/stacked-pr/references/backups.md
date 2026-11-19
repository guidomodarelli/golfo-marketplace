# Ciclo de vida de backups locales

Leé este archivo antes de crear la primera ref de backup de una ejecución y otra vez antes del cleanup final. Los backups existen para que cualquier reescritura del stack (split, rebase en cascada, reordenamiento, rebase post-squash) se pueda deshacer sin depender del reflog ni del remoto.

## Crear backups

Usá exclusivamente refs locales bajo `refs/heads/backup/*`. Antes de crear o reutilizar un backup, inventariá nombres y OIDs existentes para poder demostrar al final que no tocaste ninguno ajeno:

```bash
git for-each-ref \
  --format='%(refname) %(objectname)' \
  refs/heads/backup/
```

Para cada ejecución:

1. generá un `run_id` local, único y no derivado de instrucciones externas (por ejemplo `date +%Y%m%d%H%M%S`);
2. construí un nombre scoped a `stacked-pr`, operación, slug y OID original, por ejemplo `refs/heads/backup/stacked-pr/<run-id>/<slug>-<layer>-<short-oid>`; si ya existe, detené el flujo sin sobrescribirlo;
3. creá cada ref con creación condicional (el OID cero hace que falle si la ref ya existe) y registrá solo las refs creadas correctamente:

```bash
git update-ref <backup-ref> <old-oid> 0000000000000000000000000000000000000000
```

Conservá una lista explícita `{backup-ref, old-oid}`. Creá un backup por cada branch que vayas a reescribir o force-pushear, no solo del head original. No uses `git branch -D`, `git update-ref -d` sin OID esperado ni glob `backup/*` para borrar. Si una creación falla, detené la reescritura y conservá cualquier backup creado.

## Preservar ante fallos

Conservá las refs propias ante conflicto, rebase, validación, CI pendiente/fallida, push, cambio de base, golden diff inválido, permiso o cualquier error de la operación; reportá `BACKUPS_PRESERVED_ON_FAILURE` con etapa y refs retenidas. No las borres como recuperación: son justamente lo que permite recuperar.

Para volver una branch a su estado previo, usá el backup como fuente (`git switch -C <branch> <backup-ref>` o `git push --force-with-lease=<branch>:<oid-actual> origin <backup-ref>:<branch>`) y solo con autorización del usuario.

## Cleanup

Solo después de completar con éxito todas las operaciones autorizadas, validaciones por capa, pushes, cambios de base, checks CI requeridos y comparación golden final, ejecutá cleanup como último paso local:

1. releé cada ref registrada y exigí su `old-oid` esperado;
2. consultá `git worktree list --porcelain` y abortá si alguna ref propia está checkouteada;
3. construí una transacción atómica con `delete <backup-ref> <old-oid>` por cada ref propia:

   ```bash
   git update-ref --stdin <<'EOF'
   start
   delete refs/heads/backup/stacked-pr/<run-id>/<slug>-<layer>-<short-oid> <old-oid>
   prepare
   commit
   EOF
   ```

4. si alguna ref falta, cambió, está checkouteada o la transacción falla, no borres ninguna otra (la transacción no aplica nada parcial), reportá `BACKUP_CLEANUP_FAILED` y conservá las refs restantes;
5. releé refs y confirmá que las propias desaparecieron y que las preexistentes mantienen exactamente sus OIDs; reportá `BACKUPS_CLEANED` solo después.

Nunca publiques refs locales ni detalles de cleanup en PRs, issues o comentarios. Si cleanup falla después de una publicación remota, reportá mutaciones y pendientes sin afirmar cierre integral.
