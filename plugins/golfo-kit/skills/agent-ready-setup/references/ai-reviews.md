# Revisiones de IA y su caché

Qué revisa la IA en agent-ready-setup, qué se guarda de cada revisión, cómo se
configura y cómo se acepta o descarta un hallazgo. Leer al explicar por qué una revisión
corrió o no corrió, al mostrar los hallazgos conocidos, al cambiar las opciones `reviews.*`
o cuando el usuario pide aceptar o descartar un hallazgo.

## Contenido

1. Qué se revisa
2. Unidad y clave
3. Dónde se guarda
4. Opciones
5. Ver los hallazgos y forzar una revisión
6. Aceptar o descartar un hallazgo

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
chequeo se omite con un aviso. Si el provider no da una respuesta válida, el hook informa el
chequeo como incompleto, nunca como limpio, y esos pares se revisan en la próxima edición. Un
documento borrado no deja nada que comparar.

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

### Caché compartida (`reviews.commit`)

Con `reviews.commit: true`, cada resultado se guarda también en
`.agents/agent-ready.review-cache.json`, que se commitea. Un clon nuevo o el CI, que no tienen
caché local, saltean las revisiones cuya clave coincide sin pagarlas de nuevo, y `status` muestra
sus hallazgos. Está apagada por defecto, porque cualquiera puede editar un archivo versionado:

- La caché local responde primero. La compartida solo cuenta para una unidad con la misma clave
  y los mismos archivos.
- Un resultado compartido que no encontró nada nunca oculta un hallazgo que la caché local
  conoce para esa unidad: ahí la revisión vuelve a correr. Un resultado compartido con hallazgos
  siempre se muestra, porque solo agrega qué mirar.
- Nunca da un hallazgo por aceptado: eso solo lo hacen las decisiones de
  `.agents/agent-ready.reviews.json` (sección 6), con su motivo.
- Las entradas de archivos que ya no existen salen del archivo en la siguiente escritura, y
  `agent-ready remove` lo borra.

## 4. Opciones

Módulo `reviews` de la configuración ([configuration.md](configuration.md), claves en
[configuration-keys.md](configuration-keys.md)):

| Clave | Default | Efecto |
|---|---|---|
| `reviews.enabled` | `true` | `false` apaga las dos revisiones: el apply copia el bloque gestionado sin revisar y el hook no llama al provider |
| `reviews.cache` | `true` | `false` revisa todo cada vez y nunca reutiliza una entrada; igual guarda el último resultado, así `status` lo muestra y se puede decidir sobre sus hallazgos |
| `reviews.ttl` | sin vencimiento | horas que vale una entrada; pasado ese tiempo se revisa otra vez aunque nada haya cambiado |
| `reviews.commit` | `false` | `true` guarda además cada resultado en `.agents/agent-ready.review-cache.json` para commitearlo (ver «Caché compartida») |

Los hooks corren sin el motor, así que cada apply deja las opciones efectivas en la
caché, una vez por worktree, y los hooks las leen de ahí: un cambio de configuración vale
para los hooks después del siguiente `agent-ready apply` en ese worktree. Las revisiones
guardadas sí se comparten entre worktrees.

## 5. Ver los hallazgos y forzar una revisión

- Cada hallazgo lleva un id corto y estable (`! [3f9a1c2b7e] …`), calculado con su chequeo,
  los archivos que involucra, su tipo y las líneas que cita. Si la revisión redacta el mismo
  problema de otra forma, el id se mantiene, y agregar una rule ajena no lo cambia. Un
  hallazgo sin líneas citadas usa su texto. Una inconsistencia de `AGENTS.md` involucra la
  línea del proyecto y la rule con la que choca.
- `agent-ready status` y `agent-ready plan` muestran los hallazgos conocidos sin llamar al
  provider (`--json`: objeto `reviews` con `units`, `stale`, `findings`, `quiet` y
  `decisions`). Una entrada cuyos archivos cambiaron desde su revisión cuenta como
  desactualizada y vuelve a correr en la próxima edición o apply.
- La revisión de `AGENTS.md` que sale de la caché repite sus inconsistencias en cada sync,
  hasta que alguien edite el archivo o la rule, o decida sobre ellas.
- `agent-ready apply --recheck` ignora la caché de `AGENTS.md` y lo revisa otra vez.

## 6. Aceptar o descartar un hallazgo

Las decisiones del equipo se guardan en `.agents/agent-ready.reviews.json`, que se commitea.
Cada una tiene el id del hallazgo, el motivo, quién la tomó (el `user.name` de Git) y cuándo.

```bash
agent-ready review list [--json]                                       # hallazgos con su id y estado
agent-ready review accept <id> --reason "<motivo>" [--scope content|pair]  # es a propósito
agent-ready review dismiss <id> --reason "<motivo>" [--scope content|pair] # no es un problema real
agent-ready review reset <id>... | --all                               # vuelven a mostrarse
```

- **Motivo obligatorio.** Sin `--reason`, o con un motivo vacío, el comando falla (código
  2) y no escribe nada. Un id que ningún hallazgo actual usa también falla.
- **Sesiones simultáneas.** Cada decisión lee y reescribe el archivo bajo un lock, así dos
  sesiones que deciden a la vez conservan las dos decisiones.
- **Alcance `content` (default).** La decisión vale mientras no cambie ninguno de los
  archivos del hallazgo. Si cambia alguno, el hallazgo se revisa de nuevo y vuelve como
  «a confirmar» (`? [id] … (accepted before the files changed: <motivo>)`). Se confirma
  aceptándolo otra vez.
- **Alcance `pair`.** La decisión vale para ese par de archivos aunque cambie su
  contenido, hasta que alguien la quite con `reset`.
- **Solo ese hallazgo.** Aceptar nunca modifica las rules ni silencia otros hallazgos del
  mismo par: los demás se siguen mostrando con su propio id.
- **Archivo ilegible.** Si `.agents/agent-ready.reviews.json` no es JSON válido, los hooks lo
  ignoran y muestran todos los hallazgos. El CLI se niega a escribir encima y pide
  corregirlo o borrarlo.
- **Pedido en el chat.** Cuando el usuario pide aceptar un hallazgo («aceptá ese conflicto,
  es a propósito»), el agente corre `agent-ready review accept <id> --reason "<motivo>"`
  con el motivo que dio el usuario. Si no dio ninguno, se lo pregunta: nunca lo inventa.
  Usa `--scope pair` solo si el usuario quiere que la decisión siga valiendo aunque cambien
  los archivos.
- `review list` también muestra las decisiones que ya no usa ningún hallazgo actual, para
  quitarlas con `reset`. `agent-ready remove` conserva el archivo: son decisiones del equipo.
