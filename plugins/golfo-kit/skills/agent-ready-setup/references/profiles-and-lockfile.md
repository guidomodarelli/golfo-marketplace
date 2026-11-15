# Manifest, lockfile y ownership

Fuente única del contrato de adopción versionada de agent-ready-setup. Leer
cuando el usuario pida `plan` o `status`, cuando un apply reporte conflictos o
assets retirados, o al explicar qué versión de las reglas usa un repositorio.
La implementación vive en `scripts/agent-ready-state.py` y los `scripts/agent_ready_*.py`.

El contrato sigue en estas referencias:

- [profiles.md](profiles.md): qué declara un profile, capas, defaults, bundles y workspaces.
- [detection.md](detection.md): la selección sin manifest, las señales y el stack primario.
- [profile-packs.md](profile-packs.md): fuentes de profiles de otros repositorios o carpetas.
- [updates.md](updates.md): los modos de actualización, el contenido, el refresco y el chequeo de CI.

## Contenido

1. Manifest y lockfile
2. Ownership
3. Operaciones: status, plan, check, apply, doctor y remove
4. SessionStart y modo review
5. Providers y capacidades
6. Límites conocidos

## 1. Manifest y lockfile

| Archivo | Quién lo edita | Contenido |
|---|---|---|
| `.agents/agent-ready.json` | personas (versionado) | `profiles` elegidos y lo que difiere de los defaults (capa de proyecto de [configuration.md](configuration.md)) |
| `.agents/agent-ready.lock.json` | solo el apply | source resuelto, profiles con digest, fuentes de packs, inventario de assets, archivos fusionados |

El lockfile registra `source.name` (`golfo`), `source.version` (versión del contenido),
`source.kind` (`git`, o `local` con el override de desarrollo), `source.revision` (commit del pack de
contenido), `source.origin` (repositorio del que se puede volver a descargar), `source.requestedRef` (la ref de
la que vino) y `source.contentDigest`,
que identifica el contenido exacto (assets, templates fusionados y plantillas de
instrucciones) aunque no haya revisión git. `generator.version` es la versión del
motor que proyectó. Cada fuente de `profileSources` guarda además su `version`, si el
catálogo la declara. Por asset guarda `profile`,
`source`, `sha256` aplicado y `state` (`applied`, `conflict`, `failed`,
`retired-preserved`), más `viewPreserved` cuando un archivo del proyecto ocupa su
vista `.claude/`. `merged` lista `AGENTS.md` (bloque gestionado),
`.claude/settings.json` y `.codex/hooks.json` con el sha256 del template: se
fusionan con contenido del proyecto, así que no se comparan con una base. `blocks`
guarda, por archivo y por id, el `profile`, el `source`, el `sha256` y el `state` de cada
bloque gestionado de un archivo compartido ([managed-agents-block.md](managed-agents-block.md),
sección «Bloques en otros archivos»), también de cada `AGENTS.md` anidado
([nested-instructions.md](nested-instructions.md)). El JSON es
determinista (sin timestamps ni paths de la máquina): la misma resolución
produce los mismos bytes. `workspaces` registra, por carpeta, los `profiles` que elige el manifest y los
que suma a la raíz (`own`), [profiles.md](profiles.md), «Workspaces».

**Apply reproducible.** `agent-ready apply --from-lock` aplica exactamente el lock, en otra máquina o un año
después, sin importar `updates.mode` ni las `ref` del manifest:

- Toma la selección del lock y la revisión del contenido y de cada pack que registra, aunque el manifest declare
  ahora otra `ref` (el origen tiene que ser el mismo). Las descarga en la caché del usuario si faltan; con
  `--dry-run` y `updates.refresh: false` no descarga nada y falla si falta una revisión.
- Antes de escribir compara byte a byte: la selección, las revisiones, el digest de cada pack, el sha256 de cada
  asset, y el template y los textos con que se arma el bloque gestionado de `AGENTS.md`
  (`merged["AGENTS.md"].inputsSha256`). Si algo no coincide, falla sin escribir y nombra la fuente
  (`golfo`, un pack o `selection`) y el archivo.
