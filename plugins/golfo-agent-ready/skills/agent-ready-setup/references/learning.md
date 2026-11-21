# Aprendizaje

agent-ready-setup aprende de las instrucciones del usuario: una preferencia o una restricción que se
repite puede quedar como rule del proyecto, y un procedimiento de varios pasos, como skill. Decide el
agente, con reglas de evidencia fijas. Al usuario nunca se le pregunta «¿lo guardo?».

Esta referencia cubre el registro, la evidencia, la decisión de `agent-ready learn record`, cómo
`agent-ready learn apply` escribe lo aprendido, cómo lo revisa el desarrollador (`accept`, `reject` y
`revert`) y qué pasa cuando el profile cambia una rule reemplazada (`keep` y `retire`). El resto vive en
referencias propias:

- [learning-episodes.md](learning-episodes.md): los episodios, los hooks, la revisión al cerrar un
  episodio y el barrido programado.
- [learning-reorganize.md](learning-reorganize.md): cómo `reorganize` consolida, divide o pasa a skill
  lo aprendido.
- [learning-share.md](learning-share.md): cómo el desarrollador junta lo que aprendieron varios
  clientes (`export` y `harvest`) y cómo lo sube a un pack (`promote`).

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
`Learning-Id: <id>`, `Learned-from: <episodios>` y `Learned-by: <id de la persona>`
([collaboration.md](collaboration.md)). `.agents/learning/log.md` suma una línea con la fecha,
la acción, el id, la rule y el statement, y nunca la cita.

Antes de escribir, la rule resultante pasa el lint de una rule atómica ([atomic-rules.md](atomic-rules.md)):
un statement con varias decisiones o demasiado largo no se escribe.

**El aviso al usuario.** Después de escribir, `apply` le recuerda al agente que le avise al usuario en
una línea que lo va a tener en cuenta («Lo tengo en cuenta para las próximas»), sin llamarlo rule ni
skill. Con `learning.notify` apagado le dice que no avise: lo aprendido queda igual en el commit y en
`log.md`. `accept`, que corre el desarrollador, no pide el aviso. En `--json` sale en `notify`.

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

## Cuando el profile cambia una rule reemplazada

Una rule aprendida que reemplaza una gestionada (`overrides=`) sigue en vigor aunque una versión nueva del
profile cambie esa rule: el repo se queda con lo que pidió su cliente. Pero el cambio del profile puede
importar, así que el plan de actualización lo muestra:

- `learn apply` guarda en la entrada la huella de cada rule gestionada que reemplaza (su statement, sus
  excepciones y sus detalles), en `learned.overridden`. Una reorganización la pasa a las rules nuevas.
- `agent-ready plan` (y el plan de cada apply) compara esa huella con la rule que el profile publica
  ahora. Si cambió, el reemplazo sale como **«customized, review»** (personalizado, revisar) debajo de su
  línea `Rule overridden:`, y en `--json` con `customized: {learningId, since}` en `ruleOverrides`. Un
  asset que la rule aprendida no reemplaza se recibe normal.
- El desarrollador decide: `agent-ready learn keep <id>` se queda con la versión aprendida (guarda la
  huella nueva en un commit y una línea `keep` del log, y la marca desaparece) y `agent-ready learn
  retire <id>` saca la rule aprendida con su `overrides=`, así el próximo apply vuelve a proyectar la
  versión nueva del profile. `retire` no trae de vuelta lo que la rule reemplazó antes: `learn revert`
  sí, y por eso no sirve para esto cuando la rule aprendida reemplazó a otra aprendida (pino → winston
  volvería a pino).

`learn retire` deja la entrada `retired`: si el cliente vuelve a pedirlo, cuenta como evidencia nueva,
igual que una revertida. No retira una rule `locked` ni una que otra pide con `requires=`, ni una skill
(esa se saca a mano o con `learn revert`).

El plan solo lee el repo: la huella de lo que el profile publica la guarda en la caché del usuario, y
`learn keep` la toma de ahí, así que primero hay que correr `agent-ready plan`. Un reemplazo escrito a
mano, sin entrada de aprendizaje, no tiene huella y no se marca.

## Comandos

```bash
# Una instrucción explícita: se aprende en el momento.
agent-ready learn record --kind rule --key records.header \
  --statement "Records carry the case number in the header." \
  --quote "de ahora en más, el número de expediente va en el encabezado" --explicit --session <sesión>

# Escribirla como rule del proyecto y commitearla.
agent-ready learn apply learn-5db4a07240

# Quedarse con una rule aprendida aunque el profile cambió la que reemplaza («customized, review»), o
# sacarla para volver a la del profile.
agent-ready learn keep learn-5db4a07240
agent-ready learn retire learn-5db4a07240

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

# Lo aprendido de este repo, sin citas, para que el cliente lo revise y lo comparta.
agent-ready learn export --output learned.json

# Lo que aprendieron varios repos (y los exports que pasaron los clientes), como candidatos para un pack.
agent-ready learn harvest --repos ../cliente-a ../cliente-b --export cliente-c.json

# Ver el cambio que haría un candidato en un profile del pack, y escribirlo en una rama con su pull request.
agent-ready learn promote harvest-1a2b3c4d5e --to ../mi-pack --profile base
agent-ready learn promote harvest-1a2b3c4d5e --to ../mi-pack --profile base --yes
```

`record` acepta `--date` con la fecha del mensaje, por ejemplo cuando la revisión de fin de sesión
registra un mensaje de ayer, y `--source session-end` para esa revisión. No acepta una fecha futura.
Dos sesiones pueden registrar a la vez: un lock en la caché del usuario ordena las escrituras.
