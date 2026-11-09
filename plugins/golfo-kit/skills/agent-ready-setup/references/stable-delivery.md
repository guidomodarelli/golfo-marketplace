# Entregar una solución estable a un cliente

Cómo dejar un repositorio con agent-ready-setup para que no cambie su comportamiento hasta que
alguien decida actualizarlo, y cómo actualizarlo después de forma controlada. Leer cuando el
usuario entrega una solución a un cliente, quiere que un repo quede «congelado» o pregunta cómo
actualizar uno entregado sin sorpresas.

## Contenido

1. El preset `delivered`
2. Dejarlo estable
3. Aplicar en otra máquina y en CI
4. Actualizar de forma controlada
5. Qué sigue actualizándose solo
6. Pisar un valor o salir del modo entregado

## 1. El preset `delivered`

Una sola clave, `updates.preset: delivered`, fija todo lo que necesita una solución entregada
([configuration.md](configuration.md), sección 7):

| Clave | Valor | Efecto |
|---|---|---|
| `updates.mode` | `pinned` | ninguna fuente se actualiza sola; el inicio de sesión solo informa |
| `sources.golfoKit.updates` | `pinned` | golfo-kit también queda en la revisión del lock |
| `updates.refresh` | `false` | plan, status y el inicio de sesión no usan la red para buscar versiones nuevas |
| `updates.fromLock` | `true` | cada apply que no actualiza ni cambia la selección reproduce el lock, como `--from-lock` |
| `ci.mode` | `fail` | el chequeo de CI falla si el repo se aparta del lock |

Sin el preset, el repositorio sigue en `auto`, como siempre: es opt-in por repositorio.

## 2. Dejarlo estable

1. `agent-ready preset delivered` escribe `updates.preset: delivered` en `.agents/agent-ready.json`.
2. Opcional: fijar golfo-kit a una versión concreta con `agent-ready update golfo-kit --to <tag>`.
   Sin `--to`, queda en la revisión que aplicó el último apply.
3. `agent-ready apply`, y commitear `.agents/agent-ready.json`, `.agents/agent-ready.lock.json` y
   los assets. El lock registra la revisión y el digest de cada fuente y el sha256 de cada asset.
4. Opcional: `agent-ready config set conflicts.block true`, para que una actualización futura
   que contradiga una rule propia se frene antes de escribir ([ai-reviews.md](ai-reviews.md),
   sección 7).

## 3. Aplicar en otra máquina y en CI

- `agent-ready apply` reproduce el lock: misma selección, misma revisión de cada fuente y mismos
  sha256. Si algo no coincide, falla antes de escribir y nombra la fuente o el archivo. Un asset
  borrado vuelve desde la revisión del lock, no desde una versión nueva.
- Un manifest editado a mano que cambia la selección no se aplica en silencio: el apply falla y
  pide decidirlo. Para cambiar la selección, pasarla explícita con `--profiles` o `--stack` (o
  `agent-ready profiles add|remove`); usa las revisiones fijadas.
- `agent-ready check` en el CI sale con `4` si el repo se apartó del lock
  ([ci-check.md](ci-check.md)).

## 4. Actualizar de forma controlada

1. `agent-ready update <fuente> --to <tag|commit> --dry-run` muestra sin escribir:
   - versión actual y nueva, y su changelog, con los cambios `breaking` resaltados;
   - archivos que se agregan, actualizan o retiran, con diff;
   - conflictos estructurales y semánticos con lo propio del proyecto.

   Ver «Version changes» en [profiles-and-lockfile.md](profiles-and-lockfile.md).
2. Si está bien, el mismo comando sin `--dry-run` lo aplica, solo para esa fuente: las demás
   quedan como estaban. La granularidad es por fuente, nunca por archivo.
3. Commitear el lock nuevo. Desde ahí, cada apply reproduce esa versión.

## 5. Qué sigue actualizándose solo

El motor (los scripts y hooks de agent-ready-setup) nunca se fija: sigue al plugin golfo-kit
instalado en la máquina. Por eso `--from-lock` deja que los archivos del motor sigan al plugin y
solo los cuenta. Si una fuente declara `minEngine` mayor que el motor instalado, el apply falla
antes de escribir y dice qué versión del plugin instalar.

## 6. Pisar un valor o salir del modo entregado

- Cada clave del preset se puede pisar en la misma capa o en una superior, por ejemplo
  `agent-ready config set updates.refresh true`. `agent-ready config explain` muestra de dónde
  sale cada valor: `project (preset updates.preset=delivered)`.
- `agent-ready preset none` vuelve a los defaults; `agent-ready preset` lista los presets y marca
  el vigente.
