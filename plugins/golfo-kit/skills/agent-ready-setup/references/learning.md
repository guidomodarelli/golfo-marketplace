# Aprendizaje

agent-ready-setup aprende de las instrucciones del usuario: una preferencia o una restricción que se
repite puede quedar como rule del proyecto, y un procedimiento de varios pasos, como skill. Decide el
agente, con reglas de evidencia fijas. Al usuario nunca se le pregunta «¿lo guardo?».

Esta referencia cubre el registro, la evidencia y la decisión de `agent-ready learn record`. Escribir lo
aprendido, revertirlo, los hooks de sesión, la reorganización y el `harvest` entre clientes son las
partes siguientes de la issue #156.

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
| `explicit` | el usuario pidió que dure |
| `evidence` | cada vez que el usuario la dio: `session`, `episode`, `date`, `source` (`in-session` o `session-end`) y `quote`, la frase literal |
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
vuelve, la entrada pasa otra vez a `candidate`, pero la evidencia vencida no suma episodios.

`learning.enabled` en `false` hace que `record` no registre nada y salga con 0; `status` y `list` siguen
leyendo el registro. Las claves y sus defaults: [configuration-keys.md](configuration-keys.md), sección
`learning`.

## Comandos

```bash
# Una instrucción explícita: se aprende en el momento.
agent-ready learn record --kind rule --key records.header \
  --statement "Records carry the case number in the header." \
  --quote "de ahora en más, el número de expediente va en el encabezado" --explicit --session <sesión>

# Qué espera una repetición y con qué configuración.
agent-ready learn status

# Todo el registro, o solo un estado, sin las citas.
agent-ready learn list --status candidate --json
```

`record` acepta `--date` con la fecha del mensaje, por ejemplo cuando la revisión de fin de sesión
registra un mensaje de ayer, y `--source session-end` para esa revisión. No acepta una fecha futura.
Dos sesiones pueden registrar a la vez: un lock en la caché del usuario ordena las escrituras.
