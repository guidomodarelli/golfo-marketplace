# 🛒 Golfo Marketplace

> Multi-provider marketplace de skills y plugins para agentes AI.  
> Soporta **Claude Code**, **Codex** y **Hermes** 🤖

---

## 📁 Estructura del repositorio

```
├── .claude-plugin/
│   └── marketplace.json        # Registro de plugins para Claude Code
├── .agents/plugins/
│   └── marketplace.json        # Registro de plugins para Codex
├── .agents/skills/             # Skills locales del repo (mantenimiento), no distribuidas
├── .claude/skills/             # Symlinks a .agents/skills para Claude Code
├── plugins/
│   └── <plugin-name>/
│       ├── .claude-plugin/
│       │   └── plugin.json     # Manifiesto del plugin para Claude Code
│       ├── .codex-plugin/
│       │   └── plugin.json     # Manifiesto del plugin para Codex (si es compatible)
│       ├── plugin.json         # Manifiesto portable Agent Plugins v1 (Hermes)
│       └── skills/
│           └── <skill-name>/
│               ├── SKILL.md    # Definición del skill — requerido para cada skill
│               └── evals/
│                   └── eval-config.json
├── packages/
│   └── agent-ready/            # @golfo/agent-ready: el CLI agent-ready en el PATH
└── skill-eval-runner/          # CLI para correr evals localmente
```

### 🔀 Implementaciones por proveedor (opcional)

Cuando un plugin requiere una implementación diferente por proveedor, usá subdirectorios en lugar de un `skills/` compartido:

```
plugins/<plugin-name>/
├── claude/
│   ├── .claude-plugin/plugin.json
│   └── skills/
└── codex/
    ├── .codex-plugin/plugin.json
    └── skills/
```

Cada registro luego referencia la ruta del subdirectorio de su proveedor (ej. `./plugins/<name>/codex`).

---

## 🧩 Plugins

Cada plugin tiene un ámbito: una plataforma o una tecnología. Una skill va al plugin **exclusivo** de su ámbito, y si sirve en varios ámbitos sube al plugin **compartido** que los cubre. El nombre del plugin dice cuándo no aplica: `golfo-node-backend` no sirve para un backend en Java, ni `golfo-react` para una UI nativa de Android.

| Plugin | Ámbito | Skills |
|---|---|---|
| `golfo-kit` | Núcleo para trabajar con agentes | skill-optimizer, be-ambitious, deepen-prompt, cross-agent-skill-portability, windows-git-bash-agent-gotchas |
| `golfo-agent-ready` | Setup Agent Ready de un repositorio (Claude Code y Codex) | agent-ready-setup |
| `golfo-engineering` | Cualquier lenguaje, front, back o CLI | constants-refactor, refactor-modularize-code, simplify-code, async-operation-error-handling, error-observability-diagnostics, review-maintainability, review-performance, review-security, vivid-visual-output, undocumented-protocol-client |
| `golfo-javascript` | Solo JavaScript y TypeScript, front o back | typed-errors-refactor, enforce-jsdoc-tsdoc, test-best-practices, mock-first-testing-design, golfo-lint-adoption, golfo-npm-package-release |
| `golfo-testing` | Testing en cualquier lenguaje | test-planning, fix-tests-intelligently |
| `golfo-frontend` | Cualquier tecnología de UI (web, mobile nativo o React) | ui-ux-flow-patterns, optimistic-action-mutations, widget-ui-proposals |
| `golfo-react` | Solo React, web y React Native | react-render-performance-patterns |
| `golfo-web` | Solo web, cualquier framework | measured-performance-optimization, semantic-html-a11y, mobile-first-responsive-layout, user-manual, installed-pwa-platform-quirks, device-visual-bug-repro |
| `golfo-react-web` | Solo React en la web con SSR (Next.js, Remix, SSR propio) | prevent-ssr-hydration-mismatches, refactor-ssr-data-fetching, react-data-fetching-best-practices |
| `golfo-nextjs` | Solo Next.js App Router | nextjs-route-ui-boundaries |
| `golfo-node-backend` | Solo backend en Node.js | node-runtime-debugging |
| `golfo-cli` | Solo CLIs, cualquier lenguaje | interactive-cli-design |
| `golfo-git` | Git con cualquier host | sibling-worktree, generate-commit-messages, fix-in-ephemeral-clone, review-fix-loop, pr-flow-graph |
| `golfo-github` | Solo GitHub | feature-branch-pr, pr-description-template, pr-inline-comment-template, stacked-pr, codex-autofix-loop, claude-autofix-loop, codex-comment-closeout, inline-thread-autofix, pr-feedback-sweep, parallel-pr-hygiene |
| `golfo-planning` | Planificación con cualquier herramienta | create-issue, improve-spec, functionality-check |
| `golfo-jira` | Solo Jira | jira-ticket |

### 🔗 Dependencias entre plugins

Cada plugin se instala por separado, así que una skill no enlaza archivos de otro plugin: la nombra junto con su plugin (por ejemplo, «`async-operation-error-handling` (plugin `golfo-engineering`)»). La skill que nombra skills de otros plugins los declara en `metadata.plugin-dependencies` de su `SKILL.md`, como texto separado por comas:

```yaml
metadata:
  plugin-dependencies: "golfo-engineering, golfo-nextjs"
```

Instalá también esos plugins para que la skill pueda derivar a ellos. `pnpm check-plugin-boundaries` (CI) falla si un link se sale de su plugin o si una skill nombra una skill de otro plugin sin declararlo.

### 📦 Archivos compartidos (`shared/`)

Lo que usan varios plugins vive una sola vez en `shared/`: `references/agent-capabilities.md`, `references/review-convergence.md`, `references/skill-coverage.md` y el CLI `tools/skill-coverage/` (con sus tests). `shared/shared-files.json` dice qué plugin lleva cada uno; `pnpm sync-shared-files` escribe las copias en cada plugin y `pnpm sync-shared-files --check` (CI) falla si una copia difiere. Editá solo la fuente en `shared/` y volvé a sincronizar: las copias dentro de `plugins/` no se editan a mano.

