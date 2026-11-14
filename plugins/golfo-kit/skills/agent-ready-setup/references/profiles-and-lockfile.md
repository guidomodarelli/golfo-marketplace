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
7. Operaciones: status, plan, check, apply, doctor y remove
8. SessionStart y modo review
9. Providers y capacidades
10. Límites conocidos

## 1. Profiles

`assets/profiles.json` es el catálogo. Cada profile declara:

| Campo | Significado |
|---|---|
| `kind` | `stack` (aporta sus rules y su sección de `AGENTS.md`), `capability`, `bundle` (solo agrupa otros profiles, ver «Bundles») o `ci` (los archivos de CI de un proveedor, que elige `ci.provider` y nunca la selección; ver [ci-check.md](ci-check.md)) |
| `assets` | árbol de templates del profile, relativo a la skill; opcional |
| `requires` | profiles que se agregan antes, en orden; siempre vienen |
| `defaults` | profiles que trae al elegirlo, después de la selección; el repo puede dejarlos afuera con `excludedDefaults` |
| `conflicts` | profiles incompatibles; seleccionarlos juntos es error |
| `overrides` | assets de otro profile de la selección que este reemplaza a propósito, como `<profile>:<path>` (`software-development:rules/testing-scope.md`, o `react:skills/component-creation` para una skill): se proyecta solo el suyo y `plan` lo muestra (`Overridden: …`). Reemplazar algo que la selección no tiene, o el núcleo (`common`), falla antes de escribir |
| `complements` | skills o herramientas de otros profiles con las que este va junto, como `<profile>:skills/<nombre>`, `<profile>:mcpServers/<nombre>` o `<profile>:clis/<nombre>`: declara que no compiten, y el aviso de herramientas que compiten por la misma capacidad (`provides`) no sale |
| `tools` | herramientas que el apply instala o registra (`browser`) |
| `detect` | señales estáticas para detectar el profile; opcional (ver «Detección») |
| `nested` | destinos anidados: un bloque en el `AGENTS.md` de una carpeta del repo, como `{"app-router": {"candidates": ["app", "src/app"]}}` con el bloque en `nested/app-router.md`; el manifest elige o apaga la carpeta con `nested.targets` ([nested-instructions.md](nested-instructions.md)) |

`assets/common/` es el núcleo: siempre se proyecta, en cualquier repo, y tiene el template neutro de
`AGENTS.md`. Lo de desarrollo (rules de código, el template de PR, `pr-review-workflow` y el esqueleto
de software de `AGENTS.md`) es la capability `software-development`, que cada stack requiere. Un stack
es opcional: un repo sin código (actas, documentación, investigación) elige solo capabilities
(`--profiles business-flows`) y recibe el núcleo con el template neutro. Con stacks, el más específico
es el **stack primario**, el que desempata la detección; sin stack no hay primario y el lock lo
registra como `null`. Con un solo profile con assets se proyecta su
directorio tal cual; con varios, `resolve` los compone en
`${XDG_CACHE_HOME:-~/.cache}/agent-ready-setup/compose/` y la proyección,
la normalización y el bloque gestionado leen ese árbol (variable
`AGENT_READY_SETUP_STACK_DIR`). Si dos profiles (o un profile y la base)
publican el mismo destino, la resolución falla **antes de escribir** y nombra
los dos profiles. Las stacks no chocan entre sí: cada una nombra sus assets con su
prefijo (`rules/node-security.md`, `agents/react-perf-analyzer.md`,
`commands/go-review-pr.md`), así que un monorepo selecciona varias
(`--profiles react,node`). Cada stack suma sus rules, agents, commands y skills, y su
sección de `AGENTS.md` como bloque con id ([managed-agents-block.md](managed-agents-block.md),
«Secciones de los stacks»).

**Workspaces.** En un monorepo, `workspaces` le da a una carpeta su propia selección, al lado de la del
repositorio:

```json
{
  "profiles": ["node"],
  "workspaces": [
    { "path": "apps/web", "profiles": ["nextjs-app-router"] },
    { "path": "services/api", "profiles": ["node"] }
  ]
}
```

- **Resolución:** cada workspace resuelve sus profiles junto con los de la raíz (`requires`, `defaults`,
  `excludedDefaults`), así que un profile suyo que choca con uno de la raíz (`conflicts`) falla como fallaría en
  la raíz. Lo que la raíz ya resuelve vale para todo el repositorio, así que un workspace solo suma los
  profiles que la raíz no tiene; dos workspaces no se afectan entre sí. En el ejemplo, `apps/web` suma `react`, `nextjs` y
  `nextjs-app-router`, y `services/api` no suma nada.
