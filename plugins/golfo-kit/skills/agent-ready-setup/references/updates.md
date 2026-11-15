# Actualizaciones

Qué hace cada mecanismo de actualización: los modos de `updates`, el contenido (la fuente `golfo`) y cómo
se adopta, la seguridad de seguir una `ref`, el refresco de `--plan` y `--status` y el chequeo de CI. Leer
al explicar por qué un repositorio se actualizó o no. Es parte del contrato de [profiles-and-lockfile.md](profiles-and-lockfile.md).

Cada mecanismo es opcional y se configura por separado, con defaults que funcionan sin configurar nada, igual en
un proyecto personal y en uno de empresa. Las opciones, sus capas (defaults, organización, usuario, proyecto,
entorno y flags), qué afloja la seguridad y cómo ver el valor efectivo con su origen están en
[configuration.md](configuration.md); la lista de claves, en [configuration-keys.md](configuration-keys.md). Esta
referencia explica qué hace cada mecanismo.

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
[configuration.md](configuration.md)). El contenido queda en la revisión del lock (ver «El contenido»), así que
el pack se actualiza solo sin arrastrarlo. Si el lock no tiene una revisión del contenido (el override de desarrollo),
un apply proyecta toda la selección: si el contenido tiene una versión pendiente, el sync no actualiza el pack solo y
espera una adopción explícita de ambos.

**El contenido.** El catálogo, la base, los stacks, las capabilities y sus rules, skills, agents, commands y el
template de `AGENTS.md` no vienen con el plugin: salen de un **pack de contenido**, la fuente `golfo` del manifest.
Sin declararla, es el pack oficial,
[guidomodarelli/golfo-agent-profiles](https://github.com/guidomodarelli/golfo-agent-profiles), siguiendo `main`:

```json
{ "sources": { "golfo": { "source": "git+https://github.com/guidomodarelli/golfo-agent-profiles", "ref": "main", "updates": "pinned" } } }
```

- `source` es el repositorio del pack: solo `git+https://` o `git+ssh://`, sin credenciales ni `#<revisión>` en la
  URL (la revisión va en `ref`). Cambiarlo es adoptar otro contenido: el lock de la fuente anterior no cuenta, y
  `apply --from-lock` falla hasta un apply que lo adopte.
- `ref` (rama, tag o commit completo) es lo que sigue en `auto` y lo que adopta `agent-ready update golfo`. Sin red,
  la `ref` vale el último commit que vio esta máquina o, si no vio ninguno, la revisión del lock que vino de esa
  `ref`. Si el remoto no responde, `plan`, `status` y `check` avisan y comparan con esa revisión; un apply falla
  antes de escribir.
- `updates` pisa `updates.mode` solo para el contenido. En `pinned`, cada apply proyecta el contenido de la revisión
  del lock (`source.revision` y `source.origin`), aunque el pack publique una nueva: sumar un profile, recrear un
  asset borrado o adoptar otra fuente no cambia nada del contenido. No hay copia instalada de la que partir, así que
  el primer apply adopta la `ref`, también en `pinned`. En un repositorio `pinned`, `sources.golfo.updates: auto`
  hace que el inicio de sesión adopte el contenido solo, como a un pack en `auto`.
- `agent-ready update golfo --to <tag|rama|commit>` adopta exactamente esa revisión, y `--to` también sirve para un
  pack (`agent-ready update acme --to v2`). La actualización es por fuente, nunca por archivo, y `--dry-run` muestra
  antes qué cambia. El pack oficial publica un tag por versión (`v1.0.0`).
- **Descarga.** La revisión se descarga con Git en la caché del usuario y se compone con el motor instalado en una
  carpeta propia de esa revisión y de ese motor. Un apply siempre la descarga si falta, aunque `updates.refresh`
  esté apagado, y si no puede, falla antes de escribir. `plan`, `status` e `init` también la descargan; sin red,
  `plan` y `status` frenan antes de escribir nada si esta máquina nunca la bajó. El inicio de sesión nunca usa la
  red en primer plano: resuelve la `ref` y descarga en la sincronización en segundo plano, y avisa que el contenido
  todavía no está en la máquina.
- `agent-ready check` compara con el contenido de la revisión del lock. Si no la tiene (sin red o sin acceso al
  repositorio), informa la fuente como no disponible, bajo el `ci.mode` vigente, en vez de cambios que un apply no
  haría. `agent-ready profiles list|add|remove` e `init` eligen del catálogo de esa revisión.
- **El motor nunca se fija.** Los scripts, los hooks (`assets/common/hooks/`, que se actualizan solos en cada sync),
  los templates de `.claude/settings.json` y `.codex/hooks.json` que los conectan, los schemas de configuración,
  `providers.json` y los profiles de CI con sus archivos (`assets/ci/`) siguen siempre al plugin instalado. Un motor
  nuevo no frena la sincronización de un contenido fijado: solo cambia lo que es del motor. El lock registra la
  versión del contenido en `source.version` y la del motor en `generator.version`.
- **Formato del pack.** Un `agent-ready-pack.json` en la raíz con `schemaVersion`, `name`, `version` (obligatoria)
  y, si hace falta, `minEngine` y `changes` («Compatibilidad declarada», en [profile-packs.md](profile-packs.md)), sus `profiles` y `baseAssets`:
  - **Base:** `baseAssets` es la carpeta de la base que recibe todo repositorio. Lleva `rules/`, `skills/`, `blocks/`
    y `agents-template.md`, el template de `AGENTS.md`, que es obligatorio. Los hooks y los settings son del motor.
    La base y cada profile pueden traer también `evals/`, los evals de sus rules: el motor los acepta y nunca los proyecta.
  - **Profiles:** se nombran sin prefijo (`node`, no `acme/node`), con los campos de [profiles.md](profiles.md), y ninguno se
    llama `common`, el nombre que el motor le da a la base. Sus `assets` publican lo mismo que un pack (`rules/`,
    `skills/`, `agents/`, `commands/`, `blocks/`, `nested/`) y, en una capability, `agents-skeleton.md`, el
    esqueleto de `AGENTS.md` (como `software-development`). Un profile no puede poner sus assets en una carpeta
    que usa el motor (`ci/`, `codex/`, `config/`, …).
  - **CI:** los profiles de CI (`kind: ci`) siempre salen del catálogo del motor (`assets/ci/profiles.json`),
    porque sus workflows corren el CLI de esa versión. Un pack de contenido que declara uno falla antes de escribir.
  - **Validación:** un repositorio sin `agent-ready-pack.json`, sin `baseAssets`, con un symlink o con algo que no
    puede publicar frena el apply, el plan y el status antes de escribir.
- **Precedencia:** la base y el template salen solo del contenido: hay uno por repositorio. Un pack de
  `sources.packs` no puede declarar `baseAssets` ni llamarse `golfo`. El gate de colisiones de [profile-packs.md](profile-packs.md) compara
  la base con los profiles y con los packs.
- **Override de desarrollo.** `AGENT_READY_SETUP_CONTENT_DIR=<carpeta absoluta>` toma el contenido de un checkout
  local del pack tal como está, sin Git, sin `ref` y sin la revisión del lock: sirve para probar un cambio del pack
  antes de publicarlo y para los tests del motor. El lock registra `source.kind: "local"`, sin `revision`, con el
  `contentDigest` de lo proyectado.
- El lock nombra la fuente en `source`: `name` (`golfo`), `version`, `kind` (`git` o `local`), `revision`,
  `origin`, `requestedRef` y `contentDigest`; `status` la muestra como `golfo 1.0.0 (git, revision <commit>, from
  <origin>; ...)`.

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