- `merge-instructions.sh` arma `AGENTS.md` desde el stack que compuso el apply (la línea
  `Resolved stack directory:` de `bootstrap.sh`, en `AGENT_READY_SETUP_STACK_DIR`), así nunca toma una revisión
  más nueva de un pack que esté en la caché.
- Los archivos del motor (los hooks y los templates de `.claude/settings.json` y `.codex/hooks.json`) siguen al
  plugin instalado, porque el motor nunca se fija: `--from-lock` los proyecta del motor y dice cuántos difieren
  del lock.
- No acepta `--profiles`, `--stack` ni `--updates`, y `--dry-run` muestra el plan con la misma verificación.
- Un apply de un repositorio `pinned` ya proyecta las revisiones del lock. `--from-lock` agrega la verificación
  y rechaza cualquier cambio de selección, así que es explícito: sumar un profile en `pinned` sigue siendo un
  apply normal.
- Con `updates.fromLock: true` (lo enciende `updates.preset: delivered`), cada apply o plan que no actualiza
  ninguna fuente ni pasa `--profiles`, `--stack` o `--updates` corre como `--from-lock`, una vez que hay
  lockfile. La guía completa para una solución entregada: [stable-delivery.md](stable-delivery.md).

No confundir con `.agents/.agent-ready-assets.lock` (lock de concurrencia del
sync) ni con el hash de revisión de instrucciones bajo `.git/`. Fijar la
configuración de un MCP remoto no fija el comportamiento del servicio.

## 2. Ownership

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

## 3. Operaciones

```bash
python3 "$SKILL_DIR/scripts/agent-ready" status [--offline] [--json]
python3 "$SKILL_DIR/scripts/agent-ready" plan [--offline] [--json]
python3 "$SKILL_DIR/scripts/agent-ready" apply [--profiles a,b] [--updates pinned|auto] [--recheck] [--dry-run]
python3 "$SKILL_DIR/scripts/agent-ready" apply --from-lock [--dry-run]
python3 "$SKILL_DIR/scripts/agent-ready" update [<fuente>...] [--to <ref>] [--dry-run]
python3 "$SKILL_DIR/scripts/agent-ready" doctor [--offline] [--json]
python3 "$SKILL_DIR/scripts/agent-ready" remove [--dry-run] [--yes] [--json]
```

- `status` y `plan` no escriben en el repo ni instalan herramientas. Antes de
  comparar refrescan la caché y el snapshot del marketplace. Con `--offline` o
  `updates.refresh: false` comparan contra lo ya disponible y no llaman a la CLI del provider.
- `agent-ready check` compara para CI, y su código de salida sigue a `ci.mode` ([updates.md](updates.md)).
- `agent-ready config explain` muestra la configuración efectiva y la capa de cada valor.
- `update` sin fuentes adopta la última revisión de cada fuente Git que sigue una `ref` y del contenido (también
  fijado, ver [updates.md](updates.md), «El contenido»); `--to <ref>` elige la revisión de una sola fuente;
  con `--dry-run` muestra el plan de esa adopción y solo descarga en la caché del usuario.
- `status` separa assets aplicados, modificados, faltantes, conflictos
  preservados, escrituras fallidas y retirados que no se pudieron borrar; además dice si el
  source resuelto o la selección de profiles difieren del lock (`Update
  available`). También cuenta como faltante una vista `.claude/` o un archivo fusionado que se borró; su
  contenido gestionado lo revisa `plan`. Al final muestra los hallazgos conocidos de las revisiones de IA,
  leídos de la caché sin llamar al provider ([ai-reviews.md](ai-reviews.md)). `agent-ready-state.py
  status --check` sale con 4 si hay drift o si la selección no se puede resolver.
- `plan` muestra de dónde salió la selección, la configuración efectiva con su origen, las señales detectadas y las capabilities
  sugeridas con su evidencia (ver [detection.md](detection.md)). Lista cada destino con su acción,
  profile y motivo, los diffs (local →
  template), los archivos fusionados que cambiarían, los `CLAUDE.md` que se
  normalizarían, los efectos fuera de los assets con su alcance (`user`,
  `user-cache`, `project`, `repository-config`) y los requisitos con su
  disponibilidad.