- **Validación:** el plan y el apply frenan antes de escribir si un path no cumple estas condiciones:
  - es una carpeta que existe;
  - es relativa y está dentro del repositorio;
  - no está bajo `.git/`, `.agents/`, `.claude/` o `.codex/`;
  - no se llega por un symlink;
  - Git no la ignora;
  - no aparece dos veces ni está dentro de otro workspace.

  Un profile de un workspace que no resuelve, o uno de CI (los elige `ci.provider`), también frena el
  plan, y el error nombra el workspace.
- **Lectura:** `agent-ready plan` muestra una línea por workspace con lo que suma
  (`Workspace apps/web: nextjs-app-router (adds react, nextjs, nextjs-app-router to the root selection)`), y
  `--json` deja la lista en `workspaces`.
- **Lock y drift:** el lock registra en `workspaces` la selección y lo que suma cada uno, y
  `apply --from-lock` falla si un workspace del manifest no es el del lock. `status` muestra
  los workspaces del manifest y marca como drift el que el último apply no adoptó o el que salió del
  manifest; `agent-ready check` lo cuenta como un problema del CI.
- **Rules del workspace:** cada rule de un profile que suma el workspace va a
  `.agents/rules/workspaces/<path>/`, con su vista en `.claude/rules/workspaces/<path>/`.
  - **`paths:`:** la rule lleva `paths:` limitado a la carpeta, así que Claude Code la carga solo al leer,
    escribir o editar un archivo de ahí. Una rule sin frontmatter recibe `paths: ["<path>/**"]`. Una que
    ya tenía `paths:` conserva sus patrones, dentro del workspace. El resto del frontmatter, como
    `assumes:`, queda igual.
  - **Cuándo falla:** dos profiles del mismo workspace que publican la misma rule fallan antes de escribir.
    Dos workspaces no chocan, porque el destino incluye la carpeta. Un profile del workspace solo puede
    hacer `overrides` de los profiles que suma el workspace: reemplazar un asset de la raíz falla, porque
    la raíz lo proyecta para todo el repositorio y el workspace cargaría los dos.
  - **Raíz:** el `AGENTS.md` raíz no lista esas rules. `rules/workspaces/` es una carpeta del motor: una
    rule propia ahí tampoco se lista en la raíz.
  - **`assumes:`:** se compara con la carpeta del workspace, su `package.json` y sus archivos de
    configuración, no con la raíz.
- **`AGENTS.md` del workspace:** `<path>/AGENTS.md` lleva el bloque `agent-ready:workspace`, que lista esas
  rules para Codex.
  - Es un `AGENTS.md` anidado como los de [nested-instructions.md](nested-instructions.md): lleva su
    `CLAUDE.md` con `@AGENTS.md`, el índice para Codex del `AGENTS.md` raíz lo lista, y espera junto a
    un `CLAUDE.md` propio.
  - El contenido propio del archivo, fuera de los bloques, es del proyecto.
- **Retiro:** sacar un workspace del manifest, o un profile de su selección, retira sus rules, sus vistas
  (también las carpetas que quedan vacías) y sus bloques. Un `AGENTS.md` que queda vacío se borra con su
  proxy.
- **Todavía no:** skills, subagentes, comandos, bloques de otros archivos, destinos anidados y la sección de
  `AGENTS.md` de los profiles de un workspace son la parte 64c de #64. La sección queda afuera hasta
  entonces porque nombra comandos y skills que el workspace todavía no proyecta.
- **Fuentes:** un pack que solo elige un workspace cuenta como seleccionado: su digest va al lock y su modo
  `pinned` frena al sync como el de un pack de la raíz.

**Capas.** Un stack puede extender otro con `requires`: la web va en tres capas,
`react` ← `nextjs` ← `nextjs-app-router`. Cada capa publica solo sus propios assets, con
nombres que no repite ninguna otra, y trae por `requires` las capas que extiende:
seleccionar `nextjs-app-router` resuelve `react`, `nextjs` y `nextjs-app-router`, en ese
orden, sin assets duplicados (si dos capas publicaran el mismo destino, la composición
fallaría). Cada capa suma su sección a `AGENTS.md`.

| Capa | Requiere | Qué agrega |
|---|---|---|
| `react` | — | rules de estilo, tests y seguridad de React y TypeScript, los agents de review y `/react-review-pr` |
| `nextjs` | `react` | flujo de datos en el servidor, contratos con upstreams, arquitectura por módulos, endpoints, services y logger |
| `nextjs-app-router` | `nextjs` | dónde empiezan los client components y, en el `AGENTS.md` de `app/` o `src/app/` (destino anidado `nextjs-app-router/app-router`), qué guarda el directorio de rutas y cómo validan los route handlers |

