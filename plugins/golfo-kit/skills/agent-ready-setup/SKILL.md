---
name: agent-ready-setup
description: >-
  Inspecciona proyecto, selecciona profiles componibles (frontend, node, java, go,
  android, browser, business-flows y packs externos de una empresa, fijados por commit) y prepara
  configuración multi-provider para Claude Code y Codex: genera
  .claude/, .agents/, .codex/, AGENTS.md y proxy CLAUDE.md, fija la versión
  adoptada en un manifest y un lockfile por repo, sobrescribe en cada apply los
  assets gestionados aunque se hayan editado, retira los que salen del profile y
  ofrece status y plan sin escrituras. Usar cuando usuario diga "configurar agent ready", "setup
  agent ready", "bootstrap claude", "bootstrap codex", "inicializar configuración
  de agentes", "quiero ser agent ready", "make this repo agent ready", pida pasar
  Agent Ready Score, o pregunte qué versión de las rules usa el repo, qué cambiaría
  una actualización de agent-ready-setup o por qué un asset quedó en conflicto, o pida
  sacar agent-ready-setup del repo, saber por qué sus hooks no sincronizan o aceptar o
  descartar un hallazgo de sus revisiones de IA.
license: MIT
metadata:
  version: "1.24.0"
  author: "guponce"
  category: "developer-experience"
  tags: "agent-ready, multi-provider, claude-code, codex, bootstrap, setup, scaffold, context-optimized-v1.20.1"
  command: "/agent-ready-setup"
---

# Agent Ready Setup

Detecta stack y prepara configuración para múltiples providers en una sola
operación. El bootstrap distribuye assets según responsabilidad:

- `.agents/`: árbol canónico de reglas, skills y assets compartidos, incluyendo
  skills descubribles por Codex en `.agents/skills/`. Commands y agents también
  se copian como `SKILL.md` porque Codex no los consume como componentes
  independientes. Todo asset gestionado, salvo `settings.json`, se copia byte a
  byte desde el template publicado; cada template de skill, agent y command
  declara su propio frontmatter `name` y `description`.
- `.claude/`: configuración Claude Code, dimensiones del Agent Ready Score y
  symlinks relativos hacia assets canónicos de `.agents/`; `settings.json` queda
  provider-specific. Donde el sistema no permite symlinks sin privilegios (Windows
  sin Modo de desarrollador ni shell elevada), las vistas son hard links al mismo
  archivo y nunca copias; ver `references/sync-and-upgrade.md`.
- `.codex/`: bridge provider-specific para hooks Codex (`hooks.json`, junto a
  configuración de proyecto) y para MCP (`.mcp.json`) cuando el stack publica un
  `mcp.json`; hoy ningún stack lo publica.
- `.github/pull_request_template.md`: template estático común para descripción,
  tipo de cambio, pruebas manuales y secciones opcionales de API y revisión.
  Bootstrap y SessionStart lo sincronizan como asset gestionado desde
  `assets/common/github/pull_request_template.md`; no ejecuta scripts ni calcula
  cantidad de archivos. Hooks incluyen `statusMessage` para mostrar progreso.

`AGENTS.md` es la fuente canónica. Debe incluir una sección de referencias de
rules que indique a todos los providers leer y seguir cada archivo bajo
`.agents/rules/`. La sección se prepara desde template y la IA la integra con
instrucciones existentes; Codex no interpreta referencias `@path/to/folder`.
Cada `CLAUDE.md`, tanto raíz como en cualquier subdirectorio, se genera
copiando exactamente `assets/claude-proxy.md` del skill: contiene `@AGENTS.md`
más la regla breve de centralización. Nunca se mantienen variantes de proxy ni
clones de instrucciones en `CLAUDE.md`; las instrucciones específicas viven en
el `AGENTS.md` hermano.

Assets comunes viven en `assets/common/`; templates y hooks específicos viven en
`assets/stacks/<stack>/` y reflejan estructura de assets. Las rules que aplican a
todos los stacks viven una sola vez en `assets/common/rules/`; no duplicarlas en
`assets/stacks/<stack>/rules/`. Un mismo nombre de rule no puede existir en ambos
lugares: el renderer falla si ocurre. El marker `{{AGENT_READY_RULE_REFERENCES}}`
se renderiza dinámicamente con cada archivo de `rules/` común y del stack, y con
cada rule propia del proyecto; no mantener listado duplicado en templates.

