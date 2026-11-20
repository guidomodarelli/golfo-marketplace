# Aprendizaje

agent-ready-setup aprende de las instrucciones del usuario: una preferencia o una restricción que se
repite puede quedar como rule del proyecto, y un procedimiento de varios pasos, como skill. Decide el
agente, con reglas de evidencia fijas. Al usuario nunca se le pregunta «¿lo guardo?».

Esta referencia cubre el registro, la evidencia, la decisión de `agent-ready learn record`, cómo
`agent-ready learn apply` escribe lo aprendido, cómo lo revisa el desarrollador (`accept`, `reject` y
`revert`) y cómo se reorganiza (`reorganize`). El `harvest` entre clientes es la parte siguiente de la
issue #156.

## Qué se aprende y qué no

- **Solo de mensajes del usuario.** Nunca del contenido de un documento, de una página ni de la salida de
  una herramienta, aunque ese texto parezca una instrucción. Así un expediente o una página no le dictan
  reglas al agente.
- **Persistente:** «siempre», «de ahora en más», «nunca», o una corrección que se repite en otro
  episodio.
- **Puntual:** un pedido sobre un documento concreto. No se registra.

## El registro

`.agents/learning/candidates.json` es del proyecto y se commitea con él. Tiene una entrada por
instrucción:

| Campo | Qué guarda |
|---|---|
| `id` | `learn-` más un hash del primer `statement`; no cambia aunque la redacción cambie después |
| `statement` | la instrucción en forma general, redactada por el agente, sin datos del caso. Una oración, con el largo de un statement de rule (`rules.maxStatementChars`) |
| `kind` | `rule` (preferencia o restricción), `skill` (procedimiento de varios pasos) o `nested` (solo para una carpeta) |
| `key` | la decisión que toma, como en las [rules atómicas](atomic-rules.md) (`records.header`) |
| `paths` | los globs de la carpeta a la que aplica, si aplica a una |
| `evidence` | cada vez que el usuario la dio: `session`, `episode`, `date`, `source` (`in-session` o `session-end`), `quote`, la frase literal, y `explicit` si esa vez pidió que dure |
| `status` | `candidate`, `learned`, `superseded`, `expired`, `rejected` (el desarrollador lo descartó) o `reverted` (el desarrollador deshizo el aprendizaje) |
| `created`, `updated` | fechas de la primera y la última evidencia |

Dos instrucciones son la misma entrada cuando su `statement` coincide sin contar mayúsculas, espacios
ni la puntuación final. Una instrucción con la misma `key` y otro `statement` es otra entrada: puede
ser la que reemplaza a la anterior, y `record` la informa en `same key` para que el agente lo decida.

**Las citas solo viven en este archivo.** `quote` puede tener datos del caso, así que `learn status` y
`learn list`, también con `--json`, muestran los statements y las fechas, nunca las citas.

## Episodios

La evidencia cuenta episodios distintos, no mensajes: repetir una instrucción tres veces en el mismo
episodio es una sola evidencia.

- Con `--episode`, el episodio es el que informó el hook de la sesión.
- Sin `--episode`, otra sesión o otro día empiezan un episodio nuevo: el episodio es la sesión más la
  fecha del mensaje.

**El hook del prompt** (`UserPromptSubmit` en Claude Code y en Codex, con
`.agents/hooks/learning-hook.sh`) corre `agent-ready learn episode --session <id> --touch` en cada
mensaje del usuario. Guarda por sesión, en `.git/info/agent-ready/episodes.json` (local, nunca
versionado), el episodio, cuándo empezó y la hora del último mensaje. El mensaje siguiente abre un
episodio nuevo si es de otro día de la máquina o si pasaron `learning.episodeGapHours` horas (4 por
defecto) sin mensajes. Así un chat largo cuenta varios episodios. Nada corre entre mensajes: el corte
se calcula cuando llega el próximo. Al abrir un episodio, el hook le dice al agente el id que tiene que
pasar en `--episode`; el resto de los mensajes no imprime nada.

