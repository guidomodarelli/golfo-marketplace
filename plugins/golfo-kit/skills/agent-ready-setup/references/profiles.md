# Profiles

Qué declara un profile, cómo se combinan (capas, defaults y bundles) y los workspaces de un monorepo.
Leer al elegir profiles, al explicar qué publica una selección o al configurar un workspace. Es parte
del contrato de [profiles-and-lockfile.md](profiles-and-lockfile.md).

El catálogo es el `agent-ready-pack.json` del pack de contenido ([updates.md](updates.md), «El contenido»), más los profiles
de CI del motor (`assets/ci/profiles.json`). Cada profile declara:

| Campo | Significado |
|---|---|
| `kind` | `stack` (aporta sus rules y su sección de `AGENTS.md`), `capability`, `bundle` (solo agrupa otros profiles, ver «Bundles») o `ci` (los archivos de CI de un proveedor, que elige `ci.provider` y nunca la selección; son del motor, en `assets/ci/profiles.json`; ver [ci-check.md](ci-check.md)) |
| `assets` | árbol de templates del profile, relativo a la skill; opcional |
| `requires` | profiles que se agregan antes, en orden; siempre vienen |
| `defaults` | profiles que trae al elegirlo, después de la selección; el repo puede dejarlos afuera con `excludedDefaults` |
| `conflicts` | profiles incompatibles; seleccionarlos juntos es error |
| `overrides` | assets de otro profile de la selección que este reemplaza a propósito, como `<profile>:<path>` (`software-development:rules/testing-scope.md`, o `react:skills/component-creation` para una skill): se proyecta solo el suyo y `plan` lo muestra (`Overridden: …`). Reemplazar algo que la selección no tiene, o el núcleo (`common`), falla antes de escribir. Para reemplazar una sola rule de un archivo, `overrides` va en la rule ([atomic-rules.md](atomic-rules.md), sección 5) |
| `complements` | skills o herramientas de otros profiles con las que este va junto, como `<profile>:skills/<nombre>`, `<profile>:mcpServers/<nombre>` o `<profile>:clis/<nombre>`: declara que no compiten, y el aviso de herramientas que compiten por la misma capacidad (`provides`) no sale |
| `tools` | herramientas que el apply instala o registra (`browser`) |
| `detect` | señales estáticas para detectar el profile; opcional (ver [detection.md](detection.md)) |
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
    la raíz lo proyecta para todo el repositorio y el workspace cargaría los dos. Dos workspaces pueden
    reemplazar la misma rule con profiles distintos, cada uno en su carpeta; un skill, subagente o comando,
    que va una sola vez al repositorio, admite un solo reemplazo.
  - **Raíz:** el `AGENTS.md` raíz no lista esas rules. `rules/workspaces/` es una carpeta del motor: una
    rule propia ahí tampoco se lista en la raíz.
  - **`assumes:`:** se compara con la carpeta del workspace, su `package.json` y sus archivos de
    configuración, no con la raíz.
- **`AGENTS.md` del workspace:** `<path>/AGENTS.md` lleva el bloque `agent-ready:workspace`, que lista esas
  rules para Codex, y la sección de cada stack que suma el workspace, con sus referencias a esas rules
  movidas a `.agents/rules/workspaces/<path>/`. Una referencia a una rule de la raíz queda igual.
  - Es un `AGENTS.md` anidado como los de [nested-instructions.md](nested-instructions.md): lleva su
    `CLAUDE.md` con `@AGENTS.md`, el índice para Codex del `AGENTS.md` raíz lo lista, y espera junto a
    un `CLAUDE.md` propio.
  - El contenido propio del archivo, fuera de los bloques, es del proyecto.
- **Skills, subagentes y comandos:** los de un profile que suma un workspace van a `.agents/` una sola vez,
  para todo el repositorio, porque ni Claude Code ni Codex los acotan por carpeta. Dos workspaces que eligen
  el mismo profile comparten esos archivos, y uno que choca con un asset de la raíz falla antes de escribir,
  como en la raíz. Sus referencias a una rule del workspace apuntan a `.agents/rules/workspaces/<path>/`;
  si varios workspaces los comparten, nombran la rule de cada uno y piden leer la del workspace donde se
  trabaja. `agent-ready plan` muestra cuántos archivos suma cada workspace. Las herramientas que
  piden esos profiles (por ejemplo, las del navegador) y las que declara un pack también se instalan para el
  repositorio.
- **Otros archivos con bloques:** el bloque de `.gitignore`, `.gitattributes` o `.dockerignore`, que Git y
  Docker leen por carpeta, va al archivo del workspace (`apps/web/.gitignore`). El bloque de cualquier otro
  archivo (`.github/pull_request_template.md`, `CONTRIBUTING.md`) va al de la raíz, una sola vez. Sus
  referencias a una rule del workspace apuntan a `.agents/rules/workspaces/<path>/`, como las de los
  skills compartidos.
- **Destinos anidados:** un profile que suma un workspace busca sus candidatas dentro del workspace: el
  destino App Router de `apps/web` es `apps/web/app/AGENTS.md`. Su bloque nombra las rules del workspace, y
  `agent-ready plan` agrega el workspace a la línea del destino. `nested.enabled` y la entrada de
  `nested.targets` con su id valen igual que en la raíz. Los `paths` de esa entrada son carpetas del
  repositorio, y cada una va al workspace que la contiene.
- **Lo que queda en la raíz:** el template de `AGENTS.md`, el esqueleto y los settings de Claude salen solo de
  la selección raíz; los de un profile que suma un workspace no se usan.
- **Retiro:** sacar un workspace del manifest, o un profile de su selección, retira sus rules, sus vistas
  (también las carpetas que quedan vacías), sus bloques y sus destinos anidados, y los skills, subagentes y
  comandos que ningún otro workspace ni la raíz siguen usando. Un `AGENTS.md` que queda vacío se borra con
  su proxy.
- **Detección:** `agent-ready plan` y `agent-ready workspaces list` sugieren como workspace cada carpeta con
  un stack que la raíz no tiene, con la evidencia que lo muestra. Buscan en las carpetas que declaran
  `package.json` (`workspaces`), `pnpm-workspace.yaml` (`packages`) y `go.work` (`use`), y en las de
  `apps/`, `packages/` y `services/`. Un patrón recursivo (`modules/**`) baja a las subcarpetas, salvo
  `node_modules` y las ocultas. Mira hasta 50 carpetas, sin contar las que ya son o contienen un workspace,
  que saltea. La sugerencia no cambia el manifest. `detection.workspaces: false`, o
  `detection.enabled: false`, la apaga.
- **CLI:** `agent-ready workspaces` cambia los workspaces del manifest, siempre validados con las mismas
  reglas que el plan antes de escribir; después, `apply` los proyecta.
  - `list [--json]`: cada workspace con lo que suma a la raíz, y las sugerencias de la detección.
  - `add <path> [profile...]`: agrega el workspace, o esos profiles al que ya existe. Sin profiles toma el
    stack que la detección encuentra en la carpeta, y falla si no encuentra uno o encuentra varios.
  - `remove <path> [profile...]`: saca esos profiles del workspace, o el workspace entero; uno que queda
    sin profiles también sale.
- **Fuentes:** un pack que solo elige un workspace cuenta como seleccionado: su digest va al lock y su modo
  `pinned` frena al sync como el de un pack de la raíz. Lo que proyecta un profile del contenido que solo
  eligen workspaces entra al `contentDigest` por los archivos de los que sale, no por dónde queda: un
  contenido fijado ve su cambio y el digest no depende de las carpetas del repositorio.

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
