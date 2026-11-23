# Colaboración: identidad y presets

Cómo comparten lo aprendido las personas de un repositorio, y quién es cada una aunque usen la misma
cuenta de Git. Leer al explicar `agent-ready identity`, el trailer `Learned-by:` o qué preset de
colaboración usa un repositorio.

> **Estado.** La identidad, el preset, los merge drivers, la sincronización
> ([team-sync.md](team-sync.md)), el aprendizaje personal, la promoción a equipo y los conflictos que
> decide una persona son las partes 169a a 169f de la issue #169; los conflictos del merge en un
> repositorio de código, la 169g.

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

## Conflictos en un repositorio de código

En el preset `software` no hay sync propio: lo aprendido es un commit de la rama actual y viaja en su PR.
Los merge drivers combinan dos ramas que aprendieron rules distintas. Si dos ramas cambiaron la misma
rule de forma distinta, el conflicto aparece en el merge que hace el desarrollador (`git merge`, un pull,
el merge local de un PR), solo en esa rule.

- **Se explica.** `agent-ready sync --conflicts`, que corre al iniciar la sesión, lista cada rule del merge
  en curso: quién la cambió en cada rama, cuándo y la diferencia.
- **Se propone qué conservar:** esta rama (`--keep mine`), la otra (`--keep theirs`) o un enunciado que
  combina las dos (`--merged "<enunciado>"`), que el agente muestra antes de guardarlo. No hay «cada uno
  la suya»: en un repositorio de código no hay rules personales.
- **El merge sigue siendo del desarrollador.** `agent-ready sync --resolve <id> <opción>` escribe la rule
  en su archivo y lo agrega al index cuando no le queda otra rule en conflicto. Nunca hace commit, pull ni
  push: el desarrollador termina el merge con `git commit`.

## Aprendizaje personal y de equipo

En el preset `business`, una instrucción es **de equipo** («en el estudio siempre…», un formato o un
procedimiento del estudio) o **personal** («a mí me gusta…»). En `software` todo es de equipo: las
preferencias de un desarrollador viven en su configuración del provider o en Engram, nunca en el repo.

- **Registrarla.** `agent-ready learn record --scope personal` la guarda para la persona de esta máquina
  (`agent-ready identity`), con su `owner` en el registro. Sin `--scope`, es de equipo. Una personal es
  una rule para todo el repositorio: `--kind rule` y sin `--paths`.
- **Dónde va.** `learn apply` la escribe en `.agents/rules/learned/users/<persona>/learned.md`, con ids
  `learned/users/<persona>/<slug>`, donde `<persona>` es el id de la identidad con solo `[a-z0-9-]`. Se
  sincroniza como lo demás ([team-sync.md](team-sync.md)), así sigue a la persona en todas sus máquinas
  (`identity link`).
- **Quién la carga.** Ninguna vista la proyecta: no tiene vista en `.claude/rules/` ni línea en
  `AGENTS.md`. El hook del inicio de sesión (`learn summary`) le da a cada persona solo las suyas, en
  Claude Code y en Codex. Las de los demás tampoco aparecen en el resumen ni entre lo que espera.
- **Precedencia.** personal > equipo > profile, salvo una rule `locked`: una rule de equipo bloqueada
  frena también el aprendizaje personal de su `key`. Una rule personal nunca reemplaza otra con
  `overrides`, porque vale solo en la sesión de su persona, y compite solo con las otras rules personales
  de esa persona: con la misma `key`, la edita. Por eso `agent-ready rules lint` no marca como conflicto
  una rule personal que decide la misma `key` que una de equipo.
- **Alcance dudoso.** El agente hace la pregunta de alcance del aprendizaje («¿Lo querés así solo vos o
  para todo el estudio?»), como mucho una por episodio. Sin respuesta, o con `learning.clarify: off`,
  queda como personal.

## Promoción a equipo

Lo que varias personas enseñaron igual como preferencia propia pasa a ser del estudio.

- **Cuándo.** En cada sync, después de traer lo de los demás: una `key` que `sync.promoteAfterUsers`
  personas (2) deciden con el mismo enunciado (sin contar mayúsculas, espacios ni el punto final) en sus
  rules personales.
- **Qué hace.** Escribe la rule de equipo en `.agents/rules/learned.md`, saca las personales de sus
  archivos, marca sus entradas `superseded` con `supersededBy` y suma una línea `promote` al log con las
  personas. La entrada nueva junta la evidencia de todas. Todo va en un commit del sync.
- **Sin duplicados.** La rule de equipo tiene un id que sale de su `key`, con los puntos como guiones (`reports.summary` da `learned/reports-summary`), y su entrada uno
  que sale del enunciado. Dos máquinas que promueven a la vez escriben lo mismo, y los merge drivers lo
  unen por id.
- **Lo que no promueve.** Una `key` que ya decide una rule del equipo, una instrucción sin `key` y la
  preferencia distinta de otra persona, que queda como personal. Con `sync.promoteAfterUsers: 0` no
  promueve nunca; con `1`, cada rule personal con `key` pasa a equipo en el próximo sync.