`react` no requiere `node`: las rules de `node` son de servicios backend, y una SPA o una
app Next.js no las necesita. Un repo full stack selecciona las dos (`--profiles nextjs,node`).

**Defaults.** `react`, `node`, `java` y `go` declaran `"defaults": ["browser"]`; `android` no,
porque una app nativa no usa esas herramientas (para una que prueba un `WebView`, usar
`--profiles android,browser`). Una capa hereda los defaults de las que requiere: `nextjs` trae
`browser` por `react`. A diferencia de `requires`, un default se puede dejar afuera:

```json
{ "profiles": ["node"], "excludedDefaults": ["browser"] }
```

`agent-ready config set excludedDefaults browser` lo escribe. Un profile que la selección nombra o
que otro requiere no se puede excluir, y el plan falla antes de escribir. `--stack <s>` es un alias
de `--profiles <s>`: los defaults salen del profile, no de una tabla aparte.

**Manifest y lock.** El manifest guarda lo elegido (`["node"]`, o un bundle) y el lock lo resuelto
(`profileOrder`: `node`, `browser`). Así, un cambio de `defaults` o de un bundle llega a los repos
ya aplicados en el próximo apply, y `plan` muestra qué trajo cada profile (`Profile added: browser
(default of node)`).

**Bundles.** Un profile `kind: bundle` no publica assets, herramientas, detección ni defaults
propios: solo agrupa otros profiles por `requires`, cada uno con sus defaults. Se elige como
cualquier profile, el manifest guarda el bundle y el lock registra lo que resolvió; como no publica
nada, no aparece en el inventario de assets. Un bundle no esconde nada: los `conflicts` y los
destinos repetidos de lo que trae fallan igual que si se eligieran a mano. Los packs pueden publicar
bundles (`acme/backend` en `assets/examples/acme-profile-pack/`).

Un profile nuevo que extiende una stack (por ejemplo, testing
específico de una plataforma) declara `requires: ["<stack>"]` y publica solo
assets con nombres propios; no copia los de la stack. Si es un `stack`, la detección lo
prefiere a la capa que extiende y su sección de `AGENTS.md` se suma a la de ella.

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
3. Detección inicial, solo sin manifest: el apply guarda el stack primario en el manifest, y
   sus `defaults` se resuelven en cada apply. Sin ninguna señal de stack no es un error: el apply
   deja solo el núcleo y guarda `"profiles": []` (lo mismo que `--profiles none`), y `detect` sale
   con 0. Una lista vacía en el manifest también es una selección: una señal posterior no la cambia.

`detection.enabled: false` apaga la detección y las sugerencias ([configuration.md](configuration.md)).
Una detección posterior nunca cambia el manifest. `plan` informa la selección (`Selected
by`), las señales y, si apuntan a otro stack, un aviso. Para cambiar la selección hay que
pedirlo con `--stack` o `--profiles`.

**Stack primario.** Detectar varias señales no aplica varios stacks. Una capa reemplaza a
las que requiere cuando coinciden juntas, y hereda lo que ellas reemplazan. Una capa solo
coincide si coinciden también las capas que requiere: un `app/layout.tsx` sin `next` en
`package.json` es un archivo más, no el App Router. La más
específica es el primario y trae las otras por `requires`. `supersedes` declara qué stacks
reemplaza uno sin requerirlos, y solo se usa donde uno es una especialización del otro:

| Coincidencias | Primario | Motivo |
|---|---|---|
| `react` + `nextjs` + `nextjs-app-router` | `nextjs-app-router` | la capa más específica: `next` en `package.json` y un `app/layout.*` (o `src/app/layout.*`) |
| `react` + `nextjs` | `nextjs` | `next` sin App Router |
| `react` + `node` | `react` | un proyecto React también tiene `package.json`; vale igual para las capas de Next.js |
| `react` + `android` | `react` | el directorio `android/` de React Native o Capacitor es un host generado |
| `android` + `java` | `android` | una app Android también tiene Gradle |
| cualquier otra, por ejemplo `node` + `go` | ninguno | nada dice cuál es el principal: se listan las coincidencias y se pide una selección explícita, que puede nombrar las dos (`--profiles go,node`) |

