# Sincronización del equipo

Cómo llega lo que aprendió una persona de una oficina a las demás, sin que nadie use Git. Leer al explicar
`agent-ready sync`, por qué algo aprendido no llegó a otra máquina o qué dice la línea `Sync:` de
`agent-ready status`. La identidad y los presets están en [collaboration.md](collaboration.md).

> **Estado.** Partes 169c a 169f de la issue #169: la sincronización, la promoción a equipo y los
> conflictos que decide una persona. La convención de documentos y `sync.mode: pr` llegan en la última.

## Qué hace una corrida

Solo en el preset `business`. En `software` no hace nada, porque lo aprendido viaja en el PR del cambio.

1. **Commitea lo pendiente del aprendizaje.** `learn record` escribe el registro y lo deja para el
   próximo commit. El sync commitea solo los archivos del aprendizaje: `.agents/rules/learned*.md`,
   `.agents/rules/learned/`, `candidates.json`, `log.md` y `reorganize.json` de `.agents/learning/`. Lo
   hace aunque haya otros cambios en el índice, que quedan como estaban. El commit lleva `Learned-by:`.
2. **Trae la rama** actual de `sync.remote` (`origin` por defecto).
3. **La integra con un merge** que usa los merge drivers ([collaboration.md](collaboration.md)), así dos
   rules distintas del mismo archivo no chocan. El merge no toca los cambios sin commitear del resto
   del repositorio. Si todavía hay un conflicto, lo aborta: el checkout **nunca queda a medio mergear**,
   y la próxima corrida lo vuelve a intentar.
