# Cobertura incremental de skills (`skill-coverage`)

Fuente única del protocolo con el que una skill de `golfo-kit` consulta qué cubrió antes, decide si repetir el análisis y registra la cobertura que acredita. Para las skills integradas el protocolo es **obligatorio**: si el repositorio no tiene registro o ninguna unidad cubre el código tocado, la skill los crea, y una ejecución que termina sin `record` exitoso por unidad cierra **incompleta**. Las skills integradas (`ui-ux-flow-patterns`, `measured-performance-optimization`, `optimistic-action-mutations`, `nextjs-route-ui-boundaries`) solo agregan sus reglas propias y remiten acá.

## Contenido

- [Qué resuelve](#qué-resuelve)
- [Dónde vive cada cosa](#dónde-vive-cada-cosa)
- [Cómo invocar el CLI](#cómo-invocar-el-cli)
- [Protocolo de una skill](#protocolo-de-una-skill)
- [Cierre incompleto o bloqueado](#cierre-incompleto-o-bloqueado)
- [Unidades funcionales](#unidades-funcionales)
- [Estados, vigencia y decisiones](#estados-vigencia-y-decisiones)
- [Detección de impacto](#detección-de-impacto)
- [Evidencia](#evidencia)
- [Formato del registro](#formato-del-registro)
- [Políticas por skill](#políticas-por-skill)
- [Integración en CI](#integración-en-ci)
- [Limitaciones y fallbacks](#limitaciones-y-fallbacks)
- [Agregar otra skill](#agregar-otra-skill)

## Qué resuelve

Cada skill que revisa una funcionalidad deja una cobertura **verificable** sobre una **unidad funcional** (normalmente un subflujo: "Crear proveedor", "Aprobar solicitud"): qué código revisó (fingerprint por símbolo), en qué commit, con qué versión y definición de la skill, con qué evidencia y con qué limitaciones. Al volver a invocarla, la skill sabe si la cobertura sigue vigente, qué cambió desde entonces y qué alcance mínimo tiene que revisar. Nada se marca verificado sin la evidencia que exige su política.

## Dónde vive cada cosa

| Pieza | Ubicación |
|---|---|
| Motor y CLI (Node ≥ 20, sin dependencias) | `plugins/golfo-kit/tools/skill-coverage/skill-coverage.mjs` y `lib/` |
| Tests del motor (`node --test`, repos Git temporales) | `plugins/golfo-kit/tools/skill-coverage/tests/` (`pnpm run test:skill-coverage`) |
| Registro de cada repositorio consumidor | `.golfo/skill-coverage/` en ese repositorio, versionado con su código |

```text
.golfo/skill-coverage/
├── config.json                          # opcional: ignore, alias, sharedInputs, overrides por skill
├── .gitignore                           # excluye .pending/ y locks
├── units/<unit-id>.json                 # una unidad funcional por archivo
├── records/<skill>/<unit-id>.json       # cobertura de una skill sobre una unidad
├── runs/<run-id>.json                   # reporte de cada ejecución registrada
└── .pending/<run-id>.json               # corridas en curso (locales, no se commitean)
```

Un archivo por unidad y por par skill/unidad evita conflictos de Git y que una corrida reescriba coberturas ajenas. El registro y sus reportes nunca forman parte de un fingerprint.

## Cómo invocar el CLI

Resolvé la ruta **real** del directorio de la skill (siguiendo symlinks: `realpath` en POSIX, `(Resolve-Path ...).ResolvedTarget` o `Get-Item` en PowerShell) y desde ahí `../../tools/skill-coverage/skill-coverage.mjs`. En un plugin instalado es `<raíz del plugin>/tools/skill-coverage/skill-coverage.mjs` (`${CLAUDE_PLUGIN_ROOT}` en Claude Code). Correlo con `node` desde cualquier carpeta del repositorio consumidor (o con `--root <repo>`); `--json` da salida para agentes. `help` lista todos los comandos.

```bash
COVERAGE="node <skill-dir-real>/../../tools/skill-coverage/skill-coverage.mjs"
$COVERAGE status --details
```

El CLI no depende del agente: funciona igual en Claude Code, Codex y Hermes con una terminal y `node` (≥ 20) en `PATH`. Si no hay `node` o el CLI no está instalado junto a la skill, la skill termina su trabajo pero el cierre queda **incompleto** (ver [Cierre incompleto o bloqueado](#cierre-incompleto-o-bloqueado) y [agent-capabilities.md](agent-capabilities.md#tabla-de-capacidades), fila «Registrar cobertura de skills»).

## Protocolo de una skill

1. **Identificar la unidad y crearla si falta.** `affected --changed --skill <skill>` (cambios staged, unstaged y untracked) o `affected --paths <archivo>...` devuelve las unidades cuyo código incluye esos archivos. Un pedido puede tocar varias unidades: el protocolo corre por cada una. Si el repositorio no tiene registro o ninguna unidad cubre el código tocado, crearlos es parte de la skill, no una sugerencia:
   1. `init` crea `.golfo/skill-coverage/` con su `config.json` y su `.gitignore` (también lo hacen `add-unit` y `discover --write`).
   2. En páginas de Next.js App Router, `discover --scope <carpeta> --write` propone y guarda unidades; revisá las creadas y ajustá a mano sus límites, nombres e ids según [Unidades funcionales](#unidades-funcionales) (son definiciones, no evidencia).
   3. Para el resto (APIs, jobs, webhooks, backend, UI fuera de páginas del App Router o lo que `discover` no propuso), `add-unit --id <id> --kind <kind> --module <m> [--page <p>] [--section <s>] --subflow <s> --entry <path[:symbol]>...` crea la unidad validada contra el schema.
   4. Volvé a correr `affected` para confirmar que la unidad cubre el código tocado y seguí con el paso 2. Una unidad recién creada no tiene cobertura: `check` decide `full`.
2. **Consultar.** `check --unit <id> --skill <skill>` devuelve estado, vigencia, decisión, motivos, cambios relevantes y alcance sugerido. Un pedido explícito de auditoría completa (o de "revisá todo de nuevo") agrega `--force-full`: el cache nunca gana sobre ese pedido.
3. **Decidir con la respuesta:**
   - `skip`: la cobertura verificada está vigente. No repetir el análisis de la unidad; decir al cierre que la cobertura vigente respalda la unidad (commit y versión). Si además hay trabajo nuevo de la skill fuera de esa unidad, aplicarlo normalmente.
   - `incremental`: revisar solo el alcance sugerido (los símbolos cambiados y su contexto necesario según la política) y lo pendiente de una corrida parcial.
   - `full`: analizar toda la unidad (sin cobertura previa, cambio mayor de la skill, corrida bloqueada, entrada movida o la mayoría del código cambiado).
   - `not-applicable`: la skill no corresponde a la unidad (declarado en la unidad o registrado antes y sin cambios relevantes).
4. **Trabajar** con la skill como siempre (análisis, cambios, verificaciones), acotada a la decisión.
5. **Fijar el código final.** Cuando ya no vas a editar el código de la unidad: `begin --unit <id> --skill <skill> --mode <full|incremental|lightweight>`. Guarda el fingerprint de ese momento y devuelve un `runId`.
6. **Registrar evidencia** de las verificaciones que hacés **después** de `begin`:
   - comandos (tests, typecheck, lint, scripts de medición): `evidence --run <id> --kind test --exec "<comando>"`. El CLI lo ejecuta, guarda exit code, duración y un hash de la salida (nunca la salida) y la muestra por stderr.
   - lo que no es un comando (revisión, recorrido en navegador, accesibilidad, mediciones): `evidence --run <id> --kind <review|browser|accessibility|measurement> --outcome <pass|fail|measured|skipped> --summary "<qué y cómo>"`, con `--tool`, `--metric`, `--before`, `--after`, `--conditions` cuando aplican.
7. **Registrar el resultado** al terminar, sin esperar a que el usuario lo pida: `record --run <id> --result <verified|partial|blocked|not-applicable>` con `--limitation` y `--pending` repetibles. El registro es automático y parte del cierre de la skill.
   - Si el CLI rechaza el registro (exit 3) porque el código cambió después de `begin`, no se guardó nada: `abort --run <id>`, `begin` otra vez sobre el código final y repetir las verificaciones afectadas.
   - Si falta evidencia requerida, el CLI guarda `partial` en lugar de `verified` y lista lo pendiente. No es un error: reportalo así.
8. **Reportar** en el cierre de la skill una línea por unidad: unidad (y si se creó en esta ejecución), decisión tomada, resultado registrado y pendientes. Si alguna unidad tocada quedó sin `record` exitoso, el cierre es incompleto: ver [Cierre incompleto o bloqueado](#cierre-incompleto-o-bloqueado).

Reglas que valen siempre:

- Nunca editar a mano `records/` ni `runs/`, ni fabricar evidencia: solo lo que realmente se ejecutó o se recorrió en la sesión. Una verificación que no se pudo hacer va como `--limitation` y el resultado no es `verified`.
- `verified` exige el análisis completo de la unidad: un modo `incremental` o `lightweight` solo acredita sobre una cobertura verificada anterior; sin ella queda `partial`.
- `partial` es para una ejecución que se hizo pero dejó verificaciones sin hacer o sin evidencia (sin tests para esa parte, sin recorrido en navegador, modo incremental sin cobertura verificada previa): el trabajo está, falta acreditarlo. Cada verificación faltante va con `--pending` (lo que queda por hacer) o `--limitation` (por qué no se hizo).
- `blocked` es para un impedimento real que frenó la ejecución de la skill sobre la unidad (sin entorno para correrla, sin datos, sin acceso al servicio), con el motivo en `--limitation`. Una verificación que faltó pero no frenó el trabajo es `partial`, no `blocked`.
- El registro avanza solo con `record`; terminar la skill sin `record` deja la cobertura anterior intacta y el cierre incompleto.
- No guardar secretos, tokens, emails ni payloads en resúmenes: el CLI redacta lo que reconoce, pero la responsabilidad es de quien escribe.

## Cierre incompleto o bloqueado

El cierre de una skill integrada está **completo** solo si cada unidad tocada terminó con un `record` exitoso (cualquier resultado: `verified`, `partial`, `blocked` o `not-applicable`). Si no se pudo registrar, la skill igual termina su trabajo (el código, el análisis y las verificaciones no se descartan), pero el cierre se reporta como **incompleto: cobertura sin registrar**, nunca como completo ni como una simple limitación. Casos:

| Situación | Qué hacer y reportar |
|---|---|
| No hay `node` (≥ 20) en `PATH` | Cierre incompleto. Motivo: `node` no disponible (lo que devolvió `node --version` o el shell). Falta: instalar Node ≥ 20 y correr el protocolo sobre las unidades listadas. |
| El CLI no está junto a la skill (plugin incompleto o ruta no resuelta) | Cierre incompleto. Motivo: la ruta probada que no existe. Falta: reinstalar o actualizar `golfo-kit` (o apuntar a su `tools/skill-coverage/`) y registrar. |
| `init`, `add-unit` o `discover --write` fallan, o no se puede definir una unidad válida | Cierre incompleto. Motivo: el error literal del CLI. Falta: la unidad a crear (id, kind, entradas propuestas) para crearla con el comando corregido. |
| `record` falla (exit 3 por código cambiado después de `begin` que `abort` + `begin` no resolvieron, registro inválido, error de escritura) | Cierre incompleto. Motivo: el error literal. Falta: el `runId`, el resultado que se iba a registrar y la evidencia ya ejecutada para repetirla. |
| `record` funcionó con `blocked` o `partial` | El registro está completo: se reporta el resultado registrado con sus limitaciones y pendientes. |

Si el usuario pidió solo un plan o prohibió ejecutar comandos, no hay `record` posible: listá los comandos del protocolo que corresponden (incluida la creación del registro o la unidad) y cerrá incompleto con ese motivo.

En el reporte final va una línea **Cobertura: incompleta** con, por cada unidad tocada, el id (o el id propuesto si no se pudo crear), el motivo concreto y qué falta para registrar. No escribir `records/` ni `runs/` a mano para "completar" el cierre.

## Unidades funcionales

Jerarquía: **módulo → página → sección → subflujo** (`hierarchy.module`, `page`, `section`, `subflow`; `page` y `section` pueden ser `null`). La unidad es un comportamiento verificable por separado, no un archivo ni un botón; los estados de carga, vacío, error, feedback y accesibilidad se evalúan dentro de su subflujo. Se agrupan subflujos que comparten la misma implementación (por ejemplo, crear y editar un proveedor con el mismo formulario y handler) y se separan los que tienen código propio.

```json
{
  "schemaVersion": 1,
  "id": "academy.manage.providers.save",
  "kind": "ui-flow",
  "hierarchy": { "module": "Academia", "page": "Gestionar academia", "section": "Proveedores de verificación", "subflow": "Crear o editar proveedor" },
  "description": "Alta y edición comparten formulario, handler y endpoint.",
  "routes": ["/[slug]/academia/gestionar"],
  "entries": [
    { "path": "components/academy/academy-management/index.tsx", "symbol": "ProvidersSection" },
    { "path": "app/api/tribes/[slug]/verification-providers/route.ts", "symbol": "POST", "role": "server" }
  ],
  "dependsOn": [{ "path": "src/modules/member-verifications/setup.ts", "symbol": "*", "reason": "composición que la ruta resuelve en runtime" }],
  "skills": { "measured-performance-optimization": { "applicable": true, "reason": "guarda con una request" } }
}
```

- `id`: estable, en minúsculas con puntos y kebab-case. No depende del archivo: si el código se mueve, se actualiza `entries` y el id queda (`discover --write` detecta símbolos movidos y lo hace solo).
- `entries[].symbol`: `*` (archivo completo), `Nombre`, `Nombre/handler` (una función interna, por ejemplo `ReviewQueueRow/decide`), `Nombre~shell` (el cuerpo de un componente sin sus handlers: su render y su carga de datos, para un subflujo de consulta) o `Nombre.miembro` (una propiedad de un objeto constante). `follow: false` hashea solo esa entrada sin seguir sus dependencias (útil para la composición de la página). `role`: `ui` (por defecto), `server` (por defecto en `route.ts`) o `contract`.
- `dependsOn`: dependencias que el análisis estático no ve (endpoints llamados por URL, inyección en runtime, configuración), con `reason` obligatorio.
- `kind`: `ui-flow`, `api`, `job`, `webhook` o `backend`; una unidad puede cruzar varias pantallas o no tener interfaz.
- `skills.<skill>.applicable: false` declara que una skill no corresponde.

`add-unit --id <id> --kind <ui-flow|api|job|webhook|backend> --module <m> [--page <p>] [--section <s>] --subflow <s> --entry <path[:symbol]>... [--route <r>]... [--description <texto>]` crea una unidad en cualquier repositorio: inicializa el registro si falta, valida la definición contra el schema (id, kind, jerarquía, gramática de `symbol`), exige que cada archivo de `--entry` exista y rechaza un id que ya existe. `--entry path` sin símbolo cubre el archivo completo (`*`). No registra cobertura. `dependsOn`, `role`, `follow` y `skills` se agregan después editando `units/<id>.json`.

`discover [--scope <carpeta>] [--include-api] [--write]` propone unidades desde las páginas del App Router: sigue el código de UI que cada página renderiza y propone una unidad por acción independiente de una sección (handlers internos que hacen I/O) cuando hay dos o más, una por sección con una sola acción o con carga propia, y una `view` por página que carga datos (con sus `loading`/`error`). Reutiliza ids existentes, omite componentes compartidos por varias páginas y nunca registra cobertura. Las propuestas son un punto de partida: los límites, nombres e ids definitivos se ajustan a mano.

## Estados, vigencia y decisiones

El **resultado** se guarda; la **vigencia** se calcula en cada lectura y nunca se escribe.

| Estado | Significado |
|---|---|
| `verified` | análisis completo con toda la evidencia requerida |
| `partial` | se ejecutó pero faltan verificaciones (`pendingChecks`) |
| `blocked` | un impedimento real frenó la ejecución |
| `unreviewed` | no hay evidencia de que la skill haya corrido sobre la unidad |
| `not-applicable` | la skill no corresponde |
| `unknown` | el registro no se pudo leer o evaluar |

| Vigencia | Significado |
|---|---|
| `current` | las entradas relevantes y la definición de la skill coinciden con lo registrado |
| `stale` | hay cambios relevantes de código o cambió la definición de la skill |
| `unknown` | no se puede comparar con seguridad (otro analizador, closure truncada, skill no instalada junto al CLI) |

`check` elige el intento que representa la unidad (el más nuevo que sigue vigente; si no, el verificado; si no, el más nuevo) y decide:

| Situación | Decisión |
|---|---|
| `--force-full` | `full` |
| Sin cobertura previa | `full` |
| Versión mayor nueva de la skill, corrida anterior bloqueada o entrada que ya no existe | `full` |
| Verificada y vigente | `skip` |
| Solo cambió la definición de la skill | `incremental` contra los archivos de reglas cambiados |
| Cambios relevantes en menos del 60 % de las partes | `incremental` con el alcance de la política |
| Cambios relevantes en más del 60 % | `full` |
| Corrida anterior parcial | `incremental` con sus pendientes |
| Vigencia `unknown` | `incremental` sobre todos los archivos cambiados (conservador) |

`status [--module] [--page] [--unit <prefijo>] [--skill] [--details]` muestra el árbol con conteos por sección, página y módulo (`UI/UX 2/3` = 2 de 3 subflujos vigentes), sin ocultar subflujos pendientes; con `--details` agrega commit, versión, cambios, motivo, alcance siguiente y evidencia. `diff --unit --skill [--patch]` suma los commits que tocaron los archivos cambiados desde la base (si siguen en el historial) y el patch.

## Detección de impacto

El analizador usa el AST de Babel del proyecto (`@babel/parser` o la copia que trae `next`) y divide cada módulo en partes hasheadas por tokens (formato y comentarios no invalidan):

- `<module>`: directivas (`"use client"`) e imports con efectos.
- `Nombre`: una declaración de nivel superior (función, clase, tipo, constante).
- `Nombre~shell` + `Nombre/handler`: un componente con funciones internas se divide en sus handlers y el resto (estado y JSX). Dos subflujos del mismo componente o archivo tienen cobertura independiente.
- `Nombre~frame` + `Nombre.miembro`: un objeto constante (diccionario de copy o config) se divide por propiedad; cambiar un mensaje solo afecta a quien lo lee.

Las entradas de la unidad se expanden por referencias del mismo archivo, imports (con alias de `tsconfig`, `index` y re-exports), paquetes (con la versión del lockfile) y `dependsOn`/`sharedInputs`. Una entrada `Nombre/handler` incluye el `~shell` de su componente y los handlers hermanos que llama, pero no los handlers que solo el JSX llama. Así un cambio en `ProvidersSection` no invalida `ReviewQueueSection`, y un cambio en un helper compartido (cliente HTTP, DTO, validación, política) invalida a todas las unidades que lo alcanzan.

La comparación es por contenido del working tree: incluye cambios staged, unstaged, untracked, borrados y renombres, funciona sin commitear, sin red y después de rebases o squash. El commit se guarda como referencia histórica (`baseline.commit`) y, si el contenido registrado no estaba commiteado, `baseline.uncommittedFiles` lo marca como provisional; al commitear el mismo contenido sigue vigente sin repetir nada. Un símbolo movido a otro archivo con el mismo contenido cuenta como `relocated`, no como cambio. Si el commit base ya no existe, la comparación sigue por fingerprints y lo dice.

Una política puede sumar al closure entradas de contexto que la unidad no declara (`contextEntries`, ver `base-policy.mjs`). `nextjs-route-ui-boundaries` las usa para el árbol de rutas: por cada `routes` de la unidad (y cada entrada bajo `app/` o `src/app/`) agrega las páginas y route handlers de esa URL (sus propias partes y los datos que esperan, no los otros componentes que renderizan), todos los archivos de segmento de cada ancestro (`layout`, `template`, `loading`, `error`, `not-found`, `forbidden`, `unauthorized`, `default` de los slots `@*`), `global-error`/`global-not-found` y `next.config.*`, `middleware.*` o `proxy.*`, seguidos dos saltos (la chrome o el skeleton que renderizan y sus estilos), más `next`, `react` y `react-dom` a la versión que declara el proyecto aunque ningún archivo los importe. Así un layout compartido invalida todas las rutas que envuelve, un `loading.tsx` nuevo solo su segmento y un handler de una ruta ninguna otra. Las otras políticas no tienen contexto: su closure sigue siendo solo el código de la unidad.

Para lo que el análisis no resuelve (URLs, inyección, configuración): `dependsOn` en la unidad o `sharedInputs` en `config.json` (`[{ "path": "middleware.ts", "symbol": "*", "skills": ["ui-ux-flow-patterns"], "reason": "..." }]`).

## Evidencia

| Fuente | Cómo se obtiene | Qué se guarda |
|---|---|---|
| `witnessed` | `evidence --exec "<comando>"`: el CLI lo ejecuta en la raíz del repo | comando sanitizado, exit code, duración, hash de la salida |
| `attested` | `--outcome` y `--summary` declarados por el agente | tipo, resultado, resumen sanitizado y campos de medición |

Una evidencia con `outcome: fail` impide `verified` en esa corrida. Las mediciones necesitan métrica, herramienta, condiciones, `--after` y `--before` (o `--baseline-kind new-flow` con `--reference` para un flujo que no existía).

## Formato del registro

`records/<skill>/<unit-id>.json` guarda `verified` (el último intento verificado) y `latest` (el último intento no verificado, si es más nuevo). Un `partial` o `blocked` nunca borra la evidencia verificada anterior. Cada intento tiene:

- `result`, `mode`, `recordedAt`, `runId`, `report` (`runs/<run-id>.json`).
- `skill`: nombre, versión, `definitionHash` y hash por archivo de la definición (`SKILL.md` sin la línea de versión y `references/**/*.md`).
- `baseline`: `commit`, `branch`, `uncommittedFiles`, `analyzer`, `fingerprint`, `inputs` (hash por parte), `files` (hash por archivo) y, en performance, `signals` (carga por parte).
- `scope`: decisión, motivos y cambios relevantes al empezar.
- `evidence`, `limitations`, `pendingChecks`, `summary`.

`schemaVersion` versiona todos los documentos; un documento con otra versión se rechaza con un error explícito.

## Políticas por skill

| | `ui-ux-flow-patterns` | `measured-performance-optimization` | `optimistic-action-mutations` | `nextjs-route-ui-boundaries` |
|---|---|---|---|---|
| Cambio relevante | todo cambio visible o interactivo (copy, handlers, JSX, estilos, paquetes de UI) | solo el que agrega carga: requests, queries, `await`, loops con `await`, timers, listeners, effects, imports dinámicos, paquetes nuevos o actualizados | todo lo que puede cambiar el ciclo de vida de una operación: handlers, estado y render del componente, helpers, contratos, código servidor, paquetes, partes que no se pueden clasificar, miembros de configuración (tiempos, límites, reintentos, endpoints, claves de caché, estados) o que hacen I/O, y miembros de objetos no clasificados (ni configuración ni presentación identificada) | todo lo que puede mover una decisión de ruta: archivos de ruta y de segmento (aunque solo se muevan a otro segmento o route group, o cambien de convención, como `loading` → `template`), directivas e imports con efectos (`<module>`), render de componentes, handlers, `await`/requests nuevos en el render, `next.config`/`middleware`/`proxy`, estilos que importa cualquier skeleton o `loading` (aunque también los use otro componente), paquetes, imports sin resolver y miembros no identificados como copy |
| No relevante | código movido sin cambios | copy, estilos, tipos, refactors con la misma carga, código que quita carga | código movido sin cambios y solo los miembros de presentación identificados por el nombre del objeto (diccionario de copy, como `COPY` o `*_COPY`) o del miembro (texto visible, como `title`, `label` o `message`) | código movido sin cambios fuera del árbol de rutas, miembros de copy identificados por nombre (salvo los que nombran UI de carga, como `fallback` o `skeleton`) y estilos que ningún skeleton ni `loading` usa |
| Código servidor | hasta el route handler (un salto) | completo (use cases, repositorios, queries) | completo (idempotencia, transacciones y payload de reconciliación) | hasta el route handler o la server action (un salto); el contexto de ruta, dos saltos |
| Archivos excluidos | ninguno | estilos, catálogos de traducción, Markdown | estilos, catálogos de traducción, Markdown | catálogos de traducción y Markdown |
| Modos | `lightweight`, `incremental`, `full` | `incremental`, `full` | `lightweight`, `incremental`, `full` | `lightweight`, `incremental`, `full` |
| Evidencia para `verified` | `lightweight`: review + (test o browser). `incremental`/`full`: review + test + (browser o accessibility) | measurement con antes/después + test | `lightweight`: review + (test o browser). `incremental`/`full`: review + test | `lightweight`: review + (command o test). `incremental`/`full`: review + command (build, lint o typecheck) + (browser o test). Los `command` y `test` acreditan solo ejecutados con `--exec` |
| Alcance incremental | cada parte cambiada con su foco (handler: pending, doble envío, feedback, error; shell: estados y copy) | medir el flujo completo (antes = commit base si sigue en el historial y la medición no se registró sobre cambios sin commitear; si fue provisional, la primera revisión que contiene ese código) y la carga agregada por parte | cada parte cambiada con su foco (handler: clase, doble envío, respuestas viejas, rollback y resultado desconocido; shell: pending, optimista y confirmado; servidor: contrato e idempotencia; configuración: dónde se usa) | cada parte cambiada con su foco (`<module>`: dónde cae el boundary server/cliente; archivo de ruta: layout, Suspense, boundaries y segment config; movido: segmento, layouts y boundaries heredados; configuración: opciones de render, caché y navegación; estilos: forma del skeleton) |

Un `not-applicable` registrado con `record` se reevalúa cuando hay cambios relevantes en la unidad; `skills.<skill>.applicable: false` en la unidad, en cambio, es permanente. Para `optimistic-action-mutations` usar siempre el registro, así una mutación agregada después vuelve a evaluarse.

## Integración en CI

Empezar en modo informativo y de solo lectura: un job que hace checkout de `golfo-marketplace` junto al repositorio, instala dependencias (para el parser) y corre `validate --informative` y `status`, publicando la salida en el resumen del job. No bloquear PRs por coberturas viejas o inexistentes ni modificar código por detectar cobertura desactualizada.

## Limitaciones y fallbacks

- **Sin `node` o sin CLI**: no hay fallback que registre cobertura; la skill termina su trabajo y cierra incompleta con el motivo ([Cierre incompleto o bloqueado](#cierre-incompleto-o-bloqueado)).
- **Sin parser** (proyecto sin dependencias instaladas, `GOLFO_COVERAGE_PARSER=none`, archivo que no parsea): cada archivo se hashea completo y los imports se siguen por patrón. Más conservador: un cambio en el archivo invalida a todas sus unidades. Un registro hecho con símbolos y leído sin parser (o al revés) se compara por archivo: si nada cambió sigue vigente; si algo cambió la vigencia es `unknown` y la decisión es revisar esos archivos.
- **Estilos** (`.scss`, `.css`) se hashean por archivo: un cambio de estilos invalida la UI/UX de todas las unidades que importan ese módulo.
- **Llamadas por URL** (`fetch('/api/...')`) no enlazan con el route handler: declararlo en `entries` o `dependsOn`.
- **Señales de carga** son heurísticas (conteo de llamadas y `await`): un cambio de una query que mantiene la cantidad de llamadas no reactiva performance, igual que la regla de activación de la skill. Ante la duda, `--force-full`.
- **Definición de la skill no instalada** junto al CLI: la vigencia queda `unknown`; apuntar `GOLFO_COVERAGE_SKILLS_DIR` o `--skills-dir` al directorio `skills/` de golfo-kit.
- **Rutas de una unidad** (`nextjs-route-ui-boundaries`): el contexto se deriva de `routes` (URL exacta, con route groups y slots ignorados como hace Next.js) y de las entradas bajo `app/`. Una unidad sin ninguna de las dos solo suma `next.config`/`middleware`/`proxy`; las rutas interceptadas (`(.)foto`) no comparten la URL de la ruta que interceptan y van en `dependsOn`. Un archivo de ruta movido con el mismo contenido nunca cuenta como `relocated` irrelevante.
- **Closure muy grande** (más de 6000 partes): se trunca, se avisa y la vigencia no puede ser `current`; acotar `entries`.

## Agregar otra skill

Sin código: cualquier skill funciona con la política genérica (todo cambio es relevante; evidencia review + test) y se ajusta en `config.json` con `skills.<skill>.label`, `excludeFiles` (globs) y `evidence` (`{ "<modo>": [["kind"]] }`), que suman requisitos sin quitar los propios. Para reglas propias de relevancia o alcance, agregar un módulo en `tools/skill-coverage/lib/policies/` con el contrato documentado en `base-policy.mjs`, registrarlo en `policies/index.mjs` y cubrirlo con tests.
