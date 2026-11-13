# Revisiones de IA y su caché

Qué revisa la IA en agent-ready-setup, qué se guarda de cada revisión, cómo se
configura y cómo se acepta o descarta un hallazgo. Leer al explicar por qué una revisión
corrió o no corrió, al mostrar los hallazgos conocidos, al cambiar las opciones `reviews.*`
o `conflicts.*`, al explicar un conflicto semántico del plan o cuando el usuario pide aceptar o
descartar un hallazgo.

## Contenido

1. Qué se revisa
2. Unidad y clave
3. Dónde se guarda
4. Opciones
5. Ver los hallazgos y forzar una revisión
6. Aceptar o descartar un hallazgo
7. Conflictos semánticos con lo propio del proyecto
8. Presupuesto de contexto
9. Choques con la máquina
10. Rules contra la realidad del repo
11. Hooks, permisos y settings
12. Paridad entre providers, variables de entorno y CI
13. Skills que compiten
14. Todos los conflictos juntos

## 1. Qué se revisa

| Revisión | Quién la corre | Unidad |
|---|---|---|
| `instructions` | `merge-instructions.sh` en el apply y en la sincronización en segundo plano ([managed-agents-block.md](managed-agents-block.md)) | `AGENTS.md` junto con todas las rules que ve la revisión, del template y propias |
| `harness-consistency` | el hook `PostToolUse` `.agents/hooks/check-harness-consistency.sh`, después de editar una rule, una skill o `.claude/CLAUDE.md` | un par de documentos del mismo root (`.agents/` o `.claude/`) |
| `harness-consistency` (conflictos semánticos) | `agent-ready plan` y el plan de cada apply (sección 7) | un par: una rule gestionada y una rule propia o el `AGENTS.md` del proyecto |

El hook compara cada documento editado contra todos los demás de su root, de a pares.
Los pares que ya están en la caché no se vuelven a revisar. Los que faltan van al provider
que hizo la edición en una sola llamada: `claude -p` en Claude Code y `codex exec
--sandbox read-only` en Codex (eventos `apply_patch`). Los documentos le llegan por stdin
y se tratan como datos, nunca como instrucciones. Si falta la CLI del provider, el
chequeo se omite con un aviso. Si el provider no da una respuesta válida, el hook informa el
chequeo como incompleto, nunca como limpio, y esos pares se revisan en la próxima edición. Un
documento borrado no deja nada que comparar.

## 2. Unidad y clave

Cada revisión se guarda por unidad, nunca con un hash global: editar una rule solo vuelve
a revisar las unidades donde participa. La clave de una unidad es el hash de todo lo que
puede cambiar su resultado:

- el contenido de cada archivo, con los fines de línea normalizados a LF;
- el id y la versión del chequeo, que cambia con su prompt;
- el provider y el modelo (`AGENT_READY_SETUP_MERGE_MODEL` cambia el de `instructions`);
- la versión de golfo-kit que aplicó el repo (`generator.version` del lockfile).

Si cambia cualquiera de estas partes, la unidad se revisa otra vez y su entrada se
reemplaza. Cada entrada guarda el veredicto (`consistent` o `findings`) y los hallazgos:
archivos, líneas citadas, tipo y texto. Un `AGENTS.md` recién creado desde el template se
guarda como revisado por `template`, así ningún provider lo revisa hasta que alguien lo edite.

## 3. Dónde se guarda

La caché es local y nunca llega al repositorio: vive en
`.git/info/agent-ready/reviews.json`, el directorio `info` que comparten todos los
worktrees del repo, así una revisión no se repite en cada worktree.

- Cada escritura toma un lock (`reviews.lock`, al lado), reescribe el archivo de forma
  atómica y descarta las entradas de archivos que ya no existen. Varios procesos pueden
  escribir a la vez sin corromperla.
- Una revisión que no se pudo guardar vuelve a correr la próxima vez. Nunca hace fallar
  el apply ni el hook.