4. **Promueve a equipo** lo que varias personas enseñaron igual como rule personal y lo commitea
   ([collaboration.md](collaboration.md#promoción-a-equipo)).
5. **Sube** la rama. Si el remoto la rechaza porque otro subió antes, vuelve a traer e integrar, hasta
   `sync.pushRetries` veces (3). **Nunca hace force push.**

Sin red, los commits quedan locales y salen con la primera corrida que llega al remoto. Git nunca pide
credenciales en una corrida (`GIT_TERMINAL_PROMPT=0`): sin credenciales es un error del remoto, que
`status` muestra.

## Cuándo corre

| Disparador | Cómo |
|---|---|
| Inicio de sesión | el hook `SessionStart` corre `agent-ready sync --background` después del resumen del aprendizaje, para traer lo nuevo antes de trabajar |
| Cada aprendizaje | `learn apply` lo arranca en segundo plano al terminar, para que lo aprendido llegue a los demás enseguida |
| Timer | la tarea programada del barrido del aprendizaje (`learn sweep --registered`, cada `learning.sweep.intervalMinutes`, [learning-episodes.md](learning-episodes.md)) sincroniza cada repositorio que barre |
| A mano | `agent-ready sync [--json]` |

`--background` corre desacoplado del hook, con su salida en `~/.cache/agent-ready-setup/team-sync/`, y
nunca hace esperar al agente. Dos corridas del mismo checkout no se pisan: la segunda sale con `running`.
El commit y el merge esperan al aprendizaje: corren con el lock del registro, el mismo de `learn record`
y `learn apply`, así ninguno guarda una copia vieja encima de lo que trajo el sync. El fetch y el push
corren sin él, para que un remoto lento no haga esperar al aprendizaje.

## Resultados

El último queda en `.git/info/agent-ready/sync.json`, nunca en el repositorio, y `agent-ready status`
lo muestra en la línea `Sync:`.

| Resultado | Qué pasó | Qué hacer |
|---|---|---|
| `synced` | todo subido y traído | nada |
| `offline` | no llegó al remoto; dice cuántos commits esperan | nada: sale solo con la próxima corrida con red |
| `no-remote`, `detached`, `busy`, `running` | sin remoto, sin rama, con un merge o rebase a mano en curso o el registro del aprendizaje tomado, u otra corrida | configurar el remoto o terminar lo que está en curso |
| `conflict` | la misma parte cambió en dos máquinas; el merge se abortó | la próxima sesión lo explica y la persona decide (sección «Conflictos») |
| `blocked`, `push-failed` | Git no pudo commitear, integrar (un cambio sin commitear choca con lo que viene) o subir | leer el mensaje: credenciales vencidas, permisos o un archivo modificado a mano |

`agent-ready sync` sale con 1 en `conflict`, `blocked` y `push-failed`, y con 0 en el resto.

## Apagarlo

`{"sync": {"enabled": false}}` en el manifest (o `AGENT_READY_SETUP_TEAM_SYNC=0` en una corrida): el
sync no hace commits, fetch ni push, y ningún disparador lo corre. Las claves están en
[configuration-keys.md](configuration-keys.md).

## Documentos

Con `sync.scope: knowledge+documents`, el sync también sube y trae los documentos de la oficina. El valor
`auto`, que es el default, lo activa cuando la selección tiene la capability `documents` del contenido.
La convención es la de esa capability: el Markdown es la fuente, y un PDF o un Word es una salida o una
entrada.

- **Qué entra.** Los `.md` del repositorio y los `.pdf`, `.docx`, `.doc`, `.odt` y `.rtf` que subió
  alguien. Nunca entran `output/` (lo que se genera desde el Markdown), `.agents/`, `.claude/`, `.codex/`
  ni los `AGENTS.md` y `CLAUDE.md`.
- **Cambios en partes distintas** de un Markdown se combinan solos, línea por línea.
- **La misma parte cambiada en dos máquinas** queda como conflicto del documento entero, como el de una
  rule:
  - `--conflicts` muestra quién y cuándo, con las líneas que difieren;
  - la persona elige `--keep mine`, `--keep theirs` o `--merged-file <archivo>` con el documento entero
    combinado, que el agente muestra antes de guardar;
  - un documento no tiene «cada uno la suya».
- **Dos archivos subidos con el mismo nombre** se conservan los dos, sin preguntar: el de esta máquina
  queda con su nombre, y el que llegó del remoto se guarda al lado con la fecha (`poder-2026-11-23.pdf`).

## Nunca se sincroniza

Engram, los episodios del aprendizaje, la caché de revisiones y la identidad viven fuera del
repositorio (`.git/info/`, la caché o la configuración del usuario), así que ningún commit del sync
los lleva.

## Conflictos

Cuando dos máquinas cambiaron la misma rule de forma distinta, el merge driver deja el conflicto solo en
esa rule, y el sync lo aborta. Antes de abortar guarda, por cada rule en conflicto, las dos versiones,
quién escribió cada una (su `Learned-by:`) y cuándo, en `.git/info/agent-ready/sync-conflicts.json`. Lo
guarda en la máquina que se encontró con el conflicto, porque es la que tiene las dos versiones.

- **Se le explica a la persona.** El inicio de sesión corre `agent-ready sync --conflicts`, que le da al
  agente los datos para contarlo sin términos de Git: quién lo cambió, cuándo y la diferencia. Por
  ejemplo: «Juan puso el número de expediente arriba a las 10:40, y vos la fecha a las 10:15».
- **Decide la persona,** con una de cuatro opciones:

  | Opción | Comando |
  |---|---|
  | conservar la versión de esta máquina | `agent-ready sync --resolve <id> --keep mine` |
  | conservar la del otro | `agent-ready sync --resolve <id> --keep theirs` |
  | fusionar las dos: el agente muestra el enunciado combinado y lo guarda recién cuando la persona está de acuerdo | `agent-ready sync --resolve <id> --merged "<enunciado>"` |
  | cada uno la suya, solo para una rule de equipo que vale para todo el repositorio y con versiones de dos personas distintas: cada versión queda como rule personal de quien la enseñó, y la de equipo sale | `agent-ready sync --resolve <id> --each-their-own` |

- **Una sola vez.** `--resolve` guarda la decisión y sincroniza: el merge se repite con la decisión (los
  drivers la leen de `AGENT_READY_MERGE_RESOLUTIONS`), se commitea con una línea `resolve` en el log, con
  quién decidió, y nadie más vuelve a ver esa pregunta.
  - **Cada versión, con su autor.** Quién y cuándo salen del commit que dejó esa rule así, no del último
    que tocó su archivo: un archivo tiene varias rules.
  - **Vale para lo que vio la persona.** Si una de las dos versiones cambia antes de que el merge la use,
    la decisión no se aplica y se pregunta por las versiones nuevas.
  - **Espera al resto.** Con varias rules en conflicto, cada decisión se guarda hasta que el merge sale
    entero, aunque su archivo ya se haya podido combinar en un intento abortado por otro.
  - **También si una máquina borró el archivo** y la otra cambió su rule: Git no llama al driver en ese
    caso, así que el sync aplica la decisión él mismo y termina el merge.
- **Mientras tanto,** cada máquina conserva su versión, el resto sigue sincronizando y nada se pierde:
  las dos versiones quedan en el historial.
- **Lo que no es una rule** (un JSON que no se puede leer, un archivo fuera de `.agents/rules/`) queda en
  la línea `Sync:` de `status` con su archivo.

Cada corrida vuelve a apuntar los drivers de `.git/config` a la instalación que corre: así un driver
nunca queda nombrando una copia del motor que ya salió de la caché.

