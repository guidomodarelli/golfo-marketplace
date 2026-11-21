# Colaboración: identidad y presets

Cómo comparten lo aprendido las personas de un repositorio, y quién es cada una aunque usen la misma
cuenta de Git. Leer al explicar `agent-ready identity`, el trailer `Learned-by:` o qué preset de
colaboración usa un repositorio.

> **Estado.** Esta es la base de la issue #169: la identidad, el preset y los merge drivers. La
> sincronización automática, el aprendizaje personal y la resolución de conflictos llegan en las partes
> siguientes; hasta entonces el preset solo se informa.

## Identidad

La identidad es de la persona que usa la máquina, no de la cuenta de Git ni del hardware: dos personas
pueden compartir una computadora con distintos usuarios del sistema, y una persona puede usar dos
computadoras.

- **Dónde vive.** `${XDG_CONFIG_HOME:-~/.config}/agent-ready-setup/identity.json`, del usuario del sistema
  operativo, con un `id` y un `name`. Nunca entra al repositorio.
- **Sin configurar,** el `id` es `usuario-del-sistema@nombre-de-la-máquina`, en minúsculas.
- **El `id`** tiene de 1 a 64 caracteres: letras minúsculas, dígitos, `.`, `_`, `-` y `@`, y empieza con
  una letra o un dígito. El `name` es una línea de hasta 80 caracteres.

| Comando | Qué hace |
|---|---|
| `agent-ready identity show [--json]` | Muestra la identidad, de dónde sale (el archivo o el default) y, dentro de un repositorio, su preset de colaboración. |
| `agent-ready identity set [--id <id>] [--name <nombre>]` | Guarda la identidad; lo que no se pasa queda como estaba. |
| `agent-ready identity link <id>` | Usa en esta máquina el `id` que la misma persona tiene en otra, y conserva el nombre. |

Ninguno necesita un repositorio.

**`Learned-by:`.** Cada commit del aprendizaje (`learn apply` y `learn reorganize`,
[learning.md](learning.md)) lleva `Learned-by: <id>` además de `Learning-Id:` y `Learned-from:`. Así
la persona queda registrada aunque el commit salga con una cuenta de Git compartida.

## Presets

`collaboration` (en el manifest del repositorio) dice cómo se comparte lo aprendido:

| Valor | Para | Qué cambia |
|---|---|---|
| `business` | una oficina: un estudio jurídico o contable, con varias personas en el mismo repositorio | aprendizaje personal y de equipo; el repositorio se sincroniza por las personas, que no usan Git |
| `software` | un repositorio de código | solo aprendizaje de equipo, que viaja en el mismo PR que el cambio que lo motivó |
| `auto` (default) | — | `software` si la selección resuelta tiene `software-development`, que todo stack de código requiere; `business` si no |

`auto` lee la selección del lock, así que cambia sola cuando el repositorio suma o saca un stack de
código. Para fijarla, `{"collaboration": "business"}` en `.agents/agent-ready.json`.

## Merge drivers

Git mezcla un archivo de texto línea por línea: dos personas que aprenden dos rules al final del mismo
archivo, o que suman evidencia al registro, chocan aunque cambiaron cosas distintas. Los drivers de
`scripts/agent_ready_merge_drivers.py` mezclan por la unidad del archivo, contra la versión común:

| Driver | Archivos | Cómo mezcla |
|---|---|---|
| `agent-ready-rules` | las rules de `.agents/rules/` | por el `id` de cada rule atómica ([atomic-rules.md](atomic-rules.md)): la rule que cambió de un lado toma ese cambio; si cambió igual de los dos, queda una vez; si cambió distinto, o cambió de un lado y se borró del otro, es un conflicto **de esa rule sola**, con los marcadores de siempre |
| `agent-ready-candidates` | `.agents/learning/candidates.json` | por el `id` de cada entrada: la evidencia es la unión de los dos lados, y cada otro campo toma el lado que lo cambió (el propio si cambiaron los dos). Nunca deja un conflicto, así el registro siempre se puede leer |
| `agent-ready-log` | `.agents/learning/log.md` | solo agrega: las líneas propias y después las que agregó el otro lado |

- **Qué archivos los usan** lo dice el bloque de `.gitattributes` del profile `learning`, que se versiona
  con el repositorio.
- **El comando** de cada driver no se puede versionar: cada `agent-ready apply` lo escribe en
  `.git/config` del repositorio (`merge.<driver>.driver`), apuntando a `scripts/agent-ready-merge` de la
  instalación que corre, porque la caché del plugin cambia de carpeta en cada actualización. Una revisión
  automática (`AGENT_READY_SETUP_REVIEW_MODE=1`) no lo toca.
- **Una versión que no se puede leer** (una rule con errores de formato, un JSON roto) se mezcla línea
  por línea con `git merge-file`, como si no hubiera driver.
- En una máquina sin el driver registrado (un clon donde nunca se corrió `apply`), Git mezcla línea por
  línea. Para que nunca pase, el `apply` de cada máquina lo registra.