Si queda un solo stack después de quitar los reemplazados, es el primario. Si quedan
varios, `detect` sale con 3, y `resolve`, `plan` y un apply sin selección fallan antes de
escribir; el hook avisa y omite la proyección. Con una selección, el stack primario es el
primero que ningún otro profile seleccionado requiere. Un ciclo en `supersedes` invalida el
catálogo, y el resultado no depende del orden de los archivos ni del catálogo.

**Sugerencias.** Una capability con `detect` que coincide y falta en la selección se
sugiere en `plan`, con el profile, el archivo inspeccionado y la señal. No entra al
manifest ni instala herramientas, tampoco en una detección inicial, y no cambia los `defaults`:
`--stack android` sigue sin `browser` aunque `plan` lo sugiera por `androidx.webkit:webkit`. No se sugiere una capability incompatible con la selección.

`detect` no forma parte del digest de un profile en el lockfile, porque no cambia lo que
se proyecta: ajustar una señal no marca un update pendiente en repos ya aplicados.

## 3. Profile packs

Una empresa mantiene sus profiles en un repositorio propio y los reutiliza con versiones
fijadas. `scripts/agent_ready_packs.py` carga los packs y `assets/examples/acme-profile-pack/` es un
pack mínimo de ejemplo. Un pack con herramientas (CLIs, servidores MCP o scripts) se publica como dice
[publishing-packs-with-tools.md](publishing-packs-with-tools.md), con un ejemplo personal y otro
corporativo firmado. No hay stacks primarios externos, profiles por carpeta, distribución por
npm ni instaladores propios de un pack.

**Fuentes.** `.agents/agent-ready.json` las declara en `sources.packs`:

```json
{
  "profiles": ["node", "acme/kafka-interno"],
  "sources": {
    "packs": [
      { "name": "acme", "source": "git+https://github.com/acme/agent-profiles", "ref": "main" },
      { "name": "seguridad", "source": "git+ssh://git@github.com/acme/security-profiles#<commit-completo>" },
      { "name": "local", "source": "path:./agent-packs/local", "updates": "pinned" }
    ]
  }
}
```

`agent-ready sources add <nombre> <fuente> [--ref r] [--updates m]` la declara (validada antes de
escribir) y la trae a la caché; `agent-ready sources remove` la saca si ningún profile seleccionado la usa, y
`agent-ready profiles add acme/kafka-interno` selecciona un profile suyo.

`sources.enabled: false` (por ejemplo, desde la organización) apaga los packs: no se descargan ni se leen, y
seleccionar uno de sus profiles falla antes de escribir.

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
profile acepta `kind`, `description`, `assets`, `requires`, `conflicts`, `defaults`, `tools`, `detect` y `nested`,
con el significado de la sección 1, más `clis`, `mcpServers` y `scripts` ([pack-tools.md](pack-tools.md)), y
estos límites:

- `kind` es `capability`, `bundle` o `stack`. Un profile que necesita un stack lo declara en `requires`;
  un pack publica un `stack` propio para una tecnología que golfo-kit no tiene (ver «Stacks de un pack»).
- `tools` solo acepta herramientas que el motor ya conoce (`browser`).
- Un pack no declara `baseAssets` ni otras fuentes, ni redefine un profile de
  Golfo. Los assets compartidos van en un profile propio, como `acme/base`, que los demás requieren.
- `assets` publica solo `rules/`, `skills/`, `agents/`, `commands/`, `blocks/`, los bloques gestionados
  de archivos compartidos con el proyecto ([managed-agents-block.md](managed-agents-block.md), sección
  «Bloques en otros archivos»), y `nested/`, el bloque de cada destino anidado que declara
  ([nested-instructions.md](nested-instructions.md)). No puede traer hooks, settings, el template de
  `AGENTS.md` ni archivos `AGENTS.md` o `CLAUDE.md`; solo un profile `stack` publica su sección de `AGENTS.md`
  (`blocks/AGENTS.md`).
- Las rules de un pack entran en la lista del bloque gestionado de `AGENTS.md`, como las de cualquier
  profile. Un pack no cambia el template ni las instrucciones propias del proyecto.

**Stacks de un pack.** Un profile `kind: stack` de un pack es un stack primario como los de golfo-kit,
para una tecnología que golfo-kit no tiene (un lenguaje, un DSL propio). `assets/examples/elixir-stack-pack/`
publica `beam/elixir`:

- Se detecta por sus señales (`detect`) en cuanto el manifest declara la fuente: sin `profiles`, la
  detección inicial lo elige como a cualquier stack. También se elige con `--profiles beam/elixir` o
  `--stack beam/elixir`.
- Declara sus `defaults` y su sección de `AGENTS.md`, y se combina con las capabilities de golfo-kit.
  Puede requerir un stack de golfo-kit (una capa, como en «Capas») o no requerir ninguno.