- `agent-ready remove` la borra mientras ningún otro worktree del repositorio siga usando
  agent-ready-setup.

### Caché compartida (`reviews.commit`)

Con `reviews.commit: true`, cada resultado se guarda también en
`.agents/agent-ready.review-cache.json`, que se commitea. Un clon nuevo o el CI, que no tienen
caché local, saltean las revisiones cuya clave coincide sin pagarlas de nuevo, y `status` muestra
sus hallazgos. Está apagada por defecto, porque cualquiera puede editar un archivo versionado:

- La caché local responde primero. La compartida solo cuenta para una unidad con la misma clave
  y los mismos archivos.
- Un resultado compartido que no encontró nada nunca oculta un hallazgo que la caché local
  conoce para esa unidad: ahí la revisión vuelve a correr. Un resultado compartido con hallazgos
  siempre se muestra, porque solo agrega qué mirar.
- Nunca da un hallazgo por aceptado: eso solo lo hacen las decisiones de
  `.agents/agent-ready.reviews.json` (sección 6), con su motivo.
- Las entradas de archivos que ya no existen salen del archivo en la siguiente escritura, y
  `agent-ready remove` lo borra.

## 4. Opciones

Módulo `reviews` de la configuración ([configuration.md](configuration.md), claves en
[configuration-keys.md](configuration-keys.md)):

| Clave | Default | Efecto |
|---|---|---|
| `reviews.enabled` | `true` | `false` apaga todas las revisiones: el apply copia el bloque gestionado sin revisar, el hook no llama al provider y el plan no busca conflictos semánticos |
| `reviews.cache` | `true` | `false` revisa todo cada vez y nunca reutiliza una entrada; igual guarda el último resultado, así `status` lo muestra y se puede decidir sobre sus hallazgos |
| `reviews.ttl` | sin vencimiento | horas que vale una entrada; pasado ese tiempo se revisa otra vez aunque nada haya cambiado |
| `reviews.commit` | `false` | `true` guarda además cada resultado en `.agents/agent-ready.review-cache.json` para commitearlo (ver «Caché compartida») |

Los hooks corren sin el motor, así que cada apply deja las opciones efectivas en la
caché, una vez por worktree, y los hooks las leen de ahí: un cambio de configuración vale
para los hooks después del siguiente `agent-ready apply` en ese worktree. Las revisiones
guardadas sí se comparten entre worktrees.

## 5. Ver los hallazgos y forzar una revisión

- Cada hallazgo lleva un id corto y estable (`! [3f9a1c2b7e] …`), calculado con su chequeo,
  los archivos que involucra, su tipo y las líneas que cita. Si la revisión redacta el mismo
  problema de otra forma, el id se mantiene, y agregar una rule ajena no lo cambia. Un
  hallazgo sin líneas citadas usa su texto. Una inconsistencia de `AGENTS.md` involucra la
  línea del proyecto y la rule con la que choca.
- `agent-ready status` y `agent-ready plan` muestran los hallazgos conocidos sin llamar al
  provider (`--json`: objeto `reviews` con `units`, `stale`, `findings`, `quiet` y
  `decisions`). Una entrada cuyos archivos cambiaron desde su revisión cuenta como
  desactualizada y vuelve a correr en la próxima edición o apply.
- La revisión de `AGENTS.md` que sale de la caché repite sus inconsistencias en cada sync,
  hasta que alguien edite el archivo o la rule, o decida sobre ellas.
- `agent-ready apply --recheck` ignora la caché de `AGENTS.md` y lo revisa otra vez.

## 6. Aceptar o descartar un hallazgo

Las decisiones del equipo se guardan en `.agents/agent-ready.reviews.json`, que se commitea.
Cada una tiene el id del hallazgo, el motivo, quién la tomó (el `user.name` de Git) y cuándo.

```bash
agent-ready review list [--json]                                       # hallazgos con su id y estado
agent-ready review accept <id> --reason "<motivo>" [--scope content|pair]  # es a propósito
agent-ready review dismiss <id> --reason "<motivo>" [--scope content|pair] # no es un problema real
agent-ready review reset <id>... | --all                               # vuelven a mostrarse
```