---

## 🤖 Agent Ready multi-provider

`plugins/golfo-agent-ready/skills/agent-ready-setup` prepara siempre los tres planos sin acoplar assets compartidos a un provider:

```text
AGENTS.md                  # instrucciones canónicas
CLAUDE.md                  # raíz y subdirectorios: proxy exacto + regla
.claude/                   # Agent Ready Score y configuración Claude
.agents/hooks/             # scripts de hooks compartidos por ambos providers
.agents/skills/            # skills compartidas y descubribles por Codex
.agents/rules/             # reglas compartidas
.codex/hooks.json          # configuración de hooks específica Codex
.codex/.mcp.json           # MCP específico Codex, solo si el stack publica mcp.json
```

Si `CLAUDE.md` ya contiene instrucciones, el setup las promueve a un `AGENTS.md` hermano y deja `CLAUDE.md` como copia exacta de `assets/claude-proxy.md`. Esto también aplica a `.claude/CLAUDE.md` y cualquier subnivel. Si ambos archivos existen y difieren, no sobrescribe ninguno y reporta conflicto para resolución manual. La normalización recursiva parte de la raíz Git y omite paths ignorados no trackeados, incluidos `node_modules/` y worktrees, sin perder archivos trackeados bajo esas rutas; los destinos explícitos `.claude/`, `.agents/` y `.codex/` se siguen preparando aunque estén ignorados. El bootstrap requiere ejecutarse dentro de un worktree Git y actualiza automáticamente `golfo-marketplace` para provider activo antes de proyectar assets.

Después de `marketplace upgrade`, la actualización global no reproyecta assets sobre proyectos ya preparados. La ejecución directa de `agent-ready-setup` y el hook canónico `.agents/hooks/sync-marketplace.sh` seleccionan la versión cacheada semver más nueva y actualizan los assets gestionados bajo `.claude/`, `.agents/` y `.codex/`; ambos providers usan el mismo comportamiento con sus caches respectivas. La proyección recorre `assets/common/` y `assets/stacks/<stack>/`, incluyendo rules, agents, commands, skills, MCP y hooks; los hooks permanecen canónicos bajo `.agents/hooks/`, mientras `.claude/` recibe symlinks para assets no-hook. El hook normaliza instrucciones mediante `bootstrap.sh --normalize-only` cuando la versión instalada lo soporta y ejecuta el merge semántico de `AGENTS.md`. La normalización ocurre desde la raíz Git e incluye `.claude/CLAUDE.md`; conflictos, symlinks y destinos inseguros se preservan y reportan. Muestra diffs y aplica siempre los templates: un asset gestionado editado se sobrescribe, un asset que ya no publica ningún profile se retira aunque tenga cambios, y solo se preservan como conflicto los archivos que ningún apply escribió según `.agents/agent-ready.lock.json`. En repos con `"updates": "pinned"` en `.agents/agent-ready.json` (default) el hook solo informa el estado; `bootstrap.sh --plan` y `--status` muestran qué cambiaría sin escribir. Profiles, manifest y lockfile: `plugins/golfo-agent-ready/skills/agent-ready-setup/references/profiles-and-lockfile.md`. También combina el template con los settings JSON y preserva sus campos custom. El merge IA de `AGENTS.md` conserva cambios compatibles; si falla o queda sin resolución, aplica template y guarda backup temporal. `CLAUDE.md` nunca se modifica directamente por el merge IA.

El flujo manual y `SessionStart` usan el hook sin flags de confirmación. La resolución IA trata documentos como datos no confiables, aplica cambios compatibles automáticamente y usa fallback template + backup ante salida inválida o conflicto irresoluble. `CLAUDE.md` permanece como proxy.

### `agent-ready` en el PATH

Los agentes corren el CLI por ruta, desde la skill. Una persona lo tiene en su PATH con el paquete
npm [`@golfo/agent-ready`](packages/agent-ready/README.md), que usa el motor del plugin golfo-agent-ready
instalado en vez de traer otra copia:

```bash
npm install --global @golfo/agent-ready
agent-ready doctor
```

Para publicar una versión nueva: subir `version` en `packages/agent-ready/package.json` en un PR,
mergearlo y correr a mano el workflow **Release** (`.github/workflows/release.yml`) desde `main`
con esa versión. Publica por trusted publishing (OIDC, sin tokens, con provenance) y crea el tag
`agent-ready-vX.Y.Z` del commit publicado.

---

## 📦 Instalar este marketplace

Los nombres disponibles viven en `.claude-plugin/marketplace.json` y `.agents/plugins/marketplace.json`. Instalá el marketplace y reemplazá `<plugin-name>` por el plugin elegido:

```bash
# Claude Code, desde GitHub
claude plugin marketplace add --scope user guidomodarelli/golfo-marketplace
claude plugin install --scope user <plugin-name>@golfo-marketplace

# Codex, desde la raíz de un clone local de este repo
codex plugin marketplace add "$PWD"
codex plugin add <plugin-name>@golfo-marketplace

# Hermes, desde GitHub (paquete portable Agent Plugins v1 en plugins/<plugin-name>)
hermes plugins install guidomodarelli/golfo-marketplace#plugins/<plugin-name> --enable
hermes plugins update <plugin-name>   # traer una versión nueva
```

Hermes no usa `marketplace.json`: instala el directorio del plugin como paquete portable
y toma su `plugin.json` raíz y sus `skills/`. Las skills que no cumplen las restricciones de
Agent Skills (por ejemplo, una `description` de más de 1024 caracteres) se descartan sin
error, por eso `pnpm validate-portable-plugins` las valida en la CI.

---

## 🔧 Probar plugins y skills localmente