- **Precedencia entre fuentes:** ninguna fuente gana por ser de golfo-kit o de un pack. Si un stack de un
  pack y otro (de golfo-kit u otra fuente) coinciden en la detección, se pide una selección explícita,
  salvo que uno declare `supersedes` sobre el otro. Un stack de un pack solo puede reemplazar a uno de
  golfo-kit o de su mismo pack; golfo-kit no conoce los de los packs, y dos packs no se reemplazan entre
  sí: sus stacks que coinciden piden una selección explícita.
- Dos stacks que publican el mismo destino fallan antes de escribir, como cualquier par de profiles.
- Un stack de un pack no tiene que ser de software: `assets/examples/estudio-juridico-pack/` publica
  `estudio-juridico/estudio`, que se detecta por la estructura de carpetas (`actas/**/*.md`), no requiere
  `software-development` y trae por `defaults` la capability `actas-infraccion`. El mismo caso funciona con
  la capability sola.

**Compatibilidad declarada.** El catálogo de un pack, y el de golfo-kit (`assets/profiles.json`),
pueden declarar tres campos opcionales:

```json
{
  "schemaVersion": 1,
  "name": "acme",
  "version": "2.0.0",
  "minEngine": "0.46.0",
  "changes": [
    { "version": "2.0.0", "summary": "Los topics de Kafka cambian de nombre", "breaking": true },
    { "version": "1.1.0", "summary": "Rule nueva para el cliente interno" }
  ],
  "profiles": {}
}
```

- `version` es la versión semver del contenido. Sin `version`, golfo-kit usa la de su plugin.
- `minEngine` es la versión más vieja del motor (el plugin golfo-kit que corre agent-ready-setup)
  que tiene lo que el contenido usa. No hay tope: el motor nunca se fija y un motor más nuevo sigue
  aplicando. Con un motor más viejo, el apply, el plan o el status fallan antes de escribir y dicen
  qué versión del plugin instalar.
- `schemaVersion` sube solo si el formato del catálogo cambia de forma incompatible. Un motor que
  no conoce ese `schemaVersion` falla con el mismo pedido de actualizar el plugin.
- `changes` es el changelog: `version`, `summary` y `breaking` opcional.

El plan de una actualización (`agent-ready update <fuente> --dry-run` o `--plan --update-source`)
muestra en «Version changes» la versión del lock y la nueva de cada fuente. Debajo lista los cambios
declarados entre las dos, del más nuevo al más viejo, con los `breaking` resaltados. Un salto de
versión mayor (o de minor en `0.x`) se marca aparte. El JSON del plan los trae en `versionChanges`.
Después, «Semantic conflicts» lista lo que la actualización contradice de las rules propias y del
`AGENTS.md` del proyecto ([ai-reviews.md](ai-reviews.md), sección 7).

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
apply de `bootstrap.sh` lo adopta y un sync también, salvo con `updates.mode: pinned`. Si la ruta falta, un apply falla sin
escribir y `plan` informa la evaluación incompleta. Una carpeta externa sirve para desarrollo, pero su
digest no garantiza que pueda reconstruirse en otro entorno. Para consumo compartido, usar Git fijado o
un pack versionado dentro del propio repo.

**Modos de consulta.** `--plan`, `--status` y `AGENT_READY_SETUP_REVIEW_MODE=1` no escriben en el repo. Si
falta una fuente que la selección necesita, informan `Evaluation incomplete` y `plan` sale con 5: ese
resultado no es un plan validado. Una fuente sin profiles seleccionados que no está disponible no frena la
evaluación, pero sus sugerencias no aparecen. Cargar un catálogo o evaluar su `detect` nunca ejecuta nada
del pack. Qué refrescan y cuándo: sección 4.

## 4. Configuración y actualizaciones

Cada mecanismo es opcional y se configura por separado, con defaults que funcionan sin configurar nada, igual en
un proyecto personal y en uno de empresa. Las opciones, sus capas (defaults, organización, usuario, proyecto,
entorno y flags), qué afloja la seguridad y cómo ver el valor efectivo con su origen están en
[configuration.md](configuration.md); la lista de claves, en [configuration-keys.md](configuration-keys.md). Esta
sección explica qué hace cada mecanismo.

| Mecanismo | Opciones |
|---|---|
| Detección y sugerencias | `detection.enabled` |
| Profile packs | `sources.enabled`, `sources.packs` |
| Actualizaciones | `updates.enabled`, `updates.mode` (también por fuente) |
| Refresco en `plan` y `status` | `updates.refresh` |
| Chequeo de CI | `ci.enabled`, `ci.mode` |
| Herramientas de los profiles | `tools.enabled` |