- **Motivo obligatorio.** Sin `--reason`, o con un motivo vacío, el comando falla (código
  2) y no escribe nada. Un id que ningún hallazgo actual usa también falla.
- **Sesiones simultáneas.** Cada decisión lee y reescribe el archivo bajo un lock, así dos
  sesiones que deciden a la vez conservan las dos decisiones.
- **Alcance `content` (default).** La decisión vale mientras no cambie ninguno de los
  archivos del hallazgo. Si cambia alguno, el hallazgo se revisa de nuevo y vuelve como
  «a confirmar» (`? [id] … (accepted before the files changed: <motivo>)`). Se confirma
  aceptándolo otra vez.
- **Alcance `pair`.** La decisión vale para ese par de archivos aunque cambie su
  contenido, hasta que alguien la quite con `reset`.
- **Solo ese hallazgo.** Aceptar nunca modifica las rules ni silencia otros hallazgos del
  mismo par: los demás se siguen mostrando con su propio id.
- **Archivo ilegible.** Si `.agents/agent-ready.reviews.json` no es JSON válido, los hooks lo
  ignoran y muestran todos los hallazgos. El CLI se niega a escribir encima y pide
  corregirlo o borrarlo.
- **Pedido en el chat.** Cuando el usuario pide aceptar un hallazgo («aceptá ese conflicto,
  es a propósito»), el agente corre `agent-ready review accept <id> --reason "<motivo>"`
  con el motivo que dio el usuario. Si no dio ninguno, se lo pregunta: nunca lo inventa.
  Usa `--scope pair` solo si el usuario quiere que la decisión siga valiendo aunque cambien
  los archivos.
- `review list` también muestra las decisiones que ya no usa ningún hallazgo actual, para
  quitarlas con `reset`. `agent-ready remove` conserva el archivo: son decisiones del equipo.

## 7. Conflictos semánticos con lo propio del proyecto

`agent-ready plan`, y el plan que corre antes de cada apply, revisan con IA si las rules
gestionadas contradicen lo que el proyecto escribió, o las de otro profile, en tres direcciones:

| Dirección | Qué se compara | Marca en el plan |
|---|---|---|
| update | cada rule gestionada que el apply crea, actualiza o adopta, con el contenido que va a escribir, contra cada rule propia (`.agents/rules/` sin equivalente gestionado) y contra lo que el proyecto escribió en su `AGENTS.md`, fuera del bloque gestionado que el mismo apply puede reemplazar | `(this update)` |
| project | cada rule propia contra cada rule gestionada ya aplicada que no cambia | `(a project rule)` |
| profiles | cada rule de un pack contra cada rule gestionada de otro profile; las de los profiles de golfo-kit no se revisan entre sí. Como llega con el apply, `conflicts.block` lo frena igual que un update. Para quedarse con una de las dos, `overrides` | `(two profiles)` |

- **Misma revisión y misma caché.** Usa el prompt, la llamada al provider y la caché de
  `harness-consistency`: un par que el hook ya revisó no se paga de nuevo, `status` muestra sus
  hallazgos sin llamar al provider y se aceptan o descartan con `agent-ready review` (sección 6).
  Toma `reviews.cache`, `reviews.ttl` y `reviews.commit` de la configuración de esa corrida, sin
  esperar a que un apply los registre, y revisa con el provider de la sesión, también en la
  sincronización en segundo plano. Un `plan` guarda lo que revisó solo en la caché local: con
  `reviews.commit`, el apply lo publica en `.agents/agent-ready.review-cache.json`.
- **Lo propio de `AGENTS.md`.** De `AGENTS.md` la revisión lee, y la caché identifica, solo lo que
  el proyecto escribió, sin el bloque gestionado. Por eso un conflicto con `AGENTS.md` sigue
  listado y se puede decidir aunque el mismo apply reescriba el bloque.