Usá esta guía para probar cualquier skill standalone, plugin o marketplace sin
publicarlo. Definí variables según el árbol que quieras probar:

```bash
MARKETPLACE_NAME="golfo-marketplace"
PLUGIN_NAME="<plugin-name>"
SKILL_NAME="<skill-name>"
PLUGIN_SRC="$PWD/plugins/$PLUGIN_NAME"
SKILL_SRC="$PLUGIN_SRC/skills/$SKILL_NAME"
```

Para una skill standalone, reemplazá `SKILL_SRC` por:

```bash
SKILL_SRC="$PWD/skills/$SKILL_NAME"
```

### 1. Cargar una skill directamente con symlink

Este método valida `SKILL.md`, recursos bundled y ejecución de la skill. No valida
manifests ni discovery del marketplace.

```bash
ln -sfn "$SKILL_SRC" "$HOME/.claude/skills/$SKILL_NAME"   # Claude Code
ln -sfn "$SKILL_SRC" "$HOME/.codex/skills/$SKILL_NAME"    # Codex
```

Reiniciá cada cliente después de crear el symlink. Las ediciones posteriores a
`SKILL.md`, `subcommands/*`, `knowledge/*`, `assets/*` o `scripts/*` quedan
reflejadas desde el repositorio.

### 2. Cargar un plugin en una sesión de Claude Code

Este método valida el plugin Claude sin instalarlo persistentemente:

```bash
claude --plugin-dir "$PLUGIN_SRC"
```

`--plugin-dir` no valida la instalación del marketplace Codex ni el registro de
`marketplace.json`.

### 3. Probar marketplace local completo

Ejecutá estos comandos desde raíz del marketplace, no desde `PLUGIN_SRC`:

```bash
# Claude Code
claude plugin marketplace add --scope local "$PWD"
claude plugin install --scope local "$PLUGIN_NAME@$MARKETPLACE_NAME"

# Codex
codex plugin marketplace add "$PWD"
codex plugin add "$PLUGIN_NAME@$MARKETPLACE_NAME"
```

Verificá instalación y discovery:

```bash
claude plugin list
codex plugin marketplace list
codex plugin list --json
```

Para probar cambios posteriores sin publicar el marketplace, actualizá la fuente
local cuando corresponda. En proyectos preparados con Agent Ready, el hook
SessionStart ejecuta siempre proyección local y merge de instrucciones:

```bash
claude plugin marketplace update "$MARKETPLACE_NAME"
codex plugin marketplace upgrade "$MARKETPLACE_NAME"

# Flujo completo desde hook canónico
bash .agents/hooks/sync-marketplace.sh --provider claude
bash .agents/hooks/sync-marketplace.sh --provider codex
```

### 4. Ejecutar evals de una skill

```bash
run-evals "$SKILL_SRC"
run-evals "$SKILL_SRC" --provider codex
```

Usá `--pretty` para un reporte legible. Las evals validan comportamiento de la
skill; no reemplazan la prueba de instalación del plugin o marketplace.

### ✅ Qué valida cada método

| Método | Valida | No valida |
|---|---|---|
| Symlink en `~/.claude/skills` o `~/.codex/skills` | Carga directa y cambios live de una skill | Manifests y registro del marketplace |
| `claude --plugin-dir` | Plugin Claude en una sesión | Instalación Codex y marketplace persistente |
| Marketplace local + `plugin install` / `plugin add` | Registry, manifests, plugin y skills del provider | Publicación remota |
| `run-evals` | Contrato y comportamiento declarado de una skill | Discovery del plugin instalado |

### 🗑️ Cleanup local

```bash
# Symlinks directos
rm -f "$HOME/.claude/skills/$SKILL_NAME" "$HOME/.codex/skills/$SKILL_NAME"

# Plugins instalados
claude plugin uninstall --scope local "$PLUGIN_NAME@$MARKETPLACE_NAME"
codex plugin remove "$PLUGIN_NAME@$MARKETPLACE_NAME"

# Marketplaces configurados
claude plugin marketplace remove "$MARKETPLACE_NAME"
codex plugin marketplace remove "$MARKETPLACE_NAME"
```

Solo los comandos de cleanup modifican la configuración local de los clientes;
el repositorio no cambia.

---

## ➕ Agregar un plugin

1. 🌿 Creá una feature branch: `feature/<plugin-name>`
2. 📂 Agregá tu plugin en `plugins/<plugin-name>/` siguiendo la estructura de arriba
3. 📋 Registralo en los archivos de registro correspondientes:
   - `.claude-plugin/marketplace.json` para Claude Code
   - `.agents/plugins/marketplace.json` para Codex
4. 🔍 Abrí un PR

> 📌 Un plugin debe aparecer en al menos un registro. Un plugin solo se instala para un proveedor si está listado en el `marketplace.json` de ese proveedor.
>
> 🔒 Todos los archivos `plugin.json` dentro del mismo plugin (`.claude-plugin/plugin.json`, `.codex-plugin/plugin.json` y el `plugin.json` portable de la raíz) deben compartir la misma versión. Si cambia cualquier skill, todos los manifiestos deben hacer bump juntos.
>
> 🧳 Cada plugin necesita un `plugin.json` portable en su raíz (Agent Plugins v1: `$schema` `https://agent-plugins.org/schemas/1.0.0/plugin.schema.json`, `name` igual al directorio y solo campos del spec) para poder instalarse en Hermes. `pnpm validate-portable-plugins` lo verifica.

**Formato de commit:** `feat(marketplace): add <name>`

---

## 🔖 Bumping de versión de un plugin

Usá el script `create-version` para hacer bump a la versión de un plugin. Actualiza el campo `version` en **todos** los manifiestos (`.claude-plugin/plugin.json`, `.codex-plugin/plugin.json` y, si existe, el `plugin.json` portable de la raíz) a la vez, manteniéndolos sincronizados. `pnpm cv` es un alias corto con los mismos argumentos (`pnpm cv --dry-run`).