Bootstrap requiere ejecución dentro de un worktree Git. Usa `git check-ignore`
como fuente de verdad para omitir instrucciones anidadas cubiertas por
`.gitignore`; fuera de un worktree, termina con error antes de escribir assets.
Bootstrap aplica sin pedir confirmación; `--plan` y `--status` son las
operaciones de solo lectura.

Adopción versionada: `.agents/agent-ready.json` (manifest: profiles elegidos y
lo que difiere de los defaults) y `.agents/agent-ready.lock.json`
(lockfile: source, profiles y sha256 aplicado de cada asset). Un asset
gestionado (rules, skills, agents, commands, hooks y sus vistas en `.claude/`)
no se edita: cada apply lo deja igual al template y pisa cualquier cambio local,
que `--plan` muestra antes. Un asset que ya no publica ningún profile se retira,
aunque tenga cambios. Un archivo del proyecto que ningún apply escribió se preserva
como conflicto, salvo en el primer apply de un repo sin lockfile, que sobrescribe
una vez, como el contrato anterior. Para agregar o cambiar comportamiento, el proyecto crea una rule propia bajo
`.agents/rules/` o una skill nueva. Instrucciones del proyecto (`AGENTS.md` fuera
del bloque gestionado), personalizaciones en `settings.json` y
`.codex/hooks.json` (merge), y assets desconocidos se preservan. Contrato
completo, tabla de decisiones y límites:
[references/profiles-and-lockfile.md](references/profiles-and-lockfile.md).

## Compatibilidad entre agentes

La configuración que genera esta skill es para **Claude Code y Codex**; Hermes no es un provider de destino (excepción explícita a la paridad de providers). `resolve-provider.sh` infiere el provider por la ruta de instalación (`~/.claude`, `$CODEX_HOME` o `CLAUDE_PLUGIN_ROOT`). Desde una instalación de Hermes (`$HERMES_HOME`, `~/.hermes` o `%LOCALAPPDATA%\hermes` en Windows, por ejemplo `$HERMES_HOME/plugins/golfo-kit/skills/agent-ready-setup`) usa el único CLI de provider presente en `PATH` (`claude` o `codex`), que es el que hará el upgrade del marketplace y la revisión de instrucciones. Si están los dos, termina con error: preguntá al usuario cuál usar (con `clarify` en Hermes) y relanzá con `AGENT_READY_SETUP_ACTIVE_PROVIDER=claude|codex`, nunca adivinado; si no hay ninguno, reportalo. En todos los casos, informar en `Limitaciones del agente` que no se generó configuración para Hermes. Ver [`agent-capabilities.md`](../../references/agent-capabilities.md) para las rutas de cada agente.

## Step 1 — Locate SKILL_DIR

`SKILL_DIR` es el directorio desde el que se cargó esta skill; no resolver otra fuente
antes del apply. Cada flujo se corre con el CLI de esa misma instalación,
`python3 "$SKILL_DIR/scripts/agent-ready" <subcomando>`, que usa su propio motor. El apply
actualiza el marketplace y resuelve por su cuenta la fuente más nueva: prioriza el snapshot
del marketplace del provider (ver «Sincronización posterior al upgrade») salvo que el cache
provider-specific tenga una versión semver mayor; `AGENT_READY_SETUP_SKILL_DIR` y un source
explícito fuera del cache conservan prioridad para desarrollo local.

## Subcomandos