**`updates.mode: auto`.** Los assets se mantienen al día solos, sin bloquear nada. El hook de SessionStart
informa el resultado de la actualización anterior y lanza la siguiente desacoplada con
`scripts/run-detached.py`: refresca el snapshot de `golfo-marketplace`, resuelve la `ref` de cada fuente
en `auto` a su último commit y aplica con el gate de ownership y el lock de concurrencia de siempre. El
cambio queda sin commitear en el árbol, para revisarlo y commitearlo. El lockfile sigue registrando el
commit resuelto y sus digests, así cada resultado es reproducible y auditable. Lo que cambió, o el error,
se informa una vez en la sesión siguiente. Tras tres fallas seguidas, el próximo intento espera una hora.
En una máquina sin ninguna fuente de la skill, el primer upgrade del marketplace es sincrónico porque no
hay scripts para desacoplarlo.

**`updates.mode: pinned`.** Nada se aplica solo: el hook informa drift y updates pendientes, sin escribir en el
repo. Con `updates.refresh` encendido, la tarea desacoplada solo refresca la caché, para que la sesión siguiente pueda
avisar. Se adopta con `agent-ready update <fuente>` (`--dry-run` muestra antes qué cambiaría) o editando la
revisión del manifest. Un apply es siempre explícito: sigue las fuentes en `auto`, adopta
el drift de las rutas locales y deja el resto en la revisión del lock.

**`updates.enabled: false`.** SessionStart no actualiza, no chequea ni refresca nada, y no informa: solo un apply
explícito de `bootstrap.sh` o una sincronización en primer plano cambian los assets.

Se puede combinar por fuente. Un repo en `auto` puede fijar una fuente con `"updates": "pinned"`, y entonces
un cambio de esa fuente frena el sync sin escribir nada. Un repo `pinned` puede seguir una fuente con
`"updates": "auto"` (si el usuario o la organización fijaron `pinned`, eso cuenta como aflojar; ver
[configuration.md](configuration.md)). golfo-kit queda en la revisión del lock (ver «golfo-kit como fuente»), así que
el pack se actualiza solo sin arrastrarlo. Si el lock no tiene una revisión de golfo-kit que se pueda descargar (un
source local sin Git), un apply proyecta toda la selección: si golfo-kit tiene una versión pendiente, el sync no
actualiza el pack solo y espera una adopción explícita de ambos.

**golfo-kit como fuente.** El contenido de golfo-kit (catálogo, base, stacks, capabilities y sus rules, skills,
agents, commands y templates de instrucciones) se puede fijar como un pack, con `sources.golfoKit` en el manifest:

```json
{ "sources": { "golfoKit": { "updates": "pinned", "ref": "main" } } }
```

- Sin declararlo, el contenido sigue al plugin instalado, como siempre.
- `updates` pisa `updates.mode` solo para golfo-kit. En `pinned`, cada apply proyecta el contenido de la
  revisión del lock (`source.revision` y `source.origin`), aunque el marketplace publique una nueva: sumar un
  profile, recrear un asset borrado o adoptar otra fuente no cambia nada de golfo-kit. El primer apply adopta la
  revisión del plugin instalado.
- `ref` (rama, tag o commit completo) es lo que sigue en `auto` y lo que adopta `agent-ready update golfo-kit`.
  Sin `ref`, el update adopta la versión del plugin instalado. Sin red, la `ref` vale el último commit que vio
  esta máquina o, si no vio ninguno, la revisión del lock que vino de esa `ref`. Si el remoto no responde, `plan`,
  `status` y `check` avisan y comparan con esa revisión; un apply falla antes de escribir.
- `agent-ready update golfo-kit --to <tag|rama|commit>` adopta exactamente esa revisión, y `--to` también sirve
  para un pack (`agent-ready update acme --to v2`). La actualización es por fuente, nunca por archivo, y
  `--dry-run` muestra antes qué cambia. Hoy el marketplace no publica tags por versión de golfo-kit: usar un
  commit o una rama.
- La revisión se descarga con Git del repositorio del marketplace (el `repository` del manifest del plugin) en
  la caché del usuario, sin depender de la versión instalada. Un apply siempre la descarga si falta, aunque
  `updates.refresh` esté apagado, y si no puede, falla antes de escribir: nunca reemplaza el contenido fijado por
  el instalado. Solo `plan`, `status` y el inicio de sesión (que no escriben) comparan con el instalado, con un
  aviso, cuando la revisión no está en la caché y corren sin red. El inicio de sesión nunca usa la red en primer
  plano: resuelve la `ref` y descarga en la sincronización en segundo plano.
