<!-- Generado por `scripts/agent-ready-state.py config-reference` desde `assets/config/*.schema.json`. No editar a mano. -->

# Claves de configuración

Referencia generada desde los schemas de `assets/config/`. Capas, precedencia, aprobación de la máquina,
`locked` y presets: [configuration.md](configuration.md).

Columnas: **Capas** dice desde dónde se puede declarar la clave; **Variable** la pisa en una corrida;
**Seguridad** ordena los valores de la más floja a la más estricta, y aflojar desde el proyecto requiere
la aprobación de la máquina.

## Raíz del manifest: Selección del repositorio

Qué profiles y providers usa el repositorio. No es una funcionalidad que se apague: solo la declara el proyecto.

| Clave | Tipo | Default | Capas | Variable | Seguridad | Descripción |
|---|---|---|---|---|---|---|
| `profiles` | lista de string | — | project | — | — | Profiles elegidos, en orden; el primero de tipo stack aporta el template de AGENTS.md. Sin valor, la detección inicial elige y el apply lo guarda. |
| `providers` | lista de string (`claude`, `codex`) | `["claude", "codex"]` | project | — | — | Providers para los que el repositorio declara su configuración; el lockfile los registra. |

## `ci`: Chequeo de CI

agent-ready-state.py check compara las fuentes, el lockfile y los assets commiteados; corre en cualquier proveedor de CI.

| Clave | Tipo | Default | Capas | Variable | Seguridad | Descripción |
|---|---|---|---|---|---|---|
| `ci.enabled` | boolean | `true` | todas | — | — | Apagado, el chequeo no compara nada, no usa la red y sale con 0. |
| `ci.mode` | `fail` \| `warn` | `"fail"` | todas | `AGENT_READY_SETUP_CI` | — | fail sale con el código de cada resultado; warn informa lo mismo y sale con 0. |

## `conflicts`: Conflictos semánticos

Revisión de IA de las rules gestionadas contra las propias del proyecto y su AGENTS.md, en las dos direcciones. Solo informa: nunca borra ni reescribe.

| Clave | Tipo | Default | Capas | Variable | Seguridad | Descripción |
|---|---|---|---|---|---|---|
| `conflicts.enabled` | boolean | `true` | todas | — | — | plan y el apply revisan con IA una rule gestionada nueva o cambiada contra las rules propias y el AGENTS.md del proyecto, y una rule propia contra las gestionadas. Usa la caché y las decisiones de las revisiones de IA. Apagado, no se revisa. También se apaga con reviews.enabled: false. |
| `conflicts.block` | boolean | `false` | todas | — | `false` < `true` | Un apply que trae un conflicto semántico con lo propio del proyecto, o que no pudo revisarlo, se frena antes de escribir. Apagado, el conflicto solo se informa. |

## `detection`: Detección

Señales estáticas del proyecto que eligen el stack primario de un repositorio sin selección y sugieren capabilities en plan.

| Clave | Tipo | Default | Capas | Variable | Seguridad | Descripción |
|---|---|---|---|---|---|---|
| `detection.enabled` | boolean | `true` | todas | `AGENT_READY_SETUP_DETECTION` | — | Apagada, plan no muestra señales ni sugerencias y un repositorio sin selección pide --stack o --profiles. |

## `reviews`: Revisiones de IA

Caché de las revisiones de IA: la de AGENTS.md contra sus rules y la de consistencia entre rules y skills al editarlas.

| Clave | Tipo | Default | Capas | Variable | Seguridad | Descripción |
|---|---|---|---|---|---|---|
| `reviews.enabled` | boolean | `true` | todas | — | — | Las revisiones de IA: la de AGENTS.md, que borra líneas redundantes fuera del bloque gestionado, y la de consistencia de las rules y skills que se editan. Apagado, el apply copia el bloque gestionado sin revisar y el hook no llama al provider. Los hooks lo toman del último apply. |
| `reviews.cache` | boolean | `true` | todas | — | — | Guarda el resultado de cada revisión por unidad (AGENTS.md contra sus rules, o un par de rules o skills) en el directorio info de Git, fuera del repositorio. Una edición solo vuelve a revisar las unidades donde participa, y status muestra los hallazgos sin llamar al provider. Apagado, cada revisión llama al provider. Los hooks lo toman del último apply. |
| `reviews.ttl` | integer | — | todas | — | — | Horas que vale una revisión guardada; pasado ese tiempo se revisa de nuevo aunque nada haya cambiado. Sin valor, no vence. |
| `reviews.commit` | boolean | `false` | todas | — | — | Además de la caché local, guarda cada resultado en .agents/agent-ready.review-cache.json para commitearlo, así el CI y el equipo saltean las revisiones cuyo hash coincide sin pagarlas de nuevo. Cualquiera puede editar un archivo versionado: un resultado de ahí solo evita repetir una revisión idéntica y nunca oculta un hallazgo que la caché local conoce. Los hooks lo toman del último apply. |

## `security`: Seguridad

Qué puede aflojar el manifest de un repositorio. Endurecer siempre se aplica; aflojar desde el proyecto requiere que la máquina haya aprobado el repositorio.