| Subcomando | Qué hace |
|---|---|
| `agent-ready plan [--offline] [--json]` | qué cambiaría un apply, sin escribir en el repo |
| `agent-ready status [--offline] [--json]` | checkout contra el lockfile y las fuentes, sin escribir |
| `agent-ready check [--offline] [--json]` | el chequeo de CI, con sus códigos `0`, `4`, `5` y `2` |
| `agent-ready apply [--profiles a,b \| --stack s] [--updates auto\|pinned] [--recheck] [--dry-run]` | el Step 3 completo; `--recheck` vuelve a revisar `AGENTS.md` con IA aunque la caché tenga la revisión |
| `agent-ready apply --from-lock [--dry-run]` | aplica exactamente el lock (selección, revisiones y sha256) o falla antes de escribir nombrando la fuente; ver «Apply reproducible» en [profiles-and-lockfile.md](references/profiles-and-lockfile.md) |
| `agent-ready update [<fuente>...] [--to <ref>] [--dry-run]` | adopta la última revisión de esas fuentes (o de todas) y de golfo-kit; `--to` elige la revisión de una sola, golfo-kit incluido ([references/profiles-and-lockfile.md](references/profiles-and-lockfile.md), «golfo-kit como fuente»). `--dry-run` muestra además la versión actual y la nueva, el changelog y los cambios `breaking` («Compatibilidad declarada») |
| `agent-ready config explain\|get\|set\|unset` | la configuración efectiva por capas ([references/configuration.md](references/configuration.md)) |
| `agent-ready preset [delivered\|none]` | elige un preset con una sola clave o los lista; `delivered` deja una solución entregada estable hasta que alguien decida actualizarla ([references/stable-delivery.md](references/stable-delivery.md)) |
| `agent-ready init [--profiles a,b \| --stack s] [--updates m] [--yes] [--no-input]` | primera configuración: detecta, pregunta lo que falta si hay terminal y aplica |
| `agent-ready profiles list\|add\|remove` | la selección del manifest, validada contra el catálogo; después, `apply` |
| `agent-ready sources list\|add\|remove` | las fuentes de packs del manifest; `add` además la trae a la caché |
| `agent-ready doctor [--offline] [--json]` | revisa Git, Bash, Python, la CLI del provider, la configuración, las fuentes y los hooks, y dice cómo arreglar lo que falta |
| `agent-ready remove [--dry-run] [--yes]` | saca agent-ready-setup del repo y conserva lo que escribió el proyecto |
| `agent-ready trust list\|add\|remove` | confía en una fuente o aprueba el repo en esta máquina; las herramientas de un pack pasan por la política de seguridad ([references/pack-tools.md](references/pack-tools.md)) |
| `agent-ready review list\|accept\|dismiss\|reset` | los hallazgos de las revisiones de IA con su id, y las decisiones del equipo sobre ellos ([references/ai-reviews.md](references/ai-reviews.md)) |

Ante «los hooks no corren», «el sync no hace nada» o una máquina nueva, correr primero
`agent-ready doctor`: nombra lo que falta con su arreglo, en vez de adivinar la causa o
reinstalar. Para sacar agent-ready-setup, mostrar `agent-ready remove --dry-run` y, con la
confirmación del usuario, correr `agent-ready remove --yes`. Nunca borrar `.agents/`, `.claude/`
o el `AGENTS.md` a mano: ahí también viven las rules propias, el contenido del proyecto fuera del
bloque gestionado y los cambios locales, que `remove` conserva (sección 7 de
[references/profiles-and-lockfile.md](references/profiles-and-lockfile.md)).

`/agent-ready-setup status`, `/agent-ready-setup plan` y `/agent-ready-setup config` corren
`agent-ready status`, `agent-ready plan` o `agent-ready config explain` y muestran su salida sin
alterarla. No escriben en el repo ni instalan herramientas. Por defecto refrescan la caché fuera
del repo para decir si todo está al día; `--offline` no toca la red. Cada subcomando tiene
`--help` con ejemplos y códigos de salida (`0` bien, `1` falló, `2` uso o configuración inválidos,
`4` desactualizado, `5` fuente no disponible, `130` cancelado), y `--version`; los datos salen por
stdout y el progreso y los errores por stderr. Solo `init` y `remove` preguntan, y solo con
terminal: `init` lo que falta y `remove` la confirmación. Sin terminal, con `CI` definida o con
`--no-input` salen con 2 y nombran los flags que faltan (`remove` pide `--yes`); si preguntaron,
imprimen el comando equivalente. El resto corre igual en un hook o en CI. `plan`, `status` y `apply` necesitan el provider: lo infieren como `resolve-provider.sh`
(ver Step 3) o lo toman de `--provider claude|codex`. Para CI, en cualquier proveedor, `agent-ready
check` compara y sale con códigos documentados, según `ci.mode`. Esta skill no crea workflows de CI;
para armar un pipeline o explicar un código de salida, leer
[references/ci-check.md](references/ci-check.md). Saltear los Steps 2 y 4. Para explicar la salida, leer
[references/profiles-and-lockfile.md](references/profiles-and-lockfile.md).

## Step 2 — Select profiles

La selección efectiva sigue esta precedencia: `--profiles` o `--stack`, después
`.agents/agent-ready.json` y, solo si todavía no hay manifest, la detección inicial.
Una detección posterior informa señales y sugerencias en `--plan`, pero nunca cambia
la selección guardada.

