# Aprendizaje

agent-ready-setup aprende de las instrucciones del usuario: una preferencia o una restricción que se
repite puede quedar como rule del proyecto, y un procedimiento de varios pasos, como skill. Decide el
agente, con reglas de evidencia fijas. Al usuario nunca se le pregunta «¿lo guardo?».

Esta referencia cubre el registro, la evidencia, la decisión de `agent-ready learn record` y cómo
`agent-ready learn apply` escribe lo aprendido. Revertirlo, los hooks de sesión, la reorganización y el
`harvest` entre clientes son las partes siguientes de la issue #156.

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
| `status` | `candidate`, `learned`, `superseded` o `expired` |
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

## La decisión

`agent-ready learn record` suma la evidencia y dice qué hacer con la instrucción:

| Decisión | Cuándo |
|---|---|
| `learn` | la instrucción es explícita (`--explicit`), o una implícita llegó a `learning.threshold` episodios |
| `propose` | lo mismo, con `learning.mode` en `developer-review`: queda para el desarrollador y el agente no escribe nada |
| `wait` | una implícita con menos episodios que el umbral, o un candidato vencido |
| `already-learned` | la entrada ya está aprendida |

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
```

`record` acepta `--date` con la fecha del mensaje, por ejemplo cuando la revisión de fin de sesión
registra un mensaje de ayer, y `--source session-end` para esa revisión. No acepta una fecha futura.
Dos sesiones pueden registrar a la vez: un lock en la caché del usuario ordena las escrituras.
