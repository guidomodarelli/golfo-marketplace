# Browser setup

Bootstrap ejecuta `scripts/setup-browser-tools.py` después de proyectar assets.
Requiere Python 3.11+, Node.js 24+ y npm; no actualiza runtimes ni usa sudo.
Reutiliza `tomlkit` disponible para preservar TOML, o lo instala mediante pip en
directorio privado `browser-tools/python` según `scripts/requirements-browser.txt`;
pip solo hace falta si esa dependencia no está disponible. No instala paquetes
Python en entorno global.
Las versiones de Chrome DevTools MCP, Playwright MCP y agent-browser viven únicamente
en `scripts/browser-tools.json`. npm instala esos paquetes bajo
`~/.local/share/agent-ready-setup/browser-tools/<versions>/`, sin agregar dependencias
al proyecto ni modificar instalaciones globales existentes. Reutiliza paquetes de
la versión fijada y descarga Chromium mediante Playwright cuando falta; los tres
tools usan ese executable, evitando tres descargas de browser. Tras verificar la
instalación, repunta de forma atómica el symlink `browser-tools/current` a esa
versión y regenera un launcher por servidor en
`~/.local/share/agent-ready-setup/browser-tools/bin/<server>`. Los paths de la máquina (paquetes vía `current`, Chromium y flags) viven solo en esos
launchers: un cambio de versión o de Chromium no toca el repositorio.

Registra servidores en la config del proyecto sin paths de usuario ni versiones:
`.mcp.json` raíz (Claude) usa `"command": "${HOME}/.local/share/agent-ready-setup/browser-tools/bin/<server>"`,
porque Claude expande variables; `.codex/config.toml` (Codex) usa `command = "sh"`
con `args = ["-c", "exec \"$HOME/.../bin/<server>\""]`, porque Codex no expande
variables en `command`. Esos archivos pueden commitearse y sirven a todo el equipo.
La config de usuario (`~/.claude.json`, `$CLAUDE_CONFIG_DIR/.claude.json` y
`$CODEX_HOME/config.toml`) solo se lee, nunca se escribe.
Una entrada es gestionada si su `command` o `args` apuntan a
`agent-ready-setup/browser-tools/`; bootstrap la agrega si falta y reemplaza solo
`command`, `args` y `env` si cambió, conservando otros campos como `enabled`.
No agrega un servidor si existe un alias conocido definido por el usuario en el
proyecto, scope usuario o scope local de Claude; no reemplaza sus commands,
credenciales, flags o decisiones de disabled. Conserva mapas TOML inline y
comentarios con editor real, sin convertirlos mediante regex.
JSON/TOML inválido, symlinks y cambios concurrentes se reportan sin sobrescribir.
Los launchers de Chrome DevTools y Playwright usan `--isolated` para evitar
conflictos con perfiles abiertos. En Linux sin `DISPLAY` ni `WAYLAND_DISPLAY`,
agregan `--headless`. Registro parcial conserva progreso: intenta
ambos providers y termina con error si alguno queda pendiente.
Reejecutar bootstrap completa pasos faltantes sin
reinstalar paquetes cuya versión ya coincide.
Reutilización exige también ejecutables presentes; una extracción parcial de npm
vuelve a instalación. El launcher de agent-browser exporta Chromium mediante
`AGENT_BROWSER_EXECUTABLE_PATH`; flag CLI no configura sus invocaciones MCP.

`.agents/browser-tools.json` registra paths de CLI y browser para skill común
`agent-browser`; agents y comandos también pueden usar el MCP registrado. Como
contiene paths de la máquina, el bloque gestionado de `.gitignore` del profile `common`
(`assets/common/blocks/.gitignore`) lo ignora. El setup del navegador no edita `.gitignore`:
si `git check-ignore` no lo cubre, por ejemplo porque el bloque quedó en conflicto, no
escribe el archivo, avisa con `WARNING:` y deja los servidores registrados.
Generar configuración no concede confianza: reiniciar provider y completar su
confirmación de MCP/proyecto cuando corresponda. Codex carga configuración local
solo en proyectos confiables. Bootstrap no modifica confianza, SSO/MFA, remote
debugging ni sesión personal. `cua` se detecta en herramientas expuestas por host;
no tiene instalador portable en este bootstrap.

Instalación fallida deja assets proyectados, termina con exit no cero y permite
reintentar. Diagnóstico de operación fallida queda en log temporal privado cuyo
path se reporta; no imprimir contenido raw. Operaciones externas tienen timeout
de 600 segundos y cancelan procesos hijos al vencer; instalación
simultánea queda bloqueada por lock y requiere reejecución posterior; ese lock
cubre también la regeneración de los launchers. Linux puede
necesitar bibliotecas de sistema para lanzar Chromium; bootstrap no las instala
con privilegios elevados. SessionStart nunca espera instalaciones: ejecuta
`scripts/register-browser-servers.py`, que reutiliza la lógica de
`setup-browser-tools.py`, lee
`~/.local/share/agent-ready-setup/browser-tools/installation.json` (escrito por
bootstrap junto con los launchers) y registra o migra la config del proyecto sin
instalar paquetes, Chromium ni `tomlkit`. Si falta `installation.json` pero existe
la instalación completa de las versiones fijadas (por ejemplo, la que dejó un
bootstrap anterior a los launchers), la adopta solo con comandos locales: ubica
Chromium con el Playwright instalado y crea `current`, los launchers e
`installation.json`, sin npm, descargas ni red. Si otro setup tiene el lock, lo
informa y no cambia nada. Cuando no hay instalación utilizable ni adoptable, o falta
el editor TOML, sale con código 3 y el hook ejecuta `scripts/start-browser-install.py`, que lanza
`setup-browser-tools.py --project <repo>` desacoplado de la sesión, con log privado en
`~/.cache/agent-ready-setup/browser-install.log` (o `$XDG_CACHE_HOME`). Las
herramientas quedan disponibles en la sesión siguiente. Hace a lo sumo un intento
cada 24 horas, registrado en `browser-install-attempt.stamp` en ese mismo
directorio, y no lanza nada si la instalación ya existe, si otro setup tiene el
lock o si faltan Node.js y npm. Sin Node.js no consume el intento: la sesión
siguiente a instalarlo lanza la instalación. Nada de este camino exige haber
ejecutado bootstrap.
Para CI o entorno offline: `tools.enabled: false` (en cualquier capa de
[configuration.md](configuration.md), o `AGENT_READY_SETUP_TOOLS=0` en una corrida) omite instalación
y registro, también en SessionStart; por defecto está encendido. No reportar browser listo si se omitió o falló.

Fuentes: [Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp),
[Playwright MCP](https://github.com/microsoft/playwright-mcp),
[agent-browser](https://github.com/vercel-labs/agent-browser),
[Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).
