# Profiles, manifest, lockfile y ownership

Fuente única del contrato de adopción versionada de agent-ready-setup. Leer
cuando el usuario pida `plan` o `status`, cuando un apply reporte conflictos o
assets retirados, al elegir profiles o al explicar qué versión de las reglas usa
un repositorio. La implementación vive en `scripts/agent-ready-state.py`.

## Contenido

1. Profiles
2. Manifest y lockfile
3. Ownership
4. Operaciones: status, plan y apply
5. SessionStart y modo review
6. Providers y capacidades
7. Límites conocidos

## 1. Profiles

`assets/profiles.json` es el catálogo. Cada profile declara:

| Campo | Significado |
|---|---|
| `kind` | `stack` (aporta el template de `AGENTS.md` y sus rules) o `capability` |
| `assets` | árbol de templates del profile, relativo a la skill; opcional |
| `requires` | profiles que se agregan antes, en orden |
| `conflicts` | profiles incompatibles; seleccionarlos juntos es error |
| `tools` | herramientas que el apply instala o registra (`browser`) |

`assets/common/` es la base: siempre se proyecta. La selección necesita al
menos un profile `stack`; el primero es el **stack primario**, del que sale el
template de `AGENTS.md`. Con un solo profile con assets se proyecta su
directorio tal cual; con varios, `resolve` los compone en
`${XDG_CACHE_HOME:-~/.cache}/agent-ready-setup/compose/` y la proyección,
la normalización y el bloque gestionado leen ese árbol (variable
`AGENT_READY_SETUP_STACK_DIR`). Si dos profiles (o un profile y la base)
publican el mismo destino, la resolución falla **antes de escribir** y nombra
los dos profiles: hoy las cuatro stacks comparten nombres (`rules/security.md`,
`agents/perf-analyzer.md`), así que no se combinan entre sí.

`--stack <s>` sigue funcionando como alias de `stackDefaults[s]` (la stack más
`browser`). Un profile nuevo que extiende una stack (por ejemplo, testing
específico de una plataforma) declara `requires: ["<stack>"]` y publica solo
assets con nombres propios; no copia los de la stack.

## 2. Manifest y lockfile

| Archivo | Quién lo edita | Contenido |
|---|---|---|
| `.agents/agent-ready.json` | personas (versionado) | `profiles` elegidos, `updates` (`pinned` por defecto o `auto`), `providers` |
| `.agents/agent-ready.lock.json` | solo el apply | source resuelto, profiles con digest, inventario de assets, archivos fusionados |

El lockfile registra `source.plugin`, `source.version`, `source.kind`
(`marketplace-snapshot`, `plugin-cache` o `local`), `source.revision` (commit
git del source cuando existe) y `source.contentDigest`, que identifica el
contenido exacto (assets, templates fusionados y plantillas de instrucciones)
aunque no haya revisión git. Por asset guarda `profile`,
`source`, `sha256` aplicado y `state` (`applied`, `conflict`, `failed`,
`retired-preserved`), más `viewPreserved` cuando un archivo del proyecto ocupa su
vista `.claude/`. `merged` lista `AGENTS.md` (bloque gestionado),
`.claude/settings.json` y `.codex/hooks.json` con el sha256 del template: se
fusionan con contenido del proyecto, así que no se comparan con una base. El JSON es
determinista (sin timestamps ni paths de la máquina): la misma resolución
produce los mismos bytes.

No confundir con `.agents/.agent-ready-assets.lock` (lock de concurrencia del
sync) ni con el hash de revisión de instrucciones bajo `.git/`. Fijar la
configuración de un MCP remoto no fija el comportamiento del servicio.

## 3. Ownership

Nadie debería editar un asset gestionado: cada apply lo deja igual al template y
pisa cualquier cambio local. Un destino es gestionado cuando el lock registra que
un apply lo escribió. Para cada destino se comparan la base del lock, el archivo
local y el template nuevo:

| Situación | Acción |
|---|---|
| no existe localmente | `create` |
| igual al template | `unchanged` |
| igual a la base del lock | `update` |
| distinto de la base (editado o reemplazado por symlink) | `update`: pisa el cambio local; el link se reemplaza sin seguirlo |
| existe pero el lock nunca lo aplicó | `conflict`: es del proyecto y se preserva; renombrarlo o borrarlo para recibir el asset |
| no es un archivo regular (por ejemplo, un directorio) | `conflict`: se preserva y se reporta |
| no hay lockfile todavía | `adopt`: el primer apply sobrescribe una vez (contrato anterior) |
| la vista `.claude/` de un asset gestionado quedó como archivo regular, con contenido distinto del asset, la base y el template | `update`: se vuelve a enlazar y pisa ese contenido |
| un archivo del proyecto ocupa un path donde ningún apply creó la vista | `conflict`: se preserva hasta que se renombre o se borre |
| ya no lo publica ningún profile y el lock registra su base | `retire`: se borra junto con su vista `.claude/`, aunque se haya editado |
| ya no lo publica ningún profile y el lock nunca lo aplicó | `drop`: queda como archivo del proyecto y sale del lock |
| ya no lo publica ningún profile y no es un archivo regular | `retire-conflict`: se conserva como `retired-preserved` |
| ya no lo publica ningún profile y un directorio padre es un symlink | `retire-conflict`: se conserva como `retired-preserved`, porque borrarlo tocaría archivos fuera del proyecto |

Los hashes normalizan CRLF a LF: un checkout con `core.autocrlf` (el default de
Git en Windows) no cuenta como edición local, el apply no reescribe un archivo
cuya única diferencia son los fines de línea y el lockfile da los mismos bytes en
cualquier sistema.