- `agent-ready learn episode --session <id>` muestra el episodio actual de la sesión.
- `agent-ready learn episode --session <id> --scope-question` registra la única pregunta de alcance
  del episodio, y falla si ya se hizo: ahí el agente aplica la instrucción solo al documento actual y la
  registra sin `--explicit`.

**El resumen al iniciar la sesión** (`SessionStart`, también después de compactar en Claude Code)
corre `agent-ready learn summary`: las últimas líneas de `log.md` y los candidatos que esperan otro
episodio, sin las citas, para que el agente cuente como segunda evidencia una instrucción que vuelve.
No llama a ningún modelo. `learning.hooks.sessionStart` apagado lo deja sin salida.

El hook y el resumen no hacen nada mientras el repositorio no use el profile `learning` (el lockfile
lo registra en `profileOrder`) o `learning.enabled` esté apagado, y nunca hacen fallar el prompt ni la
sesión.

### Revisión al cerrar un episodio

La detección en la conversación puede perder una instrucción: el agente no la registró, o se compactó
el contexto antes. Por eso, al cerrarse un episodio, una revisión en background lee **solo los mensajes
del usuario** de ese episodio en el transcript local del provider y registra como candidatas, con
`source` `session-end`, las instrucciones que deben durar. Nunca escribe una rule ni una skill: el
agente decide en la sesión siguiente con las reglas de «La decisión», y el resumen de inicio se las
muestra.

Un episodio se cierra en cualquiera de estos momentos:

- **Al cerrar el chat:** `SessionEnd` en Claude Code (`learn episode --session <id> --end`).
- **Al empezar el siguiente episodio** del mismo chat.
- **Al barrer desde cualquier hook:** el prompt o el inicio de sesión de cualquier chat del repositorio
  cierra los episodios sin mensajes hace `learning.episodeGapHours` horas o de otro día.
- **Con el barrido programado** (abajo), aunque nadie vuelva a escribir en el repositorio.

Antes de compactar (`PreCompact` en Claude Code, `--review-now`) se revisa lo que el episodio lleva
dicho, y la revisión de su cierre empieza desde ahí. Codex no tiene esos dos eventos: sus episodios se
cierran con el barrido.

- El hook guarda en `episodes.json` el `transcript_path` y el provider del payload; la revisión corre
  con ese provider y el modelo de las revisiones de IA, sin herramientas ni sesión.
- Del transcript lee los mensajes del usuario y deja afuera lo que escribió el agente, los resultados de
  herramientas y lo que agrega el harness (comandos, recordatorios, contexto del entorno), que se
  reconoce por sus etiquetas. Un mensaje del usuario que empieza con otro markup se revisa igual.
- Una cita que no está en los mensajes del usuario se descarta: la revisión no puede inventar evidencia.
- Cada mensaje cuenta en un solo episodio: la ventana de cada revisión empieza donde terminó la
  anterior del mismo chat, aunque dos episodios empiecen con minutos de diferencia (por ejemplo, a
  medianoche). La ventana nunca pasa del momento en que cerró el episodio, así que un chat que se
  retoma enseguida revisa sus mensajes nuevos en el episodio siguiente.
- Lo que se manda al provider tiene un tope de caracteres: entran primero los mensajes más nuevos, y
  un mensaje enorme (un documento pegado) entra recortado.
- Cada episodio se revisa una vez. Si el provider falla o otra sesión tiene tomado el registro, queda
  en la cola para el barrido siguiente, hasta tres intentos. Un episodio sin transcript se cierra sin revisión.
- La cola vive en `episodes.json` hasta que cada revisión termina: si el barrido se corta (se apaga la
  máquina), otro barrido retoma esas revisiones una hora después.
- Nunca llama a un provider en CI ni en review mode: el episodio queda en la cola para la máquina del
  usuario.
- La revisión corre desacoplada del hook con `scripts/run-detached.py` (`agent-ready learn sweep`, con
  su log privado en `~/.cache/agent-ready-setup/learning-sweeps/`), así que el prompt no la espera.
