# Capacidades de agente: detección, equivalencias y fallbacks

Leer este archivo cuando una skill de `golfo-kit` necesite una herramienta que no todos los agentes tienen: preguntar con opciones, monitorear procesos, programar tareas, lanzar subagentes, invocar otra skill, plan/todos, widgets, verificar en un navegador, hooks, MCP o rutas de configuración. Es la única fuente de verdad de estas equivalencias; cada skill lista en su sección «Compatibilidad entre agentes» solo sus adaptaciones propias.

El [reporte de compatibilidad](compatibility-report.md) describe qué se verificó por skill y por agente. **No es la fuente de verdad para decidir qué ejecutar**: en cada ejecución la skill verifica las capacidades realmente disponibles con el protocolo de abajo, aunque el reporte diga otra cosa.

## Protocolo (obligatorio en cada skill que use una capacidad de esta tabla)

1. **Detectar** el agente con las señales de [Detección](#detección). Es solo una pista para elegir qué nombre de herramienta buscar primero.
2. **Verificar la herramienta concreta**: la fuente de verdad es que la herramienta figure en la lista de herramientas de la sesión (incluidas las diferidas que se cargan con `ToolSearch`, `tool_search`/`tool_describe` o equivalente) o que el comando esté en `PATH` (`command -v <cmd>`). Los nombres varían entre builds del mismo agente (por ejemplo Hermes expone `terminal` o `mcp__terminal`, y `process` o `process_manage`); buscá por nombre base y leé el schema antes de llamar.
3. **Usar la alternativa** de la [tabla](#tabla-de-capacidades) si la herramienta preferida no está. Una alternativa es cualquier mecanismo que logre el **mismo resultado** aunque se implemente distinto (otro plugin, otro CLI, un script, otra forma de entregar el resultado); buscala también en el [inventario](#inventario-de-capacidades-por-agente). Que la implementación original dependa de un agente no hace incompatible la funcionalidad.
4. **Si no hay alternativa**, desactivar **solo** la parte que la necesita, bloquearla en la ejecución (no llamarla, no simularla, no reemplazarla por un bucle sin tope) y seguir con el resto.
5. **Reportar** al cierre una sección `Limitaciones del agente` con: capacidad faltante, parte desactivada, alternativas evaluadas y por qué no aplicaron, y cómo obtener la funcionalidad completa (por ejemplo, correr la skill en otro agente). Si no hubo limitaciones, omitir la sección.

Reglas que valen siempre:

- Nunca simular una herramienta inexistente (por ejemplo, escribir en el chat «llamé a `Monitor`» o fabricar el resultado de un subagente).
- Nunca dejar un proceso sin supervisión: todo proceso en background tiene un timeout y un dueño que lo espera o lo mata antes de terminar la sesión.
- Nunca un bucle sin tope: toda espera tiene timeout e iteraciones máximas, y su vencimiento termina con un código o mensaje explícito.
- Una falla de capacidad nunca es silenciosa: si una rama se desactivó, aparece en `Limitaciones del agente`.

## Detección

Señales verificadas en esta máquina el 2026-10-23 (ver evidencia en el [reporte](compatibility-report.md)):

| Agente | Versión probada | Variables de entorno en sus comandos de shell | Otras señales |
|---|---|---|---|
| Claude Code | 2.1.309 | `CLAUDECODE=1`, `CLAUDE_CODE_ENTRYPOINT` (`cli`, `sdk-cli`, …), `CLAUDE_CODE_SESSION_ID` | Herramientas `Read`/`Edit`/`Bash`/`Skill`/`ToolSearch`; skills en `~/.claude/skills` o plugins con `CLAUDE_PLUGIN_ROOT` |
| Codex CLI | 0.162.1 | `CODEX_SESSION_ID`, `CODEX_THREAD_ID`, `CODEX_VERSION`; `CODEX_CI=1` en `codex exec` | Herramientas `exec_command`, `write_stdin`, `apply_patch`; skills en `$CODEX_HOME/skills` (default `~/.codex`) o `~/.agents/skills` |
| Hermes Agent | 0.22.4 | `HERMES_AGENT=true`, `AI_AGENT=hermes-agent`, `HERMES_SESSION_ID`, `HERMES_HOME` | Herramientas `terminal`, `clarify`, `delegate_task`, `skill_view` (con o sin prefijo `mcp__`) |

Las variables **se heredan**: un Claude Code lanzado desde una sesión de Hermes ve a la vez `CLAUDECODE=1` y todas las `HERMES_*` (observado en esta auditoría). Por eso:

- Si hay señales de varios agentes, el agente activo es el que expone las herramientas de la sesión actual; las variables solo ordenan la búsqueda.
- Nunca decidir una rama solo por una variable: confirmar siempre con el paso 2 del protocolo.
- Sin señales reconocibles, tratar el agente como «otro» y aplicar el protocolo igual.

## Tabla de capacidades

«No verificado» significa que no se pudo confirmar en esta auditoría: tratalo como no disponible hasta verificarlo en la sesión.

| Capacidad | Claude Code | Codex CLI | Hermes | Fallback | Qué se desactiva si no hay nada |
|---|---|---|---|---|---|
| Preguntar con opciones | `AskUserQuestion` (no aparece en sesiones headless como `claude -p` o `sdk-cli`) | `request_user_input` existe pero solo en modo Plan; en el modo default y en `codex exec` no está disponible | `clarify` (`questions[1..5]` con `choices` ≤ 4 y `multi_select`); devuelve `outcome` `submitted`, `cancelled`, `timed_out` o `undelivered` | Pregunta en texto con opciones numeradas y **detenerse** a esperar la respuesta; si `clarify` devuelve `undelivered`, `timed_out` o `cancelled`, pasar a este fallback | Nada: el fallback en texto conserva la función. Sin usuario (cron, `-q` no interactivo), cortar antes de la acción que necesitaba la respuesta y reportarlo |
| Monitorear procesos o eventos | `Monitor` (stream de eventos, `timeout_ms` máx. 1 800 000) + `TaskStop` | `exec_command` (con `yield_time_ms`) + `write_stdin` permiten esperar un proceso largo **dentro del turno**, leyendo su salida hasta el código de salida; no hay aviso al terminar el turno | `terminal(background=true, notify=true)` (en la doc, `notify_on_complete`) + `process`/`process_manage` (`poll`, `wait` con `timeout`, `kill`, `log`) | Script de espera acotada en foreground con timeout y tope de iteraciones, repetido dentro del turno | La espera desatendida **después** del turno: la skill explica cómo relanzarla |
| Tareas programadas | `CronCreate`/`CronList`/`CronDelete` (de sesión) y `/loop` | No en el CLI. La app de escritorio expone automatizaciones (`automation_update`) por el MCP `codex_app` del plugin `codex-app-tools`, pero sus herramientas las sirve la app (`CODEX_APP_TOOLS_PIPE_PATH`), así que no existen en `codex exec` ni se verificaron | `cronjob`/`cronjob_manage` (`create`, `list`, `remove`, `repeat`); cada disparo corre en una sesión nueva sin contexto ni preguntas | Cron del SO o Task Scheduler con `codex exec`/`codex exec resume`/`claude -p`/`hermes chat -q`, o GitHub Actions: crean un scheduler persistente fuera de la sesión, así que solo con pedido explícito del usuario | La recurrencia dentro de la sesión: la skill corre una vez (o espera dentro del turno) y lo reporta |
| Subagentes | `Agent` (alias `Task`), en background con handle | `spawn_agent`/`wait_agent`/`list_agents` (`multi_agent` activo en 0.162.1) | `delegate_task` (`tasks[]` en paralelo, `action` `spawn`/`list`/`stop`); los hijos no pueden usar `clarify` ni `cronjob` y mueren con el padre | Ejecutar en el mismo contexto, secuencial | El paralelismo; si la skill exige aislamiento de contexto, ver la fila siguiente |
| Revisor aislado de solo lectura | `Agent` con herramientas de lectura | `spawn_agent` no tiene modo de solo lectura. `codex exec -s read-only` en Windows bloquea **todo** proceso del agente (también leer: `CreateProcessAsUserW failed: 5`, igual con `windows.sandbox="elevated"`); en Linux/macOS no verificado | `delegate_task` hereda los toolsets del padre: no aísla | Proceso externo `claude -p "<prompt>" --tools "Read,Grep,Glob" --permission-mode dontAsk < /dev/null` desde cualquier agente con `claude` en `PATH` (verificado: lee y no puede escribir) | El aislamiento: el filtro corre inline y se reporta |
| Plan / todos | `TodoWrite` o `TaskCreate` según versión (ninguno apareció en la sesión `sdk-cli` probada) | `update_plan` no estaba en la sesión probada; hay `create_goal`/`update_goal`, que no son equivalentes | `todo` / `todo_list` | Lista de pasos en el mensaje | Nada |
| Worktrees | `EnterWorktree`/`ExitWorktree` + `git worktree` | `codex exec --worktree` (flag de arranque) + `git worktree` | `hermes chat --worktree` (flag de arranque) + `git worktree` | `git worktree` por shell | Nada si hay `git` |
| Widgets visuales | `mcp__visualize__show_widget` (solo Claude con ese conector; no aparece en sesiones headless) | Plugin `visualize@openai-bundled` (skill `visualize`; se habilita con `[plugins."visualize@openai-bundled"] enabled = true` en `$CODEX_HOME/config.toml`). No es una herramienta: el agente escribe un fragmento HTML en un directorio escribible del task y pone `visualize{"path":"<ruta-absoluta>.html"}` en una línea propia de la respuesta final; variantes con `.viz-carousel`, acciones que siguen la conversación con `window.openai.sendFollowUpMessage`. La skill aparece también en `codex exec`, pero solo la app de escritorio renderiza el visual: en el CLI y en `codex exec` la referencia queda como texto, así que ahí corresponde el preview estático. Señal de la app: sus herramientas `codex_app` en la sesión (inferido de `codex-app-tools`; no verificado desde la app) | Sin widget en el chat. Preview estático: HTML autocontenido renderizado a PNG con un navegador headless (`chrome --headless=new --screenshot`) o con `browser_exec` + `capture_screenshot()`, mostrado por ruta (CLI) o subido por el gateway (Telegram/Slack/Discord), y elección con `clarify` | Preview estático, igual que Hermes, en cualquier agente con shell y un navegador | El render: sin shell ni navegador, la skill se detiene |
| Navegador real del usuario y capturas | Claude in Chrome (`mcp__claude-in-chrome__*`). El panel de navegador integrado de Claude no es el navegador del usuario | Plugin `chrome@openai-bundled`: el Chrome del usuario vía la extensión, desde el runtime `mcp__cua_repl.js`/`node_repl` (`agent.browsers.list()` → `type: "extension"`, `family: "chrome"`); funciona en `codex exec` (verificado: abrió localhost en el perfil real, `webdriver=false`, captura JPEG). El plugin `browser` (navegador in-app, backend `iab`) no es el navegador del usuario | `computer_use` sobre la ventana real de Chrome (mueve mouse y teclado: avisar antes). `browser_exec` por defecto es Chromium **headless** con perfil descartable (verificado; además falló al arrancar 4 de 5 veces); con `browser.use_real_profile: true` + `browser.headed: true` usa el binario real sobre una copia del perfil (doc, no verificado) | Navegador headless (Playwright, `--headless`), embebido (`iab`, panel integrado) o con perfil descartable (`browser_exec` por defecto): solo para comprobar que una página carga, nunca para capturas publicadas. Una skill que solo necesita evaluar JavaScript en la página (sin publicar la imagen) puede usarlos si la pantalla no requiere la sesión del usuario: ver la fila siguiente | Las capturas publicadas: se omiten con el motivo |
| Verificar en un navegador (consola, métricas, estados de UI) | Claude in Chrome (`mcp__claude-in-chrome__*`: consola, JavaScript, clics) o un MCP de navegador conectado (Chrome DevTools, Playwright). No estaban conectados en la sesión probada: no verificado | Plugin `chrome@openai-bundled`: `tab.reload()` + `tab.dev.logs({ levels: ["error", "warn"] })` lee la consola de la carga y `tab.playwright.getByRole(...).click()` recorre estados (verificado). Su `tab.playwright.evaluate` corre en un scope de solo lectura **sin `performance` ni `PerformanceObserver`** (verificado): las métricas salen por terminal. `browser@openai-bundled`/`browser-use` (`iab`) sirve para localhost y `file://` solo en la app de escritorio (no probado) | `browser_exec` (Chromium headless, perfil descartable) sirve para localhost o staging **sin login**, cuando arranca: en esta máquina falló al arrancar 7 de 9 veces (`Chrome exited early … DevToolsActivePort`); si falla dos veces seguidas, pasar al fallback. `computer_use` solo para pantallas que necesitan la sesión del usuario, con aviso y consentimiento (no ejecutado) | [Verificación en navegador por terminal](#verificación-en-navegador-por-terminal): Lighthouse, Chrome headless con log de consola y Playwright con el Chrome instalado, desde cualquier agente con shell (verificado en Claude Code, Codex y Hermes). Headless no tiene la sesión del usuario: solo localhost/staging sin login o con credenciales de prueba del proyecto | La verificación en navegador: la skill la reporta como `BLOCKED` (nunca como `PASS`), dice qué quedó sin verificar y cómo verificarlo |
| MCP | `claude mcp`; config en `~/.claude.json` / `.mcp.json` | `codex mcp`; `[mcp_servers]` en `$CODEX_HOME/config.toml` | `mcp_servers` en `$HERMES_HOME/config.yaml` | — | Las herramientas de ese servidor |
| Hooks | `hooks` en `settings.json` | Feature `hooks` activo; formato no verificado en esta auditoría | `hooks:` en `config.yaml` (shell hooks), `HOOK.yaml` de gateway | — | La automatización del hook; hacer la acción a mano y reportarlo |
| Rutas de config | `~/.claude` (o `$CLAUDE_CONFIG_DIR`) | `$CODEX_HOME` (default `~/.codex`) | `$HERMES_HOME` (default `~/.hermes`; `%LOCALAPPDATA%\hermes` en Windows) | Preguntar la ruta | — |
| Invocar otra skill | `Skill` / `/<skill>` | Mención `$<skill>` o leer su `SKILL.md` (la mención no se verificó en esta auditoría) | `skill_view(name)` o `/<skill>` si está instalada; `hermes chat -s <skill>` para precargar | Leer el `SKILL.md` de la skill por path y seguirlo | Nada si el archivo existe |
| Registrar cobertura de skills ([`skill-coverage`](skill-coverage.md)) | `node <plugin>/tools/skill-coverage/skill-coverage.mjs` por `Bash` | El mismo comando por `exec_command` | El mismo comando por `terminal` | Cualquier shell con `node` ≥ 20 en `PATH`; sin el parser de Babel del proyecto, comparación por archivo completo (más conservadora) | Ninguno que registre: la skill termina su trabajo pero cierra **incompleta** (cobertura sin registrar), con el motivo concreto (sin `node`, CLI no encontrado, error literal de `add-unit` o `record`) y qué falta para registrar por unidad; nunca como completa ni solo como limitación ([Cierre incompleto o bloqueado](skill-coverage.md#cierre-incompleto-o-bloqueado)) |
| Notificación push | `PushNotification` | No existe en la sesión; el `notify` de `config.toml` dispara un programa al terminar cada turno, no un aviso a pedido | En el gateway, el propio mensaje llega al chat (Telegram); desde cualquier shell, `hermes send --to <destino> "<texto>"` reutiliza las credenciales del gateway (`hermes send --list` mostró `telegram`; no se envió nada en la auditoría) | Línea en el mensaje del chat | Nada |

## Verificación en navegador por terminal

Mecanismos que no dependen del agente: sirven en Claude Code, Codex y Hermes con una terminal, y son el fallback de la fila «Verificar en un navegador». Verificados el 2026-10-23 desde los tres agentes sobre una página local servida con `python -m http.server` (Chrome 156, Lighthouse 12.8.2, `playwright-core` 1.64.1). Antes de usarlos, comprobá que existan (`command -v npx`, el binario de Chrome o Chromium, o `CHROME_PATH`).

| Necesidad | Comando | Qué devuelve |
|---|---|---|
| Métricas de carga (LCP, CLS, TBT, FCP) | `npx -y lighthouse@12 <url> --output=json --output-path=<archivo>.json --quiet --only-categories=performance --chrome-flags="--headless=new"` | `audits["largest-contentful-paint"]`, `["cumulative-layout-shift"]`, `["total-blocking-time"]`, `["first-contentful-paint"]` con throttling simulado. Usa el Chrome instalado |
| Consola de la carga (warnings de hidratación, errores) | `chrome --headless=new --disable-gpu --user-data-dir=<carpeta temporal nueva> --enable-logging --log-file=<archivo>.log --v=0 --virtual-time-budget=3000 --dump-dom <url>`, y buscar las líneas `CONSOLE` del log | Cada mensaje de consola emitido al cargar, con la URL y la línea. En Windows, `chrome.exe` no escribe en el stdout de Git Bash: lanzarlo con `Start-Process -Wait` de PowerShell y leer siempre el `--log-file` |
| Interacción, estados de UI, consola y `performance` | Playwright del proyecto si está en `package.json`; si no, `playwright-core` instalado en una carpeta temporal **fuera del repo**, con `chromium.launch({ channel: "chrome", headless: true })` para usar el Chrome instalado sin descargar navegadores. `page.on("console", …)` antes de `page.goto`, `page.getByRole(...).click()` para cada estado y `page.evaluate(() => performance.getEntriesByType(...))` para tiempos | Mensajes de consola desde el primer byte, el estado del DOM después de cada acción y métricas de la página. `page.tracing`/`context.tracing` guarda un trace para analizar después |

Reglas:

- Son navegadores headless con perfil descartable: no tienen la sesión, las cookies ni las extensiones del usuario. Usalos para localhost o staging sin login, o con las credenciales de prueba que el proyecto documente; nunca escribas credenciales reales. Si la pantalla necesita la sesión del usuario, usá el navegador real del agente (fila «Navegador real del usuario y capturas») o reportá la verificación como `BLOCKED`.
- No agregues Playwright ni Lighthouse como dependencia del proyecto sin pedirlo: la instalación temporal vive fuera del repo y se borra al terminar.
- Cerrá todo navegador que lances (`browser.close()`, o el proceso con su `--user-data-dir` propio) y borrá las carpetas temporales de perfil.

## Inventario de capacidades por agente

Relevado el 2026-10-23 desde la configuración y los archivos reales de esta máquina, no desde nombres supuestos. Sirve para buscar **alternativas equivalentes** (mismo resultado con otro mecanismo) antes de desactivar una funcionalidad. En runtime manda la lista de herramientas de la sesión.

### Codex (CLI 0.162.1, app de escritorio 26.1013)

Fuente: `[plugins.*]` y `[mcp_servers.*]` de `$CODEX_HOME/config.toml`, los `.codex-plugin/plugin.json`, `skills/*/SKILL.md` y `.mcp.json` de `$CODEX_HOME/plugins/cache/<marketplace>/<plugin>/<versión>/`, y una sesión real de `codex exec` que listó sus herramientas y skills.

| Plugin o servidor | Qué aporta | Superficie |
|---|---|---|
| `visualize@openai-bundled` 1.0.50 | Skill `visualize`: fragmento HTML + `visualize{"path":…}` en la respuesta, `.viz-carousel`, `window.openai.sendFollowUpMessage`, helper `Tweak` | Skill listada en CLI y app; render interactivo en la app |
| `chrome@openai-bundled` | Chrome real del usuario vía extensión: pestañas, sesiones, cookies, extensiones; navegar, clic, escribir, capturas | Runtime `mcp__cua_repl.js` (MCP `cua_repl`) o `node_repl`; verificado en `codex exec`. Consola con `tab.dev.logs`; `tab.playwright.evaluate` sin `performance` (scope de solo lectura) |
| `browser@openai-bundled` / `browser-use` | Navegador in-app (`iab`) para localhost y `file://`: navegar, inspeccionar, clic, capturas | Requiere la app de escritorio (backend `iab`); no probado desde el CLI |
| `computer-use@openai-bundled`, `unified-computer-use@openai-bundled` | Control de apps de escritorio de Windows (capturas, mouse, teclado) | MCP `cua_repl`; no probado en esta auditoría |
| `codex-app-tools@openai-bundled` 0.1.6 | MCP `codex_app`: chats e hilos (`create_thread`, `send_message_to_thread`, `fork_thread`, `handoff_thread`), proyectos, worktrees y automatizaciones (`automation_update`) | Solo app de escritorio: las herramientas las sirve la app por `CODEX_APP_TOOLS_PIPE_PATH`; no aparecen en `codex exec` |
| `code-review@openai-bundled` | MCP de PRs de GitHub (navegar, reviews privadas de Codex, checks, merge manual) | `enabled: false` en su `.mcp.json`; no verificado |
| `github@openai-curated`, `documents`, `pdf`, `spreadsheets`, `presentations`, `template-creator` | Conectores y skills de documentos | Skills listadas en `codex exec` |
| `node_repl`, `engram` (`[mcp_servers]`) | Runtime JS de navegador/escritorio; memoria persistente | CLI y app |

Herramientas de sesión verificadas en `codex exec`: `exec_command`, `write_stdin`, `apply_patch`, `view_image`, `collaboration.spawn_agent`/`wait_agent`/`list_agents`/`send_message`, `create_goal`/`update_goal`, `request_user_input` (solo modo Plan), `web__run`, `image_gen__imagegen`, `mcp__cua_repl.js`. Comandos: `codex exec`, `codex exec resume`, `-s read-only|workspace-write|danger-full-access` (en Windows, `read-only` impide lanzar cualquier proceso).

### Hermes Agent 0.22.4

Fuente: sesión real de `hermes chat -Q -q` que listó sus herramientas, `$HERMES_HOME/config.yaml`, `hermes send --help` y la documentación (<https://hermes-agent.nousresearch.com/docs/user-guide/features/browser>, `…/computer-use`, `…/deliverable-mode`, `…/guides/pipe-script-output`, `…/reference/tools-reference`).

| Herramienta | Qué aporta | Verificación |
|---|---|---|
| `terminal` (`background`, `notify`, `pty`) + `process_manage` | Procesos largos con aviso; `poll`/`wait`/`kill` | Sesión real (auditoría anterior) |
| `cronjob_manage` | Tareas programadas en sesiones nuevas | `tool_describe` |
| `delegate_task` | Subagentes en paralelo (heredan toolsets; no aíslan) | Lista de herramientas |
| `clarify` | Preguntas con hasta 4 opciones + «Otro», `multi_select`; en `-q` no hay quien responda | Doc + lista |
| `browser_exec` | Python con helpers (`goto_url`, `js`, `click_at_xy`, `cdp`, `capture_screenshot`) sobre Chromium por CDP. Por defecto **headless** y con perfil temporal; `browser.use_real_profile`/`browser.headed`/`/browser connect` para el navegador real | Sesión real: headless confirmado (`HeadlessChrome/145`), arranque inestable (falló 4 de 5 y 7 de 9 veces en dos auditorías) |
| `computer_use` (diferida) | Escritorio real con capturas, mouse y teclado | Lista de herramientas; no ejecutada (tomaría el escritorio del usuario) |
| `vision_analyze` | Analizar imágenes locales o URLs | Lista de herramientas |
| `web_search`, `web_extract`, `execute_code`, `read_file`/`write_file`/`patch`/`search_files` | Web y archivos | Lista de herramientas |
| `skill_view`/`skill_manage`/`skills_list`, `tool_search`/`tool_describe`/`tool_call`, `manage_connections`, MCP `engram` | Skills, herramientas diferidas y MCP | Lista de herramientas |
| Entrega de archivos | En gateway, mencionar la ruta absoluta (fuera de bloques de código) sube el archivo; en el CLI solo se da la ruta | Doc; en la sesión CLI `MEDIA:` se imprime como texto |
| `hermes send` (CLI) | Mensaje a Telegram/Slack/Discord/… sin agente | `--help` y `--list` (destino `telegram`) |

No existen en la sesión CLI: `send_message`, herramientas `browser_*` separadas, `process`/`cronjob` con esos nombres (sus equivalentes son `process_manage`/`cronjob_manage`).

### Claude Code 2.1.309

`Monitor`, `TaskStop`, `CronCreate`/`CronList`/`CronDelete`, `/loop`, `AskUserQuestion`, `Agent`/`Task`, `PushNotification`, `mcp__visualize__show_widget` (con el conector), Claude in Chrome (`mcp__claude-in-chrome__*`, con la extensión), `ToolSearch` para herramientas diferidas. `claude -p` corre invocaciones aisladas; con `--tools "Read,Grep,Glob"` queda limitado a lectura (verificado).

### Fuera del agente

Cualquier agente con terminal puede usar otro CLI instalado como alternativa (verificá con `command -v`): `claude -p` como revisor de solo lectura, `codex exec` (con las limitaciones de sandbox de arriba), `hermes chat -q` y `hermes send`; navegadores instalados en modo headless para **renderizar** HTML propio (no para capturar la app del usuario); Lighthouse, Chrome headless con log de consola y Playwright para [verificar en un navegador](#verificación-en-navegador-por-terminal); cron/Task Scheduler del SO y GitHub Actions para recurrencia, solo si el usuario lo pide.

## Evidencia de capacidades

El reporte guarda la evidencia de cada fila (comandos, salidas y fuentes). Las fuentes primarias usadas:

- Claude Code: lista de herramientas de una sesión `sdk-cli` y `claude --version`.
- Codex: `codex --version`, `codex exec --help`, `codex features list` y una corrida de `codex exec` que listó sus herramientas y variables de entorno.
- Codex `visualize`: `.codex-plugin/plugin.json`, `skills/visualize/SKILL.md` y `skills/visualize/tweak.md` del plugin `visualize@openai-bundled` 1.0.50 (caché en `$CODEX_HOME/plugins/cache/openai-bundled/visualize/`).
- Codex `chrome`, `browser`, `computer-use`, `codex-app-tools`: sus `plugin.json`, `.mcp.json` y `docs/` en la caché de plugins; una corrida de `codex exec` que abrió una página local en el Chrome real del usuario y la capturó; otra que corrió `wait-for-pr-event.sh` en foreground con `write_stdin`; y dos de `codex exec -s read-only` que confirmaron el bloqueo del sandbox en Windows.
- Hermes: `hermes --version`, `hermes chat --help`, `hermes tools list`, una corrida de `hermes chat -Q -q` con `tool_describe` de `process_manage`, `cronjob_manage` y `todo_list`, otra que listó todas sus herramientas, otra con `browser_exec` sobre una página local (headless, perfil temporal, arranque inestable), `hermes send --help`/`--list`, y la documentación en <https://hermes-agent.nousresearch.com/docs>.
- Revisor aislado: `claude -p --tools "Read,Grep,Glob"` corrido desde la terminal, desde Codex y desde Hermes, sin poder escribir archivos.
- Verificación en navegador: una página local con un `console.error` de hidratación simulado y cuatro estados de UI. Codex leyó la consola y recorrió los estados con el plugin Chrome (sin acceso a `performance`); Lighthouse, Chrome headless con `--log-file` y `playwright-core` con `channel: "chrome"` corrieron desde Claude Code, `codex exec` y `hermes chat -Q -q`; `browser_exec` de Hermes no arrancó (7 de 9 fallos).
