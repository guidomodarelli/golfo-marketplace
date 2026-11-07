# Profiles, manifest, lockfile y ownership

Fuente única del contrato de adopción versionada de agent-ready-setup. Leer
cuando el usuario pida `plan` o `status`, cuando un apply reporte conflictos o
assets retirados, al elegir profiles o al explicar qué versión de las reglas usa
un repositorio. La implementación vive en `scripts/agent-ready-state.py`.

## Contenido

1. Profiles
2. Detección
3. Profile packs
4. Configuración y actualizaciones
5. Manifest y lockfile
6. Ownership
7. Operaciones: status, plan, check y apply
8. SessionStart y modo review
9. Providers y capacidades
10. Límites conocidos

## 1. Profiles

`assets/profiles.json` es el catálogo. Cada profile declara:

| Campo | Significado |
|---|---|
| `kind` | `stack` (aporta el template de `AGENTS.md` y sus rules) o `capability` |
| `assets` | árbol de templates del profile, relativo a la skill; opcional |
| `requires` | profiles que se agregan antes, en orden |
| `conflicts` | profiles incompatibles; seleccionarlos juntos es error |
| `tools` | herramientas que el apply instala o registra (`browser`) |
| `detect` | señales estáticas para detectar el profile; opcional (ver «Detección») |

`assets/common/` es la base: siempre se proyecta. La selección necesita al
menos un profile `stack`; el primero es el **stack primario**, del que sale el
template de `AGENTS.md`. Con un solo profile con assets se proyecta su
directorio tal cual; con varios, `resolve` los compone en
`${XDG_CACHE_HOME:-~/.cache}/agent-ready-setup/compose/` y la proyección,
la normalización y el bloque gestionado leen ese árbol (variable
`AGENT_READY_SETUP_STACK_DIR`). Si dos profiles (o un profile y la base)
publican el mismo destino, la resolución falla **antes de escribir** y nombra
los dos profiles: hoy las stacks comparten nombres (`rules/security.md`,
`agents/perf-analyzer.md`), así que no se combinan entre sí.

`--stack <s>` sigue funcionando como alias de `stackDefaults[s]` (la stack más
`browser`, salvo `android`, porque una app nativa no usa esas herramientas: para una
que prueba un `WebView`, usar `--profiles android,browser`). Un profile nuevo que extiende una stack (por ejemplo, testing
específico de una plataforma) declara `requires: ["<stack>"]` y publica solo
assets con nombres propios; no copia los de la stack.

`business-flows` es una capability sin `requires`, porque un mismo modelo de flujos
sirve para web y para apps nativas: se combina con cualquier stack
(`--profiles android,business-flows`) y no se selecciona por detección. Lo específico
de un motor interno de flujos no va en estos assets, que son públicos: va en una
rule del proyecto bajo `.agents/rules/`.

## 2. Detección

El campo opcional `detect` de un profile declara señales estáticas. Un profile sin
`detect` sigue disponible para selección manual, como `business-flows`, que no tiene una
señal útil. `scripts/agent_ready_detection.py` es el único evaluador, y lo comparten los
subcomandos `detect`, `resolve` y `plan` de `agent-ready-state.py`.

La evaluación solo lee archivos del proyecto: no ejecuta builds, gestores de paquetes ni
nada que nombre un catálogo. No entra a directorios enlazados y un archivo que resuelve
fuera del proyecto no cuenta. Tampoco lee archivos de más de 2 MiB. Un `package.json`
inválido o un archivo que no se puede leer se informa como aviso y no aporta señales.

```json
"detect": {
  "supersedes": ["java"],
  "signals": [
    { "type": "glob", "patterns": ["*/src/main/AndroidManifest.xml"] },
    { "type": "gradle-plugin", "ids": ["com.android.application"] }
  ]
}
```