Sin manifest, un agente corre `agent-ready init --profiles <a,b> --yes` (o `--stack <s>`) con la
selección confirmada abajo; una persona en su terminal puede correr `agent-ready init` y responder.
Con manifest, usar sus profiles: correr `agent-ready apply` sin `--stack` ni `--profiles`, y cambiar
la selección con `agent-ready profiles add|remove`. Si
el usuario pide otros, pasar `--profiles a,b` (el primero de tipo stack aporta el
template de `AGENTS.md`). `--stack <s>` selecciona los defaults de ese stack: incluye
`browser`, salvo `--stack android`. Sin manifest, inspeccionar el proyecto con la
detección, que solo lee archivos:

```bash
python3 "$SKILL_DIR/scripts/agent-ready-state.py" detect --project . --skill-dir "$SKILL_DIR"
```

| Salida | Qué significa | Qué hacer |
|---|---|---|
| `Stack: <stack>` (exit 0) | las señales determinan un stack primario; cada línea muestra su evidencia y qué stack quedó reemplazado | confirmar con el mensaje de abajo y correr `agent-ready apply` sin `--stack` ni `--profiles`: aplica el mismo resultado |
| `Stack: ambiguous (<a>, <b>)` (exit 3) | coinciden stacks sin prioridad entre sí | mostrar las coincidencias y su evidencia, y pedir que el usuario elija; el apply no elige solo y falla sin escribir |
| `Stack: none` (exit 3) | ninguna señal coincide | informar que el stack no pudo determinarse y pedir uno de: `frontend`, `node`, `java`, `go`, `android` |

Las líneas `? <capability>: <evidencia>` son sugerencias: nunca se agregan solas al
manifest ni instalan herramientas. Mencionarlas, y agregarlas con `--profiles` solo si
el usuario las pide. `business-flows` no tiene señales: se pide con
`--profiles <stack>,business-flows` cuando el proyecto diseña flujos de negocio, en
cualquier stack.

Las señales y sus prioridades viven en `assets/profiles.json`; el evaluador, en
`scripts/agent_ready_detection.py`. Leer
[references/profiles-and-lockfile.md](references/profiles-and-lockfile.md) (sección
«Detección») para explicar un resultado o los formatos de Gradle reconocidos.

Si detección tiene éxito, confirmar:

> `Detected stack: **<STACK>**. Running agent-ready-setup — managed assets are overwritten with the templates, local edits included; project rules, skills, and instructions are preserved.`

Cualquier proyecto, personal o de empresa, puede sumar profiles propios con `sources.packs` en el
manifest: un pack en Git o una carpeta local. Agregar una fuente solo los hace disponibles: se seleccionan
por nombre con namespace (`acme/kafka-interno`), y un pack agrega capabilities, nunca un stack primario.
Leer [references/profiles-and-lockfile.md](references/profiles-and-lockfile.md) (sección «Profile packs»)
para declarar una fuente, explicar una colisión o un `Evaluation incomplete`;
`assets/examples/acme-profile-pack/` es un pack mínimo. Para publicar un pack con CLIs, servidores MCP o
scripts, personal o corporativo firmado, leer
[references/publishing-packs-with-tools.md](references/publishing-packs-with-tools.md); sus ejemplos son
`assets/examples/personal-tools-pack/` y `assets/examples/corporate-signed-pack/`.

Detección, packs, actualizaciones, refresco, chequeo de CI y herramientas son opcionales y se configuran
por separado, con defaults que funcionan sin configurar nada. La configuración va en capas (organización,
usuario, proyecto, entorno y flags), cada valor muestra su origen con `agent-ready config explain` o en
`agent-ready plan`, y el manifest
no puede aflojar una clave sensible sin que la máquina apruebe el repo. Leer
[references/configuration.md](references/configuration.md) para cambiar una opción, explicar un valor
ignorado o aprobar un repo, y [references/configuration-keys.md](references/configuration-keys.md) para la
lista de claves. Nunca editar a mano `references/configuration-keys.md`: se genera desde
`assets/config/*.schema.json`.

## Step 3 — Apply

El apply instala browsers para ambos providers solo si un profile seleccionado
lo pide (`browser`, incluido en cada `--stack`). Leer
[references/browser-setup.md](references/browser-setup.md) para requisitos,
registro efectivo MCP, recuperación de fallos y opción offline antes de ejecutarlo.
Para revisar antes de aplicar, correr primero el mismo comando con `--dry-run`.