```bash
pnpm create-version              # auto-detecta el único plugin cambiado sin bump en la branch; si no, muestra menú
pnpm create-version golfo-kit    # apuntá a un plugin directamente por nombre
pnpm create-version --dry-run  # preview sin escribir, commitear ni pushear (shorthand: -n)
pnpm create-version golfo-kit --bump minor  # sin prompts (patch | minor | major)
pnpm create-version --set 2.0.0  # versión exacta sin prompts
pnpm create-version --help     # ayuda (shorthand: -h)
```

El script compara branch actual contra primera base remota disponible (`origin/develop`, `origin/master` u `origin/main`) y suma cambios locales y los commits hechos en cada plugin después del último cambio de su versión (así detecta un plugin mergeado a la rama default sin bump) para detectar qué plugin cambió. Si el repo tiene un solo plugin, lo selecciona sin mostrar el menú. Ignora archivos fuera de `plugins/` para esa decisión. Luego pregunta cómo establecer la nueva versión — un semver bump (`patch` / `minor` / `major`) calculado desde la versión actual, o una versión exacta personalizada — crea un commit que incluye **solo** los `plugin.json` actualizados (el resto de cambios staged, unstaged o untracked queda intacto) y hace `push` automático de la rama (con `-u origin HEAD` si todavía no tiene upstream). Nunca hace force-push y también pushea las ramas default (`develop`, `master`, `main`); si el push falla, el commit local se conserva y el script termina con error. Con `--dry-run` (o `-n`) recorre los mismos prompts y muestra qué archivos actualizaría, el commit y el push planeados, sin modificar nada. `--bump <kind>` o `--set <version>` evitan el prompt de versión (no se pueden combinar) y `--help` (`-h`) muestra el uso.

> ⚠️ Antes de escribir, valida que todos los manifiestos ya compartan la misma versión y aborta si difieren — nunca vas a hacer bump desde un estado inconsistente.

### Check de versión en la CI

El workflow `.github/workflows/version-bump.yml` corre en cada pull request el job `Version bump` (`pnpm check-version-bump <base>`). Falla si un plugin cambió respecto del merge base sin subir su versión, si los manifiestos (Claude, Codex y portable) quedaron en versiones distintas o si la versión no es `MAJOR.MINOR.PATCH`. Cuentan como cambio todos los archivos bajo `plugins/<plugin>/` salvo los que están dentro de carpetas `tests/` o `evals/`, que no cambian lo que el plugin entrega a los agentes. Un plugin nuevo pasa sin versión base. Para correrlo local: `pnpm check-version-bump` (compara contra `origin/main`).

### Validación del paquete portable (Hermes)

El job `Shell suites` de `.github/workflows/tests.yml` corre `pnpm validate-portable-plugins`
(`scripts/validate-portable-plugins.js`). Falla si un plugin no tiene `plugin.json` portable en su
raíz, si ese manifest no declara el schema de Agent Plugins v1, usa otro `name`, agrega campos
fuera del spec o difiere en versión del manifest de Claude, si alguna `skills/*/SKILL.md` tiene
un `name` distinto de su directorio o una `description` vacía o de más de 1024 caracteres, o si hay
un `SKILL.md` anidado dentro de una skill fuera de `assets/`, `references/`, `templates/` o
`scripts/`: Hermes recorre `skills/` recursivamente y lo instalaría como una skill aparte.

---

## 🧪 Correr tests shell localmente

