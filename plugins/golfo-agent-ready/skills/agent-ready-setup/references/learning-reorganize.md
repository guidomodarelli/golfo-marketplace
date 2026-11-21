# Reorganizar lo aprendido

Cómo `agent-ready learn reorganize` ordena lo que aprendió un proyecto ([learning.md](learning.md)):
cuándo corre, qué aplica solo, qué deja como propuesta y cómo se deshace.


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
nueva, `Reorganizes:` con las entradas que reemplaza, `Learned-from:` y `Learned-by:`, y una línea `reorganize` en
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
| `learn revert <id>` | con el id de cualquier entrada nueva, deshace la operación completa: saca sus rules (o su skill, si nadie la cambió) y devuelve las rules que reemplazó tal como estaban, con su id y marcador. Las entradas nuevas quedan `reverted` y las anteriores vuelven a `learned`. No toca nada si una rule nueva cambió después (su statement, sus excepciones o detalles, o su marcador: `key`, alcance, `overrides`, `requires=` o `locked`) o una entrada de la operación cambió de estado, ni si otra rule pide con `requires=` una de las rules nuevas |