- `agent-ready check` compara con el contenido fijado. Si no tiene esa revisión (sin red o sin acceso al
  repositorio), informa la fuente como no disponible, bajo el `ci.mode` vigente, en vez de cambios que un apply no
  haría. `agent-ready profiles list|add|remove` e `init` eligen del catálogo de la revisión fijada.
- Un motor nuevo (hooks o templates de settings distintos) no frena la sincronización de un golfo-kit fijado:
  solo cambia lo que es del motor.
- En un repositorio `pinned`, `sources.golfoKit.updates: auto` hace que el inicio de sesión adopte golfo-kit
  solo, como a un pack en `auto`.
- **El motor nunca se fija.** Los scripts, los hooks (`assets/common/hooks/`, que se actualizan solos en cada
  sync), los templates de `.claude/settings.json` y `.codex/hooks.json` que los conectan, los schemas de
  configuración y `providers.json` siguen siempre al plugin instalado. El lock registra la versión del contenido
  en `source.version` y la del motor en `generator.version`.
- Con golfo-kit fijado, `status` avisa cuando el plugin instalado trae otra versión y cómo adoptarla. Si el
  plugin instalado no es un checkout de Git (la caché del provider), compara las versiones.
- Sin red, una `ref` que esta máquina nunca resolvió y que el lock no registra deja a `check` con la fuente no
  disponible y a `plan` y `status` comparando con el contenido instalado, con un aviso.
- `golfo-kit` es un nombre reservado: un pack de `sources.packs` no puede llamarse así.

`AGENT_READY_SETUP_SYNC_FOREGROUND=1`, o `--stack` y `--profiles` en el hook, corren la sincronización en
primer plano. `AGENT_READY_SETUP_REVIEW_MODE=1` nunca actualiza, nunca usa la red y nunca escribe.

**Seguridad.** Seguir una `ref` en `auto` significa que quien pushee al pack cambia las instrucciones del
agente en todos los repos consumidores en su próxima sesión. El diff del lockfile y el chequeo de CI son el
control. Si eso no alcanza para una fuente, fijarla con un commit completo o con `"updates": "pinned"`; para todos los
repos de una máquina, `updates.mode: pinned` o `security.preset: strict` en la config de usuario.
Las credenciales nunca entran al manifest, al lock ni a los logs: un pack declara variables de entorno solo
por referencia. Los CLIs, servidores MCP y scripts que declara pasan por la política de `security`
([pack-tools.md](pack-tools.md)); por ahora el motor solo informa su veredicto y no ejecuta nada.

**Refresco.** `--plan` y `--status` actualizan por defecto la caché fuera del repo (snapshot del marketplace
y última revisión de cada `ref`) para decir si todo está al día, sin escribir en el repo. `--offline`,
`updates.refresh: false` y el modo review no tocan la red: comparan con lo que ya hay. Si el refresco falla, lo avisan
y comparan con la caché. Si aun así falta una fuente necesaria, informan `Evaluation incomplete`.

**Chequeo de CI.** `scripts/agent-ready-state.py check` compara las fuentes, el lock y los assets commiteados, y
sale con códigos documentados según `ci.enabled` y `ci.mode`. Sirve en cualquier proveedor de CI y esta skill no crea workflows.
Comando, códigos de salida, autenticación y ejemplos: [ci-check.md](ci-check.md).

## 5. Manifest y lockfile

| Archivo | Quién lo edita | Contenido |
|---|---|---|
| `.agents/agent-ready.json` | personas (versionado) | `profiles` elegidos y lo que difiere de los defaults (capa de proyecto de [configuration.md](configuration.md)) |
| `.agents/agent-ready.lock.json` | solo el apply | source resuelto, profiles con digest, fuentes de packs, inventario de assets, archivos fusionados |

El lockfile registra `source.plugin`, `source.version` (versión del contenido de
golfo-kit), `source.kind` (`marketplace-snapshot`, `plugin-cache`, `local` o `git`
cuando golfo-kit está fijado), `source.revision` (commit git del source cuando
existe), `source.origin` (repositorio del que se puede volver a descargar),
`source.requestedRef` cuando un update eligió una ref, y `source.contentDigest`,
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
que suma a la raíz (`own`), sección 1, «Workspaces».

**Apply reproducible.** `agent-ready apply --from-lock` aplica exactamente el lock, en otra máquina o un año
después, sin importar `updates.mode` ni las `ref` del manifest:

- Toma la selección del lock y la revisión de golfo-kit y de cada pack que registra, aunque el manifest declare
  ahora otra `ref` (el origen tiene que ser el mismo). Las descarga en la caché del usuario si faltan; con
  `--dry-run` y `updates.refresh: false` no descarga nada y falla si falta una revisión.
- Antes de escribir compara byte a byte: la selección, las revisiones, el digest de cada pack, el sha256 de cada
  asset, y el template y los textos con que se arma el bloque gestionado de `AGENTS.md`
  (`merged["AGENTS.md"].inputsSha256`). Si algo no coincide, falla sin escribir y nombra la fuente
  (`golfo-kit`, un pack o `selection`) y el archivo.
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
- `agent-ready check` compara para CI, y su código de salida sigue a `ci.mode` (sección 4).
- `agent-ready config explain` muestra la configuración efectiva y la capa de cada valor.
- `update` sin fuentes adopta la última revisión de cada fuente Git que sigue una `ref` y de golfo-kit (también
  fijado, ver sección 4); `--to <ref>` elige la revisión de una sola fuente;
  con `--dry-run` muestra el plan de esa adopción y solo descarga en la caché del usuario.
- `status` separa assets aplicados, modificados, faltantes, conflictos
  preservados, escrituras fallidas y retirados que no se pudieron borrar; además dice si el
  source resuelto o la selección de profiles difieren del lock (`Update
  available`). También cuenta como faltante una vista `.claude/` o un archivo fusionado que se borró; su
  contenido gestionado lo revisa `plan`. Al final muestra los hallazgos conocidos de las revisiones de IA,
  leídos de la caché sin llamar al provider ([ai-reviews.md](ai-reviews.md)). `agent-ready-state.py
  status --check` sale con 4 si hay drift o si la selección no se puede resolver.
- `plan` muestra de dónde salió la selección, la configuración efectiva con su origen, las señales detectadas y las capabilities
  sugeridas con su evidencia (ver «Detección»). Lista cada destino con su acción,
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
  repositorio que responda a `git ls-remote`; `--offline` no contacta ninguno) y, si el repo ya
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

## 8. SessionStart y modo review

El hook `.agents/hooks/sync-marketplace.sh` nunca hace esperar a la sesión. Valida la configuración efectiva e
informa el resultado de la actualización anterior:

- `updates.mode: auto` (default): lanza desacoplada la sincronización (sección 4).
- `updates.mode: pinned`: corre `status --brief` y no escribe nada en el repositorio, ni siquiera se
  autoactualiza. Con `updates.refresh` encendido, refresca la caché desacoplado, para que la sesión siguiente avise.
- `updates.enabled: false`: no hace nada más que decirlo.
- `AGENT_READY_SETUP_REVIEW_MODE=1`: nunca escribe, aunque el manifest diga `auto`, y tampoco refresca el
  marketplace ni llama a la CLI del provider. No se activa sola en CI: definirla en el entorno de reviews
  automatizadas; ver [review-consumption.md](review-consumption.md).
- Una configuración que no se puede leer o validar, en cualquier capa, frena el sync antes de escribir, porque
  podría declarar un repositorio `pinned`.

`--updates` en bootstrap cambia el modo del manifest de forma explícita.

## 9. Providers y capacidades

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

## 10. Límites conocidos

- Los profiles de un workspace proyectan sus rules y su `AGENTS.md`, pero todavía no sus skills,
  subagentes, comandos ni destinos anidados («Workspaces», sección 1).
- En Windows sin symlinks, las vistas son hard links y
  `relink-hard-link-views.sh` las reenlaza en cada prompt y en cada escritura del
  índice, para recuperar las que git separa cuando recrea el asset. Sin historial
  por vista no distingue ese caso de una edición guardada como archivo nuevo en la
  vista, que se pierde ahí. Para cambiar comportamiento, usar una rule propia.
- Si el lock no tiene una revisión de golfo-kit que se pueda descargar (un source local
  sin Git), un asset faltante se recrea desde el source resuelto en el próximo apply, no
  desde la versión del lock: el apply es un cambio explícito y revisable, y el lock pasa a
  registrar la versión nueva. `status` avisa antes si el source difiere del lock, y
  `--from-lock` falla en vez de proyectar otro contenido.
- `--from-lock` reproduce el contenido, no el motor: en otra versión del plugin, los
  hooks y los templates de settings que los conectan pueden diferir del lock.
- Las rules y la skill de browser siguen en `assets/common/` porque otras rules
  comunes las enlazan; el profile `browser` controla solo la instalación.