| Clave | Tipo | Default | Capas | Variable | Seguridad | Descripción |
|---|---|---|---|---|---|---|
| `security.enabled` | boolean | `true` | todas | — | `false` < `true` | Exige la aprobación de la máquina para que el proyecto afloje una clave sensible. Apagado, el proyecto afloja sin aprobación. |
| `security.preset` | `off` \| `standard` \| `strict` | `"standard"` | todas | — | `off` < `standard` < `strict` | Conjunto de valores con una sola clave: standard (los defaults), strict (además, updates.mode pinned) u off (sin exigir aprobación). Cualquier clave se puede pisar en la misma capa o en una superior; off desde el proyecto cuenta como aflojar. |
| `security.execution.enabled` | boolean | `true` | todas | — | `true` < `false` | Las herramientas de un pack que pasan la política se instalan, registran y corren en un apply. Apagado, ningún pack ejecuta nada; sus rules y skills se proyectan igual. |
| `security.execution.events` | lista de string (`install`, `post-apply`, `session-start`) | `["install", "post-apply"]` | todas | — | sumar valores afloja | Eventos en los que puede correr un script de un pack: install, post-apply o session-start. session-start corre en cada inicio de sesión, por eso está apagado por defecto. |
| `security.execution.ci` | boolean | `false` | todas | — | `true` < `false` | En integración continua (CI definida) las herramientas de un pack solo se instalan, registran y corren si un workflow lo pide con su propia configuración. |
| `security.checks.trustedSource` | boolean | `true` | todas | — | `false` < `true` | La fuente del pack tiene que ser de confianza en esta máquina (agent-ready trust add <fuente>). Una fuente path:, que vive en el repositorio, es de confianza si el repositorio está aprobado. |
| `security.checks.signature` | boolean | `false` | todas | — | `false` < `true` | El commit de la fuente, o un tag de su origen que apunte a ese commit, tiene que tener una firma SSH válida de una clave de security.signers para esa fuente. Una fuente path:, sin revisión propia, no pasa. Apagado por defecto: un pack personal sin firmas funciona igual. |
| `security.checks.artifactSha256` | boolean | `true` | todas | — | `false` < `true` | Cada artefacto de un CLI declara su sha256 y se verifica al descargarlo. Un paquete de npm, pip, brew o winget sin sha256 no se instala. |
| `security.checks.lockDigest` | boolean | `true` | todas | — | `false` < `true` | Lo que se ejecuta coincide con el digest que registra el lock para esa herramienta. |
| `security.allow.clis` | lista de string | `[]` | todas | — | vaciar o ampliar una lista no vacía afloja | Nombres de CLIs que un pack puede instalar. |
| `security.allow.commands` | lista de string | `[]` | todas | — | vaciar o ampliar una lista no vacía afloja | Comandos que puede lanzar un servidor MCP de un pack. |
| `security.allow.scripts` | lista de string | `[]` | todas | — | vaciar o ampliar una lista no vacía afloja | Scripts que pueden correr, como <fuente>/<ruta en el pack>. |
| `security.allow.mcpServers` | lista de string | `[]` | todas | — | vaciar o ampliar una lista no vacía afloja | Nombres de servidores MCP que un pack puede registrar. |
| `security.deny.commands` | lista de string; se une entre capas | `[]` | todas | — | — | CLIs o comandos de servidores MCP que no se instalan ni se lanzan. |
| `security.deny.scripts` | lista de string; se une entre capas | `[]` | todas | — | — | Scripts que no corren, como <fuente>/<ruta en el pack>. |
| `security.rules` | lista de objetos; se une entre capas | `[]` | todas | — | sumar una regla allow afloja | Restricciones propias: cada regla elige herramientas por fuente, profile, tipo, patrón de nombre o texto del script, y las permite o las prohíbe. Una regla deny gana sobre una allow; ninguna saltea las verificaciones de checks ni las listas deny. |
| `security.trustedSources` | lista de string; se une entre capas | `[]` | todas | — | sumar valores afloja | Orígenes de las fuentes de packs en las que esta máquina confía para ejecutar sus herramientas. Se agregan con agent-ready trust add <fuente> y agent-ready sources add; se unen entre capas, y sumarlos desde el proyecto afloja. |
| `security.signers` | lista de objetos; se une entre capas | `[]` | todas | — | sumar valores afloja | Claves públicas SSH con las que firman los mantenedores de una fuente, para security.checks.signature. Se agregan con agent-ready trust add <fuente> --signer <archivo .pub>; se unen entre capas, y sumarlas desde el proyecto afloja. |
| `security.trustedProjects` | lista de string; se une entre capas | `[]` | organization, user | — | — | Raíces de los repositorios que esta máquina aprobó para aflojar desde su manifest. Se agregan con agent-ready-state.py trust y se unen entre capas. |

Presets:

- `security.preset: off` → `security.enabled: false`, `updates.mode: auto`
- `security.preset: standard` → `security.enabled: true`, `updates.mode: auto`
- `security.preset: strict` → `security.enabled: true`, `updates.mode: pinned`

Campos de cada elemento de `security.rules`:

- `match` (object, obligatorio): Qué herramientas elige; vacío elige todas.
- `action` (`allow` | `deny`, obligatorio): allow o deny.
Campos de cada elemento de `security.signers`:

- `key` (string, obligatorio): La clave pública SSH en una línea, como la de un archivo .pub: tipo, clave en base64 y un comentario opcional.
- `source` (string, opcional): Fuentes que firma esta clave (glob sobre el nombre de la fuente); sin source, todas.

## `sources`: Profile packs

Fuentes de profiles: golfo-kit, packs en Git y carpetas locales del repositorio.

| Clave | Tipo | Default | Capas | Variable | Seguridad | Descripción |
|---|---|---|---|---|---|---|
| `sources.enabled` | boolean | `true` | todas | — | `true` < `false` | Apagado, los packs declarados no se descargan ni se leen, y seleccionar un profile de un pack falla. Encenderlo desde el proyecto cuando otra capa lo apagó afloja la seguridad. |
| `sources.packs` | lista de objetos | `[]` | project | — | — | Packs disponibles para seleccionar sus profiles por nombre con namespace (acme/kafka-interno). Declararlos no selecciona ninguno. |
| `sources.golfoKit.ref` | string | — | todas | — | — | Rama, tag o commit completo del marketplace a seguir en auto o a adoptar con agent-ready update golfo-kit. Sin valor, la versión del plugin instalado. |
| `sources.golfoKit.updates` | `auto` \| `pinned` | — | todas | — | — | Modo de actualización de golfo-kit; pisa updates.mode del repositorio. |

Campos de cada elemento de `sources.packs`:

- `name` (string, obligatorio): Namespace de sus profiles; igual al name del catálogo del pack, en kebab-case.
- `source` (string, obligatorio): git+https://..., git+ssh://... o path:<ruta relativa a la raíz del repositorio>.
- `ref` (string, opcional): Rama o tag a seguir de una fuente Git, si la URL no trae #<revisión>.
- `updates` (`auto` | `pinned`, opcional): Modo de actualización de esta fuente; pisa updates.mode del repositorio.

## `tools`: Herramientas

Herramientas que declaran los profiles seleccionados (hoy browser) y que el apply instala y registra fuera de los assets.

| Clave | Tipo | Default | Capas | Variable | Seguridad | Descripción |
|---|---|---|---|---|---|---|
| `tools.enabled` | boolean | `true` | todas | `AGENT_READY_SETUP_TOOLS` | `true` < `false` | Apagado, el apply y el inicio de sesión proyectan los assets sin instalar ni registrar herramientas. Encenderlo desde el proyecto cuando otra capa lo apagó afloja la seguridad. |

## `updates`: Actualizaciones

Cómo se mantienen al día los assets: la actualización en segundo plano del inicio de sesión y el refresco de plan y status.

| Clave | Tipo | Default | Capas | Variable | Seguridad | Descripción |
|---|---|---|---|---|---|---|
| `updates.enabled` | boolean | `true` | todas | — | — | El inicio de sesión busca actualizaciones en segundo plano e informa el resultado. Apagado, SessionStart no actualiza, no chequea ni refresca nada, y solo un apply explícito cambia los assets. |
| `updates.mode` | `auto` \| `pinned` | `"auto"` | todas | `AGENT_READY_SETUP_UPDATES` | `auto` < `pinned` | auto aplica las actualizaciones solo, sin bloquear la sesión; pinned solo informa drift y updates pendientes, sin escribir. Seguir una ref en auto deja que quien pushee al pack cambie las instrucciones del agente. |
| `updates.refresh` | boolean | `true` | todas | `AGENT_READY_SETUP_REFRESH` | — | plan, status y el inicio de sesión de un repositorio pinned refrescan la caché fuera del repositorio para decir si todo está al día. Apagado, comparan con lo que ya hay, como --offline. Una actualización explícita (agent-ready update, también con --dry-run) siempre resuelve la revisión que pide. |
| `updates.preset` | `none` \| `delivered` | `"none"` | todas | — | `none` < `delivered` | Conjunto de valores con una sola clave: none (los defaults) o delivered, para una solución entregada a un cliente que no cambia hasta que alguien decide actualizarla: updates.mode pinned, golfo-kit pinned, updates.refresh apagado, updates.fromLock encendido y ci.mode fail. Cualquier clave se puede pisar en la misma capa o en una superior. |
| `updates.fromLock` | boolean | `false` | todas | — | `false` < `true` | Un apply o un plan que no actualiza ninguna fuente ni cambia la selección reproduce el lock, como --from-lock: misma selección, misma revisión de cada fuente y mismos sha256, o falla antes de escribir. Para adoptar una versión nueva se usa agent-ready update; para cambiar la selección, --profiles o --stack. Sin lockfile, el primer apply resuelve como siempre. |

Presets:

- `updates.preset: none` → sin cambios
- `updates.preset: delivered` → `updates.mode: pinned`, `sources.golfoKit.updates: pinned`, `updates.refresh: false`, `updates.fromLock: true`, `ci.mode: fail`

`locked` es una lista de claves (o namespaces enteros) que solo declara la organización.
