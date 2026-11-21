# Colaboración: identidad y presets

Cómo comparten lo aprendido las personas de un repositorio, y quién es cada una aunque usen la misma
cuenta de Git. Leer al explicar `agent-ready identity`, el trailer `Learned-by:` o qué preset de
colaboración usa un repositorio.

> **Estado.** Esta es la base de la issue #169: la identidad y el preset. La sincronización automática,
> el aprendizaje personal y la resolución de conflictos llegan en las partes siguientes; hasta entonces
> el preset solo se informa.

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
