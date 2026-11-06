# Sincronización posterior al upgrade

Antes de cualquier escritura, el hook lee `.agents/agent-ready.json`. Con
`updates: pinned` (default) o `AGENT_READY_SETUP_REVIEW_MODE=1` solo informa el
estado y termina sin escribir; lo de abajo describe un apply (bootstrap, o el
hook con `updates: auto` o sin manifest). Manifest, lockfile, profiles y
ownership: [profiles-and-lockfile.md](profiles-and-lockfile.md).

El upgrade del marketplace usa la CLI del provider activo
(`claude plugin marketplace update golfo-marketplace` o
`codex plugin marketplace upgrade golfo-marketplace`) y actualiza la copia global
del marketplace; no vuelve a proyectar por sí mismo los templates sobre un proyecto
ya preparado. `bootstrap.sh` ejecuta ese upgrade automáticamente para el provider
activo antes de proyectar assets o adquirir lock local.
`codex plugin marketplace upgrade` solo refresca marketplaces Git: si
`~/.codex/config.toml` declara `source_type = "local"` para `golfo-marketplace`
(lo que registra `codex plugin marketplace add "$PWD/golfo-marketplace"`),
`bootstrap.sh` y el hook omiten el upgrade y resuelven assets desde ese `source`.
El hook canónico `.agents/hooks/sync-marketplace.sh` ejecuta el upgrade salvo que
haya uno exitoso de menos de 60 minutos para el mismo provider (marca en
`${XDG_CACHE_HOME:-~/.cache}/agent-ready-setup/marketplace-upgrade-<provider>.stamp`,
escrita solo tras un upgrade exitoso); `AGENT_READY_SETUP_FORCE_UPGRADE=1` lo
fuerza y `bootstrap.sh` lo ejecuta siempre. El upgrade es lo único sincrónico que
usa red: proyecta todos los assets gestionados, ejecuta la normalización recursiva de
instrucciones mediante `scripts/normalize-instructions.sh` y aplica el bloque gestionado
literal de `AGENTS.md` con `scripts/apply-managed-block.sh`, todo local, para que la
sesión que arranca ya los vea. Lo que usa red o un LLM corre desacoplado mediante
`scripts/run-detached.py`, con log en `${XDG_CACHE_HOME:-~/.cache}/agent-ready-setup/`:
la revisión de redundancias de `scripts/merge-instructions.sh`. La normalización
incluye `CLAUDE.md` bajo `.claude/` y conserva conflictos, symlinks y archivos no
regulares.
El upgrade solo refresca el snapshot del marketplace del provider (Claude:
`installLocation` de `~/.claude/plugins/known_marketplaces.json`, por defecto
`~/.claude/plugins/marketplaces/golfo-marketplace`; Codex: `source` local de
`~/.codex/config.toml` o `~/.codex/.tmp/marketplaces/golfo-marketplace`); el cache
versionado del plugin avanza recién con `/plugin` update. Por eso el hook resuelve
la fuente desde ese snapshot salvo que el cache tenga una versión semver mayor, y
proyecta la última versión publicada sin depender de la versión instalada del plugin.
`bootstrap.sh` aplica el mismo criterio y reporta la fuente elegida en `Resolved agent-ready-setup source: <path>`.
Si la fuente resuelta no contiene `scripts/asset-sync-common.sh`, el hook ejecuta un
refresh adicional de `golfo-marketplace`, vuelve a resolver la fuente y carga helper
mediante `source` antes de proyectar cualquier asset. Si refresh no entrega helper,
conserva hook local, omite proyección y muestra diagnóstico; no instala un
`sync-marketplace.sh` que no pueda arrancar.
Si la copia instalada del hook cambió, se reejecuta con el mismo provider y stack
antes de proyectar el resto. La reejecución conserva el lock de assets y usa una
guarda interna para no repetir el upgrade inicial; refresh por helper faltante solo
se intenta antes de cargar helper. `normalize-instructions.sh` no repite proyección
ni upgrade.

El hook compara cada asset gestionado con el template actualizado y muestra
`diff -u` antes de reemplazar un archivo existente. Reemplaza los assets
gestionados aunque se hayan editado y guarda su contenido local en un directorio
temporal externo al proyecto; el output muestra el path exacto. Solo preserva, como
conflicto, los archivos que ningún apply escribió (sección «Ownership» de
[profiles-and-lockfile.md](profiles-and-lockfile.md)). Sin lockfile previo, el
primer apply también reemplaza esos archivos una vez. Directorios en paths gestionados, padres inseguros y cambios
concurrentes se preservan y se reportan como conflictos estructurales.

#### Riesgos del upgrade automático

- Cada upgrade necesita la CLI del provider (`claude` o `codex`) y red; si upgrade falla,
  bootstrap y hook terminan antes de modificar assets locales y no registran la
  ventana de 60 minutos.
