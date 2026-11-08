# Revisiones de IA y su caché

Qué revisa la IA en agent-ready-setup, qué se guarda de cada revisión y cómo se
configura. Leer al explicar por qué una revisión corrió o no corrió, al mostrar los
hallazgos conocidos o al cambiar las opciones `reviews.*`.

## Contenido

1. Qué se revisa
2. Unidad y clave
3. Dónde se guarda
4. Opciones
5. Ver los hallazgos y forzar una revisión
6. Límites

## 1. Qué se revisa

| Revisión | Quién la corre | Unidad |
|---|---|---|
| `instructions` | `merge-instructions.sh` en el apply y en la sincronización en segundo plano ([managed-agents-block.md](managed-agents-block.md)) | `AGENTS.md` junto con todas las rules que ve la revisión, del template y propias |
| `harness-consistency` | el hook `PostToolUse` `.agents/hooks/check-harness-consistency.sh`, después de editar una rule, una skill o `.claude/CLAUDE.md` | un par de documentos del mismo root (`.agents/` o `.claude/`) |

El hook compara cada documento editado contra todos los demás de su root, de a pares.
Los pares que ya están en la caché no se vuelven a revisar. Los que faltan van al provider
que hizo la edición en una sola llamada: `claude -p` en Claude Code y `codex exec
--sandbox read-only` en Codex (eventos `apply_patch`). Los documentos le llegan por stdin
y se tratan como datos, nunca como instrucciones. Si falta la CLI del provider, el
chequeo se omite con un aviso. Un documento borrado no deja nada que comparar.

## 2. Unidad y clave

Cada revisión se guarda por unidad, nunca con un hash global: editar una rule solo vuelve
a revisar las unidades donde participa. La clave de una unidad es el hash de todo lo que
puede cambiar su resultado:

- el contenido de cada archivo, con los fines de línea normalizados a LF;
- el id y la versión del chequeo, que cambia con su prompt;
- el provider y el modelo (`AGENT_READY_SETUP_MERGE_MODEL` cambia el de `instructions`);
- la versión de golfo-kit que aplicó el repo (`generator.version` del lockfile).

Si cambia cualquiera de estas partes, la unidad se revisa otra vez y su entrada se
reemplaza. Cada entrada guarda el veredicto (`consistent` o `findings`) y los hallazgos:
archivos, líneas citadas, tipo y texto. Un `AGENTS.md` recién creado desde el template se
guarda como revisado por `template`, así ningún provider lo revisa hasta que alguien lo edite.

## 3. Dónde se guarda

La caché es local y nunca llega al repositorio: vive en
`.git/info/agent-ready/reviews.json`, el directorio `info` que comparten todos los
worktrees del repo, así una revisión no se repite en cada worktree.

- Cada escritura toma un lock (`reviews.lock`, al lado), reescribe el archivo de forma
  atómica y descarta las entradas de archivos que ya no existen. Varios procesos pueden
  escribir a la vez sin corromperla.
- Una revisión que no se pudo guardar vuelve a correr la próxima vez. Nunca hace fallar
  el apply ni el hook.
- `agent-ready remove` la borra mientras ningún otro worktree del repositorio siga usando
  agent-ready-setup.

## 4. Opciones

Módulo `reviews` de la configuración ([configuration.md](configuration.md), claves en
[configuration-keys.md](configuration-keys.md)):

| Clave | Default | Efecto |
|---|---|---|
| `reviews.enabled` | `true` | `false` apaga las dos revisiones: el apply copia el bloque gestionado sin revisar y el hook no llama al provider |
| `reviews.cache` | `true` | `false` revisa todo cada vez y no guarda nada; funciona igual, solo más lento |
| `reviews.ttl` | sin vencimiento | horas que vale una entrada; pasado ese tiempo se revisa otra vez aunque nada haya cambiado |

Los hooks corren sin el motor, así que cada apply deja las tres opciones efectivas en la
caché y los hooks las leen de ahí: un cambio de configuración vale para los hooks después
del siguiente `agent-ready apply`.

## 5. Ver los hallazgos y forzar una revisión

- `agent-ready status` muestra los hallazgos conocidos sin llamar al provider (`--json`:
  objeto `reviews` con `units`, `stale` y `findings`). Una entrada cuyos archivos
  cambiaron desde su revisión cuenta como desactualizada y vuelve a correr en la próxima
  edición o apply.
- La revisión de `AGENTS.md` que sale de la caché repite sus inconsistencias en cada sync,
  hasta que alguien edite el archivo o la rule.
- `agent-ready apply --recheck` ignora la caché de `AGENTS.md` y lo revisa otra vez.

## 6. Límites

Todavía no se puede aceptar ni descartar un hallazgo: se sigue mostrando mientras su
unidad no cambie. No inventar un comando para silenciarlo; para que deje de aparecer hay
que resolver la contradicción en las rules o en `AGENTS.md`.
