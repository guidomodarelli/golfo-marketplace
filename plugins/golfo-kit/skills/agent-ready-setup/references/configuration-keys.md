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
| `security.trustedProjects` | lista de string; se une entre capas | `[]` | organization, user | — | — | Raíces de los repositorios que esta máquina aprobó para aflojar desde su manifest. Se agregan con agent-ready-state.py trust y se unen entre capas. |

Presets:

- `security.preset: off` → `security.enabled: false`, `updates.mode: auto`
- `security.preset: standard` → `security.enabled: true`, `updates.mode: auto`
- `security.preset: strict` → `security.enabled: true`, `updates.mode: pinned`

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
| `updates.refresh` | boolean | `true` | todas | `AGENT_READY_SETUP_REFRESH` | — | plan, status y el inicio de sesión de un repositorio pinned refrescan la caché fuera del repositorio para decir si todo está al día. Apagado, comparan con lo que ya hay, como --offline. |

`locked` es una lista de claves (o namespaces enteros) que solo declara la organización.