- **Antes del primer apply.** Sin `AGENTS.md`, el `CLAUDE.md` raíz que el apply va a promover a
  `AGENTS.md` ocupa su lugar en la revisión, con el nombre `AGENTS.md`, salvo que sea solo el proxy.
  También vale para una variante de mayúsculas (`claude.md`) si es la única y Git no la ignora,
  que es la que la normalización renombra.
- **Decidir antes del apply.** Un conflicto de dirección update habla de una rule que todavía no
  está en disco, así que el plan lo guarda en el directorio de Git del worktree
  (`agent-ready/semantic-conflicts.json`). `review list`, `accept` y `dismiss` lo conocen desde ahí.
  Una decisión de alcance `content` vale para el contenido revisado, el que el apply va a escribir,
  así sigue valiendo después del apply. Si la rule gestionada cambia otra vez, el hallazgo vuelve
  «a confirmar».
- **Solo informa.** Nunca borra ni reescribe una rule. El plan los lista en «Semantic conflicts»
  con su id y el apply los repite como avisos en stderr antes de escribir. En el JSON del plan van
  en `semanticConflicts`, con `pairs`, `fromCache`, `reviewed`, `unchecked`, `uncheckedUpdate`,
  `reason`, `findings` (cada uno con su `direction`), `quiet` y `block`.
- **Nunca limpio sin respuesta.** Un par sin revisar deja el chequeo como «Check incomplete»,
  con el motivo. Pasa sin red (`--offline`), en una revisión automática
  (`AGENT_READY_SETUP_REVIEW_MODE=1`), sin la CLI del provider o si el provider no da una
  respuesta válida. En los dos primeros casos responde solo la caché.

Módulo `conflicts` de la configuración:

| Clave | Default | Efecto |
|---|---|---|
| `conflicts.enabled` | `true` | `false` no busca conflictos semánticos; `reviews.enabled: false` también los apaga |
| `conflicts.block` | `false` | `true` frena antes de escribir un apply cuya actualización trae un conflicto visible o que no pudo revisar algún par de la actualización |

Con `conflicts.block`, los conflictos de dirección project no frenan, porque ya están en el
repositorio. Para destrabar el apply: cambiar la rule, o aceptar o descartar cada hallazgo con
`agent-ready review accept|dismiss <id> --reason "<motivo>"`.

## 8. Presupuesto de contexto

Cada profile suma texto que el agente carga en todas las sesiones, y con varios profiles juntos el
contexto se llena sin que nadie lo note. `agent-ready plan` informa cuánto suma la selección, sin IA:

```text
Context at the start of a session: AGENTS.md ~3590 bytes; 20 rules without paths: ~84643 bytes; MCP servers: 2
```

- **AGENTS.md**: el archivo como quedaría después del apply, con lo propio del proyecto (o el
  esqueleto de uno nuevo), el bloque gestionado y la sección de cada stack. Codex corta los AGENTS.md
  combinados en `project_doc_max_bytes` (32 KiB por default).
- **Rules sin `paths:`**: Claude carga al inicio de cada sesión toda rule de `.agents/rules/` que no
  declara `paths:` en su frontmatter, gestionada o propia del proyecto. Las que tienen `paths:` se
  cargan solo al tocar esos archivos y no cuentan, y tampoco las de un profile que la selección deja,
  porque el apply las retira.
- **Servidores MCP**: los que el apply registra: los del browser si `tools.enabled` está prendido, y
  los de los packs que la política permite. Cada uno suma la definición de sus herramientas.

Al pasar un umbral, `plan` avisa y nombra los profiles que más suman, para mover contenido a rules
con `paths:` o a skills, que se cargan solo cuando hacen falta. El aviso no frena el apply. Con
`--json`, el detalle va en `context`.