- `apply` corre `bootstrap.sh`: upgrade del marketplace, proyección con el gate de ownership,
  retirada, lockfile y manifest; después alinea el bloque gestionado de `AGENTS.md` con
  `merge-instructions.sh`, que con `--recheck` revisa `AGENTS.md` aunque la caché tenga su revisión.
  Sin `--profiles` ni `--stack` usa los profiles del manifest y, si no hay manifest, la detección inicial. Aplicar dos veces el mismo plan no cambia nada.
- `python3 scripts/agent-ready-state.py detect --project . --skill-dir "$SKILL_DIR"`
  muestra la detección sola. Sale con 0 si determina un stack primario y con 3 si no.
- `doctor` solo lee. Revisa Git y el worktree, Bash, el Python que corre y el `python3` que usan
  los hooks (3.8 o más nuevo), la CLI de los providers que declara el repo (alcanza con una), la
  versión de golfo-kit, cada capa de configuración, cada fuente de packs (un path que exista, un
  repositorio que responda a `git ls-remote`; `--offline` no contacta ninguno), el motor que piden el
  contenido y cada pack que esta máquina tiene (`minEngine` y `schemaVersion`, «Compatibilidad
  declarada» en [profile-packs.md](profile-packs.md); sin red usa solo la caché) y, si el repo ya
  tiene lockfile, los hooks que el apply fusiona en `.claude/settings.json` y `.codex/hooks.json`
  junto con sus scripts. Imprime una línea por chequeo y, debajo de lo que falta, `fix:` con el
  arreglo. Sale con 1 si falta algo y con 0 si no. Funciona también fuera de un repositorio, donde
  avisa que falta el worktree.
- `remove` saca agent-ready-setup del repo. Lee solo el lockfile y los archivos, no la
  configuración, así que funciona con un manifest inválido. `--dry-run` lista cada path con su
  acción (`remove`, `edit` o `keep`) y su motivo, sin escribir nada:

  | Qué | Qué hace `remove` |
  |---|---|
  | asset gestionado igual a la base del lock | lo borra, y también las carpetas que quedan vacías |
  | asset gestionado editado después del último apply | lo conserva y lo informa: borrarlo perdería el cambio |
  | archivo del proyecto, rule propia de `.agents/rules/`, asset que no es un archivo regular o con un padre symlink | lo conserva |
  | vista `.claude/` de un path de `.agents/` (symlink, hard link o copia con el contenido aplicado) | la borra, también las de rules propias |
  | `AGENTS.md` | borra el bloque gestionado; si no queda más que el template, borra el archivo y su proxy `CLAUDE.md` |
  | proxy `CLAUDE.md` de un `AGENTS.md` que queda | lo conserva: es lo que hace que Claude Code cargue ese `AGENTS.md` |
  | `.claude/settings.json` y `.codex/hooks.json` | quita los hooks y permisos del template; si no queda nada, borra el archivo |
  | servidores MCP del browser en `.mcp.json` y `.codex/config.toml` | los quita con `unregister-browser-servers.py` (Python 3.11+) y conserva los del proyecto |
  | hook `post-index-change` de las vistas hard link y su lista | los borra del checkout |
  | caché de las revisiones de IA (`.git/info/agent-ready/reviews.json`) | la borra |
  | decisiones sobre los hallazgos (`.agents/agent-ready.reviews.json`) | las conserva: son del equipo |
  | manifest y lockfile | los borra al final, así una corrida interrumpida se puede repetir |

  Pide confirmación solo con terminal; sin terminal, con `CI` o con `--no-input` necesita `--yes` y
  sin él sale con 2 sin tocar nada. Después de confirmar toma el lock de la sincronización
  (`.agents/.agent-ready-assets.lock`) y el de la revisión de `AGENTS.md`
  (`.agents/.agent-ready-instructions.lock`), y vuelve a armar el plan: si un apply, el hook de
  sesión o la revisión en segundo plano tienen uno, sale con 1 sin tocar nada. Como `merge-instructions.sh`,
  solo toma como marcadores del bloque las líneas completas; si no son un único par, conserva
  `AGENTS.md`. El hook de git, su configuración y la caché de revisiones son de todos los worktrees del
  repositorio: quedan mientras otro worktree tenga lockfile. Nunca cambia un archivo a través de un directorio que es un
  symlink (por ejemplo, `.claude` apuntando a `~/.claude`): lo conserva. Un archivo que cambió entre
  el plan y la escritura se conserva. Sale con 1 si algo no se pudo quitar y lo nombra; si es un
  asset o una vista, el lockfile y el manifest quedan para que la siguiente corrida termine.
  Correrlo dos veces no cambia nada más.