Sobrescribir no pide confirmación. `plan` muestra antes qué cambios locales se
pisarían, con su motivo y su diff. El hook guarda una copia de cada archivo que
reemplaza en un directorio temporal e imprime la ruta; `bootstrap.sh` solo muestra
el diff, y un asset retirado no deja copia. Commitear antes lo que se quiera conservar.

Un conflicto nunca se reporta como éxito completo: el apply termina con `Lockfile: ... (applied with N
preserved conflict(s))` o `(partial: ...)` si alguna escritura falló.
Para cambiar comportamiento, el proyecto agrega una rule propia bajo
`.agents/rules/` o una skill nueva en vez de editar un asset gestionado.

## 4. Operaciones

```bash
bash "$SKILL_DIR/scripts/bootstrap.sh" --skill-dir "$SKILL_DIR" --provider "$PROVIDER" --status
bash "$SKILL_DIR/scripts/bootstrap.sh" --skill-dir "$SKILL_DIR" --provider "$PROVIDER" --plan
bash "$SKILL_DIR/scripts/bootstrap.sh" --skill-dir "$SKILL_DIR" --provider "$PROVIDER" [--profiles a,b] [--updates pinned|auto]
```

- `--status` y `--plan` no escriben archivos, no hacen upgrade del marketplace,
  no instalan herramientas y no llaman a la CLI del provider. Por eso comparan
  contra el source ya disponible: una versión publicada después del último
  upgrade (SessionStart o un apply) recién aparece cuando se refresca el snapshot.
- `status` separa assets aplicados, modificados, faltantes, conflictos
  preservados, escrituras fallidas y retirados que no se pudieron borrar; además dice si el
  source resuelto o la selección de profiles difieren del lock (`Update
  available`). También cuenta como faltante una vista `.claude/` o un archivo fusionado que se borró; su
  contenido gestionado lo revisa `plan`. `agent-ready-state.py
  status --check` sale con 4 si hay drift o si la selección no se puede resolver.
- `plan` lista cada destino con su acción, profile y motivo, los diffs (local →
  template), los archivos fusionados que cambiarían, los `CLAUDE.md` que se
  normalizarían, los efectos fuera de los assets con su alcance (`user`,
  `user-cache`, `project`, `repository-config`) y los requisitos con su
  disponibilidad.
- Sin `--status` ni `--plan`, bootstrap aplica: upgrade del marketplace,
  proyección con el gate de ownership, retirada, lockfile y manifest. Sin
  `--profiles` ni `--stack` usa los profiles del manifest. Aplicar dos veces el
  mismo plan no cambia nada.

Preferir aplicar actualizaciones como un cambio revisable: correr el apply en
una rama y abrir un PR con el diff de `.agents/`, `.claude/` y el lockfile.

## 5. SessionStart y modo review

El hook `.agents/hooks/sync-marketplace.sh` lee el manifest:

- `updates: pinned` (default): no escribe nada en el repositorio, ni siquiera
  se autoactualiza. Sí refresca, como máximo una vez por hora, el snapshot del
  marketplace del usuario (fuera del repo) y después corre `status --brief`, que
  compara ese snapshot con el lock e informa drift y updates pendientes.
- `updates: auto`: aplica con el mismo gate de ownership que bootstrap, así que
  pisa los cambios locales al iniciar sesión.
- Sin manifest (repos legacy): aplica una vez y deja manifest y lockfile.
- `AGENT_READY_SETUP_REVIEW_MODE=1`: nunca escribe, aunque el manifest diga
  `auto`, y tampoco refresca el marketplace ni llama a la CLI del provider. No se
  activa sola en CI: definirla en el entorno de reviews automatizadas; ver
  [review-consumption.md](review-consumption.md).
- Un manifest que no se puede leer frena el sync antes de escribir, porque podría
  declarar un repositorio `pinned`.

`AGENT_READY_SETUP_UPDATES=pinned|auto` define el modo cuando el apply crea el
manifest; `--updates` en bootstrap lo cambia de forma explícita.

## 6. Providers y capacidades

`assets/providers.json` declara qué soporta cada provider y cómo se adapta cada
tipo de asset; `status` lo imprime. En Codex, `agents/` y `commands/` son
adapters de skill en `.agents/skills/`, no subagentes ni comandos nativos, y
las rules llegan por la lista del bloque gestionado de `AGENTS.md`.

El hook de consistencia (`check-harness-consistency.sh`) revisa con la CLI del
provider que editó: `claude --print` para Claude Code y `codex exec --sandbox
read-only` para Codex (eventos `apply_patch`). Un entorno solo-Codex no
necesita el binario de Claude; si falta la CLI del provider, el check se omite
con un aviso.

Las herramientas de browser se instalan y registran solo si un profile
seleccionado declara `tools: ["browser"]`; `AGENT_READY_SETUP_BROWSER_INSTALL=0`
las omite igual.

## 7. Límites conocidos

- No hay asignación de profiles por ruta en monorepos: un repositorio tiene una
  sola selección.
- En Windows sin symlinks, las vistas son hard links y
  `relink-hard-link-views.sh` las reenlaza en cada prompt y en cada escritura del
  índice, para recuperar las que git separa cuando recrea el asset. Sin historial
  por vista no distingue ese caso de una edición guardada como archivo nuevo en la
  vista, que se pierde ahí. Para cambiar comportamiento, usar una rule propia.
- Un asset faltante se recrea desde el source resuelto en el próximo apply, no
  desde la versión del lock: el apply es un cambio explícito y revisable, y el
  lock pasa a registrar la versión nueva. `status` avisa antes si el source
  difiere del lock.
- Las rules y la skill de browser siguen en `assets/common/` porque otras rules
  comunes las enlazan; el profile `browser` controla solo la instalación.