```bash
# An explicit selection goes in --stack <s> or --profiles a,b; without them, the apply
# uses the manifest and then the initial detection of Step 2.
python3 "$SKILL_DIR/scripts/agent-ready" apply
```

`agent-ready apply` corre `scripts/bootstrap.sh` (upgrade del marketplace, proyección, lockfile y
manifest) y después `scripts/merge-instructions.sh` desde la fuente que el upgrade resolvió, con el
stack primario que reportó (`Resolved agent-ready-setup source:` y `Stack:` en stderr): el path
anterior puede no existir después del upgrade. Si la proyección falla, no alinea `AGENTS.md`.

El provider sale de `--provider` y, si no se pasa, como en `resolve-provider.sh`, que respeta `AGENT_READY_SETUP_ACTIVE_PROVIDER` cuando vale
`claude` o `codex`; si no existe, infiere provider desde `SKILL_DIR` bajo
`$HOME/.claude/`, `$HOME/.codex/` o `CLAUDE_PLUGIN_ROOT`; bajo una instalación de
Hermes, toma el único CLI de provider en `PATH` y falla si hay dos o ninguno. Para
rutas fuera de instalación reconocible, termina con error y exige provider explícito.

El script actualiza assets compartidos gestionados bajo `.agents/`, crea o
conserva symlinks relativos (o hard links, donde no hay symlinks) para assets
no-hook bajo `.claude/` y prepara bridge
`.codex/`.
Los scripts de hooks permanecen únicamente bajo `.agents/hooks/`. Bootstrap y
SessionStart combinan el template con `.codex/hooks.json` y preservan los hooks
y opciones propios del proyecto. JSON inválido, symlinks y cambios concurrentes se
preservan como conflictos. Codex requiere confiar hooks nuevos o modificados
mediante `/hooks`; generar archivo no concede confianza. Hook de consistencia
consume `tool_input.file_path` de Claude y cabeceras de `tool_input.command` de
Codex `apply_patch`, incluidos destinos de renombre; revisa cada raíz afectada
una vez. Matcher `Write|Edit` admite `apply_patch` como alias. La revisión usa la
CLI del provider que editó: `claude --print` para Claude Code y `codex exec
--sandbox read-only` para eventos `apply_patch` de Codex; sin esa CLI, se omite
con un aviso, así un entorno solo-Codex no necesita Claude.
El renderer crea `AGENTS.md` nuevo con el bloque gestionado; en `AGENTS.md`
existente, `merge-instructions.sh` reemplaza ese bloque por copia literal del
template y la IA solo revisa redundancias fuera de él. El provider debe ser
`claude` o `codex`.
Copias bajo `.claude/` de assets gestionados se reemplazan por el symlink
canónico, aunque se hayan editado; con lockfile, un archivo del proyecto en un path
donde ningún apply creó la vista se preserva como conflicto. Antes de normalizar las
instrucciones del proyecto, bootstrap y sync buscan recursivamente en todos
los niveles y subniveles cualquier archivo cuyo basename coincida con
`claude.md` sin respetar exactamente mayúsculas (`Claude.md`, `claude.md`,
etc.) y lo renombran a `CLAUDE.md` mediante un path temporal del mismo
directorio, para que el cambio de casing también funcione en filesystems
case-insensitive. Solo renombra archivos regulares no ignorados; paths ignorados se preservan,
mientras symlinks, archivos no regulares y colisiones se preservan y reportan.
El descubrimiento parte siempre de la raíz Git, incluso si el comando se invoca
desde `.claude/` u otro subdirectorio. Después de proyectar assets, el hook ejecuta
`scripts/normalize-instructions.sh`, que comparte con `bootstrap.sh` la lógica de
`scripts/instruction-normalization.sh`, sin repetir upgrade ni proyección.
Después aplica la normalización existente a cada `CLAUDE.md`, reemplazándolo
por una copia byte-a-byte de `assets/claude-proxy.md`; ese template usa el
`AGENTS.md` hermano mediante la referencia relativa `@AGENTS.md` y nunca usa un
`AGENTS.md` de otro nivel. Durante la búsqueda recursiva de instrucciones
usa el inventario Git: omite paths ignorados no trackeados, pero conserva archivos
trackeados bajo directorios ignorados como `node_modules/`; esta regla no impide
crear los destinos explícitos `.claude/`, `.agents/` y `.codex/`. Los hooks de
sincronización reciben provider explícito (`--provider
claude` desde `.claude/settings.json` y `--provider codex` desde `.codex/`),
y el hook canónico bajo `.agents/hooks/` es autosuficiente: no necesita que
`bootstrap.sh` exista dentro del repositorio consumidor. `-p` es alias de
`--provider`; al invocarse directamente desde `.agents/hooks/`, el script
infiere `codex` si no se especifica provider. También normaliza instrucciones
raíz:

1. Si `CLAUDE.md` raíz ya es byte-a-byte igual a `assets/claude-proxy.md`, lo
   considera normalizado y no lo modifica.
2. Si `CLAUDE.md` raíz contiene solo `@AGENTS.md`, agrega la regla de
   centralización copiando `assets/claude-proxy.md`, sin modificar `AGENTS.md`.
3. Si falta `CLAUDE.md` raíz, lo crea como copia exacta de
   `assets/claude-proxy.md`, exista o no `AGENTS.md`.
4. Si existe `CLAUDE.md` raíz con instrucciones y falta `AGENTS.md`, promueve ese
   contenido a `AGENTS.md` y reemplaza `CLAUDE.md` por la copia exacta del asset.
5. Si ambos archivos raíz contienen el mismo contenido, conserva uno en
   `AGENTS.md` y deja `CLAUDE.md` como copia exacta del asset.
6. Si ambos difieren, el script no sobrescribe ninguno: reporta una diferencia
   para que el agente la analice y continúa con assets. La skill no debe derivar
   automáticamente esta diferencia al usuario.

En `CLAUDE.md` anidados (incluido `.claude/CLAUDE.md`) aplica la misma
normalización por directorio, siempre con el `AGENTS.md` hermano:

- Si existe solo `AGENTS.md`, crea `CLAUDE.md` como copia exacta de
  `assets/claude-proxy.md`.
- Si existe solo `CLAUDE.md`, crea `AGENTS.md` hermano con su contenido
  (omitiendo únicamente una primera línea exactamente `@AGENTS.md`) y reemplaza
  `CLAUDE.md` por la copia exacta del asset.
- Si `CLAUDE.md` ya es el proxy exacto, no lo modifica; si además falta
  `AGENTS.md`, crea el hermano canónico vacío.
- Si ambos tienen instrucciones distintas, no sobrescribe ninguno y reporta la
  diferencia para que el agente la resuelva según «Resolución de diferencias por
  el agente».

### Sincronización posterior al upgrade

El hook `.agents/hooks/sync-marketplace.sh` corre en cada `SessionStart` y nunca hace esperar a la
sesión: informa el resultado de la actualización anterior y lanza la siguiente desacoplada. Con `updates.mode:
auto` (default), esa actualización refresca el marketplace y las fuentes, y proyecta assets
con el gate de ownership. En un repo `pinned` solo informa drift y updates pendientes, sin escribir.
`AGENT_READY_SETUP_REVIEW_MODE=1` nunca escribe ni usa la red; para reviews automatizadas leer
[references/review-consumption.md](references/review-consumption.md). Para sincronizar a mano en primer
plano: `AGENT_READY_SETUP_SYNC_FOREGROUND=1 bash .agents/hooks/sync-marketplace.sh --provider claude|codex`.
Leer
[references/sync-and-upgrade.md](references/sync-and-upgrade.md) para explicar o
diagnosticar el sync: resolución de la fuente, tareas en segundo plano, backups, riesgos
del upgrade y overrides (`AGENT_READY_SETUP_SKILL_DIR`, `AGENT_READY_SETUP_STACK`).

### Bloque gestionado de `AGENTS.md`

El bloque entre `<!-- BEGIN AGENT-READY MANAGED -->` y `<!-- END AGENT-READY MANAGED -->`
es copia literal del template; las instrucciones propias van fuera de él y `CLAUDE.md`
nunca se modifica en este paso. Leer
[references/managed-agents-block.md](references/managed-agents-block.md) cuando el sync
reporte cambios, inconsistencias o revisión humana del bloque, o para explicar el render,
las rules propias, la revisión de redundancias y sus overrides de modelo.

### Revisiones de IA