- Dentro de esa ventana, una versión recién publicada del marketplace puede
  tardar hasta 60 minutos en llegar por SessionStart; usar
  `AGENT_READY_SETUP_FORCE_UPGRADE=1` o `bootstrap.sh` para aplicarla antes.
- Upgrade global no tiene rollback en este script; la versión descargada puede
  cambiar aunque proyección local quede bloqueada.
- Con `updates: auto`, el hook aplica templates nuevos al iniciar sesión y pisa los
  cambios locales de los assets gestionados, sin pedir confirmación. Symlinks,
  conflictos estructurales y reemplazos atómicos siguen evitando seguir o
  sobrescribir destinos inseguros.
- Lock protege proyección local concurrente, pero no serializa upgrades globales
  del marketplace entre procesos distintos.

La proyección automática de assets:

- Actualiza assets gestionados bajo `.agents/`, settings específicos de
  `.claude/`, y bridge/configuración bajo `.codex/`.
- Copia adapters `SKILL.md` bajo `.agents/skills/` byte a byte desde su
  template, sin reescribir frontmatter: providers eligen skills según
  `description`, por lo que el template es la única fuente.
- En `.claude/`, agents y commands se registran una sola vez (`.claude/agents/`,
  `.claude/commands/`); su adapter en `.agents/skills/` queda solo para Codex.
  El sync elimina vistas `.claude/skills/<nombre>/` gestionadas que dupliquen un
  agent o command y preserva y reporta contenido custom.
- Claude Code carga `.claude/rules/` automáticamente; el bloque gestionado de
  `AGENTS.md` le indica no volver a leerlas y deja las referencias para Codex.
- Reemplaza symlinks en paths gestionados sin seguirlos: borra el link y escribe el
  template, así nunca modifica el destino del link. Con lockfile, un symlink en un
  path que ningún apply escribió es un conflicto.
- Elimina symlinks administrados stale bajo `.claude/`.
- Sin privilegio para crear symlinks (Windows sin Modo de desarrollador ni shell
  elevada), crea cada vista como hard link al asset de `.agents/`, nunca como
  copia, y la registra en `.claude/.agent-ready-hard-link-views`. Cada sync
  reenlaza las vistas que git desconectó al recrear el asset y poda, solo entre
  las registradas, las de assets borrados. Mientras existan vistas por hard link
  registra en la config local de git el hook `hook.agent-ready-relink`
  (`post-index-change`), que corre `.agents/hooks/relink-hard-link-views.sh` después
  de reset, stash, cherry-pick, revert o abortar un merge o rebase. Al ser un hook
  por config convive con `core.hooksPath` (husky, lefthook) y con hooks propios sin
  tocarlos. Si la versión de git no soporta hooks por config, instala el archivo
  `.git/hooks/post-index-change`; con `core.hooksPath` o un hook propio no lo pisa
  y lo reporta como conflicto.
- El hook `UserPromptSubmit` de Claude Code corre el mismo script en cada prompt.
  Cubre `git apply` sin `--index`, que reescribe archivos sin disparar ningún hook
  de git. No imprime nada salvo avisos, porque Claude agrega la salida al prompt.
- Combina el template con `.claude/settings.json` como JSON, preservando campos
  custom y reportando settings inválidos.
- Normaliza `CLAUDE.md` raíz y anidados, incluido `.claude/CLAUDE.md`, mediante
  `scripts/normalize-instructions.sh`; crea o actualiza únicamente el `AGENTS.md`
  hermano cuando puede preservar el contenido sin ambigüedad.
- No elimina assets desconocidos (rules, skills o archivos propios del
  proyecto); solo escribe paths que publica agent-ready-setup y solo retira los
  que el lockfile registra como aplicados y siguen sin cambios.
- Instala o registra herramientas de browser solo si un profile seleccionado lo
  declara (`browser`).

El paso posterior sobre instrucciones actualiza únicamente `AGENTS.md`; nunca
modifica `CLAUDE.md` directamente.

Para sincronizar manualmente desde un hook existente:

```bash
bash .agents/hooks/sync-marketplace.sh --provider claude
# o
bash .agents/hooks/sync-marketplace.sh --provider codex
```

Si la fuente instalada no se puede resolver o el stack no se detecta, el hook
conserva el upgrade global y muestra cómo indicar `AGENT_READY_SETUP_SKILL_DIR`,
`--stack frontend|node|java|go` o `--profiles <a,b>`. Sin flags, el hook usa los
profiles del manifest y solo detecta el stack cuando no hay manifest.
`AGENT_READY_SETUP_STACK=<stack>` y `AGENT_READY_SETUP_PROFILES=<a,b>` equivalen a
las flags (las flags tienen precedencia). En un repositorio `pinned`, solo las
flags `--stack` o `--profiles` en la línea de comandos convierten el chequeo en
un apply explícito; las variables de entorno no.
