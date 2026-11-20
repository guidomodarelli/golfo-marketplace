# Revisiones de IA y su caché

Qué revisa la IA en agent-ready-setup, qué se guarda de cada revisión, cómo se
configura y cómo se acepta o descarta un hallazgo. Leer al explicar por qué una revisión
corrió o no corrió, al mostrar los hallazgos conocidos, al cambiar las opciones `reviews.*`
o `conflicts.*`, al explicar un conflicto semántico del plan o cuando el usuario pide aceptar o
descartar un hallazgo. Los chequeos sin IA (contexto, máquina, realidad del repo, hooks y settings,
paridad), las skills que compiten y todos los conflictos juntos están en [structural-conflicts.md](structural-conflicts.md).

## Contenido

1. Qué se revisa
2. Unidad y clave
3. Dónde se guarda
4. Opciones
5. Ver los hallazgos y forzar una revisión
6. Aceptar o descartar un hallazgo
7. Conflictos semánticos con lo propio del proyecto

## 1. Qué se revisa

| Revisión | Quién la corre | Unidad |
|---|---|---|
| `instructions` | `merge-instructions.sh` en el apply y en la sincronización en segundo plano ([managed-agents-block.md](managed-agents-block.md)) | `AGENTS.md` junto con todas las rules que ve la revisión, del template y propias |
| `harness-consistency` | el hook `PostToolUse` `.agents/hooks/check-harness-consistency.sh`, después de editar una rule, una skill, `.claude/CLAUDE.md` o un `AGENTS.md` | un par de documentos del mismo root (`.agents/` o `.claude/`) |
| `harness-consistency` (conflictos semánticos) | `agent-ready plan` y el plan de cada apply (sección 7) | un par: una rule gestionada y una rule propia, el `AGENTS.md` del proyecto o un hook que puede bloquear |

El hook compara cada documento editado contra todos los demás de su root, de a pares. Con
`.agents/` entra también lo que el proyecto escribió en el `AGENTS.md` raíz y en cada `AGENTS.md`
anidado que la edición cambió, sin los bloques gestionados: editar solo dentro de un bloque no cambia
lo que se revisa. Es el mismo texto que lee `agent-ready plan`, así que los dos comparten la caché.
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

- el contenido de cada documento, con los fines de línea normalizados a LF;
- el id y la versión del chequeo, que cambia con su prompt;
- el provider y el modelo (`AGENT_READY_SETUP_MERGE_MODEL` cambia el de `instructions`);
- la versión del motor que aplicó el repo (`generator.version` del lockfile).

Si cambia cualquiera de estas partes, la unidad se revisa otra vez y su entrada se
reemplaza.

**Un archivo con rules atómicas** ([atomic-rules.md](atomic-rules.md)) bajo una carpeta `rules/` se
revisa rule por rule, en el hook y en `plan`:

- **Cada rule es un documento:** se llama `<archivo>#<id>` y lleva su comentario, el frontmatter del
  archivo y, de cada título que tiene arriba, el título y los párrafos de su sección, que dicen dónde se
  aplica la rule.
- **El resto del archivo** (títulos y párrafos) es el documento `<archivo>#`. Un archivo que fuera de
  sus rules solo tiene títulos no tiene ese documento. `<archivo>` solo sigue siendo el archivo entero,
  como en las demás revisiones (por ejemplo, la de `AGENTS.md`).
- **Qué no es una rule:** lo que está en un bloque de código, como un ejemplo. El hook lee las rules con
  el mismo formato que `agent-ready rules` (`assets/common/hooks/rule-format.py`).
- **Qué se vuelve a revisar:** cambiar una rule solo revisa los pares de esa rule. Cambiar un título o un
  párrafo revisa los de las rules de esa sección y los del resto del archivo. Los demás siguen en la
  caché, y un hallazgo nombra la rule (`.agents/rules/style.md <-> .agents/rules/testing.md#testing/mocks`).
- **Las rules del mismo archivo** no se comparan entre sí, como un archivo nunca se comparó consigo mismo.
- **Archivo entero:** un archivo sin rules atómicas, o con una forma que el lint marca como error (un
  comentario sin id o sin bullet, un id repetido), sigue siendo un documento.

Al provider le llega una línea por documento, con todos los de otro archivo con los que se compara. Cada entrada guarda el veredicto (`consistent` o `findings`) y los hallazgos:
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
| `reviews.enabled` | `true` | `false` apaga todas las revisiones: el apply copia el bloque gestionado sin revisar, el hook no llama al provider y el plan no busca conflictos semánticos |
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
  desactualizada, también en el resumen de `status --brief` del inicio de sesión.
- **Al iniciar sesión:** con `conflicts.sessionStart.reviews` (default `true`), el hook de
  `SessionStart` dice cuántas hay y las vuelve a revisar en segundo plano, sin hacer esperar a la
  sesión, con la CLI del provider de la sesión y lo que tienen sus archivos ahora. Lo revisado queda en
  la caché local; la versionada solo cambia con un apply. Un lock por proyecto hace que dos sesiones que
  arrancan juntas no revisen lo mismo, y el log queda en `~/.cache/agent-ready-setup/refresh-reviews-*.log`.
  Tras tres corridas seguidas sin una respuesta válida del provider, espera una hora antes de reintentar.
  Apagado, o con `conflicts.sessionStart.enabled: false`, esperan a la próxima edición o apply.

  ```text
  [marketplace-sync] 3 AI review(s) are out of date; reviewing them in the background with claude (conflicts.sessionStart.reviews).
  ```
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

## 7. Conflictos semánticos con lo propio del proyecto