- `learning.hooks.sessionEnd` apagado cierra los episodios sin revisarlos.

### Barrido programado

El apply registra una tarea del usuario en el planificador del sistema que corre
`agent-ready learn sweep --registered` cada `learning.sweep.intervalMinutes` minutos (60 por defecto).
Así un episodio que nadie retoma se cierra y se revisa como mucho `episodeGapHours` +
`sweep.intervalMinutes` después de su último mensaje.

- **Sin permisos de administrador:** Windows usa una tarea del usuario actual del Programador de tareas
  (`schtasks`, nunca `/RU SYSTEM`); macOS, un LaunchAgent en `~/Library/LaunchAgents` (nunca un
  LaunchDaemon); Linux, el `crontab` del usuario. Corre solo con la sesión del usuario iniciada.
- **Una tarea por máquina:** cada repositorio que usa learning se anota en
  `~/.cache/agent-ready-setup/learning-schedule/projects/`. La tarea corre tan seguido como pide el más
  frecuente, barre todos y olvida los que ya no están en el disco. Se va con el último repositorio.
- **El motor del último apply:** la tarea arranca `learning-schedule/run-sweep.py`, que apunta al
  motor que la registró. Cada apply la reescribe solo si cambió. El runner restaura el `PATH` y el
  `XDG_CACHE_HOME` del apply, porque el planificador arranca con un entorno mínimo. Si la tarea no le
  da salida (`pythonw.exe`), la escribe en `learning-schedule/last-sweep.log`.
- **Retiro:** `intervalMinutes: 0`, un apply sin el profile `learning` o `agent-ready remove` sacan al
  repositorio de la tarea. Si el sistema rechazó borrar la tarea del último repositorio, el próximo
  `learn schedule`, apply o barrido lo vuelve a intentar.
- **Si el sistema la rechaza** (una política de la máquina, `cron.deny`, sin `crontab`), el apply no
  falla: lo avisa en una línea, y `agent-ready status` y `agent-ready doctor` informan que falta. Los
  episodios se siguen cerrando al terminar el chat y desde otro hook. `agent-ready learn schedule`
  vuelve a registrarla, igual que un apply.
- **CI y review mode:** nunca tocan el planificador.

## La decisión

`agent-ready learn record` suma la evidencia y dice qué hacer con la instrucción:

| Decisión | Cuándo |
|---|---|
| `learn` | la instrucción es explícita (`--explicit`), o una implícita llegó a `learning.threshold` episodios |
| `propose` | lo mismo, con `learning.mode` en `developer-review`: queda para el desarrollador y el agente no escribe nada |
| `wait` | una implícita con menos episodios que el umbral, o un candidato vencido |
| `already-learned` | la entrada ya está aprendida |
| `rejected` | el desarrollador la rechazó: ni una instrucción explícita la aprende, hasta que el desarrollador la acepte |

Un candidato sin evidencia en `learning.candidateTtlDays` días vence (`expired`). Si la instrucción
vuelve, la entrada pasa otra vez a `candidate`, pero la evidencia vencida no suma: ni sus episodios ni
un pedido explícito. Cuenta la evidencia desde el último hueco de más de `learning.candidateTtlDays`
días entre dos evidencias, así que repeticiones espaciadas que nunca dejaron vencer al candidato suman
todas.

`learning.enabled` en `false` hace que `record` no registre nada y salga con 0; `status` y `list` siguen
leyendo el registro. Las claves y sus defaults: [configuration-keys.md](configuration-keys.md), sección
`learning`.

## Escribir lo aprendido

Cuando `record` dice `learn`, el agente corre `agent-ready learn apply <id>`. Solo escribe en la zona del
proyecto, nunca en un asset que escribió un apply (los que el lockfile registra):