| `type` | Lista | Coincide cuando |
|---|---|---|
| `file` | `paths` | existe ese archivo, relativo a la raíz, sin comodines |
| `glob` | `patterns` | un archivo coincide por segmentos con `*`, `?` y `[...]`, o con `**` como segmento completo (hasta 8 niveles). Los comodines no entran a `node_modules`, `vendor`, `build`, `dist`, `target`, `out`, `.git`, `.gradle`, `.idea`, `.next`, `.venv`, `venv`, `__pycache__`, `.agents`, `.claude` ni `.codex` |
| `package-dependency` | `names` | el `package.json` raíz declara el nombre en `dependencies`, `devDependencies`, `peerDependencies` u `optionalDependencies` |
| `gradle-plugin` | `ids` | un script de Gradle o el version catalog declara el plugin |
| `gradle-dependency` | `coordinates` | un script de Gradle o el version catalog declara `grupo:artefacto` |

Alcanza con una señal. Las rutas distinguen mayúsculas en todos los sistemas y deben
quedar dentro del proyecto; un `detect` inválido hace fallar la carga del catálogo.

**Gradle.** Se leen como texto y sin comentarios `build.gradle`, `build.gradle.kts`,
`settings.gradle` y `settings.gradle.kts` de la raíz, y `build.gradle` y `build.gradle.kts`
hasta dos niveles de módulos, más `gradle/libs.versions.toml`. Nunca se ejecuta el build
ni se interpreta Groovy o Kotlin.

| Dónde | Formatos reconocidos |
|---|---|
| Plugin en un script | `id 'x'`, `id "x"`, `id("x")`, con `version` o `apply false` detrás; `apply plugin: 'x'`, `apply(plugin = "x")` |
| Plugin en el catalog (`[plugins]`) | `alias = { id = "x", ... }`, `alias = "x:versión"` |
| Dependencia en un script | notación de string con cualquier configuración: `implementation 'g:a:1.0'`, `api("g:a")` |
| Dependencia en el catalog (`[libraries]`) | `alias = "g:a:versión"`, `{ module = "g:a" }`, `{ group = "g", name = "a" }` |

No se reconocen `kotlin("android")`, plugins aplicados por `buildSrc`, convention plugins
o `apply from:`, valores en variables, la notación de mapa `group: 'g', name: 'a'` ni un
`alias(libs...)` sin catalog en esa ruta. Como es una lectura de texto, un string con ese
formato cuenta aunque no se use.

**Precedencia de la selección.**

1. `--profiles` o `--stack`.
2. `profiles` de `.agents/agent-ready.json`.
3. Detección inicial, solo sin manifest: el stack primario se expande con `stackDefaults`,
   y el apply lo guarda en el manifest.

`detection: off` apaga la detección y las sugerencias (ver «Configuración y actualizaciones»).
Una detección posterior nunca cambia el manifest. `plan` informa la selección (`Selected
by`), las señales y, si apuntan a otro stack, un aviso. Para cambiar la selección hay que
pedirlo con `--stack` o `--profiles`.

**Stack primario.** Detectar varias señales no aplica varios stacks. `supersedes` declara
qué stacks reemplaza uno cuando coinciden juntos, y solo se usa donde uno es una
especialización del otro:

| Coincidencias | Primario | Motivo |
|---|---|---|
| `frontend` + `node` | `frontend` | un proyecto React también tiene `package.json` |
| `frontend` + `android` | `frontend` | el directorio `android/` de React Native o Capacitor es un host generado |
| `android` + `java` | `android` | una app Android también tiene Gradle |
| cualquier otra, por ejemplo `node` + `go` | ninguno | nada dice cuál es el principal: se listan las coincidencias y se pide una selección explícita |

Si queda un solo stack después de quitar los reemplazados, es el primario. Si quedan
varios, `detect` sale con 3, y `resolve`, `plan` y un apply sin selección fallan antes de
escribir; el hook avisa y omite la proyección. Un ciclo en `supersedes` invalida el
catálogo, y el resultado no depende del orden de los archivos ni del catálogo.

