---
name: agent-ready-setup
description: >-
  Inspecciona proyecto, detecta stack (frontend, node, java, go) y prepara siempre
  configuración multi-provider para Claude Code, Codex y futuros agentes: genera
  .claude/, .agents/, .codex/, AGENTS.md y proxy CLAUDE.md, sobrescribe siempre
  los assets gestionados con los templates, y mantiene el bloque gestionado de
  AGENTS.md. Usar cuando
  usuario diga "configurar agent ready",
  "setup agent ready", "bootstrap claude", "bootstrap codex", "inicializar
  configuración de agentes", "quiero ser agent ready", "make this repo agent
  ready", o pida pasar Agent Ready Score.
license: MIT
metadata:
  version: "1.5.0"
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
Bootstrap tiene un solo modo, sin flags de confirmación: sincroniza siempre los
assets gestionados con los templates sin preguntar y normaliza instrucciones.

Los assets publicados por agent-ready-setup (rules, skills, agents, commands,
hooks y sus vistas en `.claude/`) se sobrescriben siempre, aunque se
hayan editado: para agregar o cambiar comportamiento, el proyecto crea una rule
propia bajo `.agents/rules/` o una skill nueva. Un symlink en un path gestionado
se reemplaza sin seguirlo. Solo quedan como conflicto los directorios en un path
gestionado y los padres que son symlink. Instrucciones del proyecto
(`AGENTS.md` fuera del bloque gestionado), personalizaciones en `settings.json`
y `.codex/hooks.json` (merge), y assets desconocidos se preservan.

## Compatibilidad entre agentes

La configuración que genera esta skill es para **Claude Code y Codex**; Hermes no es un provider de destino (excepción explícita a la paridad de providers). `resolve-provider.sh` infiere el provider por la ruta de instalación (`~/.claude`, `$CODEX_HOME` o `CLAUDE_PLUGIN_ROOT`). Desde una instalación de Hermes (`$HERMES_HOME`, `~/.hermes` o `%LOCALAPPDATA%\hermes` en Windows, por ejemplo `$HERMES_HOME/plugins/golfo-kit/skills/agent-ready-setup`) usa el único CLI de provider presente en `PATH` (`claude` o `codex`), que es el que hará el upgrade del marketplace y la revisión de instrucciones. Si están los dos, termina con error: preguntá al usuario cuál usar (con `clarify` en Hermes) y relanzá con `AGENT_READY_SETUP_ACTIVE_PROVIDER=claude|codex`, nunca adivinado; si no hay ninguno, reportalo. En todos los casos, informar en `Limitaciones del agente` que no se generó configuración para Hermes. Ver [`agent-capabilities.md`](../../references/agent-capabilities.md) para las rutas de cada agente.

## Step 1 — Locate SKILL_DIR

`SKILL_DIR` es el directorio desde el que se cargó esta skill; no resolver otra fuente
antes del bootstrap. `bootstrap.sh` actualiza el marketplace y resuelve por su cuenta la
fuente más nueva: prioriza el snapshot del marketplace del provider (ver «Sincronización
posterior al upgrade») salvo que el cache provider-specific tenga una versión semver
mayor; `AGENT_READY_SETUP_SKILL_DIR` y un source explícito fuera del cache conservan
prioridad para desarrollo local. Al terminar imprime `Resolved agent-ready-setup source:
<path>`; usar ese path para los scripts y assets posteriores, porque el upgrade puede
reemplazar una fuente versionada y dejar el path anterior inexistente.

## Step 2 — Detect stack

Inspeccionar raíz proyecto. Usar prioridad:

| Archivo presente | Stack |
|---|---|
| `package.json` con `react` en dependencies | `frontend` |
| `package.json` sin React | `node` |
| `pom.xml` o `build.gradle` | `java` |
| `go.mod` | `go` |

```bash
detect_stack() {
  if [[ -f "package.json" ]]; then
    if grep -q '"react"' package.json 2>/dev/null; then
      echo "frontend"
    else
      echo "node"
    fi
  elif [[ -f "pom.xml" || -f "build.gradle" || -f "build.gradle.kts" ]]; then
    echo "java"
  elif [[ -f "go.mod" ]]; then
    echo "go"
  else
    echo ""
  fi
}

STACK=$(detect_stack)
```

Si detección devuelve vacío, informar que stack no pudo determinarse y pedir
uno de: `frontend`, `node`, `java`, `go`.

Si detección tiene éxito, confirmar:

> `Detected stack: **<STACK>**. Running agent-ready-setup — Claude, shared-agent and Codex-compatible managed assets will be overwritten with the templates; project rules, skills, and instructions are preserved.`

## Step 3 — Run bootstrap script

Bootstrap instala browsers automáticamente para ambos providers y todos los stacks.
Leer [references/browser-setup.md](references/browser-setup.md) para requisitos,
registro efectivo MCP, recuperación de fallos y opción offline antes de ejecutarlo.

```bash
PROVIDER="$(bash "$SKILL_DIR/scripts/resolve-provider.sh" --skill-dir "$SKILL_DIR")"
bootstrap_output="$(bash "$SKILL_DIR/scripts/bootstrap.sh" \
  --stack "$STACK" \
  --skill-dir "$SKILL_DIR" \
  --provider "$PROVIDER" 2>&1)"
printf '%s\n' "$bootstrap_output"

# Bootstrap reports the source it resolved after the upgrade; the previous path may be gone.
SKILL_DIR="$(printf '%s\n' "$bootstrap_output" | sed -n 's/^Resolved agent-ready-setup source: //p' | tail -n 1)"
if [[ -z "$SKILL_DIR" ]]; then
  echo "ERROR: bootstrap.sh did not report its resolved source; merge-instructions.sh was not run" >&2
  exit 1
fi
bash "$SKILL_DIR/scripts/merge-instructions.sh" \
  --provider "$PROVIDER" \
  --stack "$STACK" \
  --skill-dir "$SKILL_DIR"
```

`resolve-provider.sh` respeta `AGENT_READY_SETUP_ACTIVE_PROVIDER` cuando vale
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
una vez. Matcher `Write|Edit` admite `apply_patch` como alias. Revisión utiliza
CLI Claude instalada también cuando evento proviene de Codex.
El renderer crea `AGENTS.md` nuevo con el bloque gestionado; en `AGENTS.md`
existente, `merge-instructions.sh` reemplaza ese bloque por copia literal del
template y la IA solo revisa redundancias fuera de él. El provider debe ser
`claude` o `codex`.
Copias bajo `.claude/` de assets gestionados, idénticas o editadas, se
reemplazan por el symlink canónico. Antes de normalizar las
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

El hook `.agents/hooks/sync-marketplace.sh` corre en cada `SessionStart`: actualiza el
marketplace (como máximo una vez por hora; `AGENT_READY_SETUP_FORCE_UPGRADE=1` lo fuerza)
y proyecta assets, normalización y bloque gestionado de forma local y sincrónica; lo que
usa red o un LLM corre en segundo plano. Para sincronizar a mano:
`bash .agents/hooks/sync-marketplace.sh --provider claude|codex`. Leer
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

- **Todos los stacks** (`assets/common/`): `rules/browser-before-user-questions.md`, `rules/database.md`, `rules/environment-readiness.md`, `rules/error-handling.md`, `rules/established-libraries.md`, `rules/language-consistency.md`, `rules/lint-gate.md`, `rules/patterns-we-do-not-use.md`, `rules/root-cause-bug-fixes.md`, `rules/speculative-complexity-approval.md`, `rules/testing-scope.md`, `rules/user-actions-first.md`, `rules/verify-changes.md`, `skills/agent-browser/`, `skills/pr-review-workflow/`, `hooks/sync-marketplace.sh`, `hooks/check-harness-consistency.sh` y `settings.json`.
- **Go, Java y Node:** `rules/coding-style.md`, `rules/security.md`, `rules/testing.md`, `agents/perf-analyzer.md`, `agents/security-scanner.md` y `commands/review-pr.md`.
- **Frontend:** `rules/api-configuration.md`, `rules/api-validation-middleware.md`, `rules/cross-engine.md`, `rules/frontend-style.md`, `rules/hexagonal-architecture.md`, `rules/lodash.md`, `rules/no-unnecessary-mocks.md`, `rules/security.md`, `rules/server-first-data-flow.md`, `rules/testing.md`, `rules/upstream-contracts.md`, `rules/user-facing-feedback.md`, `agents/a11y-reviewer.md`, `agents/lint-reviewer.md`, `agents/perf-analyzer.md`, `agents/security-scanner.md`, `agents/test-reviewer.md`, `commands/review-pr.md`, `skills/api-endpoint/`, `skills/component-creation/`, `skills/karpathy-guidelines/`, `skills/logger/`, `skills/react-act-test-fixes/` y `skills/service/`.

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
