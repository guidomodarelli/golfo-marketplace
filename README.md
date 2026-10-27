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

## 🤖 Agent Ready multi-provider

`plugins/golfo-kit/skills/agent-ready-setup` prepara siempre los tres planos sin acoplar assets compartidos a un provider:

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

Después de `marketplace upgrade`, la actualización global no reproyecta assets sobre proyectos ya preparados. La ejecución directa de `agent-ready-setup` y el hook canónico `.agents/hooks/sync-marketplace.sh` seleccionan la versión cacheada semver más nueva y actualizan los assets gestionados bajo `.claude/`, `.agents/` y `.codex/`; ambos providers usan el mismo comportamiento con sus caches respectivas. La proyección recorre `assets/common/` y `assets/stacks/<stack>/`, incluyendo rules, agents, commands, skills, MCP y hooks; los hooks permanecen canónicos bajo `.agents/hooks/`, mientras `.claude/` recibe symlinks para assets no-hook. El hook normaliza instrucciones mediante `bootstrap.sh --normalize-only` cuando la versión instalada lo soporta y ejecuta el merge semántico de `AGENTS.md`. La normalización ocurre desde la raíz Git e incluye `.claude/CLAUDE.md`; conflictos, symlinks y destinos inseguros se preservan y reportan. Muestra diffs, aplica templates sobre archivos regulares modificados y conserva su versión local en un directorio temporal externo al proyecto; output muestra path exacto para revisión o diff. También combina el template con los settings JSON y preserva sus campos custom. El merge IA de `AGENTS.md` conserva cambios compatibles; si falla o queda sin resolución, aplica template y guarda backup temporal. `CLAUDE.md` nunca se modifica directamente por el merge IA.

El flujo manual y `SessionStart` usan el hook sin flags de confirmación. La resolución IA trata documentos como datos no confiables, aplica cambios compatibles automáticamente y usa fallback template + backup ante salida inválida o conflicto irresoluble. `CLAUDE.md` permanece como proxy.

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
fuera del spec o difiere en versión del manifest de Claude, o si alguna `skills/*/SKILL.md` tiene
un `name` distinto de su directorio o una `description` vacía o de más de 1024 caracteres.

---

## 🧪 Correr tests shell localmente

Las suites shell usan [bats-core](https://github.com/bats-core/bats-core) con versión y dependencias fijadas en `pnpm-lock.yaml`. Requieren Node.js 24 (versión exacta en `.nvmrc`) y pnpm 12 (fijado en `packageManager`). `pnpm-workspace.yaml` activa `shellEmulator`, así los scripts con sintaxis POSIX (`VAR=valor comando`) corren igual en Windows.

```bash
# Instalación reproducible
pnpm install --frozen-lockfile

# Preparación explícita de tests browser (Python 3.11+, instala tomlkit en venv local)
pnpm run setup:browser-tests

# Suites aisladas: Agent Ready, create-version y contrato del eval runner
pnpm run test
```

`pnpm run test:review-fix-loop` corre solo la suite del helper de `review-fix-loop`, que usa
providers falsos y no llama a Claude ni a Codex reales.
`pnpm run test:sibling-worktree` corre la suite del helper de `sibling-worktree` sobre repos git
temporales.
`pnpm run test:skill-coverage` corre con `node --test` la suite del motor de cobertura incremental de
skills (`plugins/golfo-kit/tools/skill-coverage/`) sobre repos git temporales; usa `@babel/parser`
de las devDependencies para el análisis por símbolos.
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
La excepción es `pnpm run test:bootstrap` (parte de `test:shell`), con 120 segundos por test: sus
tests corren bootstrap y sync completos varias veces, y en Windows algunos tardan más de un minuto.
Las suites bats corren con `LC_ALL=C.UTF-8`: el shell de `pnpm run` no pasa la configuración
regional, y sin UTF-8 bats no ejecuta los tests cuyo nombre lleva tildes.
Un test que se cuelga falla con `timeout` en vez de bloquear la corrida. Para cambiar el límite en las
suites bash, exportá `TEST_TIMEOUT_SECONDS`.

### Qué suite correr según el cambio

`pnpm run test` completo tarda cerca de una hora en Windows, porque `bootstrap.bats` corre sus
128 tests en serie y cada uno ejecuta bootstrap y sync completos. Durante una tarea, corré solo
lo que cubre el cambio y dejá la suite completa a la CI:

| Cambio | Comando local |
|---|---|
| Solo rules `.md` bajo `assets/**/rules/` o el template de `AGENTS.md` | `pnpm exec bats plugins/golfo-kit/skills/agent-ready-setup/tests/merge-instructions.bats` y `pnpm exec bats --filter 'rules' plugins/golfo-kit/skills/agent-ready-setup/tests/bootstrap.bats` |
| Un flujo puntual de `agent-ready-setup` | `pnpm exec bats --filter '<parte del nombre del test>' plugins/golfo-kit/skills/agent-ready-setup/tests/bootstrap.bats` |
| Scripts compartidos de `agent-ready-setup` (`scripts/*.sh`, `sync-marketplace.sh`) | `pnpm run test:bootstrap` completo |
| `review-fix-loop`, `sibling-worktree`, `create-version`, `check-version-bump`, `validate-portable-plugins` o el eval runner | Su suite (`pnpm run test:review-fix-loop`, `pnpm run test:sibling-worktree`, `pnpm exec bats tests/create-version.bats tests/check-version-bump.bats tests/validate-portable-plugins.bats`, `pnpm exec bats skill-eval-runner/tests/*.bats`) |
| Motor de cobertura de skills (`plugins/golfo-kit/tools/skill-coverage/**`) | `pnpm run test:skill-coverage` |
| `user-manual`: navegación de `DESIGN.md`, `scripts/check-*`, `build-manual.mjs` o `assets/` | `pnpm run test:user-manual` (con Playwright para la suite de navegador) y, si se tocó la paleta, `pnpm exec bats plugins/golfo-kit/skills/user-manual/tests/check-design-tokens.bats` |
| Frontmatter de una skill o `plugin.json` de un plugin | `pnpm validate-portable-plugins` |

Anteponé `LC_ALL=C.UTF-8` a cada `bats` (ver más abajo). En Windows, `bats --jobs` no funciona:
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

# Comparar contra una corrida sin skill (opcional; no se evalúa y duplica llamadas)
run-evals plugins/<plugin-name>/skills/<skill-name> --baseline

# Override persistente de proveedor
export GOLFO_MARKETPLACE_EVAL_PROVIDER=codex
```