**Sugerencias.** Una capability con `detect` que coincide y falta en la selección se
sugiere en `plan`, con el profile, el archivo inspeccionado y la señal. No entra al
manifest ni instala herramientas, tampoco en una detección inicial, y `stackDefaults` no
cambia: `--stack android` sigue sin `browser` aunque `plan` lo sugiera por
`androidx.webkit:webkit`. No se sugiere una capability incompatible con la selección.

`detect` no forma parte del digest de un profile en el lockfile, porque no cambia lo que
se proyecta: ajustar una señal no marca un update pendiente en repos ya aplicados.

## 3. Profile packs

Una empresa mantiene sus profiles en un repositorio propio y los reutiliza con versiones
fijadas. `scripts/agent_ready_packs.py` carga los packs y `examples/acme-profile-pack/` es un
pack mínimo de ejemplo. No hay stacks primarios externos, profiles por carpeta, distribución por
npm ni instaladores propios de un pack.

**Fuentes.** `.agents/agent-ready.json` las declara en `profileSources`:

```json
{
  "profiles": ["node", "acme/kafka-interno"],
  "profileSources": [
    { "name": "acme", "source": "git+https://github.com/acme/agent-profiles", "ref": "main" },
    { "name": "seguridad", "source": "git+ssh://git@github.com/acme/security-profiles#<commit-completo>" },
    { "name": "local", "source": "path:./agent-packs/local", "updates": "pinned" }
  ]
}
```

| Forma | Significado |
|---|---|
| `git+https://…#<commit-completo>`, `git+ssh://…#<commit-completo>` | revisión fija: nunca se mueve |
| `git+https://…` con `"ref": "<rama-o-tag>"` (o `#<rama-o-tag>` en la URL) | se resuelve a un commit, que el lock registra; en `auto` sigue a la `ref`, en `pinned` espera una actualización explícita |
| `path:<ruta relativa>` | carpeta local, relativa a la raíz del repo consumidor |

Las credenciales no van en el manifest, el lockfile ni los logs: una URL con usuario de HTTPS,
contraseña o query se rechaza, y Git usa la autenticación ya configurada, sin prompts. Una ruta
absoluta se rechaza porque no existiría en otra máquina. Agregar una fuente hace disponibles sus
profiles, pero no selecciona ninguno ni proyecta sus assets.

**Pack.** Tiene `agent-ready-pack.json` en la raíz, con `schemaVersion`, `name` y `profiles`. `name`
debe ser igual al de la fuente en el manifest, porque los profiles se referencian por él. Cada
profile acepta `kind`, `description`, `assets`, `requires`, `conflicts`, `tools` y `detect`, con el
significado de la sección 1, y estos límites:

- `kind` es siempre `capability`. Un profile que necesita un stack lo declara en `requires`.
- `tools` solo acepta herramientas que el motor ya conoce (`browser`).
- Un pack no declara `stackDefaults`, `baseAssets` ni otras fuentes, ni redefine un profile de
  Golfo. Los assets compartidos van en un profile propio, como `acme/base`, que los demás requieren.
- `assets` publica solo `rules/`, `skills/`, `agents/` y `commands/`. No puede traer hooks, settings,
  el template de `AGENTS.md` ni archivos `AGENTS.md` o `CLAUDE.md`.
- Las rules de un pack entran en la lista del bloque gestionado de `AGENTS.md`, como las de cualquier
  profile. Un pack no cambia el template ni las instrucciones propias del proyecto.

| Referencia | Significado |
|---|---|
| `node` | profile de Golfo |
| `acme/kafka-interno` | profile de la fuente `acme` |
| `otra-fuente/base` | profile de otra fuente declarada en el manifest; un pack no trae fuentes por su cuenta |