Las suites shell usan [bats-core](https://github.com/bats-core/bats-core) con versión y dependencias fijadas en `pnpm-lock.yaml`. Requieren Node.js 24 (versión exacta en `.nvmrc`) y pnpm 12 (fijado en `packageManager`). `pnpm-workspace.yaml` activa `shellEmulator`, así los scripts con sintaxis POSIX (`VAR=valor comando`) corren igual en Windows.

```bash
# Instalación reproducible
pnpm install --frozen-lockfile

# Preparación explícita de tests browser (Python 3.11+, instala tomlkit en venv local)
pnpm run setup:browser-tests

# Todas las suites: las rápidas, Agent Ready, bootstrap y el resto
pnpm run test
```

`pnpm run test:shell` corre las suites bats rápidas (create-version, check-version-bump, el contrato del
eval runner, la detección de áreas de la CI, el lanzador de bats y las de otras skills). `pnpm run test:agent-ready` corre las
suites bats de `agent-ready-setup` y `pnpm run test:bootstrap`, `bootstrap.bats`. La CI usa esos mismos
scripts, así que la lista de suites vive en un solo lugar: `package.json`.

Esos scripts y la CI corren bats con `scripts/run-bats.sh`, que arranca el bats de las devDependencies.
Para correr bats a mano, usá el mismo script (`bash scripts/run-bats.sh <opciones> <archivos>`) y no
`pnpm exec bats`. En Windows, el shim de pnpm arranca bats por su ruta `C:\`, y con esa ruta bats abre un
proceso por cada comando de su propia librería. Antes del primer test de `bootstrap.bats`, eso cuesta algo más
de 1 minuto, o casi 3 con un filtro de tags, y después algunos segundos por test (#95).

Las suites de `agent-ready-setup` proyectan el pack oficial de contenido
([golfo-agent-profiles](https://github.com/guidomodarelli/golfo-agent-profiles)) en el tag de
`plugins/golfo-agent-ready/skills/agent-ready-setup/tests/content-pack.ref`. `tests/prepare-content-pack.sh` lo clona una
sola vez en `node_modules/.cache/agent-ready-content-pack/`, así que la primera corrida necesita red y las
siguientes no.

`pnpm run test:review-fix-loop` corre solo la suite del helper de `review-fix-loop`, que usa
providers falsos y no llama a Claude ni a Codex reales.
`pnpm run test:sibling-worktree` corre la suite del helper de `sibling-worktree` sobre repos git
temporales.
`pnpm run test:skill-coverage` corre con `node --test` la suite del motor de cobertura incremental de
skills (`shared/tools/skill-coverage/`, la fuente que `pnpm sync-shared-files` copia a cada plugin) sobre repos git temporales; usa `@babel/parser`
de las devDependencies para el análisis por símbolos.
`pnpm run test:pr-flow-graph` corre con `node --test` las suites de `pr-flow-graph`: el
validador del modelo, los renderers de Mermaid y HTML, la compuerta de Lean, el contrato del CLI y la
página del grafo en un navegador real. Esta última usa `playwright-core` y su Chromium, igual que la
suite de `user-manual`, y toma ELK de la devDependency `elkjs`, sin red.
`pnpm run test:user-manual` corre con `node --test` las suites de `user-manual`: el contrato CLI de
`check-manual.mjs` y `build-manual.mjs` (sin dependencias) y la prueba de navegador de la
lectura por etapas y del adaptador de visor. Esta última usa `playwright-core` (devDependency) y
necesita su Chromium: `pnpm exec playwright-core install chromium` lo descarga, o
`PLAYWRIGHT_CHROMIUM_EXECUTABLE` apunta a un binario ya instalado. En local, sin Playwright, se marca
como omitida; en la CI (`CI` definido) es obligatoria y falla si no puede correr.
`skill-eval-runner/install.sh` instala `run-evals` como symlink al script del repo o, donde no hay
symlinks reales (Git Bash en Windows), como un lanzador que lo ejecuta: nunca una copia que quede vieja.

Cada test tiene un timeout de 30 segundos: `test:shell` usa `BATS_TEST_TIMEOUT=30` y las suites
bash de `review-fix-loop` y `sibling-worktree` corren cada test bajo `timeout` (`gtimeout` en macOS).
La excepción es `pnpm run test:bootstrap`, con 120 segundos por test: sus
tests corren bootstrap y sync completos varias veces, y en Windows algunos tardan más de un minuto.
Las suites bats corren con `LC_ALL=C.UTF-8`: el shell de `pnpm run` no pasa la configuración
regional, y sin UTF-8 bats no ejecuta los tests cuyo nombre lleva tildes.
Un test que se cuelga falla con `timeout` en vez de bloquear la corrida. Para cambiar el límite en las
suites bash, exportá `TEST_TIMEOUT_SECONDS`.

### Qué corre la CI en cada PR

El workflow `Tests` decide qué correr con `scripts/detect-test-areas.js`, que compara el PR contra el
merge-base de su base:

| Grupo | Corre cuando |
|---|---|
| `Shell suites` (`test:shell`, `compat:validate` y las suites de las demás skills) | Siempre |
| Agent Ready en Linux, Windows y macOS, los shards de `bootstrap.bats` y `Browser registration` | El PR cambia `plugins/golfo-agent-ready/skills/agent-ready-setup/**`, `package.json`, `pnpm-lock.yaml`, `pnpm-workspace.yaml`, `.nvmrc`, `.gitattributes`, `.github/workflows/tests.yml`, el lanzador de bats (`scripts/run-bats.sh`) o el script de detección y su test. También cuando cambia un manifest de golfo-agent-ready (`plugin.json`, `.claude-plugin/`, `.codex-plugin/`) en algo distinto de `version`, o se agrega o borra un archivo en esas carpetas |

- Un bump de versión solo no dispara Agent Ready: las suites nunca leen la versión real, y
  `check-version-bump.js` ya la valida en cada PR.
- Un `push` a `main` y `workflow_dispatch` corren todo, sin filtro. Son la red de seguridad del filtro, así
  que en `main` una corrida nueva no cancela la anterior.
- Si la detección no puede comparar, corre todo. El check `Tests` acepta un job salteado solo si la
  detección terminó bien y dijo que su área no hacía falta.
- Para sumar un path al filtro, editar `AGENT_READY_TRIGGER_PATHS` en el script y sumar su caso a
  `tests/detect-test-areas.bats`.

### Qué suite correr según el cambio

En local en Windows, las suites de agent-ready-setup tardan mucho. Cada test ejecuta bootstrap y sync
completos, y en Git Bash cada proceso cuesta unos 40 ms. Corridas en serie con `scripts/run-bats.sh` (#95);
`bootstrap.bats` y `merge-instructions.bats` suman sus áreas, corridas de a una:

| Suite | Tests | En serie |
|---|---|---|
| `bootstrap.bats` | 133 | ~32 min |
| `agent-ready-state.bats` | 52 | ~14 min |
| `merge-instructions.bats` | 35 | ~3 min |

Correrlas en paralelo no ayuda: con 8 procesos de bats, `merge-instructions.bats` baja solo ×1,5, porque cada test
se vuelve más lento. Durante una tarea, corré solo lo que cubre el cambio y dejá la suite completa a la CI:

| Cambio | Comando local |
|---|---|
| La ref del pack de contenido de los tests (`tests/content-pack.ref`) o el bloque gestionado de `AGENTS.md` | `bash scripts/run-bats.sh plugins/golfo-agent-ready/skills/agent-ready-setup/tests/merge-instructions.bats` y `bash scripts/run-bats.sh --filter 'rules' plugins/golfo-agent-ready/skills/agent-ready-setup/tests/bootstrap.bats` (las rules y el template viven en [golfo-agent-profiles](https://github.com/guidomodarelli/golfo-agent-profiles)) |
| Un flujo puntual de `agent-ready-setup` | `bash scripts/run-bats.sh --filter '<parte del nombre del test>' plugins/golfo-agent-ready/skills/agent-ready-setup/tests/bootstrap.bats` |
| Scripts de bash de `agent-ready-setup` (`scripts/*.sh`, `assets/common/hooks/*.sh`) | el área de `bootstrap.bats` o de `merge-instructions.bats` que cubre el script ([Áreas](#áreas-de-bootstrapbats-y-merge-instructionsbats)); la suite entera, en la CI |
| Profiles, manifest, lockfile u ownership de `agent-ready-setup` (`scripts/agent-ready-state.py`, `scripts/agent_ready_*.py`, `assets/providers.json`) | `bash scripts/run-bats.sh plugins/golfo-agent-ready/skills/agent-ready-setup/tests/agent-ready-state.bats` y las áreas `area:projection` y `area:managed-assets` de `bootstrap.bats` |
| Configuración por capas de `agent-ready-setup` (`assets/config/*.schema.json`, `scripts/agent_ready_config.py`) | `bash scripts/run-bats.sh plugins/golfo-agent-ready/skills/agent-ready-setup/tests/agent-ready-config.bats` |
| CLI `agent-ready` (`scripts/agent-ready`, `scripts/agent_ready_cli.py`) | `bash scripts/run-bats.sh plugins/golfo-agent-ready/skills/agent-ready-setup/tests/agent-ready-cli.bats` |
| Caché de las revisiones de IA de `agent-ready-setup` (`assets/common/hooks/review-cache.py`, `harness-review.py`, `check-harness-consistency.sh`) | `bash scripts/run-bats.sh plugins/golfo-agent-ready/skills/agent-ready-setup/tests/agent-ready-reviews.bats`, y para la revisión de `AGENTS.md` también `merge-instructions.bats` |
| Rules atómicas de `agent-ready-setup` (`scripts/agent_ready_rules.py`, `agent-ready rules`) | `bash scripts/run-bats.sh plugins/golfo-agent-ready/skills/agent-ready-setup/tests/agent-ready-rules.bats` |
| Aprendizaje de `agent-ready-setup` (`scripts/agent_ready_learning.py`, `agent-ready learn`) | `bash scripts/run-bats.sh plugins/golfo-agent-ready/skills/agent-ready-setup/tests/agent-ready-learning.bats plugins/golfo-agent-ready/skills/agent-ready-setup/tests/agent-ready-learning-reorganize.bats plugins/golfo-agent-ready/skills/agent-ready-setup/tests/agent-ready-learning-share.bats` |
| El contenido de `agent-ready-setup` (`sources.golfo`, `scripts/agent_ready_content.py`) | `bash scripts/run-bats.sh plugins/golfo-agent-ready/skills/agent-ready-setup/tests/agent-ready-content.bats` |
| Conflictos semánticos entre rules gestionadas y propias de `agent-ready-setup` (`scripts/agent_ready_conflicts.py`) | `bash scripts/run-bats.sh plugins/golfo-agent-ready/skills/agent-ready-setup/tests/agent-ready-conflicts.bats` |
| Archivos de CI por proveedor de `agent-ready-setup` (`assets/ci/`, `ci.provider`, `agent-ready ci setup`) | `bash scripts/run-bats.sh plugins/golfo-agent-ready/skills/agent-ready-setup/tests/agent-ready-ci.bats` |
| Herramientas de un pack y política de seguridad de `agent-ready-setup` (`scripts/agent_ready_pack_tools.py`, `agent-ready trust`) | `bash scripts/run-bats.sh plugins/golfo-agent-ready/skills/agent-ready-setup/tests/agent-ready-pack-tools.bats` |
| `review-fix-loop`, `sibling-worktree`, `create-version`, `check-version-bump`, `validate-portable-plugins` o el eval runner | Su suite (`pnpm run test:review-fix-loop`, `pnpm run test:sibling-worktree`, `bash scripts/run-bats.sh tests/create-version.bats tests/check-version-bump.bats tests/validate-portable-plugins.bats`, `bash scripts/run-bats.sh skill-eval-runner/tests/*.bats`) |
| Motor de cobertura de skills (`shared/tools/skill-coverage/**`) | `pnpm run test:skill-coverage` y `pnpm sync-shared-files` |
| Un archivo de `shared/`, `shared/shared-files.json`, un link entre skills o `metadata.plugin-dependencies` | `pnpm sync-shared-files --check`, `pnpm check-plugin-boundaries` y `bash scripts/run-bats.sh tests/sync-shared-files.bats tests/check-plugin-boundaries.bats` |
| `user-manual`: navegación de `DESIGN.md`, `scripts/check-*`, `build-manual.mjs` o `assets/` | `pnpm run test:user-manual` (con Playwright para la suite de navegador) y, si se tocó la paleta, `bash scripts/run-bats.sh plugins/golfo-web/skills/user-manual/tests/check-design-tokens.bats` |
| `pr-flow-graph`: el modelo de flujo, `scripts/` o `assets/flow-graph-template.html` | `pnpm run test:pr-flow-graph` (con Playwright para la suite de navegador) |
| Helper de `jira-ticket` (`scripts/jira-ticket.py`) | `pnpm run test:jira-ticket` (necesita `pytest`: `python3 -m pip install pytest`) |
| Frontmatter de una skill o `plugin.json` de un plugin | `pnpm validate-portable-plugins` |

Anteponé `LC_ALL=C.UTF-8` a cada `bats` (ver más arriba). En Windows, `bats --jobs` no funciona:
Git Bash no trae `flock` ni GNU `parallel`.

La CI (`.github/workflows/tests.yml`) corre todas las suites en cada pull request y en cada push a
`main`, sobre Ubuntu: `bootstrap.bats` se reparte en 3 shards que corren en paralelo y, dentro de
cada shard, en paralelo con `bats --jobs`. El check `Tests` exige que pasen todas.

`pnpm run test:browser` ejecuta pruebas de registro browser desde el venv local,
sin descargar dependencias. La prueba de lanzamiento real es opt-in mediante
`AGENT_READY_SETUP_BROWSER_SMOKE_ROOT` (directorio administrado de herramientas)
y `AGENT_READY_SETUP_BROWSER_SMOKE_EXECUTABLE` (path de Chromium instalado).
Los tests comunes usan parser TOML real; instalación de paquetes y browsers queda
fuera de la suite aislada.

### Áreas de `bootstrap.bats` y `merge-instructions.bats`

Cada test de esas dos suites lleva un tag de área (`# bats test_tags=area:<área>`). Corré la del cambio con
`--filter-tags`, y una más si el cambio toca dos áreas. En local en Windows, los tests de cada área suman menos de
5 minutos: la columna «En Windows» es lo que tardó cada área corrida sola con `scripts/run-bats.sh` en #95,
contando el arranque de bats.

```bash
LC_ALL=C.UTF-8 bash scripts/run-bats.sh --filter-tags area:skill-source plugins/golfo-agent-ready/skills/agent-ready-setup/tests/bootstrap.bats
```

| Suite | Área | Qué cubre | Archivos | Tests | En Windows |
|---|---|---|---|---|---|
| `bootstrap.bats` | `area:session-start` | SessionStart y el registro de los servidores MCP del browser | `assets/common/hooks/sync-marketplace.sh`, `scripts/setup-browser-tools.py` | 5 | ~1,4 min |
| `bootstrap.bats` | `area:cli` | argumentos, flags y salidas de bootstrap y del hook, y qué provider se usa | `scripts/bootstrap.sh`, `scripts/resolve-provider.sh` | 13 | <1 min |
| `bootstrap.bats` | `area:pr-template` | el template de PR de GitHub y su bloque gestionado | `scripts/managed-block.sh` | 5 | ~1,4 min |
| `bootstrap.bats` | `area:projection` | los árboles de Claude, `.agents` y Codex, y que un segundo apply no cambie nada | `scripts/bootstrap-asset-projection.sh` | 5 | <1 min |
| `bootstrap.bats` | `area:stacks` | las rules y los adaptadores de cada stack | `scripts/bootstrap-asset-projection.sh`, el pack de contenido | 2 | ~1,5 min |
| `bootstrap.bats` | `area:browser-rule` | la rule del browser en cada stack, con los dos providers | `scripts/bootstrap-asset-projection.sh` | 1 | ~1,5 min |
| `bootstrap.bats` | `area:adapters` | los adaptadores de skills y el registro de agents y commands en Claude | `scripts/bootstrap-asset-projection.sh` | 4 | <1 min |
| `bootstrap.bats` | `area:settings` | el merge de los settings de Claude con lo propio del proyecto | `scripts/merge-managed-settings.py` | 5 | ~1,6 min |
| `bootstrap.bats` | `area:autonomous-sync` | la sync en segundo plano: settings y copias de Claude | `assets/common/hooks/sync-marketplace.sh` | 2 | ~1,1 min |
| `bootstrap.bats` | `area:claude-views` | las vistas de `.claude/` de las rules gestionadas y propias | `scripts/asset-sync-common.sh` | 3 | ~1,2 min |
| `bootstrap.bats` | `area:instructions-root` | `AGENTS.md` y el proxy `CLAUDE.md` de la raíz | `scripts/instruction-normalization.sh`, `scripts/normalize-instructions.sh` | 9 | ~1,3 min |
| `bootstrap.bats` | `area:instructions-nested` | los pares anidados y el `CLAUDE.md` de `.claude/` | `scripts/instruction-normalization.sh` | 5 | ~1,5 min |
| `bootstrap.bats` | `area:instructions-edge` | mayúsculas distintas, archivos ignorados por Git y raíces symlink | `scripts/instruction-normalization.sh` | 9 | ~1,2 min |
| `bootstrap.bats` | `area:harness-hooks` | el hook que revisa una rule editada, en Claude y en Codex | `assets/common/hooks/harness-review.py`, `check-harness-consistency.sh` | 6 | ~1,5 min |
| `bootstrap.bats` | `area:codex-hooks` | la instalación de los hooks de Codex | `scripts/asset-sync-common.sh` (`sync_codex_hooks`) | 1 | ~1,4 min |
| `bootstrap.bats` | `area:codex-hooks-merge` | el merge de `.codex/hooks.json` con lo propio del proyecto | `scripts/merge-codex-hooks.py` | 6 | ~1,8 min |
| `bootstrap.bats` | `area:marketplace-upgrade` | el upgrade del marketplace y su ventana de una hora | `scripts/bootstrap.sh` (`upgrade_marketplace`), `sync-marketplace.sh` | 8 | ~1,6 min |
| `bootstrap.bats` | `area:skill-source` | qué versión de la caché de plugins usa bootstrap | `scripts/bootstrap-skill-source.sh` | 4 | ~1,3 min |
| `bootstrap.bats` | `area:skill-snapshot` | el snapshot del marketplace contra la caché de plugins, y `--skill-dir` | `scripts/bootstrap-skill-source.sh` | 3 | <1 min |
| `bootstrap.bats` | `area:sync-hook-cache` | qué versión usa el hook de sync: caché o snapshot | `assets/common/hooks/agent-ready-skill-source.sh`, `sync-marketplace.sh` | 4 | ~1,6 min |
| `bootstrap.bats` | `area:sync-hook-codex` | los marketplaces locales y Git de Codex en el hook de sync | `assets/common/hooks/agent-ready-skill-source.sh` | 4 | ~1 min |
| `bootstrap.bats` | `area:sync-hook` | el hook de sync sin bootstrap: helpers, escrituras atómicas y locks | `assets/common/hooks/sync-marketplace.sh`, `scripts/asset-sync-common.sh` | 11 | ~1,6 min |
| `bootstrap.bats` | `area:managed-assets` | las actualizaciones de assets gestionados, sus diffs y los destinos inseguros | `scripts/bootstrap-asset-projection.sh` (`sync_file`) | 7 | ~1,6 min |
| `bootstrap.bats` | `area:hard-links` | las vistas como hard links: cuándo se usan, se relinkean y se podan | `scripts/asset-sync-common.sh` | 6 | ~1,3 min |
| `bootstrap.bats` | `area:relink-hook` | el hook de git que relinkea las vistas después de un `git reset` | `scripts/asset-sync-common.sh` (`install_hard_link_git_hook`) | 5 | ~1,1 min |
| `merge-instructions.bats` | `area:managed-block` | el bloque gestionado de `AGENTS.md`, sus rules y las secciones de los stacks | `scripts/managed-block.sh`, `scripts/merge-instructions.sh` | 13 | <1 min |
| `merge-instructions.bats` | `area:review` | la revisión de IA de `AGENTS.md`, su caché y sus rechazos | `scripts/merge-instructions.sh` | 15 | ~1,6 min |
| `merge-instructions.bats` | `area:merge-safety` | el reemplazo atómico, los locks y el orden del hook de sync | `scripts/merge-instructions.sh`, `sync-marketplace.sh` | 7 | <1 min |

Un test nuevo lleva el tag del área que cubre. Si un área pasa de 5 minutos, partila en dos que tengan sentido por sí
solas.

---

## 🧪 Correr evals localmente

```bash
# Configuración inicial (una sola vez)
cd skill-eval-runner && ./install.sh

# Correr evals para un skill específico (JSONL por defecto)
run-evals plugins/<plugin-name>/skills/<skill-name>

# Reporte legible con colores (opcional)
run-evals plugins/<plugin-name>/skills/<skill-name> --pretty

# Run every case N times and report flaky cases (passed some runs) apart from broken ones
run-evals plugins/<plugin-name>/skills/<skill-name> --repeat 3

# Override de proveedor (por defecto: auto-detecta Codex o Claude)
run-evals plugins/<plugin-name>/skills/<skill-name> --provider codex

# Medir la activación del description con evals/trigger-evals.json (solo Claude)
run-evals plugins/<plugin-name>/skills/<skill-name> --triggers --repeat 3

# Correr los evals de un directorio de rules (rules/*.md sin SKILL.md, por ejemplo un stack de un pack de contenido)
run-evals ../golfo-agent-profiles/stacks/nextjs

# Correr cada caso también sin la skill y calificar esa respuesta con las mismas aserciones (duplica llamadas)
run-evals plugins/<plugin-name>/skills/<skill-name> --baseline --repeat 3

# Override persistente de proveedor
export GOLFO_MARKETPLACE_EVAL_PROVIDER=codex
```

Con `--baseline`, el JSONL de cada caso suma `baseline`. Su `status` es `passed` si el caso pasa sin la skill en
todas las corridas calificadas, y entonces no discrimina: pasaría aunque la skill no aportara nada. Vale `flaky` si
pasa solo en algunas, `failed` si falla en todas, e `infrastructure` si el provider falló en todas y no hubo nada que
calificar. El resumen suma `baseline_passed` y `baseline_flaky`, y `--pretty` lista los casos que pasan sin la skill.
Solo la corrida con la skill decide si un caso pasa.

Un caso que pasa sin la skill a propósito, porque mide algo que el modelo ya hace bien por defecto, se marca como caso
de control con `"control": "<motivo>"`. El motivo no puede estar vacío. Si pasa sin la skill, no cuenta en
`baseline_passed`: suma en `baseline_control`, `baseline.control` lleva el motivo y `--pretty` lo lista aparte.

En Windows (Git Bash, MSYS2 o Cygwin), el prompt nombra la copia de la skill con su ruta de Windows
(`cygpath -m`), porque el CLI nativo del agente no abre una ruta como `/tmp/tmp.X`.

**Activación (`--triggers`):** mide si el `description` hace que el agente elija la skill.

- **Los pedidos** salen de `evals/trigger-evals.json`, con el formato de skill-creator `[{query, should_trigger}]`, o
  de un archivo pasado con `--config`.
- **Cada corrida** usa un directorio vacío con una copia del frontmatter bajo un nombre único, que es la única skill
  del proyecto. Corre con `--setting-sources project`, así que no entran las skills ni los plugins del usuario.
- **Pasa** si la primera herramienta que llama el agente elige esa copia cuando debe, y no la elige cuando no debe.
  Si la sesión no cargó la copia, la corrida no se califica.
- **El JSONL** tiene una línea `trigger` por pedido y una `trigger_summary` con `trigger_rate`, la tasa en los pedidos
  que deben activarla, y `false_trigger_rate`, la tasa en los que no.
- **Solo funciona con Claude.** No se combina con `--all` ni con `--baseline`.

**Directorios de rules:** una rule no es una skill, así que un directorio con `rules/*.md` y sin `SKILL.md` es un
destino propio. Puede ser un stack, un profile o `base/` de un pack como golfo-agent-profiles. Sus evals van al lado,
en `<dir>/evals/eval-config.json`, y el prompt le pide al agente que aplique las rules de `<dir>/rules/` que cubren el
pedido. Ese directorio no se instala como skill. La copia aislada incluye las otras carpetas del pack, sin los
`evals/` del directorio, así que una rule que nombra a otra por su archivo (por ejemplo, una de `base/rules/`) la
encuentra. Si el directorio tiene `SKILL.md`, es una skill aunque traiga `rules/`.

**Qué puede leer el agente con Claude:**

- **Con la skill:** su directorio de trabajo y la copia de la skill, sin `evals/` (`--add-dir`).
- **Sin la skill:** solo su directorio vacío.

`Read`, `Glob` y `Grep` no van en `--allowedTools`, porque ahí permiten cualquier ruta. Con esa libertad, la corrida sin
la skill leía las copias instaladas de la skill, con sus `evals/`: los cachés de plugins y el clon del marketplace
(#93). Cada lectura que Claude rechaza suma en `usage.permission_denials`, con la skill y en `baseline.usage` sin
ella. Con `--repeat`, cada elemento de `run_results` trae su propio `usage`.

Con Codex, `codex exec --sandbox read-only` puede leer todo el disco: ahí la baseline no tiene este aislamiento.