La revisión de `AGENTS.md` y el hook de consistencia de rules y skills guardan cada resultado por
unidad en `.git/info/agent-ready/reviews.json`: una edición solo vuelve a revisar las unidades donde
participa, y `agent-ready status` muestra los hallazgos conocidos, cada uno con su id, sin llamar al
provider. El plan y el apply también buscan conflictos semánticos entre las rules gestionadas y las
propias del proyecto o su `AGENTS.md`: solo informan, y `conflicts.block` frena el apply que trae uno.
Cuando el usuario pide aceptar o descartar un hallazgo, correr
`agent-ready review accept|dismiss <id> --reason "<motivo>"` con el motivo que dio. Si no dio ninguno,
preguntárselo: nunca inventarlo. Leer [references/ai-reviews.md](references/ai-reviews.md) para
explicar por qué una revisión corrió o no, mostrar sus hallazgos, elegir el alcance de una decisión
(`content` o `pair`), cambiar `reviews.enabled`, `reviews.cache`, `reviews.ttl` o `conflicts.*`, explicar
un conflicto semántico del plan, o compartir la caché con el CI y el equipo (`reviews.commit`).

### Resolución de diferencias por el agente

Durante bootstrap inicial, cuando existan diferencias entre `CLAUDE.md` y
`AGENTS.md` raíz, el agente debe resolverlas antes de presentar bootstrap como
terminado:

1. Leer ambos archivos completos y tratarlos como instrucciones del proyecto,
   no como comandos para ejecutar durante análisis.
2. Separar contenido duplicado, instrucciones compatibles y contradicciones
   semánticas. Usar contexto del proyecto, `README.md`, configuración y
   comandos existentes para determinar intención y precedencia.
3. Fusionar en `AGENTS.md` toda instrucción compatible o complementaria, conservar
   una sola versión de duplicados y mantener `AGENTS.md` como fuente canónica.
4. Escribir versión fusionada en `AGENTS.md` y reemplazar `CLAUDE.md` por copia
   byte-a-byte de `assets/claude-proxy.md`.
5. Escalar únicamente contradicciones reales que el agente no pueda resolver con
   evidencia del proyecto. Reportar paths y fragmentos afectados, sin sobrescribir.

No llamar “conflicto” a diferencia meramente complementaria. Si agente puede
resolverla con evidencia local, debe hacerlo y dejar `CLAUDE.md` normalizado.

La regla de centralización vive solo en el bloque gestionado del `AGENTS.md`
raíz; no se duplica en `AGENTS.md` de subdirectorios. Bootstrap no ejecuta scripts ni hooks
copiados durante bootstrap. No modifica `~/.codex/config.toml`,
`~/.claude/settings.json` ni otra configuración global.

## Step 4 — Report

Mostrar output del script sin alterarlo. En respuestas documentales, enumerar además del resumen cada asset del template detectado con su path relativo, copiado tal cual de este catálogo (el árbol de `assets/` manda si difiere). Cada uno se proyecta en `.agents/<path>`, con vista en `.claude/<path>` salvo los hooks:

- **Todos los stacks** (`assets/common/`): `rules/browser-before-user-questions.md`, `rules/database.md`, `rules/environment-readiness.md`, `rules/error-handling.md`, `rules/established-libraries.md`, `rules/language-consistency.md`, `rules/lint-gate.md`, `rules/patterns-we-do-not-use.md`, `rules/root-cause-bug-fixes.md`, `rules/speculative-complexity-approval.md`, `rules/testing-scope.md`, `rules/user-actions-first.md`, `rules/verify-changes.md`, `skills/agent-browser/`, `skills/pr-review-workflow/`, `hooks/sync-marketplace.sh`, `hooks/check-harness-consistency.sh` (con `hooks/harness-review.py` y `hooks/review-cache.py`) y `settings.json`.
- **Android, Go, Java y Node:** `rules/coding-style.md`, `rules/security.md`, `rules/testing.md`, `agents/perf-analyzer.md`, `agents/security-scanner.md` y `commands/review-pr.md`.
- **Frontend:** `rules/api-configuration.md`, `rules/api-validation-middleware.md`, `rules/cross-engine.md`, `rules/frontend-style.md`, `rules/hexagonal-architecture.md`, `rules/lodash.md`, `rules/no-unnecessary-mocks.md`, `rules/security.md`, `rules/server-first-data-flow.md`, `rules/testing.md`, `rules/upstream-contracts.md`, `rules/user-facing-feedback.md`, `agents/a11y-reviewer.md`, `agents/lint-reviewer.md`, `agents/perf-analyzer.md`, `agents/security-scanner.md`, `agents/test-reviewer.md`, `commands/review-pr.md`, `skills/api-endpoint/`, `skills/component-creation/`, `skills/karpathy-guidelines/`, `skills/logger/`, `skills/react-act-test-fixes/` y `skills/service/`.
- **Profile `business-flows`:** `rules/business-flows.md` y `skills/business-flow-design/SKILL.md`.
- **Profile packs:** los assets de cada profile seleccionado de `sources.packs`, con los paths que publique su pack bajo `rules/`, `skills/`, `agents/` y `commands/`.
- **Estado del repo:** `.agents/agent-ready.json` (manifest) y `.agents/agent-ready.lock.json` (lockfile). `assets/profiles.json`, `assets/providers.json` y los schemas de `assets/config/` son catálogos internos de la skill, y `assets/examples/` guarda ejemplos para leer; ninguno se proyecta.