**Validación antes de escribir.** Al resolver se validan el schema, las dependencias, los ciclos, los
conflictos y los nombres de fuente duplicados. También se rechazan estas colisiones de destino:
entre un pack y Golfo, entre dos packs, entre profiles de un mismo pack, en los destinos que generan
los adaptadores (`agents/x.md` y `commands/x.md` producen el mismo `.agents/skills/x/SKILL.md`) y entre
paths que solo difieren en mayúsculas. El namespace no evita una colisión de archivos. Los assets deben
quedar dentro del pack, sin symlinks, y un destino no puede pasar por un directorio enlazado del
proyecto. Cualquiera de estos errores frena el apply antes de modificar el repositorio.

**Lockfile.** `profileSources` registra por fuente `type`, `origin`, `requestedRef`, `resolvedCommit`
(`null` en una ruta), `catalogDigest`, `contentDigest` (assets de los profiles seleccionados) y
`profiles`. Cada asset guarda su propietario en `profile` y su origen en `source`
(`acme:profiles/kafka-interno/rules/acme-kafka.md`), con su `sha256` y `state`. El resultado es
determinista, sin timestamps ni rutas de la máquina. Un repo sin fuentes no suma ningún campo. `detect`
sí cuenta en `catalogDigest`, pero no en el digest de cada profile. El commit y el digest identifican el
contenido; la confianza en sus instrucciones sigue dependiendo de la fuente y de quien la revisa.

**Actualizaciones.** Un apply descarga lo que falta en
`${XDG_CACHE_HOME:-~/.cache}/agent-ready-setup/packs/`. Necesita resolver todas las fuentes declaradas,
también las que no tienen profiles seleccionados: si una falla, frena antes de escribir. Cada actualización
deja un diff revisable de assets y lockfile, y sigue el ownership de la sección 6. Cada repo tiene su lock;
dos repos con el mismo pack pueden usar revisiones distintas. Cómo se actualiza cada fuente: sección 4.

**Rutas locales.** El digest se calcula sobre el contenido real de la carpeta, incluidos cambios sin
commitear, porque el `HEAD` no identifica un árbol modificado. `plan` y `status` muestran el drift, un
apply de `bootstrap.sh` lo adopta y un sync también, salvo con `updates: pinned`. Si la ruta falta, un apply falla sin
escribir y `plan` informa la evaluación incompleta. Una carpeta externa sirve para desarrollo, pero su
digest no garantiza que pueda reconstruirse en otro entorno. Para consumo compartido, usar Git fijado o
un pack versionado dentro del propio repo.

**Modos de consulta.** `--plan`, `--status` y `AGENT_READY_SETUP_REVIEW_MODE=1` no escriben en el repo. Si
falta una fuente que la selección necesita, informan `Evaluation incomplete` y `plan` sale con 5: ese
resultado no es un plan validado. Una fuente sin profiles seleccionados que no está disponible no frena la
evaluación, pero sus sugerencias no aparecen. Cargar un catálogo o evaluar su `detect` nunca ejecuta nada
del pack. Qué refrescan y cuándo: sección 4.

## 4. Configuración y actualizaciones

Cada mecanismo es opcional y se configura por separado. Sin configurar nada, todo funciona con estos
defaults, igual en un proyecto personal y en uno de empresa. Una variable de entorno gana sobre el
manifest y sirve para una máquina o un job de CI; nunca se escribe en el manifest.

El manifest es disperso: el apply solo escribe lo que difiere del default (también `providers`), así un
default que mejora llega a todos los repos. Los defaults viven en `scripts/agent_ready_defaults.py`.

| Mecanismo | Campo del manifest | Variable | Default | Para apagarlo o cambiarlo |
|---|---|---|---|---|
| Detección y sugerencias | `detection`: `on`, `off` | `AGENT_READY_SETUP_DETECTION` | `on` | `off`: `plan` no muestra señales ni sugerencias, y un repo sin manifest pide `--stack` o `--profiles` |
| Profile packs | `profileSources` | — | sin fuentes | no declarar ninguna |
| Actualizaciones | `updates`: `auto`, `pinned` | `AGENT_READY_SETUP_UPDATES` | `auto` | `pinned`: nada se aplica solo. También por fuente, con `updates` en `profileSources[]` |
| Refresco en `plan` y `status` | `refresh`: `on`, `off` | `AGENT_READY_SETUP_REFRESH` | `on` | `off`, o `--offline` en una corrida |
| Chequeo de CI | `ci`: `fail`, `warn`, `off` | `AGENT_READY_SETUP_CI` | `fail` | `warn` o `off`. Solo corre si el repo agrega el job |