`agent-ready plan`, y el plan que corre antes de cada apply, revisan con IA si las rules
gestionadas contradicen lo que el proyecto escribió, o las de otro profile o de otro nivel, en cinco
direcciones:

| Dirección | Qué se compara | Marca en el plan |
|---|---|---|
| update | cada rule gestionada que el apply crea, actualiza o adopta, con el contenido que va a escribir, contra cada rule propia (`.agents/rules/` sin equivalente gestionado) y contra lo que el proyecto escribió en su `AGENTS.md`, fuera del bloque gestionado que el mismo apply puede reemplazar | `(this update)` |
| project | cada rule propia contra cada rule gestionada ya aplicada que no cambia | `(a project rule)` |
| hooks | los hooks `PreToolUse` de `.claude/settings.json` y `.codex/hooks.json`, que pueden frenar una llamada a una herramienta, con su matcher, su comando y el script del proyecto que corren, contra cada rule y skill gestionada de la raíz: como update si el apply la cambia (y `conflicts.block` lo frena), como lo propio del proyecto si ya está aplicada. Se apaga con `conflicts.hooks.enabled` | `(this update; a hook that blocks it)` o `(a hook of the project; a hook that blocks it)` |
| profiles | cada rule de un pack contra cada rule gestionada de otro profile del mismo nivel; las de los profiles del contenido (`golfo`) no se revisan entre sí. Como llega con el apply, `conflicts.block` lo frena igual que un update. Para quedarse con una de las dos, `overrides` | `(two profiles)` |
| levels | una rule de la raíz contra una de un workspace de un monorepo, con un pack de alguno de los dos lados, y lo que el proyecto escribió en un `AGENTS.md` anidado (de un workspace o de un destino anidado) contra cada rule gestionada de la raíz que el apply cambia; `agent-ready check` la compara también con las ya aplicadas. Las rules de dos workspaces no se comparan, porque nunca se cargan juntas. Llega con el apply, como profiles | `(two levels; root and apps/web/)` |

- **Los dos niveles.** Cuando los dos archivos de un hallazgo son de niveles distintos (la raíz, un
  workspace o la carpeta de un `AGENTS.md` anidado), el plan los nombra después de la dirección, en el
  orden de los archivos, cualquiera sea la dirección. `--json` los deja en `levels` de cada hallazgo.

- **Misma revisión y misma caché.** Usa el prompt, la llamada al provider y la caché de
  `harness-consistency`: un par que el hook ya revisó no se paga de nuevo, `status` muestra sus
  hallazgos sin llamar al provider y se aceptan o descartan con `agent-ready review` (sección 6).
  Toma `reviews.cache`, `reviews.ttl` y `reviews.commit` de la configuración de esa corrida, sin
  esperar a que un apply los registre, y revisa con el provider de la sesión, también en la
  sincronización en segundo plano. Un `plan` guarda lo que revisó solo en la caché local: con
  `reviews.commit`, el apply lo publica en `.agents/agent-ready.review-cache.json`.
- **Lo propio de `AGENTS.md`.** De `AGENTS.md` la revisión lee, y la caché identifica, solo lo que
  el proyecto escribió, sin el bloque gestionado. Por eso un conflicto con `AGENTS.md` sigue
  listado y se puede decidir aunque el mismo apply reescriba el bloque.
- **Antes del primer apply.** Sin `AGENTS.md`, el `CLAUDE.md` raíz que el apply va a promover a
  `AGENTS.md` ocupa su lugar en la revisión, con el nombre `AGENTS.md`, salvo que sea solo el proxy.
  También vale para una variante de mayúsculas (`claude.md`) si es la única y Git no la ignora,
  que es la que la normalización renombra.
- **Decidir antes del apply.** Un conflicto de dirección update habla de una rule que todavía no
  está en disco, así que el plan lo guarda en el directorio de Git del worktree
  (`agent-ready/semantic-conflicts.json`). `review list`, `accept` y `dismiss` lo conocen desde ahí.
  Una decisión de alcance `content` vale para el contenido revisado, el que el apply va a escribir,
  así sigue valiendo después del apply. Si la rule gestionada cambia otra vez, el hallazgo vuelve
  «a confirmar».
- **Solo informa.** Nunca borra ni reescribe una rule. El plan los lista en «Semantic conflicts»
  con su id y el apply los repite como avisos en stderr antes de escribir. En el JSON del plan van
  en `semanticConflicts`, con `pairs`, `fromCache`, `reviewed`, `unchecked`, `uncheckedUpdate`,
  `reason`, `findings` (cada uno con su `direction`), `quiet` y `block`.
- **Nunca limpio sin respuesta.** Un par sin revisar deja el chequeo como «Check incomplete»,
  con el motivo. Pasa sin red (`--offline`), en una revisión automática
  (`AGENT_READY_SETUP_REVIEW_MODE=1`), sin la CLI del provider o si el provider no da una
  respuesta válida. En los dos primeros casos responde solo la caché.

Módulo `conflicts` de la configuración:

| Clave | Default | Efecto |
|---|---|---|
| `conflicts.enabled` | `true` | `false` no busca conflictos semánticos; `reviews.enabled: false` también los apaga |
| `conflicts.block` | `false` | `true` frena antes de escribir un apply cuya actualización trae un conflicto visible o que no pudo revisar algún par de la actualización |

Con `conflicts.block`, los conflictos de dirección project no frenan, porque ya están en el
repositorio. Para destrabar el apply: cambiar la rule, o aceptar o descartar cada hallazgo con
`agent-ready review accept|dismiss <id> --reason "<motivo>"`.