| Clave | Default | Efecto |
|---|---|---|
| `conflicts.contextBudget.enabled` | `true` | `false` no calcula el presupuesto |
| `conflicts.contextBudget.bytes` | `32768` | avisa cuando AGENTS.md pasa esos bytes |
| `conflicts.contextBudget.rulesBytes` | sin valor | avisa cuando las rules sin `paths:` pasan esos bytes; sin valor, solo informa |

## 9. Choques con la máquina

`agent-ready plan` compara la selección con lo que el usuario ya tiene instalado. Solo lee la
configuración del usuario y nunca la escribe.

- **Sombra:** una skill, un subagente o un comando de un profile con el mismo nombre que uno del
  usuario (`~/.claude/skills`, `~/.claude/agents`, `~/.claude/commands`, `~/.agents/skills`) o de un
  plugin instalado. Cada provider aplica su precedencia en silencio, y `plan` dice cuál gana:
  - Claude Code usa la skill o el comando del usuario antes que el del proyecto; los de un plugin
    tienen namespace (`/plugin:skill`), así que se cargan los dos.
  - Claude Code usa el subagente del proyecto antes que el del usuario y el de un plugin.
  - Codex lista las dos skills, sin un orden documentado.
- **Servidores MCP del usuario:** un servidor de un pack que el usuario ya registró para todos los
  proyectos (`~/.claude.json`, `config.toml` de Codex), aunque tenga otro nombre. Cuenta como el
  mismo solo si hace exactamente lo mismo: igual URL, paquete (sin contar la versión) o comando con
  su ruta, los mismos argumentos y la misma configuración (`env`, headers, credenciales); ante
  cualquier diferencia se registran los dos. El apply no registra la copia del proyecto en ese
  provider, así el agente no arranca dos veces el mismo servidor, y lo informa. Codex necesita Python 3.11 para leer su
  configuración; con uno anterior no se compara.

```text
  ~ skill component-creation (react) has the same name as ~/.claude/skills/component-creation: Claude Code uses the user's
  ~ MCP server acme-docs (acme/kafka-interno) is the user's my-docs in ~/.claude.json: not registered for claude (conflicts.userServers.register: true registers it)
```

| Clave | Default | Efecto |
|---|---|---|
| `conflicts.shadowing.enabled` | `true` | `false` no busca sombras con la máquina |
| `conflicts.userServers.enabled` | `true` | `false` no compara con los servidores del usuario y registra todos |
| `conflicts.userServers.register` | `false` | `true` registra igual la copia del proyecto; `plan` lo sigue informando |

## 10. Rules contra la realidad del repo

Una rule declara en su frontmatter lo que da por sentado, y `agent-ready plan` lo compara con las
señales estáticas del repo, sin IA y sin ejecutar nada:

```markdown
---
assumes:
  testRunner: vitest
---
```

| Dato | Valores | Qué mira |
|---|---|---|
| `testRunner` | `vitest`, `jest`, `mocha` | dependencias de `package.json`, su clave `jest` y los archivos de configuración |
| `packageManager` | `pnpm`, `npm`, `yarn`, `bun` | lockfiles y el campo `packageManager` de `package.json` |
| `indentation` | `tabs`, `spaces` | `indent_style` de `[*]` en `.editorconfig` y `useTabs` de Prettier en JSON |

La rule contradice al repo cuando este muestra otro valor del mismo dato y ninguno del que la rule
asume. El agente que obedece la rule rompe el proyecto, y el que obedece al proyecto ignora la rule:

```text
  ! .agents/rules/react-testing.md (react) assumes test runner vitest, but the repository uses jest (package.json)
```

Las rules de golfo-kit que solo valen con una herramienta lo declaran, como las de testing de
`react` con Vitest. Un dato o un valor que el catálogo (`assets/repo-facts.json`) no conoce se
informa como no chequeado. Una contradicción escrita en prosa, sin `assumes`, la busca la revisión
semántica. Para reemplazar la rule de golfo-kit por la del proyecto, `overrides`
(`profiles-and-lockfile.md`).

| Clave | Default | Efecto |
|---|---|---|
| `conflicts.repoReality.enabled` | `true` | `false` no compara las rules con el repo |