**`updates: auto`.** Los assets se mantienen al día solos, sin bloquear nada. El hook de SessionStart
informa el resultado de la actualización anterior y lanza la siguiente desacoplada con
`scripts/run-detached.py`: refresca el snapshot de `golfo-marketplace`, resuelve la `ref` de cada fuente
en `auto` a su último commit y aplica con el gate de ownership y el lock de concurrencia de siempre. El
cambio queda sin commitear en el árbol, para revisarlo y commitearlo. El lockfile sigue registrando el
commit resuelto y sus digests, así cada resultado es reproducible y auditable. Lo que cambió, o el error,
se informa una vez en la sesión siguiente. Tras tres fallas seguidas, el próximo intento espera una hora.
En una máquina sin ninguna fuente de la skill, el primer upgrade del marketplace es sincrónico porque no
hay scripts para desacoplarlo.

**`updates: pinned`.** Nada se aplica solo: el hook informa drift y updates pendientes, sin escribir en el
repo. Con `refresh: on`, la tarea desacoplada solo refresca la caché, para que la sesión siguiente pueda
avisar. Se adopta con `bash "$SKILL_DIR/scripts/bootstrap.sh" … --update-source <fuente>` o editando la
revisión del manifest. Un apply de `bootstrap.sh` es siempre explícito: sigue las fuentes en `auto`, adopta
el drift de las rutas locales y deja el resto en la revisión del lock.

Se puede combinar por fuente. Un repo en `auto` puede fijar una fuente con `"updates": "pinned"`, y entonces
un cambio de esa fuente frena el sync sin escribir nada. Un repo `pinned` puede seguir una fuente con
`"updates": "auto"`, pero un apply proyecta toda la selección: si golfo-kit tiene una versión pendiente, el
sync no actualiza el pack solo y espera una adopción explícita de ambos.

`AGENT_READY_SETUP_SYNC_FOREGROUND=1`, o `--stack` y `--profiles` en el hook, corren la sincronización en
primer plano. `AGENT_READY_SETUP_REVIEW_MODE=1` nunca actualiza, nunca usa la red y nunca escribe.

**Seguridad.** Seguir una `ref` en `auto` significa que quien pushee al pack cambia las instrucciones del
agente en todos los repos consumidores en su próxima sesión. El diff del lockfile y el chequeo de CI son el
control. Si eso no alcanza para una fuente, fijarla con un commit completo o con `"updates": "pinned"`.
Credenciales y ejecución de scripts del pack no cambian: nunca entran al manifest, al lock ni a los logs, y
ningún script de un pack se ejecuta.

**Refresco.** `--plan` y `--status` actualizan por defecto la caché fuera del repo (snapshot del marketplace
y última revisión de cada `ref`) para decir si todo está al día, sin escribir en el repo. `--offline`,
`refresh: off` y el modo review no tocan la red: comparan con lo que ya hay. Si el refresco falla, lo avisan
y comparan con la caché. Si aun así falta una fuente necesaria, informan `Evaluation incomplete`.

**Chequeo de CI.** `scripts/agent-ready-state.py check` compara las fuentes, el lock y los assets commiteados, y
sale con códigos documentados según `ci`. Sirve en cualquier proveedor de CI y esta skill no crea workflows.
Comando, códigos de salida, autenticación y ejemplos: [ci-check.md](ci-check.md).

## 5. Manifest y lockfile

