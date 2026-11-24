# Sincronización posterior al upgrade

Antes de cualquier escritura, el hook valida la configuración efectiva (todas las capas de
[configuration.md](configuration.md)). Con `updates.mode: pinned` o `AGENT_READY_SETUP_REVIEW_MODE=1`
solo informa el estado y termina sin escribir; con `updates.enabled: false` no hace nada. Con
`updates.mode: auto` (el default), SessionStart lanza lo de abajo desacoplado y no hace esperar a la
sesión; lo de abajo describe un apply (bootstrap, o esa sincronización). Manifest, lockfile y
ownership: [profiles-and-lockfile.md](profiles-and-lockfile.md); profiles: [profiles.md](profiles.md).

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
`bootstrap.sh` también lo omite cuando el motor corre desde un checkout, fuera de `~/.claude`,
`$CODEX_HOME`, `CLAUDE_PLUGIN_ROOT` y las carpetas de Hermes: ese motor se usa tal cual y el contenido sale
de `sources.golfo`, así que el upgrade no cambiaría nada de la corrida y solo reemplazaría el clon del
marketplace de la máquina. `AGENT_READY_SETUP_UPGRADE_FROM_CHECKOUT=1` lo hace igual.
El hook canónico `.agents/hooks/sync-marketplace.sh` ejecuta el upgrade salvo que
haya uno exitoso de menos de 60 minutos para el mismo provider (marca en
`${XDG_CACHE_HOME:-~/.cache}/agent-ready-setup/marketplace-upgrade-<provider>.stamp`,
escrita solo tras un upgrade exitoso); `AGENT_READY_SETUP_FORCE_UPGRADE=1` lo
fuerza y `bootstrap.sh` lo ejecuta siempre. Después proyecta todos los assets gestionados,
ejecuta la normalización recursiva de instrucciones mediante
`scripts/normalize-instructions.sh` y aplica el bloque gestionado literal de `AGENTS.md`
con `scripts/apply-managed-block.sh`. Toda esa sincronización corre desacoplada de la
sesión mediante `scripts/run-detached.py`, con log en
`${XDG_CACHE_HOME:-~/.cache}/agent-ready-setup/`, igual que la revisión de redundancias de
`scripts/merge-instructions.sh`. La normalización
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
- Con `updates.mode: auto`, el hook aplica templates nuevos al iniciar sesión y pisa los
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
- Genera `.codex/agents/<nombre>.toml` desde cada `agents/<nombre>.md` con
  `render-codex-agent.py`, el mismo código con el que el plan calcula su sha256, así que el
  sync y el apply escriben los mismos bytes.
- En `.claude/`, agents y commands se registran una sola vez (`.claude/agents/`,
  `.claude/commands/`); el adapter de un command en `.agents/skills/` queda solo para Codex,
  y un agent le llega a Codex como subagente nativo, sin adapter.
  El sync elimina vistas `.claude/skills/<nombre>/` gestionadas que dupliquen un
  agent o command y preserva y reporta contenido custom.
- Claude Code carga `.claude/rules/` automáticamente; el bloque gestionado de
  `AGENTS.md` le indica no volver a leerlas y deja las referencias para Codex.
- Reemplaza symlinks en paths gestionados sin seguirlos: borra el link y escribe el
  template, así nunca modifica el destino del link. Con lockfile, un symlink en un
  path que ningún apply escribió es un conflicto.