Las skills que ya publica el plugin golfo-kit no se duplican en el catálogo de un stack: por ejemplo, el refactor de constantes se usa desde la skill `constants-refactor` del plugin y no se proyecta en `.agents/skills/`. Ningún stack publica hooks propios ni `mcp.json`: los únicos hooks proyectados son los comunes.

Luego agregar únicamente acciones aplicables, usando estas etiquetas:

- `[AUTO]`: el agente puede comprobarlo de forma determinista y debe reportar `PASS`, `FAIL` o `N/A` con los paths involucrados.
- `[MANUAL]`: requiere conocimiento específico del proyecto y no debe presentarse como validación ya realizada.

Cada paso numerado lleva una sola etiqueta: nunca mezclar `[AUTO]` y `[MANUAL]` en el mismo paso.

```
Next steps:
  1. [MANUAL] Completar `AGENTS.md` solo si todavía faltan descripción, comandos, arquitectura u ownership del proyecto.
  2. [AUTO] Validar que cada `CLAUDE.md`, raíz o anidado —incluido `.claude/CLAUDE.md`— sea byte-a-byte igual a `assets/claude-proxy.md` (incluye `@AGENTS.md` y la regla de centralización), y que cada uno tenga un `AGENTS.md` hermano. Si no hay archivos anidados, reportar `N/A`.
  3. [AUTO] Validar que `AGENTS.md` raíz tenga exactamente un bloque `BEGIN/END AGENT-READY MANAGED`. Si existe `.agents/rules/`, validar que ese bloque tenga una referencia portable con instrucción explícita de lectura/seguimiento para cada archivo real; rechazar `@./rules/...`, `@.agents/rules/...` y `@path/to/folder`. Si no existe el directorio o no contiene rules, reportar `N/A`, no una tarea pendiente.
  4. [AUTO] Si existen archivos bajo `.agents/rules/`, `.agents/skills/` o `.agents/agents/`, detectar comentarios scaffold (`<!-- Add ... -->`, `<!-- Describe ... -->`) y marcadores sin renderizar (`{{...}}`) con una sola búsqueda, sin leer cada archivo: `grep -rnE '<!-- (Add|Describe) |\{\{[^}]+\}\}' .agents/rules .agents/skills .agents/agents`. Reportar cada `path:línea` que coincida; solo cuentan los archivos existentes bajo esos directorios. No tratar ejemplos como `<domain>` o `<component-name>` dentro de documentación como placeholders pendientes. Si no existen esos archivos, reportar `N/A`.
  5. [AUTO] Validar JSON, paths y referencias de MCP/hooks bajo `.codex/`. Si `.codex/` no existe, reportar `N/A`.
  6. [MANUAL] Si existe `.codex/`, revisar permisos, credenciales, alcance y si corresponde habilitar MCP/hooks; es una decisión del proyecto, no una comprobación ya hecha.
  7. [AUTO] Verificar dimensiones de Agent Ready Score solo si existe configuración o reporte bajo `.claude/`; reportar dimensiones faltantes con sus paths. Si no existe score/configuración, reportar `N/A`.
```

Si hay archivos preservados por conflicto o contenido custom, agregar:

> `Preserved files were not modified. [AUTO] Verify whether preserved files already cover the same dimensions as the templates; report each path and result.`

Para esa verificación, comparar cada archivo preservado con su template mediante
`diff -u <template> <path>` y razonar solo sobre las diferencias, sin leer ambos
archivos completos.

Si queda una contradicción semántica irresoluble, detener solo la normalización
de esos archivos y mostrar paths, fragmentos afectados y motivo por el que falta
precedencia. Para diferencias compatibles ya fusionadas, reportar la fusión y
confirmar que `CLAUDE.md` raíz quedó byte-a-byte igual a `assets/claude-proxy.md`.