| Archivo | Quién lo edita | Contenido |
|---|---|---|
| `.agents/agent-ready.json` | personas (versionado) | `profiles` elegidos, `updates`, `providers`, `profileSources`, `ci`, `refresh`, `detection` (sección 4) |
| `.agents/agent-ready.lock.json` | solo el apply | source resuelto, profiles con digest, fuentes de packs, inventario de assets, archivos fusionados |

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

## 6. Ownership

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

## 7. Operaciones

```bash
bash "$SKILL_DIR/scripts/bootstrap.sh" --skill-dir "$SKILL_DIR" --provider "$PROVIDER" --status
bash "$SKILL_DIR/scripts/bootstrap.sh" --skill-dir "$SKILL_DIR" --provider "$PROVIDER" --plan
bash "$SKILL_DIR/scripts/bootstrap.sh" --skill-dir "$SKILL_DIR" --provider "$PROVIDER" [--profiles a,b] [--updates pinned|auto]
```

- `--status` y `--plan` no escriben en el repo ni instalan herramientas. Antes de
  comparar refrescan la caché y el snapshot del marketplace. Con `--offline` o
  `refresh: off` comparan contra lo ya disponible y no llaman a la CLI del provider.
- `agent-ready-state.py check` compara para CI, y su código de salida sigue a `ci` (sección 4).
- `status` separa assets aplicados, modificados, faltantes, conflictos
  preservados, escrituras fallidas y retirados que no se pudieron borrar; además dice si el
  source resuelto o la selección de profiles difieren del lock (`Update
  available`). También cuenta como faltante una vista `.claude/` o un archivo fusionado que se borró; su
  contenido gestionado lo revisa `plan`. `agent-ready-state.py
  status --check` sale con 4 si hay drift o si la selección no se puede resolver.
- `plan` muestra de dónde salió la selección, las señales detectadas y las capabilities
  sugeridas con su evidencia (ver «Detección»). Lista cada destino con su acción,
  profile y motivo, los diffs (local →
  template), los archivos fusionados que cambiarían, los `CLAUDE.md` que se
  normalizarían, los efectos fuera de los assets con su alcance (`user`,
  `user-cache`, `project`, `repository-config`) y los requisitos con su
  disponibilidad.
- Sin `--status` ni `--plan`, bootstrap aplica: upgrade del marketplace,
  proyección con el gate de ownership, retirada, lockfile y manifest. Sin
  `--profiles` ni `--stack` usa los profiles del manifest y, si no hay manifest, la
  detección inicial. Aplicar dos veces el mismo plan no cambia nada.
- `python3 scripts/agent-ready-state.py detect --project . --skill-dir "$SKILL_DIR"`
  muestra la detección sola. Sale con 0 si determina un stack primario y con 3 si no.

Preferir aplicar actualizaciones como un cambio revisable: correr el apply en
una rama y abrir un PR con el diff de `.agents/`, `.claude/` y el lockfile.

## 8. SessionStart y modo review

El hook `.agents/hooks/sync-marketplace.sh` nunca hace esperar a la sesión. Lee el manifest e informa el
resultado de la actualización anterior:

- `updates: auto` o sin manifest: lanza desacoplada la sincronización (sección 4).
- `updates: pinned`: corre `status --brief` y no escribe nada en el repositorio, ni siquiera se
  autoactualiza. Con `refresh: on`, refresca la caché desacoplado, para que la sesión siguiente avise.
- `AGENT_READY_SETUP_REVIEW_MODE=1`: nunca escribe, aunque el manifest diga `auto`, y tampoco refresca el
  marketplace ni llama a la CLI del provider. No se activa sola en CI: definirla en el entorno de reviews
  automatizadas; ver [review-consumption.md](review-consumption.md).
- Un manifest que no se puede leer frena el sync antes de escribir, porque podría declarar un repositorio
  `pinned`.

`--updates` en bootstrap cambia el modo del manifest de forma explícita.

## 9. Providers y capacidades

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

## 10. Límites conocidos

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