| Caso | Qué hace |
|---|---|
| Una rule del proyecto ya decide la misma `key` | edita esa rule en el lugar: cambia el statement y conserva su marcador, sus excepciones y sus detalles (`update`) |
| Esa rule es una aprendida antes | la reemplaza igual, y la entrada anterior pasa a `superseded` con `supersededBy` (`supersede`) |
| Una o más rules gestionadas deciden la misma `key` | agrega la rule aprendida con `overrides=<fuente>:<id>` de cada una, sin tocarlas: el próximo apply la deja afuera de ese repo y otro repo con el mismo profile no cambia |
| Una rule de la misma `key` es `locked`, sea gestionada o del proyecto | no escribe nada ni commitea, y sale con error: el agente le dice al usuario en una línea que eso no se puede cambiar. La entrada sigue en `candidate` |
| La rule gestionada es del núcleo (`base/` del pack) | no escribe nada: el núcleo todavía no se puede reemplazar con `overrides` |
| La rule gestionada ya reemplaza a otra con `overrides` | no escribe nada: el motor no acepta cadenas de reemplazos |
| Otra rule del proyecto, de cualquier `key`, ya reemplaza a esa gestionada | no escribe nada: una rule se reemplaza una sola vez |
| Más de una rule activa decide la `key` (sin contar las gestionadas que una rule propia ya reemplaza) | no escribe nada: editar una dejaría las otras en vigor. El equipo deja una primero |
| La rule de la misma `key` vale para otro alcance (los `paths` de su marcador o, sin ellos, los `paths:` del frontmatter de su archivo) | no escribe nada: una instrucción de una carpeta nunca pisa una de todo el repositorio, ni al revés. Se registra con una `key` propia para ese alcance |
| Ninguna rule decide esa `key` | agrega una rule nueva en `.agents/rules/learned.md` con id `learned/<key>` (o las primeras palabras del statement), su `key` y sus `paths` |
| `kind` es `skill` | el agente escribe la skill en `.agents/skills/<nombre>/SKILL.md` y la registra con `--skill .agents/skills/<nombre>`. El próximo sync o apply le da su vista en `.claude/skills/`, como a toda skill propia del proyecto; si en `.claude/skills/` ya hay una skill propia de Claude con ese nombre, la preserva y lo informa |
| `kind` es `nested`, o la entrada tiene `paths` | escribe la rule en `.agents/rules/learned-<carpetas>.md`, un archivo propio con `paths:` en el frontmatter, además de `paths=` en el marcador: Claude descarta los comentarios HTML y solo el frontmatter le deja el alcance. Sin `--paths` en `record`, `apply` lo pide |

Cada aprendizaje es **un commit** con solo sus archivos (la rule o la skill, `candidates.json` y
`log.md`), aunque haya otros cambios en el índice. El mensaje es `learn: <statement>` con los trailers
`Learning-Id: <id>` y `Learned-from: <episodios>`. `.agents/learning/log.md` suma una línea con la fecha,
la acción, el id, la rule y el statement, y nunca la cita.

Antes de escribir, la rule resultante pasa el lint de una rule atómica ([atomic-rules.md](atomic-rules.md)):
un statement con varias decisiones o demasiado largo no se escribe.

`apply` se niega con un error si la entrada no está decidida para aprender: espera otro episodio,
venció, ya está aprendida, fue reemplazada (`superseded`) o `learning.mode` es `developer-review`.
Una instrucción reemplazada vuelve solo si el usuario la da de nuevo: pasa otra vez a `candidate` y
cuenta solo la evidencia nueva, así puede reemplazar a su vez a la que la había reemplazado. La rule nueva entra al bloque
gestionado de `AGENTS.md` y a `.claude/` en el próximo sync o apply, como cualquier rule del proyecto.

## Revisar lo aprendido

Decide el agente; lo que necesita criterio humano lo revisa el desarrollador, nunca el cliente, con
`agent-ready learn status`, `list` y `log.md`:

| Comando | Qué hace |
|---|---|
| `learn accept <id>` | aprende la entrada aunque las reglas de evidencia no alcancen o `learning.mode` sea `developer-review`. Escribe igual que `apply` y con sus mismos límites (`locked`, gestionado, alcance), y el log la marca `(accepted)`. `learn status` lista las propuestas de `developer-review` |
| `learn reject <id>` | descarta una entrada que no está aprendida: queda `rejected` y la evidencia nueva no la aprende. Commitea el registro y el log. Una entrada `superseded` no se rechaza: revertir la que la reemplazó la devolvería, así que primero se revierte esa |
| `learn revert <id>` | deshace un aprendizaje. Una rule que creó se saca (y su archivo aprendido también, si no quedó nada más que el encabezado que escribió `apply`), y una que editó vuelve a su statement anterior, buscándola por su id, así no importa qué se escribió alrededor después. Si la entrada había reemplazado a otra, esa vuelve a `learned`, aunque el usuario la haya repetido mientras tanto; si el desarrollador la rechazó, `revert` no toca nada y pide aceptarla primero. Una skill vuelve a como estaba antes del commit del aprendizaje. Commitea con `Learning-Id:` y `Reverts: <sha>` |

`revert` no toca nada si la rule cambió después del aprendizaje (ya no dice lo que escribió, o alguien le
agregó excepciones o detalles, o le cambió el marcador, a una rule que el aprendizaje creó) o si el
parche de una skill no aplica: lo dice y hay que deshacerlo a mano. Una instrucción revertida vuelve
como candidata si el usuario la da de nuevo, contando solo la evidencia nueva.

## Reorganizar lo aprendido

Lo aprendido crece de a una rule. `agent-ready learn reorganize` lo ordena con tres operaciones:
consolidar rules redundantes en una (`consolidate`), dividir una rule que tiene varias instrucciones
(`split`) y pasar a skill una rule que es un procedimiento (`to-skill`). Nunca borra una instrucción:
lo que saca, lo reemplaza.

**Cuándo.** Solo cuando se cumple un disparador, que se calcula sin llamar a un modelo:

| Disparador | Cuándo se cumple |
|---|---|
| `long-rule` | una rule aprendida tiene más de `learning.reorganize.maxRuleLines` líneas no vacías desde su bullet (12 por defecto) |
| `topic` | tres o más rules aprendidas comparten el tema: el primer segmento de su `key` (`records.header` y `records.date` son del tema `records`) |
| `context-budget` | las rules raíz sin `paths:`, que Claude carga en cada sesión, pasan `conflicts.contextBudget.rulesBytes` |
| `conflict` | una rule aprendida y otra deciden la misma `key` con distinto contenido |

En background corre al cerrar el chat (`SessionEnd`) y desde el barrido programado, como mucho una vez
cada `learning.reorganize.minIntervalDays` (7 por defecto), nunca desde el hook del prompt: no corta una
tarea. La hora de la última vez queda en `.git/info/agent-ready/reorganize.json`, local. Si el provider
falla o no hay disparador que revisar, no cuenta como corrida. `agent-ready learn reorganize` la corre en
el momento, sin esperar el intervalo. En CI y en review mode no llama a ningún provider.

**Qué se aplica solo.** El provider propone las operaciones mirando solo las rules de los disparadores,
como datos. Cada operación pasa por estos filtros:

1. Se descarta si nombra una rule que no es aprendida, mezcla rules de distintos archivos o alcances,
   toca una rule `locked` o un archivo gestionado, saca una rule que otra pide con `requires=`, repite un
   statement que ya está en el registro, o no tiene la forma de su tipo. Una rule entra en una sola operación por corrida.
2. Queda como **propuesta** para el desarrollador si `learning.mode` es `developer-review`, si
   `learning.reorganize.auto` está apagado, si es `to-skill`, si una de sus rules no la creó el
   aprendizaje (una rule del equipo que el aprendizaje editó), si tiene excepciones, detalles o
   `requires=` que alguien agregó, si consolida rules de distintas `key`, o si divide una rule con `key`
   u `overrides` (alguna de las nuevas tendría que quedárselos sola).
3. Lo que pasa los dos filtros va a una segunda llamada, que compara las rules de antes con las de
   después. Se aplica solo si responde que el comportamiento es el mismo; si no, o si no responde,
   queda como propuesta con el motivo.