- Elimina symlinks administrados stale bajo `.claude/`.
- Sin privilegio para crear symlinks (Windows sin Modo de desarrollador ni shell
  elevada), o en un repo con `core.symlinks=false` (el default de Git para Windows), crea
  cada vista como hard link al asset de `.agents/`, nunca como copia, y la registra en
  `.claude/.agent-ready-hard-link-views`. Con `core.symlinks=false`, git escribe un symlink
  commiteado como un archivo con la ruta del link: un clon nuevo tendría vistas que no son
  la rule. Un hard link se commitea como un archivo común. Cada sync
  reenlaza las vistas que git desconectó al recrear el asset y poda, solo entre
  las registradas, las de assets borrados. Mientras existan vistas por hard link
  registra en la config local de git el hook `hook.agent-ready-relink`
  (`post-index-change`), que corre `.agents/hooks/relink-hard-link-views.sh` después
  de reset, stash, cherry-pick, revert o abortar un merge o rebase. En una rama
  sin ese script, como una anterior a la adopción, el hook sale en silencio. Al ser un hook
  por config convive con `core.hooksPath` (husky, lefthook) y con hooks propios sin
  tocarlos. Si la versión de git no soporta hooks por config, instala el archivo
  `.git/hooks/post-index-change`; con `core.hooksPath` o un hook propio no lo pisa
  y lo reporta como conflicto.
- El hook `UserPromptSubmit` de Claude Code corre el mismo script en cada prompt.
  Cubre `git apply` sin `--index`, que reescribe archivos sin disparar ningún hook
  de git. No imprime nada salvo avisos, porque Claude agrega la salida al prompt.
- Combina el template con `.claude/settings.json` como JSON, preservando campos
  custom y reportando settings inválidos.
- Con `antigravity` entre los providers, combina `assets/antigravity/hooks.json` con
  `.agents/hooks.json` (`merge-antigravity-hooks.py`). Antigravity agrupa sus hooks por
  nombre: el apply es dueño del nombre `agent-ready`, que reemplaza entero, y preserva
  los demás nombres del proyecto. Un JSON inválido es un conflicto y el archivo no se
  toca. Sin Antigravity, el nombre `agent-ready` sale, y un archivo que solo tenía ese
  nombre se borra. Declara dos hooks:
  - `SessionStart`: `sync-marketplace.sh --provider antigravity`, con el upgrade del
    marketplace salteado (Antigravity no tiene marketplace de plugins).
  - `PostToolUse` con el matcher `write_to_file|replace_file_content|multi_replace_file_content`:
    `check-harness-consistency.sh`, que revisa la raíz de la rule o skill editada.
    Antigravity manda en stdin `{"toolCall": {"name", "args"}}` y nombra el archivo en
    `args.TargetFile` o `args.AbsolutePath`. Un `PostToolUse` de Antigravity responde un
    objeto JSON sin campo para darle contexto al modelo: el hook imprime `{}`, deja el
    reporte en stderr y los hallazgos quedan en la caché para `agent-ready status` y `plan`.
  Los hooks de aprendizaje (`learning-hook.sh`) no se proyectan todavía en Antigravity: le
  devuelven contexto al agente, y Antigravity lo pide en otra forma (`injectSteps`).
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

Para sincronizar manualmente desde un hook existente, en primer plano:

```bash
AGENT_READY_SETUP_SYNC_FOREGROUND=1 bash .agents/hooks/sync-marketplace.sh --provider claude
# o
AGENT_READY_SETUP_SYNC_FOREGROUND=1 bash .agents/hooks/sync-marketplace.sh --provider codex
```

Si la fuente instalada no se puede resolver o el stack no se detecta, el hook
conserva el upgrade global y muestra cómo indicar `AGENT_READY_SETUP_SKILL_DIR`,
`--stack react|nextjs|nextjs-app-router|node|java|go|android` o `--profiles <a,b>`. Sin flags, el hook usa los
profiles del manifest y solo detecta el stack cuando no hay manifest, con el mismo
evaluador que bootstrap: si la detección es ambigua, lista las coincidencias y omite la
proyección (ver [detection.md](detection.md)).
`AGENT_READY_SETUP_STACK=<stack>` y `AGENT_READY_SETUP_PROFILES=<a,b>` equivalen a
las flags (las flags tienen precedencia). En un repositorio `pinned`, solo las
flags `--stack` o `--profiles` en la línea de comandos convierten el chequeo en
un apply explícito; las variables de entorno no.