## 11. Hooks, permisos y settings

`agent-ready plan` compara las capas que lee cada provider: lo que mergea golfo-kit
(`.claude/settings.json (golfo-kit)`, `.codex/hooks.json (golfo-kit)`), el resto de esos archivos
del proyecto, `.claude/settings.local.json` y la configuración del usuario (`~/.claude/settings.json`,
`$CODEX_HOME/hooks.json`). Solo lee; nunca escribe la configuración del usuario.

- **Permisos:** un patrón que una capa permite (`allow`) y otra prohíbe (`deny`) se informa con las
  dos capas. Claude Code aplica el `deny`.
- **Hooks repetidos:** el mismo comando en el mismo evento en dos capas corre una vez por cada
  registro.
- **Formateadores que compiten:** dos formateadores distintos (`assets/formatters.json`: Prettier,
  Biome, `eslint --fix`, dprint, Black, `ruff format`, gofmt, rustfmt) en el mismo evento, con matchers
  que se pisan, pueden reescribir el mismo archivo. Si los dos nombran rutas y no comparten ninguna
  (`black backend/` y `prettier --write frontend/`), no se informa. Solo cuenta el modo que reescribe:
  `prettier --check` o `black --check` no compiten.

```text
  ! permission Bash(npm run *): allowed in .claude/settings.json and denied in ~/.claude/settings.json; Claude Code applies the deny
  ~ claude PostToolUse runs two formatters that can rewrite the same files: prettier (.claude/settings.json) and biome (.claude/settings.local.json)
```

Que un hook de un profile bloquee una acción que pide otro profile lo cubre la revisión semántica.

| Clave | Default | Efecto |
|---|---|---|
| `conflicts.hooks.enabled` | `true` | `false` no compara los hooks |
| `conflicts.permissions.enabled` | `true` | `false` no compara los permisos |

## 12. Paridad entre providers, variables de entorno y CI

Tres chequeos más de `agent-ready plan`, sin IA y sin escribir nada.

- **Paridad entre providers** (con los dos en `providers`): `plan` dice qué ve cada uno. Claude Code
  lee las rules como `.claude/rules` y carga las que tienen `paths:` solo al tocar esos archivos;
  Codex lista todas en `AGENTS.md`. Los subagentes y los comandos le llegan a Codex como skills del
  mismo nombre. Avisa de un hook que corre en un provider y no en el otro: los de golfo-kit (salvo
  los declarados propios de uno, como el relink de las vistas de `.claude`) y los del proyecto en
  `.claude/settings.json` contra `.codex/hooks.json`.
- **Variables de entorno:** una variable que piden los servidores MCP de dos fuentes distintas, o
  que el proyecto ya lista en `.env.example` (o `.env.sample`, `.env.template`, `.env.dist`), se
  informa con los profiles que la piden, para confirmar que significa lo mismo.
- **Jobs de CI duplicados:** con el CI gestionado (`ci.provider`), un workflow propio del repo que
  ya corre el chequeo de Agent Ready se informa, para no correrlo dos veces.

```text
Providers: Claude Code sees 20 rules (0 only for their paths), 5 skills, 5 subagents and 1 commands; Codex sees 20 rules in AGENTS.md and 11 skills
  ~ claude runs the PostToolUse hook `npm run lint` (.claude/settings.json) and codex does not
  ~ .github/workflows/own.yml already runs the Agent Ready check; the managed .github/workflows/agent-ready.yml runs it again
```

| Clave | Default | Efecto |
|---|---|---|
| `conflicts.providerParity.enabled` | `true` | `false` no compara los providers |
| `conflicts.environment.enabled` | `true` | `false` no compara las variables de entorno |
| `conflicts.ciJobs.enabled` | `true` | `false` no busca jobs de CI duplicados |

## 13. Skills que compiten

