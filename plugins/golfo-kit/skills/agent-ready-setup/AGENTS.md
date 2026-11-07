# agent-ready-setup

## Consistencia de instrucciones

Al agregar o modificar una rule, skill, agent, command, template de instrucciones o cualquier otra instrucción de este skill:

1. Antes de cerrar el cambio, verificar que no contradiga ni duplique las instrucciones que se cargan junto con ella:
   - rules comunes de `assets/common/rules/`;
   - rules, skills, agents y commands de `assets/stacks/<stack>/`;
   - bloque gestionado de `AGENTS.md` (`assets/stacks/<stack>/CLAUDE.md` y `assets/instruction-centralization.md`);
   - proxy `assets/claude-proxy.md`;
   - `SKILL.md`.
2. Revisar el mismo cambio en todos los stacks (`frontend`, `node`, `java`, `go`, `android`) cuando aplique. Si una rule aplica igual a todos los stacks, publicarla una sola vez en `assets/common/rules/` en lugar de copiarla en cada stack.
3. Verificar que cada referencia a un archivo o sección apunte a uno existente. Al agregar, renombrar o quitar un asset de `assets/`, actualizar el catálogo de «Step 4 — Report» en `SKILL.md`.
4. Reportar al usuario cada inconsistencia encontrada (contradicción, duplicado o referencia rota) con paths, fragmentos afectados y una recomendación. No resolver en silencio contradicciones que requieran decidir precedencia.

## Assets y configuración gestionados

1. **Portabilidad:** ningún asset ni configuración que el repo pueda commitear contiene paths de la máquina, nombre de usuario ni versiones. Lo específico de la máquina vive bajo `~/.local/share` o `~/.cache`, o en archivos que el setup agrega a `.gitignore`. Para llegar a ese estado desde el repo, usar variables que el provider expanda (`${HOME}` en `.mcp.json`) o un shell (`sh -c` en Codex).
2. **Configuración del usuario:** `~/.claude.json`, `$CLAUDE_CONFIG_DIR/.claude.json`, `~/.codex/config.toml` y equivalentes solo se leen (por ejemplo, para detectar aliases o duplicados); nunca se escriben.
3. **Paridad de providers:** todo registro o asset nuevo se resuelve para Claude Code y Codex, respetando sus diferencias reales (por ejemplo, Codex no expande variables en `command`). Un provider sin soporte se documenta como excepción explícita.
4. **Idempotencia:** ejecutar el mismo sync o bootstrap dos veces seguidas no cambia nada ni reescribe archivos con contenido idéntico.
5. **Sin compatibilidad con versiones anteriores:** cuando cambia el formato, el path o el nombre de algo gestionado, el setup solo conoce el formato actual. No agregar migraciones, limpiezas ni detecciones de lo que dejaron versiones anteriores (archivos, paths, flags, marcadores, hashes o locks viejos); quien tenga una instalación anterior la actualiza a mano. Lo gestionado se identifica con un marcador estable (por ejemplo, un path bajo `agent-ready-setup/browser-tools/`), nunca por nombre o posición, y nunca se toca lo que definió el usuario.
6. **Opciones con uso real:** no agregar flags, variables de entorno ni opciones de configuración sin un llamador que las use; eliminar las que pierdan su último uso.

## Independencia del sync

`assets/common/hooks/sync-marketplace.sh` corre en cada inicio de sesión, también en máquinas donde nadie ejecutó bootstrap ni instaló la skill como plugin: muchas personas del equipo solo reciben el hook commiteado en el repo. Todo cambio en el sync, o en lo que el sync ejecuta, debe funcionar en ese escenario.

1. El sync obtiene la skill del snapshot del marketplace que trae su propio upgrade (o de la cache si es más nueva). Nunca depende de que la skill esté instalada ni de que bootstrap haya corrido.
2. Ninguna operación del sync exige estado creado por bootstrap (instalaciones, metadata, dependencias privadas, archivos generados). Si falta, el sync lo crea, lo adopta de lo que ya existe o lo deja instalando en segundo plano.
3. SessionStart nunca hace esperar a la sesión. El upgrade del marketplace, las fuentes de profiles y la proyección corren desacoplados mediante `scripts/run-detached.py`, con lock, log privado y un límite de reintentos, igual que todo lo que use red o un LLM (instalaciones, descargas, consultas a registries, revisiones con el provider). El resultado se informa en la sesión siguiente. La única excepción es una máquina sin ninguna fuente de la skill: ahí el primer upgrade es sincrónico, porque no hay scripts para desacoplarlo.
4. Los mensajes del sync no piden ejecutar bootstrap ni instalar la skill. Indican qué falta fuera de la skill (por ejemplo, Node.js) o que se reintenta solo.
5. Cada flujo del sync se testea con un `HOME` vacío, sin instalación previa ni skill instalada.

## Entry points de scripts

Cada operación que un script ejecuta en otro (por ejemplo, el hook de sync que normaliza instrucciones o registra servidores MCP) vive en su propio entry point bajo `scripts/`, con un nombre que describa esa operación (`normalize-instructions.sh`, `register-browser-servers.py`).

1. No agregar flags que solo use otro script para activar un subconjunto del trabajo de un entry point existente (como `--normalize-only` o `--register-only`). Los entry points no tienen modos ocultos: las flags de un script son las que usaría quien lo ejecuta directamente.
2. Extraer la lógica compartida a una librería (`scripts/<dominio>.sh` cargada con `source`) o a funciones reutilizables del módulo existente, para que el entry point dedicado y el script completo usen el mismo código sin duplicarlo.
3. Cada script carga la lógica compartida desde su propio directorio, para que nunca mezcle versiones de la skill.
4. El llamador invoca el entry point directamente, sin comprobar si existe ni si la librería cargada define una función: la skill resuelta siempre trae sus propios scripts, así que no se agregan guards para snapshots de versiones anteriores.
5. La regla aplica a los entry points que ejecuta una persona o un hook (`bootstrap.sh`, `sync-marketplace.sh`, `setup-browser-tools.py`, `normalize-instructions.sh`, `apply-managed-block.sh`, `merge-instructions.sh`, `register-browser-servers.py`, `start-browser-install.py`). Un helper interno que solo invocan otros scripts, como `render-instruction-template.sh` o `run-detached.py`, puede exponer varias operaciones como flags si las documenta en su `usage`.