Preferir aplicar actualizaciones como un cambio revisable: correr el apply en
una rama y abrir un PR con el diff de `.agents/`, `.claude/` y el lockfile.

## 4. SessionStart y modo review

El hook `.agents/hooks/sync-marketplace.sh` nunca hace esperar a la sesión. Valida la configuración efectiva e
informa el resultado de la actualización anterior:

- `updates.mode: auto` (default): lanza desacoplada la sincronización ([updates.md](updates.md)).
- `updates.mode: pinned`: corre `status --brief` y no escribe nada en el repositorio, ni siquiera se
  autoactualiza. Con `updates.refresh` encendido, refresca la caché desacoplado, para que la sesión siguiente avise.
- `updates.enabled: false`: no hace nada más que decirlo.
- `AGENT_READY_SETUP_REVIEW_MODE=1`: nunca escribe, aunque el manifest diga `auto`, y tampoco refresca el
  marketplace ni llama a la CLI del provider. No se activa sola en CI: definirla en el entorno de reviews
  automatizadas; ver [review-consumption.md](review-consumption.md).
- Una configuración que no se puede leer o validar, en cualquier capa, frena el sync antes de escribir, porque
  podría declarar un repositorio `pinned`.

`--updates` en bootstrap cambia el modo del manifest de forma explícita.

## 5. Providers y capacidades

`assets/providers.json` declara qué soporta cada provider y cómo se adapta cada
tipo de asset; `status` lo imprime. En Codex, `agents/` y `commands/` son
adapters de skill en `.agents/skills/`, no subagentes ni comandos nativos, y
las rules llegan por la lista del bloque gestionado de `AGENTS.md`.

El hook de consistencia (`check-harness-consistency.sh`) revisa con la CLI del
provider que editó, así que un entorno solo-Codex no necesita el binario de Claude.
Qué revisa y cómo usa la caché: [ai-reviews.md](ai-reviews.md).

Las herramientas de browser se instalan y registran solo si un profile
seleccionado declara `tools: ["browser"]`; `tools.enabled: false` (o
`AGENT_READY_SETUP_TOOLS=0` en una corrida) las omite igual.

## 6. Límites conocidos

- Los skills, subagentes y comandos de un profile que suma un workspace valen para todo el repositorio:
  los providers no los acotan por carpeta («Workspaces», en [profiles.md](profiles.md)).
- En Windows sin symlinks, o con `core.symlinks=false`, las vistas son hard links y
  `relink-hard-link-views.sh` las reenlaza en cada prompt y en cada escritura del
  índice, para recuperar las que git separa cuando recrea el asset. Sin historial
  por vista no distingue ese caso de una edición guardada como archivo nuevo en la
  vista, que se pierde ahí. Para cambiar comportamiento, usar una rule propia.
- Si el lock no tiene una revisión del contenido que se pueda descargar (el override de
  desarrollo), un asset faltante se recrea desde el contenido local en el próximo apply, no
  desde la versión del lock: el apply es un cambio explícito y revisable, y el lock pasa a
  registrar la versión nueva. `status` avisa antes si el source difiere del lock, y
  `--from-lock` falla en vez de proyectar otro contenido.
- `--from-lock` reproduce el contenido, no el motor: en otra versión del plugin, los
  hooks y los templates de settings que los conectan pueden diferir del lock.
- Las rules y la skill de browser siguen en la base del contenido porque otras rules
  comunes las enlazan; el profile `browser` controla solo la instalación.