Antes de escribir, la reorganización vuelve a leer las rules: si cambiaron mientras respondía el
provider, la operación se descarta. Cada operación aplicada es un commit con un `Learning-Id:` por rule
nueva, `Reorganizes:` con las entradas que reemplaza y `Learned-from:`, y una línea `reorganize` en
`log.md`. Las rules nuevas son entradas `learned` del registro con la evidencia de las que reemplazan,
que pasan a `superseded`. Las rules nuevas conservan la `key` común y la unión de los `overrides`, y
llevan ids nuevos: nunca heredan el de una rule que reemplazan.

Una corrida sin disparador no cuenta para el intervalo, así que un disparador que aparece mañana se
revisa mañana. Si el provider vuelve a proponer una operación que ya espera y sus rules cambiaron desde
entonces, la propuesta nueva reemplaza a la vieja.

**Propuestas.** Las operaciones que esperan quedan en `.agents/learning/reorganize.json`, versionado y
commiteado, con el motivo y el veredicto de la revisión. `learn status` dice cuántas esperan.

| Comando | Qué hace |
|---|---|
| `learn reorganize --plan` | muestra los disparadores de ahora y las propuestas que siguen valiendo, sin modelo y sin cambiar nada. Una propuesta cuyas rules cambiaron o ya no están deja de mostrarse |
| `learn reorganize --accept <id>` | el desarrollador aplica una propuesta sin pasar por la revisión de equivalencia. La rechaza si sus rules cambiaron desde que se propuso, o si es `locked`, gestionada o de otro alcance. Una `to-skill` escribe `.agents/skills/<nombre>/SKILL.md` y saca la rule; el archivo aprendido se borra si quedó solo el encabezado. El log la marca `(accepted)` |
| `learn reorganize --dismiss <id>` | descarta la propuesta; una reorganización posterior puede volver a proponerla |
| `learn revert <id>` | con el id de cualquier entrada nueva, deshace la operación completa: saca sus rules (o su skill, si nadie la cambió) y devuelve las rules que reemplazó tal como estaban, con su id y marcador. Las entradas nuevas quedan `reverted` y las anteriores vuelven a `learned`. No toca nada si una rule nueva cambió después (su statement, sus excepciones o detalles, o su marcador: `key`, alcance, `overrides`, `requires=` o `locked`) o una entrada de la operación cambió de estado |

## Comandos

```bash
# Una instrucción explícita: se aprende en el momento.
agent-ready learn record --kind rule --key records.header \
  --statement "Records carry the case number in the header." \
  --quote "de ahora en más, el número de expediente va en el encabezado" --explicit --session <sesión>

# Escribirla como rule del proyecto y commitearla.
agent-ready learn apply learn-5db4a07240

# Qué espera una repetición y con qué configuración.
agent-ready learn status

# Todo el registro, o solo un estado, sin las citas.
agent-ready learn list --status candidate --json

# El episodio de la sesión, y la única pregunta de alcance del episodio.
agent-ready learn episode --session <sesión>
agent-ready learn episode --session <sesión> --scope-question

# Cerrar los episodios inactivos y revisar los cerrados, como hacen los hooks en background.
agent-ready learn sweep

# Registrar el barrido programado como pide learning.sweep.intervalMinutes, como hace el apply.
agent-ready learn schedule

# Lo que corre la tarea programada: el barrido de cada repositorio registrado.
agent-ready learn sweep --registered

# Los disparadores y las propuestas de reorganización, sin modelo; reorganizar ahora; decidir una propuesta.
agent-ready learn reorganize --plan
agent-ready learn reorganize
agent-ready learn reorganize --accept reorg-1a2b3c4d5e
agent-ready learn reorganize --dismiss reorg-1a2b3c4d5e
```

`record` acepta `--date` con la fecha del mensaje, por ejemplo cuando la revisión de fin de sesión
registra un mensaje de ayer, y `--source session-end` para esa revisión. No acepta una fecha futura.
Dos sesiones pueden registrar a la vez: un lock en la caché del usuario ordena las escrituras.
