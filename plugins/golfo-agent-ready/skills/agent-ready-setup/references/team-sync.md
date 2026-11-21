# Sincronización del equipo

Cómo llega lo que aprendió una persona de una oficina a las demás, sin que nadie use Git. Leer al explicar
`agent-ready sync`, por qué algo aprendido no llegó a otra máquina o qué dice la línea `Sync:` de
`agent-ready status`. La identidad y los presets están en [collaboration.md](collaboration.md).

> **Estado.** Parte 169c de la issue #169. El aprendizaje personal, la promoción a equipo y la
> explicación de un conflicto al usuario llegan en las partes siguientes: hasta entonces un conflicto
> queda en la línea `Sync:` de `status` y el sync lo vuelve a intentar.

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
4. **Sube** la rama. Si el remoto la rechaza porque otro subió antes, vuelve a traer e integrar, hasta
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
| `conflict` | la misma parte cambió en dos máquinas; el merge se abortó | por ahora, resolverlo a mano; la explicación al usuario llega en una parte siguiente de #169 |
| `blocked`, `push-failed` | Git no pudo commitear, integrar (un cambio sin commitear choca con lo que viene) o subir | leer el mensaje: credenciales vencidas, permisos o un archivo modificado a mano |

`agent-ready sync` sale con 1 en `conflict`, `blocked` y `push-failed`, y con 0 en el resto.

## Apagarlo

`{"sync": {"enabled": false}}` en el manifest (o `AGENT_READY_SETUP_TEAM_SYNC=0` en una corrida): el
sync no hace commits, fetch ni push, y ningún disparador lo corre. Las claves están en
[configuration-keys.md](configuration-keys.md).

## Nunca se sincroniza

Engram, los episodios del aprendizaje, la caché de revisiones y la identidad viven fuera del
repositorio (`.git/info/`, la caché o la configuración del usuario), así que ningún commit del sync
los lleva.