Dos skills que hacen el mismo trabajo, con descripciones que se pisan («crear un endpoint»),
parten la activación: el agente usa una u otra según cómo se pida. Que dos skills se activen ante
el mismo pedido no es un problema si cada una resuelve una parte distinta: son complementarias (una
mide, la otra arregla).

`agent-ready plan` revisa con IA cada skill de un pack contra cada skill de otro profile y avisa
solo de las que compiten, con el pedido en común y en qué difieren:

```text
  ! [a1b2c3] .agents/skills/pr-review-workflow/SKILL.md <-> .agents/skills/team-review/SKILL.md: Both review pull requests; one follows the team checklist. (competing skills: "review this pull request")
```

- **Qué pares.** Solo los de profiles distintos con una skill de un pack: las de golfo-kit no se
  revisan entre sí. Un par que un profile declara en `complements`
  (`"software-development:skills/pr-review-workflow"`) no se revisa.
- **Misma infraestructura.** Usa la llamada al provider, la caché y las decisiones de las demás
  revisiones (secciones 3 a 6), bajo su propio chequeo, `skill-overlap`: un par sin cambios no se
  paga de nuevo, y sin red ni provider queda sin revisar, nunca limpio. Solo avisa: no frena el
  apply.

| Clave | Default | Efecto |
|---|---|---|
| `conflicts.competingSkills.enabled` | `true` | `false` no revisa las skills; `reviews.enabled: false` también la apaga |

## 14. Todos los conflictos juntos

`agent-ready conflicts` corre los chequeos de las secciones 7 a 13 sobre la selección y muestra solo
los conflictos, sin escribir nada:

```text
Structural conflicts:
  ! .agents/rules/react-testing.md (react) assumes test runner vitest, but the repository uses jest (package.json)
AI review findings:
  ! [a1b2c3] .agents/rules/acme-team.md <-> .agents/rules/verify-changes.md: … 
```

- **Estructurales:** sin IA, los de las secciones 9 a 12 y las herramientas que compiten. Lo que solo
  informa (el presupuesto de contexto, qué ve cada provider, los servidores que quedan para el usuario,
  un dato que el catálogo no conoce) no cuenta como conflicto.
- **De IA:** las contradicciones entre rules (sección 7) y las skills que compiten (sección 13), de
  la caché o con el provider. `--offline` responde solo de la caché y dice cuántos pares quedaron sin
  revisar.
- **Código de salida:** `0` sin conflictos, `6` con alguno. `--json` deja el detalle de cada chequeo.

En CI, `agent-ready check` corre los mismos chequeos con `ci.conflicts` (`ci-check.md`).

### Al iniciar sesión y al editar

Los conflictos estructurales también aparecen sin pedirlos, en dos momentos. Cada uno se apaga por
separado:

- **Al iniciar sesión:** el hook de `SessionStart` (`sync-marketplace.sh`) los lista con el prefijo
  `[conflicts]`, cualquiera sea `updates.mode`. Los hallazgos de IA salen de la caché, en la línea
  `AI reviews:` de `status`.
- **Al editar:** el hook de `PostToolUse` (`check-harness-consistency.sh`) los recalcula cuando la
  edición toca una de sus entradas: `AGENTS.md`, `CLAUDE.md`, lo que hay bajo `.agents/`, `.claude/`
  y `.codex/`, `.mcp.json`, `.github/workflows/` y los archivos que leen los `assumes` (`package.json`,
  lockfiles, `.editorconfig`, Prettier). Corre sin red y sin la CLI del provider. La revisión de IA
  de rules y skills sigue igual que antes (sección 1).

```text
[conflicts] ! .agents/rules/ours.md (project) assumes test runner vitest, but the repository uses jest (package.json)
[conflicts] Each one with its fix: agent-ready conflicts
```

`agent-ready status` los lista siempre, bajo `Conflicts between the profiles:`.

| Clave | Default | Efecto |
|---|---|---|
| `conflicts.sessionStart.enabled` | `true` | `false` no los calcula al iniciar sesión |
| `conflicts.onEdit.enabled` | `true` | `false` no los recalcula al editar |
