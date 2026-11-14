# Salida de terminal

Cómo lograr una salida linda y con vida que se degrade bien. Los kits resuelven la mecánica: capacidades, ancho, spinner y limpieza. Su tema no es un default: antes de usar un kit, reemplazar colores, glifos y ritmo por el carácter del proyecto, porque copiarlos haría que todos los proyectos se vean iguales.

## Índice

1. [Capacidades](#1-capacidades)
2. [Anatomía de una corrida](#2-anatomía-de-una-corrida)
3. [Estados, tablas y listas](#3-estados-tablas-y-listas)
4. [Ancho](#4-ancho)
5. [Esperas](#5-esperas)
6. [Salida limpia](#6-salida-limpia)
7. [Kit de Node](#7-kit-de-node)
8. [Kit de PowerShell](#8-kit-de-powershell)
9. [Kit de bash y zsh](#9-kit-de-bash-y-zsh)
10. [Kit de Python](#10-kit-de-python)
11. [Antes y después](#11-antes-y-después)
12. [Verificar](#12-verificar)

## 1. Capacidades

Decidir por stream, stdout y stderr por separado, y en este orden. Con `tool | jq`, stdout queda limpio y el spinner sigue vivo en stderr.

| Orden | Señal | Resultado |
|---|---|---|
| 1 | Salida para máquinas (`--json` y similares) | Nunca lleva decoración |
| 2 | Flag explícito de la herramienta (`--color=never`, `--color=always`) | Manda el flag |
| 3 | Modo agente ([abajo](#modo-agente)) | Texto plano, sin animación, sin tarjeta de encabezado ni emojis decorativos, aunque haya TTY y aunque esté `FORCE_COLOR` |
| 4 | `NO_COLOR` no vacía, o `TERM=dumb` | Texto plano, aunque esté `FORCE_COLOR` |
| 5 | `FORCE_COLOR=0` o `false` | Texto plano |
| 6 | Otro `FORCE_COLOR` no vacío | Color aun en CI o sin TTY, pero sin animación si no hay TTY |
| 7 | `CI` definida (distinta de `0` y `false`, sin importar mayúsculas), o stream que no es TTY | Texto plano |
| 8 | Todo lo demás | La mejor profundidad disponible: truecolor, 256, 16 |

Texto plano significa sin ningún escape, sin `\r` suelto y sin animación. El progreso sigue: una línea al empezar cada paso, otra al terminar y un latido cada 20 s en procesos largos.

### Modo agente

Un agente lee la salida como texto y paga cada línea en tokens: lo decorativo no le aporta nada, y algunos corren los comandos en una pseudoconsola, así que el chequeo de TTY dice «persona». Los kits lo detectan por entorno con `isAgentSession`, `Test-AgentSession`, `is_agent_session` (bash) e `is_agent_session` (Python):

- `<TOOL>_AGENT=1` o `true` lo fuerza; `0` o `false` lo apaga, aunque haya señales. Renombrar `TOOL_AGENT` por herramienta (`EMU_AGENT`, `RELEASE_AGENT`).
- Sin override, alcanza con una de estas señales. Cambian entre versiones de cada agente: verificarlas en una sesión real antes de sumar otra.

| Agente | Señal | Verificación |
|---|---|---|
| Convención entre agentes | `AI_AGENT` no vacía | Claude Code la define como `claude-code_<versión>_agent` (visto en una sesión el 2026-11-13). Hermes la definiría como `hermes-agent`: **sin verificar** |
| Claude Code | `CLAUDECODE=1` | Visto en una sesión el 2026-11-13 |
| Codex | `CODEX_SESSION_ID` o `CODEX_THREAD_ID` no vacías | Vistas en `codex exec` el 2026-11-13, junto a `CODEX_CI=1` |
| Hermes | `HERMES_AGENT=true` | **Sin verificar**: tomada del mapa de capacidades entre agentes |

El modo agente es de `interactive-cli-design` (`references/agent-mode.md`): ahí está qué cambia en el CLI (no preguntar, errores autosuficientes, `--json`). Acá solo decide la capacidad: el kit devuelve profundidad 1 y expone `isAgent` para que quien llama saltee la tarjeta, los emojis y los íconos.

Trampas de cada plataforma:

- **Node:** `getColorDepth()` devuelve 24 con `CI=1`. Con `NO_COLOR=1 FORCE_COLOR=3` también devuelve 24, y además emite un warning por stderr. Chequear los pasos 1 a 6 antes de llamarla.
- **`FORCE_COLOR=0`:** `Boolean('0')` es `true`, así que un chequeo de veracidad enciende el color. force-color.org dice que cualquier valor no vacío fuerza; la documentación de Node y este contrato tratan `0` como apagado.
- **`NO_COLOR=""`:** no cuenta. El estándar pide que esté presente y no vacía.
- **PowerShell, redirección del proceso:** `$PSStyle.OutputRendering` no aplica a la salida del proceso host, así que `pwsh script.ps1 | cat` no quita los escapes. Hay que decidir antes de escribirlos.
- **PowerShell, captura en la sesión:** con `$datos = ./script.ps1` o `./script.ps1 > archivo`, `IsOutputRedirected` da `false` y `PipelineLength` da 1, y el texto puro llega con sus escapes. Pintar stdout solo cuando la invocación descarta una captura, como hace el kit.
- **bash, `$(...)`:** adentro, el descriptor 1 es un pipe, así que `$(funcion_que_mira_-t_1)` siempre responde que no hay TTY. Guardar `[ -t 1 ]` antes, en el nivel superior.
- **bash, `tput`:** `$(tput cols 2>/dev/null)` deja a `tput` sin ningún descriptor conectado a la terminal y devuelve siempre 80. Leer con `stty size </dev/tty`.
- **Python, ancho:** `shutil.get_terminal_size()` consulta stdout. Con `tool > archivo`, la interfaz en stderr se dibuja a 80 columnas aunque la terminal tenga 40. Medir sobre el stream donde se dibuja: `os.get_terminal_size(stream.fileno())`, con respaldo a `COLUMNS` y a 80 (`terminal_columns` del kit de Python).
- **`CI` y `FORCE_COLOR`:** comparar sin importar mayúsculas. `CI=False` no es CI.

## 2. Anatomía de una corrida

```text
╭──────────────────────────────────────╮
│ release-status                v2.3.0 │   tarjeta de encabezado: nombre y versión
│ ──────────────────────────────────── │   divisor dentro de la celda, sin tocar los bordes
│ Publica los servicios del monorepo.  │   descripción breve, una o dos líneas
╰──────────────────────────────────────╯
[1/4] Leer manifiestos
  ✓ hecho · 00:02
[2/4] Compilar
⠹ Compilando… 00:14                spinner con tiempo transcurrido

Servicio        Versión  Estado    tabla: es el dato, va a stdout
api-gateway     3.14.2   ✓ hecho

╭ Listo ─────────────────────╮
│ 6 servicios, 1 con error   │   resumen: resultado y próximos comandos
│ Siguiente: pnpm release    │
╰────────────────────────────╯
```

- **Toda corrida de un CLI o script abre con la tarjeta de encabezado:** un recuadro con el nombre de la herramienta a la izquierda, la versión arriba a la derecha, una línea divisoria y una descripción breve de qué hace. El divisor va dentro de la celda, con un espacio a cada lado, sin tocar los bordes: es una sola tarjeta, no una tabla de dos filas. Los kits la dibujan con `renderBox`, `Write-Box` o `render_box` pasándoles la versión. Si el nombre y la versión no entran en una fila, la versión baja a la siguiente, alineada a la derecha. Sin logos gigantes ni arte ASCII. No se muestra con `--version`, con una salida para máquinas (`--json`) ni con `--quiet`; con `--help`, la tarjeta reemplaza la línea de «qué hace».
- El producto de la herramienta (tabla, lista, JSON) va a stdout. Tarjeta, pasos, spinner, resumen y errores van a stderr.
- El resumen dice qué pasó y qué hacer ahora. El código de salida dice lo mismo que el resumen.
- **El resumen muestra lo que quedó en el sistema, no lo que se mandó.** Los IDs y datos se leen de vuelta de la fuente después de crear. Si la lectura falla, mostrar lo enviado marcado («según lo enviado») y avisar. Si la fuente devuelve datos enmascarados en algún entorno (PII en producción), mostrarlos con la marca «(enmascarado)», no como si fueran el dato real. Si falta un campo, «sin dato en <fuente>», atenuado. Agrupar el resumen por entidad (usuario, recurso).
- **El entorno y la región van en el encabezado** del resumen y de cada reporte (chequeo de permisos, `--dry-run`), como etiquetas con color: `🧪 RELEASE · pruebas` en verde, `🚨 PROD · producción` en rojo. Sin color: `[RELEASE · pruebas]`.
- **Entorno peligroso.** Al elegir producción, por flag, por archivo de configuración o en el menú, mostrar un cartel con fondo rojo y letras blancas, de hasta 80 columnas o el ancho de la terminal si es menor, con el nombre del entorno en letras grandes (5 filas de bloques `█`, todas del mismo ancho). Si la terminal es más angosta que el arte, sale sin las letras grandes. Sin color, el mismo cartel con bordes `│` y sin fondo. `render_danger_banner` del kit de Python lo dibuja. Después del cartel va la confirmación que pide escribir el nombre (`interactive-cli-design`, fila «Acción peligrosa»).
  - Es una **excepción** a «sin logos gigantes ni arte ASCII» de la tarjeta de encabezado: esa regla es para la tarjeta. El cartel es una advertencia y tiene que verse.
- Los errores son una línea clara con color y símbolo, no un stack crudo. El detalle técnico va a un log o detrás de un flag.

## 3. Estados, tablas y listas

Cinco estados, siempre con símbolo y palabra:

| Estado | Glifo | Alternativa ASCII | Palabra | Color |
|---|---|---|---|---|
| Hecho | `✓` | `+` | hecho | Verde o el «bien» del proyecto |
| Saltado | `↷` | `-` | saltado | Atenuado |
| Cambiado | `~` | `~` | cambiado | Azul o el acento |
| Aviso | `!` | `!` | aviso | Ámbar |
| Error | `✗` | `x` | error | Rojo |

Glifos y colores pueden cambiar por proyecto, siempre que los cinco sigan distinguiéndose por texto.

- **Tablas:** alinear por ancho visible, con los escapes ya quitados. Números y duraciones a la derecha. Títulos en negrita o atenuados, sin grilla completa.
- **Listas:** la jerarquía va con sangría, no solo con color. Viñetas de una celda.
- **Columnas alineadas:** usar glifos de una celda. Un emoji ocupa dos en casi todas las terminales, pero no en todas.

### Emojis

Sumar un emoji a una opción de menú, una fila de tabla o un resultado solo cuando el emoji correcto es obvio y ayuda a encontrar el valor de un vistazo. No por decorar.

| Sí | No |
|---|---|
| Valores concretos con un emoji que cualquiera asocia: sistemas (🍎 macOS, 🐧 Linux, 🪟 Windows), entornos (🧪 test, 🚨 producción), tipos de archivo (📄 documento, 🖼️ imagen), dispositivos (📱 Android) | Conceptos abstractos (modo, estrategia, nivel), donde cada lector elegiría otro emoji |
| Un grupo donde **todas** las opciones tienen su emoji claro | Un grupo donde solo algunas lo tienen: o todas o ninguna |
| Junto a la palabra: `🚨 producción` | En lugar de la palabra, o en los estados, que ya tienen su glifo de una celda |

- Para producción, 🚨 y no 🚀: 🚀 se lee como «deploy» o «lanzamiento», no como riesgo.
- Fijarlos en constantes por valor (`producción → 🚨`), así el mismo valor lleva el mismo emoji en el menú, en la tabla y en el resumen.
- Medir el ancho con los helpers de los kits de Node o PowerShell, que cuentan dos celdas por emoji; el kit de bash cuenta caracteres. Preferir emojis sin el selector U+FE0F (`🖼️` lo lleva), que algunas terminales dibujan con otro ancho.
- **Banderas:** `🇧🇷` son dos indicadores regionales (U+1F1E7 U+1F1F7) y ocupan **dos** celdas, no cuatro. Los helpers de los kits de Node, PowerShell y Python las cuentan como un solo emoji; Windows PowerShell 5.1 las separa en dos y el kit las vuelve a juntar.
- **Todo lo que recorre texto carácter por carácter** (degradés, cortes, animaciones de revelado) recorre graphemes: un escape de color entre los dos indicadores de una bandera, o dentro de una secuencia ZWJ (`👨‍👩‍👧`), la rompe.
- **Sin color, sin emojis decorativos.** Con `NO_COLOR`, `TERM=dumb` o salida a un pipe, el emoji que acompaña a una palabra se omite y queda la palabra (`🚨 PROD` → `PROD`), igual que los íconos de Nerd Fonts pasan a su respaldo.
- Nunca en una salida para máquinas (`--json`, datos por pipe que otro programa parsea). Con una regla de proyecto «solo ASCII», no van.

### Íconos de Nerd Fonts

Para roles fijos de la interfaz, no para valores: el comando para repetir la corrida, un archivo, una carpeta, una rama. Cada ícono es una constante con su nombre de Nerd Fonts y su respaldo:

| Rol | Ícono | Nombre | Respaldo |
|---|---|---|---|
| Comando para repetir | `\u{F120}` | `nf-fa-terminal` | `$` |
| Archivo | `\u{F15B}` | `nf-fa-file` | `-` |
| Carpeta | `\u{F07B}` | `nf-fa-folder` | `/` |
| Rama de git | `\u{E725}` | `nf-dev-git_branch` | `*` |

- Una terminal sin Nerd Font muestra un cuadrado vacío, y no hay forma confiable de detectarlo. Usar el ícono solo con TTY, y documentar `NERD_FONT=0` para pasar al respaldo. Sin TTY va siempre el respaldo.
- El ícono va en la línea del título, nunca pegado a algo que se copia: un comando copiado con el ícono adelante no corre.
- Mide una celda: dejar un espacio después.

## 4. Ancho

- **Tablas y recuadros miden como máximo 80 columnas**, o el ancho de la terminal si es menor. También la tarjeta de encabezado, el resumen y la tabla del `--help`. Sin TTY, el tope es 80. Los kits lo aplican con `layoutWidth`, `Get-LayoutWidth` o `layout_width` (`MAXIMUM_LAYOUT_COLUMNS`).
- Con TTY, leer el ancho real en cada dibujo, porque puede cambiar durante la corrida. Fuera de tablas y recuadros, sin TTY no hay ancho: no truncar ni partir las demás líneas.
- **Si la tabla no entra, primero achicar columnas.** Empezar por la más ancha, de a una, sin bajar del mínimo de cada columna (su parte indivisible más larga: una palabra, un ID), y partir esas celdas en varias líneas. Recién si ni así entra, pasar a formato apilado: una línea por campo debajo del nombre. Después de partir, cada columna mide lo que ocupa su línea más ancha. Nunca truncar un dato. `renderTable` de Node lo hace con `fitColumnWidths`, y el kit de Python trae `fit_column_widths`; los kits de PowerShell y bash apilan directo: si el proyecto los usa con una columna larga, portar esa función.
- **Un dato que se copia nunca se parte.** Una URL, un mail o un ID más ancho que la línea va solo en su renglón, entero y sin sangría, aunque se pase del ancho (dentro de un recuadro, sin borde): partirlo rompe el clic y el copiado. Los tres kits y el de Python lo hacen al partir.
- **Cortar o partir texto con color nunca parte un escape, y cierra el color al cortar.** Los escapes miden 0 celdas y se copian enteros; si se cortó un texto pintado, terminar con `ESC[0m`. `sliceVisible`, `Get-FittingPrefix` y `slice_visible` lo hacen; el kit de bash recibe texto sin pintar y pinta después.
- Lo mismo vale para toda línea propia: pasos, errores, banner y el contenido del resumen, también dentro de un recuadro. Partirlas con el mismo ajuste, porque una sola línea larga rompe el recuadro a 40 columnas.
- Lo decorativo sí se recorta: etiqueta del spinner, reglas y bordes. La línea del spinner tiene que medir menos que el ancho, o la terminal la parte y `\r` ya no la borra.
- Medir graphemes y no bytes. `ñ` ocupa una celda; un ideograma, dos. ZWJ, U+FE0E y U+FE0F, cero. `👨‍👩‍👧` y `1️⃣` miden dos.
- Medir sobre el stream donde se dibuja (stderr para la interfaz), no sobre stdout.

## 5. Esperas

- **Total conocido:** barra o contador con porcentaje. **Total desconocido:** spinner.
- Mostrar el tiempo transcurrido siempre que la espera pueda superar unos segundos.
- Un cuadro cada 80 a 120 ms, solo con TTY. Antes de escribir cualquier otra línea, parar el spinner y limpiar la suya.
- El trabajo síncrono congela los timers: correrlo en async, en un proceso hijo o en un job.
- La pausa entre cuadros existe solo mientras hay trabajo pendiente. Medir: con trabajo de 0 ms, el script no tarda más que su arranque.
- **Notas durante una espera.** Un estado («reintentando, 2/3») va al final de la línea del spinner. Sin animación, se escribe como línea propia **solo cuando cambia**: no se repite en cada intento.
- **Spinner en un hilo (Python):** esperar con `stop_event.wait(intervalo)` y no con `time.sleep`, para cortar enseguida; hilo `daemon=True`; `stop()` idempotente, con `join()` antes de limpiar la línea y mostrar el cursor; un paso que termina con cualquier excepción (también Ctrl+C) se marca con ✖ y la excepción se relanza. `Spinner` y `step` del kit de Python.

## 6. Salida limpia

Restaurar cursor y línea en toda salida: normal, error y Ctrl+C. El estado de salida ante Ctrl+C es 130.

- **Node:** en Windows las escrituras a una TTY son asíncronas, así que `process.exit()` puede perderlas. En el handler de `exit` usar `fs.writeSync`. En el flujo normal, asignar `process.exitCode` en vez de llamar a `process.exit()`, que también puede cortar datos en un pipe en POSIX.
- **PowerShell:** usar `try/finally`. `trap` no corre en Ctrl+C.
- **bash y zsh:** usar `trap` en el nivel superior del script, porque en zsh un `trap ... EXIT` dentro de una función es local a esa función.

Cancelar también corta el trabajo, no solo el dibujo. Si la espera corre en un proceso hijo, terminarlo con todos sus descendientes, para que no sigan teniendo efectos después de cancelar. En un script de shell, además, los jobs en background ignoran SIGINT. El kit de bash lo resuelve con `kill_process_tree`. En Node, usar `spawn` con `detached: true` y `process.kill(-child.pid)`; en Windows, `taskkill /T /F /PID`, igual que en PowerShell.

## 7. Kit de Node

Sin dependencias. Node 18 o superior.

```js
import { writeSync } from 'node:fs';
import { stripVTControlCharacters } from 'node:util';

const ESCAPE = '\x1b[';
const HIDE_CURSOR = `${ESCAPE}?25l`;
const SHOW_CURSOR = `${ESCAPE}?25h`;
const CLEAR_LINE = `\r${ESCAPE}2K`;
const RESET = `${ESCAPE}0m`;
const COLUMN_GAP = 2;
const MAXIMUM_LAYOUT_COLUMNS = 80; // tablas y recuadros: nunca más anchos que esto

// El carácter del proyecto vive acá. Reemplazar estos valores: solo muestran la forma.
const THEME = {
  colors: {
    accent: { rgb: [94, 196, 182], ansi256: 79, ansi16: 36 },
    muted: { rgb: [138, 147, 166], ansi256: 102, ansi16: 90 },
    done: { rgb: [126, 211, 135], ansi256: 114, ansi16: 32 },
    skipped: { rgb: [138, 147, 166], ansi256: 102, ansi16: 90 },
    changed: { rgb: [122, 176, 255], ansi256: 111, ansi16: 34 },
    warning: { rgb: [240, 196, 96], ansi256: 221, ansi16: 33 },
    error: { rgb: [244, 118, 118], ansi256: 210, ansi16: 31 },
  },
  gradient: { from: [94, 196, 182], to: [122, 176, 255] },
  statuses: {
    done: { glyph: '✓', word: 'hecho' },
    skipped: { glyph: '↷', word: 'saltado' },
    changed: { glyph: '~', word: 'cambiado' },
    warning: { glyph: '!', word: 'aviso' },
    error: { glyph: '✗', word: 'error' },
  },
  spinnerFrames: ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'],
  spinnerIntervalMs: 90,
  heartbeatIntervalMs: 20000,
};

// Modo agente (§1): renombrar TOOL_AGENT por herramienta. [variable, valor esperado o null si alcanza con no vacía]
const AGENT_OVERRIDE_VARIABLE = 'TOOL_AGENT';
const AGENT_ENVIRONMENT_SIGNALS = [
  ['AI_AGENT', null],
  ['CLAUDECODE', '1'],
  ['CODEX_SESSION_ID', null],
  ['CODEX_THREAD_ID', null],
  ['HERMES_AGENT', 'true'],
];

function isAgentSession(env = process.env) {
  const override = (env[AGENT_OVERRIDE_VARIABLE] ?? '').trim().toLowerCase();
  if (override === '0' || override === 'false') return false;
  if (override === '1' || override === 'true') return true;
  return AGENT_ENVIRONMENT_SIGNALS.some(([name, expected]) => {
    const value = (env[name] ?? '').trim().toLowerCase();
    return value !== '' && (expected === null || value === expected);
  });
}

/** Devuelve la profundidad de color de un stream: 1 (plano), 4, 8 o 24 bits. */
function detectColorDepth(stream, env = process.env) {
  if (isAgentSession(env)) return 1; // aunque haya TTY y FORCE_COLOR
  const forceColor = env.FORCE_COLOR?.toLowerCase();
  if (env.NO_COLOR || env.TERM === 'dumb' || forceColor === '0' || forceColor === 'false') return 1;
  if (forceColor) return { 1: 4, 2: 8, 3: 24 }[forceColor] ?? 4;
  const continuousIntegration = env.CI?.toLowerCase();
  const isContinuousIntegration = continuousIntegration && continuousIntegration !== '0' && continuousIntegration !== 'false';
  if (isContinuousIntegration || !stream.isTTY) return 1;
  return stream.getColorDepth();
}

function createOutput(stream) {
  const depth = detectColorDepth(stream);
  return {
    stream,
    depth,
    isAgent: isAgentSession(), // sin tarjeta de encabezado, emojis ni íconos
    canAnimate: depth > 1 && Boolean(stream.isTTY),
    get width() {
      return stream.isTTY ? stream.columns : Infinity;
    },
    /** Ancho de tablas y recuadros: el de la terminal, hasta MAXIMUM_LAYOUT_COLUMNS. Sin TTY, ese tope. */
    get layoutWidth() {
      return Math.min(stream.isTTY ? stream.columns : MAXIMUM_LAYOUT_COLUMNS, MAXIMUM_LAYOUT_COLUMNS);
    },
  };
}

function colorCode(color, depth) {
  if (depth === 24) return `38;2;${color.rgb.join(';')}`;
  if (depth === 8) return `38;5;${color.ansi256}`;
  return String(color.ansi16);
}

function paint(output, colorName, text, { bold = false } = {}) {
  if (output.depth === 1) return text;
  const weight = bold ? '1;' : '';
  return `${ESCAPE}${weight}${colorCode(THEME.colors[colorName], output.depth)}m${text}${ESCAPE}0m`;
}

function paintBold(output, text) {
  return output.depth === 1 ? text : `${ESCAPE}1m${text}${ESCAPE}0m`;
}

function paintGradient(output, text) {
  if (output.depth < 24) return paint(output, 'accent', text, { bold: true });
  // Por grapheme, no por code point: un escape entre los dos indicadores de 🇧🇷 rompe la bandera.
  const graphemes = [...graphemeSegmenter.segment(text)].map(({ segment }) => segment);
  const { from, to } = THEME.gradient;
  const painted = graphemes.map((grapheme, index) => {
    const ratio = index / Math.max(graphemes.length - 1, 1);
    const rgb = from.map((channel, channelIndex) => Math.round(channel + (to[channelIndex] - channel) * ratio));
    return `${ESCAPE}1;38;2;${rgb.join(';')}m${grapheme}`;
  });
  return `${painted.join('')}${RESET}`;
}

const WIDE_CHARACTER = /[\p{Emoji_Presentation}ᄀ-ᅟ⺀-꓏가-힣豈-﫿︰-﹯＀-｠￠-￦]/u;
const graphemeSegmenter = new Intl.Segmenter();
const ANSI_ESCAPE_SPLIT = /(\x1b\[[0-9;?]*[ -/]*[@-~])/;

function visibleWidth(text) {
  let width = 0;
  for (const { segment } of graphemeSegmenter.segment(stripVTControlCharacters(text))) {
    width += WIDE_CHARACTER.test(segment) ? 2 : 1;
  }
  return width;
}

function padVisible(text, width, { alignRight = false } = {}) {
  const padding = ' '.repeat(Math.max(width - visibleWidth(text), 0));
  return alignRight ? `${padding}${text}` : `${text}${padding}`;
}

/**
 * Prefijo que entra en maximumWidth celdas. Siempre lleva un grapheme, para que el ajuste avance.
 * Los escapes de color miden 0 y se copian enteros; si se cortó un texto pintado, cierra el color.
 */
function sliceVisible(text, maximumWidth) {
  let usedWidth = 0;
  let prefix = '';
  let hasEscapes = false;
  let wasCut = false;
  for (const part of text.split(ANSI_ESCAPE_SPLIT)) {
    if (ANSI_ESCAPE_SPLIT.test(part)) {
      if (!wasCut) prefix += part;
      hasEscapes = true;
      continue;
    }
    for (const { segment } of graphemeSegmenter.segment(part)) {
      if (wasCut) break;
      const segmentWidth = WIDE_CHARACTER.test(segment) ? 2 : 1;
      if (usedWidth > 0 && usedWidth + segmentWidth > maximumWidth) {
        wasCut = true;
        break;
      }
      usedWidth += segmentWidth;
      prefix += segment;
    }
  }
  return wasCut && hasEscapes ? `${prefix}${RESET}` : prefix;
}

function truncateVisible(text, maximumWidth) {
  if (visibleWidth(text) <= maximumWidth) return text;
  return `${sliceVisible(text, Math.max(maximumWidth - 1, 1))}…`;
}

/**
 * Parte en palabras. Una palabra más ancha que la línea (una URL, un mail, un ID) va sola en su renglón,
 * entera aunque se pase: partirla rompe el clic y el copiado.
 */
function wrapText(text, width) {
  const lines = [];
  let line = '';
  for (const word of text.split(' ')) {
    const candidate = line ? `${line} ${word}` : word;
    if (visibleWidth(candidate) <= width) {
      line = candidate;
      continue;
    }
    if (line) lines.push(line);
    line = word;
    if (visibleWidth(word) > width) {
      lines.push(word);
      line = '';
    }
  }
  if (line || lines.length === 0) lines.push(line);
  return lines;
}

/** Achica primero las columnas más anchas, sin bajar del mínimo de cada una (su palabra más larga). */
function fitColumnWidths(naturalWidths, minimumWidths, availableWidth) {
  const widths = [...naturalWidths];
  let excess = widths.reduce((total, width) => total + width, 0) - availableWidth;
  const widestFirst = widths.map((_, index) => index).sort((left, right) => widths[right] - widths[left]);
  for (const column of widestFirst) {
    if (excess <= 0) break;
    const reduction = Math.min(excess, widths[column] - minimumWidths[column]);
    widths[column] -= reduction;
    excess -= reduction;
  }
  return widths; // si todavía suman más que availableWidth, la tabla se apila
}

function statusLabel(statusName) {
  const { glyph, word } = THEME.statuses[statusName];
  return `${glyph} ${word}`;
}

const longestWord = (text) => Math.max(...text.split(' ').map(visibleWidth));

/**
 * Cada columna: { title, read(row), colorOf?(row), alignRight? }. Si no entra, primero achica las columnas
 * más anchas y parte sus celdas en varias líneas; recién si ni así entra, apila las filas.
 */
function renderTable(output, columns, rows) {
  const naturalWidths = columns.map(({ title, read }) =>
    Math.max(visibleWidth(title), ...rows.map((row) => visibleWidth(read(row)))),
  );
  const minimumWidths = columns.map(({ title, read }) =>
    Math.max(visibleWidth(title), ...rows.map((row) => longestWord(read(row)))),
  );
  const gapsWidth = COLUMN_GAP * (columns.length - 1);
  const fitted = fitColumnWidths(naturalWidths, minimumWidths, output.layoutWidth - gapsWidth);
  if (fitted.reduce((total, width) => total + width, 0) + gapsWidth > output.layoutWidth) {
    return renderStackedRows(output, columns, rows);
  }
  const cellLines = rows.map((row) => columns.map(({ read }, index) => wrapText(read(row), fitted[index])));
  // Después de partir, cada columna mide lo que ocupa su línea más ancha, sin espacio de sobra.
  const columnWidths = columns.map(({ title }, index) =>
    Math.max(visibleWidth(title), ...cellLines.flatMap((lines) => lines[index].map(visibleWidth))),
  );

  const gap = ' '.repeat(COLUMN_GAP);
  const header = columns
    .map(({ title, alignRight }, index) => paintBold(output, padVisible(title, columnWidths[index], { alignRight })))
    .join(gap);
  const body = rows.flatMap((row, rowIndex) => {
    const lineCount = Math.max(...cellLines[rowIndex].map((lines) => lines.length));
    return Array.from({ length: lineCount }, (_, lineIndex) =>
      columns
        .map(({ colorOf, alignRight }, index) => {
          const cell = padVisible(cellLines[rowIndex][index][lineIndex] ?? '', columnWidths[index], { alignRight });
          return colorOf ? paint(output, colorOf(row), cell) : cell;
        })
        .join(gap)
        .trimEnd(),
    );
  });
  return [header.trimEnd(), ...body].join('\n');
}

function renderStackedRows(output, columns, rows) {
  const [titleColumn, ...detailColumns] = columns;
  return rows
    .flatMap((row) => [
      ...wrapText(titleColumn.read(row), output.layoutWidth).map((line) => paintBold(output, line)),
      ...detailColumns.flatMap(({ title, read, colorOf }) => {
        const cell = `  ${title}: ${read(row)}`;
        return wrapText(cell, output.layoutWidth).map((line) => (colorOf ? paint(output, colorOf(row), line) : line));
      }),
      '',
    ])
    .join('\n')
    .trimEnd();
}

/** Recuadro. Con `version` es la tarjeta de encabezado: la versión arriba a la derecha y un divisor bajo el título. */
function renderBox(output, title, lines, { version } = {}) {
  const versionLabel = version ? `v${version}` : '';
  const titleRowWidth = visibleWidth(title) + (versionLabel ? COLUMN_GAP + visibleWidth(versionLabel) : 0);
  const maximumInnerWidth = Math.max(output.layoutWidth - 4, 1);
  const innerWidth = Math.min(Math.max(titleRowWidth, ...lines.map(visibleWidth)), maximumInnerWidth);
  const border = (text) => paint(output, 'accent', text);
  const toRow = (content) => `${border('│')} ${content} ${border('│')}`;
  const paintTitle = (text) => paintGradient(output, text);
  const versionText = (width) => paint(output, 'muted', padVisible(versionLabel, width, { alignRight: true }));
  const titleRows =
    versionLabel && titleRowWidth <= innerWidth
      ? [toRow(`${paintTitle(title)}${versionText(innerWidth - visibleWidth(title))}`)]
      : [
          // El título no es un dato que se copia: una palabra más ancha que el recuadro se recorta.
          ...wrapText(title, innerWidth).map((line) =>
            toRow(paintTitle(padVisible(truncateVisible(line, innerWidth), innerWidth))),
          ),
          ...(versionLabel ? [toRow(versionText(innerWidth))] : []),
        ];
  return [
    border(`╭${'─'.repeat(innerWidth + 2)}╮`),
    ...titleRows,
    // El divisor queda dentro de la celda, sin tocar los bordes: es una sola tarjeta, no una tabla de dos filas.
    ...(versionLabel ? [toRow(paint(output, 'muted', '─'.repeat(innerWidth)))] : []),
    // Un dato más ancho que el recuadro (una URL) va entero y sin borde: con borde se partiría o se cortaría.
    ...lines
      .flatMap((line) => wrapText(line, innerWidth))
      .map((line) => (visibleWidth(line) > innerWidth ? line : toRow(padVisible(line, innerWidth)))),
    border(`╰${'─'.repeat(innerWidth + 2)}╯`),
  ].join('\n');
}

function formatElapsed(elapsedMs) {
  const totalSeconds = Math.floor(elapsedMs / 1000);
  const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, '0');
  const seconds = String(totalSeconds % 60).padStart(2, '0');
  return `${minutes}:${seconds}`;
}

function startSpinner(output, label) {
  const startedAt = Date.now();
  const elapsedText = () => formatElapsed(Date.now() - startedAt);
  if (!output.canAnimate) {
    output.stream.write(`... ${label}\n`);
    const heartbeat = setInterval(
      () => output.stream.write(`... ${label} (${elapsedText()})\n`),
      THEME.heartbeatIntervalMs,
    );
    return { stop: () => clearInterval(heartbeat), elapsedText };
  }

  let frameIndex = 0;
  const drawFrame = () => {
    const frame = THEME.spinnerFrames[frameIndex % THEME.spinnerFrames.length];
    frameIndex += 1;
    const text = truncateVisible(`${label} ${elapsedText()}`, output.width - 3);
    output.stream.write(`${CLEAR_LINE}${paint(output, 'accent', frame)} ${text}`);
  };
  output.stream.write(HIDE_CURSOR);
  drawFrame();
  const timer = setInterval(drawFrame, THEME.spinnerIntervalMs);
  return {
    stop() {
      clearInterval(timer);
      output.stream.write(`${CLEAR_LINE}${SHOW_CURSOR}`);
    },
    elapsedText,
  };
}

const dataOutput = createOutput(process.stdout);
const uiOutput = createOutput(process.stderr);

process.on('exit', () => {
  if (!uiOutput.canAnimate) return;
  try {
    writeSync(process.stderr.fd, `${CLEAR_LINE}${SHOW_CURSOR}`);
  } catch {
    // La terminal ya no está: no queda nada que restaurar.
  }
});
process.on('SIGINT', () => process.exit(130));
process.on('SIGTERM', () => process.exit(143));
```

## 8. Kit de PowerShell

Para PowerShell 7 y Windows PowerShell 5.1. Windows PowerShell lee como ANSI un `.ps1` sin BOM, así que el kit es ASCII puro y arma los glifos con `[char]`. Si el script trae texto no ASCII literal, guardarlo como UTF-8 con BOM.

Los datos van con `Write-Output`, para que sigan funcionando en un pipeline de PowerShell. La decoración va a `[Console]::Error`: `Write-Host` termina en el stdout del proceso cuando la salida se redirige.

```powershell
# Pintar stdout solo si nadie puede estar capturando: con -File, la redirección del proceso se ve en
# IsOutputRedirected; en una sesión, la línea de invocación no tiene que traer pipe, > ni asignación.
$script:CanPaintData = (-not [Console]::IsOutputRedirected) -and (
  (-not $MyInvocation.Line) -or ((-not $MyInvocation.ScriptName) -and ($MyInvocation.Line -notmatch '[|>=]'))
)
$script:Escape = [string][char]27
$script:ClearLine = "`r$($script:Escape)[2K"
$script:Reset = "$($script:Escape)[0m"
$script:AnsiEscapePattern = "$([char]27)\[[0-9;?]*[ -/]*[@-~]"
$script:RegionalIndicator = '^\uD83C[\uDDE6-\uDDFF]$'
$script:ColumnGap = '  '
$script:MaximumLayoutColumns = 80 # tablas y recuadros: nunca mas anchos que esto
$script:WideCharacter = '^([\u1100-\u115F\u2E80-\uA4CF\uAC00-\uD7A3\uF900-\uFAFF\uFE30-\uFE6F\uFF00-\uFF60\uFFE0-\uFFE6]|[\uD83C-\uD83E][\uDC00-\uDFFF])'

# El caracter del proyecto vive aca. Reemplazar estos valores: solo muestran la forma.
$script:Theme = @{
  Colors            = @{
    accent  = @{ Rgb = @(94, 196, 182); Ansi256 = 79; Ansi16 = 36 }
    muted   = @{ Rgb = @(138, 147, 166); Ansi256 = 102; Ansi16 = 90 }
    done    = @{ Rgb = @(126, 211, 135); Ansi256 = 114; Ansi16 = 32 }
    skipped = @{ Rgb = @(138, 147, 166); Ansi256 = 102; Ansi16 = 90 }
    changed = @{ Rgb = @(122, 176, 255); Ansi256 = 111; Ansi16 = 34 }
    warning = @{ Rgb = @(240, 196, 96); Ansi256 = 221; Ansi16 = 33 }
    error   = @{ Rgb = @(244, 118, 118); Ansi256 = 210; Ansi16 = 31 }
  }
  Statuses          = @{
    done    = @{ Glyph = [string][char]0x2713; Word = 'hecho' }
    skipped = @{ Glyph = [string][char]0x21B7; Word = 'saltado' }
    changed = @{ Glyph = '~'; Word = 'cambiado' }
    warning = @{ Glyph = '!'; Word = 'aviso' }
    error   = @{ Glyph = [string][char]0x2717; Word = 'error' }
  }
  SpinnerFrames     = @(0x280B, 0x2819, 0x2839, 0x2838, 0x283C, 0x2834, 0x2826, 0x2827, 0x2807, 0x280F) | ForEach-Object { [string][char]$_ }
  SpinnerIntervalMs = 90
  HeartbeatSeconds  = 20
}

# Modo agente (seccion 1): renombrar TOOL_AGENT por herramienta. Valor esperado, o $null si alcanza con no vacia.
$script:AgentOverrideVariable = 'TOOL_AGENT'
$script:AgentEnvironmentSignals = [ordered]@{ AI_AGENT = $null; CLAUDECODE = '1'; CODEX_SESSION_ID = $null; CODEX_THREAD_ID = $null; HERMES_AGENT = 'true' }

function Test-AgentSession {
  $override = ([string][Environment]::GetEnvironmentVariable($script:AgentOverrideVariable)).Trim().ToLowerInvariant()
  if ($override -in @('0', 'false')) { return $false }
  if ($override -in @('1', 'true')) { return $true }
  foreach ($name in $script:AgentEnvironmentSignals.Keys) {
    $value = ([string][Environment]::GetEnvironmentVariable($name)).Trim().ToLowerInvariant()
    $expected = $script:AgentEnvironmentSignals[$name]
    if ($value -and ($null -eq $expected -or $value -eq $expected)) { return $true }
  }
  return $false
}

function Get-ColorDepth {
  param([Parameter(Mandatory)][bool]$IsRedirected)

  if (Test-AgentSession) { return 1 } # aunque haya consola y FORCE_COLOR
  $forceColor = $env:FORCE_COLOR
  if ($env:NO_COLOR -or $env:TERM -eq 'dumb' -or $forceColor -eq '0' -or $forceColor -eq 'false') { return 1 }
  if ($forceColor) {
    $forcedDepths = @{ '1' = 4; '2' = 8; '3' = 24 }
    if ($forcedDepths.ContainsKey($forceColor)) { return $forcedDepths[$forceColor] }
    return 4
  }
  if (($env:CI -and $env:CI -ne '0' -and $env:CI -ne 'false') -or $IsRedirected) { return 1 }
  $virtualTerminalProperty = $Host.UI.PSObject.Properties['SupportsVirtualTerminal']
  if (-not ($virtualTerminalProperty -and $virtualTerminalProperty.Value)) { return 1 }
  if ($env:COLORTERM -match 'truecolor|24bit' -or $env:OS -eq 'Windows_NT') { return 24 }
  if ($env:TERM -match '256') { return 8 }
  return 4
}

function New-ConsoleOutput {
  param([Parameter(Mandatory)][ValidateSet('Data', 'Ui')][string]$Role)

  $isRedirected = [Console]::IsErrorRedirected
  if ($Role -eq 'Data') { $isRedirected = -not $script:CanPaintData }
  $depth = Get-ColorDepth -IsRedirected $isRedirected
  return @{
    Role         = $Role
    IsRedirected = $isRedirected
    IsAgent      = Test-AgentSession
    Depth        = $depth
    CanAnimate   = ($depth -gt 1) -and (-not $isRedirected)
  }
}

function Get-OutputWidth {
  param([Parameter(Mandatory)][hashtable]$Output)

  if ($Output.IsRedirected) { return [int]::MaxValue }
  try { return [Console]::WindowWidth } catch { return 80 }
}

# Ancho de tablas y recuadros: el de la terminal, hasta MaximumLayoutColumns. Sin terminal, ese tope.
function Get-LayoutWidth {
  param([Parameter(Mandatory)][hashtable]$Output)

  return [Math]::Min((Get-OutputWidth -Output $Output), $script:MaximumLayoutColumns)
}

function Write-Ui {
  param([AllowEmptyString()][string]$Text = '', [switch]$NoNewline)

  if ($NoNewline) { [Console]::Error.Write($Text) } else { [Console]::Error.WriteLine($Text) }
}

function Format-Paint {
  param(
    [Parameter(Mandatory)][hashtable]$Output,
    [Parameter(Mandatory)][string]$ColorName,
    [Parameter(Mandatory)][AllowEmptyString()][string]$Text,
    [switch]$Bold
  )

  if ($Output.Depth -le 1) { return $Text }
  $color = $script:Theme.Colors[$ColorName]
  $code = [string]$color.Ansi16
  if ($Output.Depth -eq 24) { $code = "38;2;$($color.Rgb -join ';')" }
  if ($Output.Depth -eq 8) { $code = "38;5;$($color.Ansi256)" }
  $weight = ''
  if ($Bold) { $weight = '1;' }
  return "$($script:Escape)[$weight${code}m$Text$($script:Escape)[0m"
}

function Format-Bold {
  param([Parameter(Mandatory)][hashtable]$Output, [Parameter(Mandatory)][AllowEmptyString()][string]$Text)

  if ($Output.Depth -le 1) { return $Text }
  return "$($script:Escape)[1m$Text$($script:Escape)[0m"
}

# Graphemes con su ancho. Windows PowerShell 5.1 (.NET Framework) separa los dos indicadores regionales
# de una bandera: se vuelven a juntar para que mida 2 celdas, como en PowerShell 7.
function Get-TextElements {
  param([AllowEmptyString()][string]$Text = '')

  $result = New-Object System.Collections.Generic.List[object]
  if (-not $Text) { return , $result.ToArray() }
  $elements = [System.Globalization.StringInfo]::GetTextElementEnumerator($Text)
  $isOpenFlag = $false
  while ($elements.MoveNext()) {
    $element = $elements.GetTextElement()
    $isRegionalIndicator = $element -match $script:RegionalIndicator
    if ($isRegionalIndicator -and $isOpenFlag) {
      $result[$result.Count - 1].Text += $element
      $isOpenFlag = $false
      continue
    }
    $isOpenFlag = $isRegionalIndicator
    $cells = 1
    if ($element -match $script:WideCharacter) { $cells = 2 }
    $result.Add([pscustomobject]@{ Text = $element; Cells = $cells })
  }
  return , $result.ToArray()
}

function Get-VisibleWidth {
  param([AllowEmptyString()][string]$Text = '')

  $usedCells = 0
  foreach ($element in (Get-TextElements ($Text -replace $script:AnsiEscapePattern, ''))) { $usedCells += $element.Cells }
  return $usedCells
}

# Prefijo que entra en $Width celdas. Siempre lleva un grapheme, para que el ajuste avance.
# Los escapes de color miden 0 y se copian enteros; si se corto un texto pintado, cierra el color.
function Get-FittingPrefix {
  param([AllowEmptyString()][string]$Text = '', [int]$Width)

  if (-not $Text) { return '' }
  $usedCells = 0
  $prefix = ''
  $hasEscapes = $false
  $wasCut = $false
  foreach ($part in [regex]::Split($Text, "($($script:AnsiEscapePattern))")) {
    if ($part -match "^$($script:AnsiEscapePattern)$") {
      if (-not $wasCut) { $prefix += $part }
      $hasEscapes = $true
      continue
    }
    if ($wasCut -or -not $part) { continue }
    foreach ($element in (Get-TextElements $part)) {
      if ($usedCells -gt 0 -and $usedCells + $element.Cells -gt $Width) { $wasCut = $true; break }
      $usedCells += $element.Cells
      $prefix += $element.Text
    }
  }
  if ($wasCut -and $hasEscapes) { return "$prefix$($script:Reset)" }
  return $prefix
}

function Format-Pad {
  param([AllowEmptyString()][string]$Text = '', [int]$Width, [switch]$AlignRight)

  $padding = ' ' * [Math]::Max($Width - (Get-VisibleWidth $Text), 0)
  if ($AlignRight) { return "$padding$Text" }
  return "$Text$padding"
}

function Split-TextToWidth {
  param([AllowEmptyString()][string]$Text = '', [int]$Width)

  $lines = New-Object System.Collections.Generic.List[string]
  $line = ''
  foreach ($word in ($Text -split ' ')) {
    $candidate = $word
    if ($line) { $candidate = "$line $word" }
    if ((Get-VisibleWidth $candidate) -le $Width) {
      $line = $candidate
      continue
    }
    if ($line) { $lines.Add($line) }
    $line = $word
    # Una palabra mas ancha que la linea (URL, mail, ID) va sola y entera: partirla rompe el clic y el copiado.
    if ((Get-VisibleWidth $word) -gt $Width) {
      $lines.Add($word)
      $line = ''
    }
  }
  if ($line -or $lines.Count -eq 0) { $lines.Add($line) }
  return , $lines.ToArray()
}

function Get-StatusLabel {
  param([Parameter(Mandatory)][string]$StatusName)

  $status = $script:Theme.Statuses[$StatusName]
  return "$($status.Glyph) $($status.Word)"
}

# Cada columna: @{ Title; Read = { param($row) ... }; ColorOf = { param($row) ... }; AlignRight = $true }.
function Get-RenderedTable {
  param([Parameter(Mandatory)][hashtable]$Output, [Parameter(Mandatory)][object[]]$Columns, [Parameter(Mandatory)][object[]]$Rows)

  $columnWidths = @()
  foreach ($column in $Columns) {
    $widest = Get-VisibleWidth $column.Title
    foreach ($row in $Rows) { $widest = [Math]::Max($widest, (Get-VisibleWidth ([string](& $column.Read $row)))) }
    $columnWidths += $widest
  }
  $tableWidth = ($columnWidths | Measure-Object -Sum).Sum + $script:ColumnGap.Length * ($Columns.Count - 1)
  $outputWidth = Get-LayoutWidth -Output $Output

  $lines = New-Object System.Collections.Generic.List[string]
  if ($tableWidth -gt $outputWidth) {
    foreach ($row in $Rows) {
      foreach ($line in (Split-TextToWidth -Text ([string](& $Columns[0].Read $row)) -Width $outputWidth)) { $lines.Add((Format-Bold -Output $Output -Text $line)) }
      foreach ($column in ($Columns | Select-Object -Skip 1)) {
        foreach ($line in (Split-TextToWidth -Text "  $($column.Title): $(& $column.Read $row)" -Width $outputWidth)) {
          if ($column.ColorOf) { $line = Format-Paint -Output $Output -ColorName (& $column.ColorOf $row) -Text $line }
          $lines.Add($line)
        }
      }
      $lines.Add('')
    }
    return , $lines.ToArray()
  }

  $headerCells = for ($i = 0; $i -lt $Columns.Count; $i++) {
    Format-Bold -Output $Output -Text (Format-Pad -Text $Columns[$i].Title -Width $columnWidths[$i] -AlignRight:([bool]$Columns[$i].AlignRight))
  }
  $lines.Add($headerCells -join $script:ColumnGap)
  foreach ($row in $Rows) {
    $cells = for ($i = 0; $i -lt $Columns.Count; $i++) {
      $cell = Format-Pad -Text ([string](& $Columns[$i].Read $row)) -Width $columnWidths[$i] -AlignRight:([bool]$Columns[$i].AlignRight)
      if ($Columns[$i].ColorOf) { $cell = Format-Paint -Output $Output -ColorName (& $Columns[$i].ColorOf $row) -Text $cell }
      $cell
    }
    $lines.Add($cells -join $script:ColumnGap)
  }
  return , $lines.ToArray()
}

# Con -Version es la tarjeta de encabezado: la versión arriba a la derecha y un divisor bajo el título.
function Write-Box {
  param(
    [Parameter(Mandatory)][hashtable]$Output,
    [Parameter(Mandatory)][string]$Title,
    [Parameter(Mandatory)][AllowEmptyCollection()][string[]]$Lines,
    [string]$Version
  )

  $versionLabel = ''
  if ($Version) { $versionLabel = "v$Version" }
  $titleRowWidth = Get-VisibleWidth $Title
  if ($versionLabel) { $titleRowWidth += $script:ColumnGap.Length + (Get-VisibleWidth $versionLabel) }
  $widest = $titleRowWidth
  foreach ($line in $Lines) { $widest = [Math]::Max($widest, (Get-VisibleWidth $line)) }
  $innerWidth = [Math]::Min($widest, [Math]::Max((Get-LayoutWidth -Output $Output) - 4, 1))
  $horizontal = ([string][char]0x2500) * ($innerWidth + 2)
  $side = Format-Paint -Output $Output -ColorName accent -Text ([string][char]0x2502)
  Write-Ui (Format-Paint -Output $Output -ColorName accent -Text "$([char]0x256D)$horizontal$([char]0x256E)")
  if ($versionLabel -and $titleRowWidth -le $innerWidth) {
    $titleText = Format-Paint -Output $Output -ColorName accent -Bold -Text $Title
    $versionText = Format-Paint -Output $Output -ColorName muted -Text (Format-Pad -Text $versionLabel -Width ($innerWidth - (Get-VisibleWidth $Title)) -AlignRight)
    Write-Ui "$side $titleText$versionText $side"
  } else {
    foreach ($line in (Split-TextToWidth -Text $Title -Width $innerWidth)) {
      # El titulo no es un dato que se copia: una palabra mas ancha que el recuadro se recorta.
      if ((Get-VisibleWidth $line) -gt $innerWidth) { $line = "$(Get-FittingPrefix -Text $line -Width ([Math]::Max($innerWidth - 1, 1)))$([char]0x2026)" }
      Write-Ui "$side $(Format-Paint -Output $Output -ColorName accent -Bold -Text (Format-Pad -Text $line -Width $innerWidth)) $side"
    }
    if ($versionLabel) {
      Write-Ui "$side $(Format-Paint -Output $Output -ColorName muted -Text (Format-Pad -Text $versionLabel -Width $innerWidth -AlignRight)) $side"
    }
  }
  if ($versionLabel) {
    # El divisor queda dentro de la celda, sin tocar los bordes: es una sola tarjeta, no dos filas.
    Write-Ui "$side $(Format-Paint -Output $Output -ColorName muted -Text (([string][char]0x2500) * $innerWidth)) $side"
  }
  foreach ($sourceLine in $Lines) {
    foreach ($line in (Split-TextToWidth -Text $sourceLine -Width $innerWidth)) {
      # Un dato mas ancho que el recuadro va entero y sin borde.
      if ((Get-VisibleWidth $line) -gt $innerWidth) { Write-Ui $line; continue }
      Write-Ui "$side $(Format-Pad -Text $line -Width $innerWidth) $side"
    }
  }
  Write-Ui (Format-Paint -Output $Output -ColorName accent -Text "$([char]0x2570)$horizontal$([char]0x256F)")
}

function Restore-Console {
  if ($script:UiOutput -and $script:UiOutput.CanAnimate) { Write-Ui "$($script:ClearLine)$($script:Escape)[?25h" -NoNewline }
}

# Espera hasta que $IsFinished devuelva verdadero: la pausa solo existe mientras hay trabajo.
function Wait-WithSpinner {
  param([Parameter(Mandatory)][hashtable]$Output, [Parameter(Mandatory)][string]$Label, [Parameter(Mandatory)][scriptblock]$IsFinished)

  $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
  if (-not $Output.CanAnimate) {
    Write-Ui "... $Label"
    $nextHeartbeatSeconds = $script:Theme.HeartbeatSeconds
    while (-not (& $IsFinished)) {
      Start-Sleep -Milliseconds $script:Theme.SpinnerIntervalMs
      if ($stopwatch.Elapsed.TotalSeconds -ge $nextHeartbeatSeconds) {
        Write-Ui ("... {0} ({1:mm\:ss})" -f $Label, $stopwatch.Elapsed)
        $nextHeartbeatSeconds += $script:Theme.HeartbeatSeconds
      }
    }
    return $stopwatch.Elapsed
  }

  $frameIndex = 0
  Write-Ui "$($script:Escape)[?25l" -NoNewline
  try {
    while (-not (& $IsFinished)) {
      $frame = $script:Theme.SpinnerFrames[$frameIndex % $script:Theme.SpinnerFrames.Count]
      $frameIndex++
      $text = "{0} {1:mm\:ss}" -f $Label, $stopwatch.Elapsed
      $maximumWidth = [Math]::Max((Get-OutputWidth -Output $Output) - 3, 1)
      $text = Get-FittingPrefix -Text $text -Width $maximumWidth
      Write-Ui "$($script:ClearLine)$(Format-Paint -Output $Output -ColorName accent -Text $frame) $text" -NoNewline
      Start-Sleep -Milliseconds $script:Theme.SpinnerIntervalMs
    }
  } finally {
    Restore-Console
  }
  return $stopwatch.Elapsed
}

# Entrada: envolver el trabajo para restaurar la consola en toda salida.
function Invoke-WithConsole {
  param([Parameter(Mandatory)][scriptblock]$Body)

  $originalEncoding = [Console]::OutputEncoding
  try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { $originalEncoding = $null }
  $script:DataOutput = New-ConsoleOutput -Role Data
  $script:UiOutput = New-ConsoleOutput -Role Ui
  $exitCode = 130
  try {
    & $Body
    $exitCode = 0
  } catch {
    Restore-Console
    Write-Ui (Format-Paint -Output $script:UiOutput -ColorName error -Text "$([char]0x2717) error: $($_.Exception.Message)")
    $exitCode = 1
  } finally {
    # Corre también con Ctrl+C. No usar [Environment]::Exit: cerraría la sesión de quien lo lanzó.
    Restore-Console
    if ($originalEncoding) { try { [Console]::OutputEncoding = $originalEncoding } catch { } }
  }
  exit $exitCode
}
```

## 9. Kit de bash y zsh

Sin arrays ni separación implícita de palabras, que es donde bash y zsh se diferencian. Las tablas las arma `awk`: `printf '%-10s'` cuenta bytes en bash, así que `ñ` desalinea.

El kit mide caracteres, no celdas: con texto de doble ancho (CJK, emoji) las columnas se desalinean. Si el proyecto muestra ese texto, medirlo en un lenguaje que conozca el ancho, como en los kits de Node o PowerShell.

```bash
#!/usr/bin/env bash
case "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" in
  *[Uu][Tt][Ff]-8* | *[Uu][Tt][Ff]8*) ;;
  # LC_ALL le gana a LC_CTYPE: con LC_ALL=C heredado hay que sacarlo, o se miden bytes y se parten caracteres.
  *)
    unset LC_ALL
    export LC_CTYPE=C.UTF-8
    ;;
esac

ESC=$(printf '\033')
# El carácter del proyecto vive acá y en color_code. Reemplazar estos valores: solo muestran la forma.
SPINNER_FRAMES='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
MAXIMUM_LAYOUT_COLUMNS=80 # tablas y recuadros: nunca más anchos que esto
SPINNER_FRAME_COUNT=10
SPINNER_INTERVAL_SECONDS=0.09
HEARTBEAT_SECONDS=20

# Modo agente (§1): renombrar TOOL_AGENT por herramienta.
is_agent_session() { # 0 si corre bajo un agente
  case "$(printf '%s' "${TOOL_AGENT:-}" | tr '[:upper:]' '[:lower:]')" in
    0 | false) return 1 ;;
    1 | true) return 0 ;;
  esac
  [ -n "${AI_AGENT:-}" ] || [ "${CLAUDECODE:-}" = 1 ] || [ -n "${CODEX_SESSION_ID:-}" ] ||
    [ -n "${CODEX_THREAD_ID:-}" ] || [ "$(printf '%s' "${HERMES_AGENT:-}" | tr '[:upper:]' '[:lower:]')" = true ]
}

color_depth() { # 1 si el stream es una TTY, 0 si no
  if is_agent_session; then echo 1; return; fi # aunque haya TTY y FORCE_COLOR
  if [ -n "${NO_COLOR:-}" ] || [ "${TERM:-}" = dumb ]; then echo 1; return; fi
  case "${FORCE_COLOR:-}" in
    0 | false) echo 1; return ;;
    1) echo 4; return ;;
    2) echo 8; return ;;
    3) echo 24; return ;;
    '') ;;
    *) echo 4; return ;;
  esac
  case "$(printf '%s' "${CI:-}" | tr '[:upper:]' '[:lower:]')" in
    '' | 0 | false) ;;
    *) echo 1; return ;;
  esac
  [ "$1" = 1 ] || { echo 1; return; }
  case "${COLORTERM:-}" in
    truecolor | 24bit) echo 24; return ;;
  esac
  terminal_colors=$(tput colors 2>/dev/null || echo 8)
  if [ "$terminal_colors" -ge 256 ]; then echo 8; elif [ "$terminal_colors" -ge 8 ]; then echo 4; else echo 1; fi
}

terminal_width() { # 1 si el stream es una TTY, 0 si no; devuelve 0 cuando no hay límite
  [ "$1" = 1 ] || { echo 0; return; }
  terminal_size=$(stty size </dev/tty 2>/dev/null)
  terminal_columns=${terminal_size##* }
  case "$terminal_columns" in
    '' | *[!0-9]*) echo 80 ;;
    *) echo "$terminal_columns" ;;
  esac
}

# Ancho para render_table y render_box: el de la terminal, hasta MAXIMUM_LAYOUT_COLUMNS. Sin TTY, ese tope.
layout_width() { # 1 si el stream es una TTY, 0 si no
  available_columns=$(terminal_width "$1")
  if [ "$available_columns" -eq 0 ] || [ "$available_columns" -gt "$MAXIMUM_LAYOUT_COLUMNS" ]; then
    echo "$MAXIMUM_LAYOUT_COLUMNS"
  else
    echo "$available_columns"
  fi
}

color_code() { # rol, profundidad
  case "$1:$2" in
    accent:24) echo '38;2;94;196;182' ;;
    accent:8) echo '38;5;79' ;;
    accent:*) echo 36 ;;
    done:24) echo '38;2;126;211;135' ;;
    done:8) echo '38;5;114' ;;
    done:*) echo 32 ;;
    skipped:24) echo '38;2;138;147;166' ;;
    skipped:8) echo '38;5;102' ;;
    skipped:*) echo 90 ;;
    changed:24) echo '38;2;122;176;255' ;;
    changed:8) echo '38;5;111' ;;
    changed:*) echo 34 ;;
    warning:24) echo '38;2;240;196;96' ;;
    warning:8) echo '38;5;221' ;;
    warning:*) echo 33 ;;
    error:24) echo '38;2;244;118;118' ;;
    error:8) echo '38;5;210' ;;
    error:*) echo 31 ;;
  esac
}

paint() { # profundidad, rol, texto
  if [ "$1" -le 1 ]; then
    printf '%s' "$3"
  else
    printf '%s[%sm%s%s[0m' "$ESC" "$(color_code "$2" "$1")" "$3" "$ESC"
  fi
}

status_label() {
  case "$1" in
    done) echo '✓ hecho' ;;
    skipped) echo '↷ saltado' ;;
    changed) echo '~ cambiado' ;;
    warning) echo '! aviso' ;;
    error) echo '✗ error' ;;
  esac
}

# mawk, el awk por defecto de Debian y Ubuntu, cuenta bytes aunque el locale sea UTF-8: length y substr
# partirían una ñ. Estas funciones cuentan caracteres en los dos casos.
AWK_TEXT_HELPERS='
    # Se arma en ejecución: gawk en UTF-8 rechaza este rango de bytes si está escrito en el programa.
    function continuation_bytes() { return sprintf("[%c-%c]", 128, 191) }
    function text_length(text, copy) {
      if (length("ñ") == 1) return length(text)
      copy = text
      return length(text) - gsub(continuation_bytes(), "", copy)
    }
    function text_units(text, count, position, seen) {
      if (length("ñ") == 1) return count
      seen = 0
      for (position = 1; position <= length(text); position++) {
        if (substr(text, position, 1) !~ continuation_bytes() && ++seen > count) return position - 1
      }
      return length(text)
    }
    function text_prefix(text, count) { return substr(text, 1, text_units(text, count)) }
    function text_rest(text, count) { return substr(text, text_units(text, count) + 1) }
'

# Lee filas separadas por | desde stdin; la primera son los títulos. La columna $3 trae un estado.
# Pasar como ancho "$(layout_width "$DATA_IS_TTY")", que ya aplica el tope de MAXIMUM_LAYOUT_COLUMNS.
render_table() { # profundidad, ancho (de layout_width), número de la columna de estado
  awk -F'|' -v depth="$1" -v width="$2" -v status_column="$3" -v esc="$ESC" \
    -v done_code="$(color_code done "$1")" -v skipped_code="$(color_code skipped "$1")" \
    -v changed_code="$(color_code changed "$1")" -v warning_code="$(color_code warning "$1")" \
    -v error_code="$(color_code error "$1")" "$AWK_TEXT_HELPERS"'
    BEGIN {
      label["done"] = "✓ hecho"; label["skipped"] = "↷ saltado"; label["changed"] = "~ cambiado"
      label["warning"] = "! aviso"; label["error"] = "✗ error"
      code["done"] = done_code; code["skipped"] = skipped_code; code["changed"] = changed_code
      code["warning"] = warning_code; code["error"] = error_code
    }
    function paint(status_name, text) {
      return depth <= 1 ? text : esc "[" code[status_name] "m" text esc "[0m"
    }
    function bold(text) { return depth <= 1 ? text : esc "[1m" text esc "[0m" }
    # Parte el texto antes de pintarlo, en un espacio: un dato largo no se trunca ni rompe la fila.
    # Una palabra mas ancha que la linea (URL, mail, ID) va sola y entera: partirla rompe el clic y el copiado.
    function print_stacked(text, style, head, position, space) {
      while (text_length(text) > width) {
        head = text_prefix(text, width + 1)
        space = 0
        for (position = length(head); position > 3; position--) {
          if (substr(head, position, 1) == " ") { space = position; break }
        }
        if (!space) space = index(substr(text, 4), " ") ? index(substr(text, 4), " ") + 3 : 0
        if (!space) break
        print_styled(substr(text, 1, space - 1), style)
        text = substr(text, space + 1)
        sub(/^ +/, "", text)
      }
      print_styled(text, style)
    }
    function print_styled(text, style) {
      if (style == "title") print bold(text)
      else if (style != "") print paint(style, text)
      else print text
    }
    {
      for (i = 1; i <= NF; i++) {
        value = (NR > 1 && i == status_column) ? label[$i] : $i
        cell[NR, i] = value
        status[NR] = (i == status_column) ? $i : status[NR]
        if (text_length(value) > widest[i]) widest[i] = text_length(value)
      }
      column_count = NF
    }
    END {
      total = 2 * (column_count - 1)
      for (i = 1; i <= column_count; i++) total += widest[i]
      if (width > 0 && total > width) {
        for (row = 2; row <= NR; row++) {
          print_stacked(cell[row, 1], "title")
          for (i = 2; i <= column_count; i++) {
            print_stacked("  " cell[1, i] ": " cell[row, i], (i == status_column) ? status[row] : "")
          }
          if (row < NR) print ""
        }
        exit
      }
      for (row = 1; row <= NR; row++) {
        line = ""
        for (i = 1; i <= column_count; i++) {
          padded = sprintf("%s%" (widest[i] - text_length(cell[row, i])) "s", cell[row, i], "")
          if (row == 1) padded = bold(padded)
          else if (i == status_column) padded = paint(status[row], padded)
          line = line (i > 1 ? "  " : "") padded
        }
        print line
      }
    }'
}

# Lee las líneas del recuadro desde stdin; la primera es el título. Con versión es la tarjeta de
# encabezado: la versión arriba a la derecha y un divisor bajo el título.
render_box() { # profundidad, ancho (de layout_width), versión (opcional)
  awk -v depth="$1" -v width="$2" -v version="${3:-}" -v esc="$ESC" -v accent_code="$(color_code accent "$1")" "$AWK_TEXT_HELPERS"'
    function accent(text) { return depth <= 1 ? text : esc "[" accent_code "m" text esc "[0m" }
    function repeat_text(text, count, result) {
      result = ""
      while (count-- > 0) result = result text
      return result
    }
    function append_wrapped(text, word_count, position, current) {
      word_count = split(text, words, " ")
      current = ""
      for (position = 1; position <= word_count; position++) {
        if (current == "") current = words[position]
        else if (text_length(current) + 1 + text_length(words[position]) <= inner) current = current " " words[position]
        else { wrapped[++wrapped_count] = current; current = words[position] }
      }
      wrapped[++wrapped_count] = current
    }
    function print_row(text) {
      # Un dato mas ancho que el recuadro va entero y sin borde.
      if (text_length(text) > inner) { print text; return }
      print accent("│") " " sprintf("%s%" (inner - text_length(text)) "s", text, "") " " accent("│")
    }
    function print_wrapped(row) {
      for (row = 1; row <= wrapped_count; row++) print_row(wrapped[row])
      wrapped_count = 0
    }
    # El título no es un dato que se copia: una palabra más ancha que el recuadro se recorta.
    function print_title_wrapped(row, line) {
      for (row = 1; row <= wrapped_count; row++) {
        line = wrapped[row]
        if (text_length(line) > inner) line = text_prefix(line, inner - 1) "…"
        print_row(line)
      }
      wrapped_count = 0
    }
    {
      source[NR] = $0
      row_width = text_length($0)
      if (NR == 1 && version != "") row_width += 2 + text_length("v" version)
      if (row_width > widest) widest = row_width
    }
    END {
      inner = widest
      if (width > 0 && inner > width - 4) inner = width - 4
      print accent("╭" repeat_text("─", inner + 2) "╮")
      first_body_row = 1
      if (version != "") {
        label = "v" version
        if (text_length(source[1]) + 2 + text_length(label) <= inner) {
          print_row(source[1] sprintf("%" (inner - text_length(source[1])) "s", label))
        } else {
          append_wrapped(source[1])
          print_title_wrapped()
          print_row(sprintf("%" inner "s", label))
        }
        # El divisor queda dentro de la celda, sin tocar los bordes: es una sola tarjeta, no dos filas.
        print_row(repeat_text("─", inner))
        first_body_row = 2
      } else if (NR >= 1) {
        append_wrapped(source[1])
        print_title_wrapped()
        first_body_row = 2
      }
      for (row = first_body_row; row <= NR; row++) append_wrapped(source[row])
      print_wrapped()
      print accent("╰" repeat_text("─", inner + 2) "╯")
    }'
}

# Se miran acá y no dentro de $(...), donde el descriptor 1 es un pipe.
DATA_IS_TTY=0
UI_IS_TTY=0
if [ -t 1 ]; then DATA_IS_TTY=1; fi
if [ -t 2 ]; then UI_IS_TTY=1; fi
DATA_DEPTH=$(color_depth "$DATA_IS_TTY")
UI_DEPTH=$(color_depth "$UI_IS_TTY")
UI_ANIMATES=0
if [ "$UI_DEPTH" -gt 1 ] && [ "$UI_IS_TTY" = 1 ]; then UI_ANIMATES=1; fi
UI_IS_AGENT=0 # 1: sin tarjeta de encabezado, emojis ni íconos
if is_agent_session; then UI_IS_AGENT=1; fi
WORK_PID=''

# Matar solo el PID deja corriendo lo que el trabajo lanzó, con sus efectos después de cancelar.
# Git Bash no entiende `ps -o`, por eso el fallback a `ps -ef`.
kill_process_tree() { # pid
  local child_pids child_pid
  child_pids=$({ ps -A -o pid= -o ppid= 2>/dev/null || ps -ef 2>/dev/null | awk 'NR > 1 { print $2, $3 }'; } |
    awk -v parent="$1" '$2 == parent { print $1 }')
  kill "$1" 2>/dev/null
  for child_pid in $(printf '%s\n' "$child_pids"); do
    kill_process_tree "$child_pid"
  done
}

restore_terminal() {
  if [ -n "$WORK_PID" ]; then kill_process_tree "$WORK_PID"; fi
  if [ "$UI_ANIMATES" = 1 ]; then printf '\r%s[2K%s[?25h' "$ESC" "$ESC" >&2; fi
}

# En el nivel superior del script: en zsh, un trap EXIT dentro de una función es local a ella.
trap restore_terminal EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

run_with_spinner() { # etiqueta, comando...
  spinner_label=$1
  shift
  # Con set -e, un trabajo de varios pasos no sigue si un paso falla o Ctrl+C lo corta. Pero bash lo apaga
  # si el llamador usa `if run_with_spinner ...` o `||`: ahí el trabajo tiene que encadenar sus pasos con &&.
  (
    set -e
    "$@"
  ) &
  WORK_PID=$!
  spinner_started_at=$SECONDS
  next_heartbeat=$HEARTBEAT_SECONDS
  frame_index=0
  if [ "$UI_ANIMATES" = 1 ]; then printf '%s[?25l' "$ESC" >&2; else printf '... %s\n' "$spinner_label" >&2; fi
  while kill -0 "$WORK_PID" 2>/dev/null; do
    spinner_elapsed=$((SECONDS - spinner_started_at))
    if [ "$UI_ANIMATES" = 1 ]; then
      frame=${SPINNER_FRAMES:$((frame_index % SPINNER_FRAME_COUNT)):1}
      spinner_columns=$(($(terminal_width "$UI_IS_TTY") - 3))
      spinner_text=$(printf '%s %02d:%02d' "$spinner_label" $((spinner_elapsed / 60)) $((spinner_elapsed % 60)))
      # Con texto no ASCII se corta a la mitad: alcanza aunque cada carácter ocupe dos celdas.
      case "$spinner_text" in
        *[!\ -~]*) spinner_columns=$((spinner_columns / 2)) ;;
      esac
      printf '\r%s[2K%s %s' "$ESC" "$(paint "$UI_DEPTH" accent "$frame")" "${spinner_text:0:$spinner_columns}" >&2
      frame_index=$((frame_index + 1))
    elif [ "$spinner_elapsed" -ge "$next_heartbeat" ]; then
      printf '... %s (%ss)\n' "$spinner_label" "$spinner_elapsed" >&2
      next_heartbeat=$((next_heartbeat + HEARTBEAT_SECONDS))
    fi
    sleep "$SPINNER_INTERVAL_SECONDS"
  done
  if [ "$UI_ANIMATES" = 1 ]; then printf '\r%s[2K%s[?25h' "$ESC" "$ESC" >&2; fi
  wait "$WORK_PID"
  work_status=$?
  WORK_PID=''
  return "$work_status"
}
```

## 10. Kit de Python

Sin dependencias. Python 3.9 o superior. Python no trae segmentación de graphemes: `graphemes` junta lo que una terminal dibuja como un solo carácter (marcas combinantes, selectores U+FE0E/U+FE0F, ZWJ, tonos de piel, keycaps y pares de indicadores regionales). Alcanza para medir y cortar; no es la segmentación completa de Unicode.

```python
import io, os, re, sys, threading, time, unicodedata
from contextlib import contextmanager

ESCAPE = "\x1b["
RESET = f"{ESCAPE}0m"
HIDE_CURSOR = f"{ESCAPE}?25l"
SHOW_CURSOR = f"{ESCAPE}?25h"
CLEAR_LINE = f"\r{ESCAPE}2K"
MAXIMUM_LAYOUT_COLUMNS = 80                    # tablas, recuadros y carteles: nunca más anchos que esto
FALLBACK_COLUMNS = 80
ANSI_ESCAPE_PATTERN = re.compile(r"(\x1b\[[0-9;?]*[ -/]*[@-~])")
ZERO_WIDTH_JOINER = "‍"
VARIATION_SELECTORS = {"︎", "️"}
KEYCAP = "⃣"
SKIN_TONES = range(0x1F3FB, 0x1F400)
REGIONAL_INDICATORS = range(0x1F1E6, 0x1F200)

# El carácter del proyecto vive acá. Reemplazar estos valores: solo muestran la forma.
COLORS = {"accent": "38;2;94;196;182", "muted": "38;2;138;147;166", "done": "38;2;126;211;135",
          "warning": "38;2;240;196;96", "error": "38;2;244;118;118", "danger": "1;97;41"}
SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
SPINNER_INTERVAL_SECONDS = 0.09
DONE_GLYPH, ERROR_GLYPH = "✔", "✖"


# Modo agente (§1): renombrar TOOL_AGENT por herramienta. (variable, valor esperado o None si alcanza con no vacía)
AGENT_OVERRIDE_VARIABLE = "TOOL_AGENT"
AGENT_ENVIRONMENT_SIGNALS = (
    ("AI_AGENT", None),
    ("CLAUDECODE", "1"),
    ("CODEX_SESSION_ID", None),
    ("CODEX_THREAD_ID", None),
    ("HERMES_AGENT", "true"),
)


def is_agent_session(environment=os.environ) -> bool:
    override = environment.get(AGENT_OVERRIDE_VARIABLE, "").strip().lower()
    if override in ("0", "false"):
        return False
    if override in ("1", "true"):
        return True
    return any(
        (value := environment.get(name, "").strip().lower()) and (expected is None or value == expected)
        for name, expected in AGENT_ENVIRONMENT_SIGNALS
    )


def has_color(stream, environment=os.environ) -> bool:
    if is_agent_session(environment):          # aunque haya TTY y FORCE_COLOR
        return False
    if environment.get("NO_COLOR") or environment.get("TERM") == "dumb":
        return False
    force_color = environment.get("FORCE_COLOR", "").lower()
    if force_color in ("0", "false"):
        return False
    if force_color:
        return True
    if environment.get("CI", "").lower() not in ("", "0", "false"):   # CI=False no es CI
        return False
    return stream.isatty()


def terminal_columns(stream, environment=os.environ) -> int:
    """Columnas del stream donde se dibuja. shutil.get_terminal_size() mira stdout: con `tool > archivo` da 80."""
    try:
        return os.get_terminal_size(stream.fileno()).columns
    except (AttributeError, OSError, ValueError, io.UnsupportedOperation):
        pass
    columns = environment.get("COLUMNS", "")
    return int(columns) if columns.isascii() and columns.isdigit() and int(columns) > 0 else FALLBACK_COLUMNS


def layout_width(stream) -> int:
    return min(terminal_columns(stream), MAXIMUM_LAYOUT_COLUMNS)


def paint(enabled: bool, color_name: str, text: str) -> str:
    return f"{ESCAPE}{COLORS[color_name]}m{text}{RESET}" if enabled else text


def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_PATTERN.sub("", text)


def _is_open_flag(cluster: str) -> bool:
    return len(cluster) == 1 and ord(cluster) in REGIONAL_INDICATORS


def graphemes(text: str) -> list:
    clusters = []
    for character in text:
        code = ord(character)
        if clusters and (
            unicodedata.category(character) in ("Mn", "Me")
            or character in VARIATION_SELECTORS
            or character == ZERO_WIDTH_JOINER
            or code in SKIN_TONES
            or clusters[-1].endswith(ZERO_WIDTH_JOINER)
            or (code in REGIONAL_INDICATORS and _is_open_flag(clusters[-1]))
        ):
            clusters[-1] += character
            continue
        clusters.append(character)
    return clusters


def cluster_width(cluster: str) -> int:
    if ord(cluster[0]) in REGIONAL_INDICATORS:
        return 2                               # una bandera son dos indicadores y ocupa 2 celdas, no 4
    if "️" in cluster or ZERO_WIDTH_JOINER in cluster or KEYCAP in cluster:
        return 2                               # presentación de emoji: 1️⃣ y 👨‍👩‍👧 miden 2
    return 2 if unicodedata.east_asian_width(cluster[0]) in ("W", "F") else 1


def display_width(text: str) -> int:
    return sum(cluster_width(cluster) for cluster in graphemes(strip_ansi(text)))


def pad_visible(text: str, width: int, align_right=False) -> str:
    padding = " " * max(width - display_width(text), 0)
    return f"{padding}{text}" if align_right else f"{text}{padding}"


def slice_visible(text: str, maximum_width: int) -> str:
    """Prefijo que entra en maximum_width celdas, con al menos un grapheme. Los escapes miden 0 y van enteros."""
    used_width, prefix, has_escapes, was_cut = 0, "", False, False
    for part in ANSI_ESCAPE_PATTERN.split(text):
        if ANSI_ESCAPE_PATTERN.fullmatch(part):
            if not was_cut:
                prefix += part
            has_escapes = True
            continue
        for cluster in graphemes(part):
            if was_cut:
                break
            width = cluster_width(cluster)
            if used_width and used_width + width > maximum_width:
                was_cut = True
                break
            used_width += width
            prefix += cluster
    return prefix + RESET if was_cut and has_escapes else prefix


def truncate_visible(text: str, maximum_width: int) -> str:
    if display_width(text) <= maximum_width:
        return text
    return slice_visible(text, max(maximum_width - 1, 1)) + "…"


def wrap_text(text: str, width: int) -> list:
    """Parte en palabras. Una palabra más ancha que la línea (URL, mail, ID) va sola y entera."""
    lines, line = [], ""
    for word in text.split(" "):
        candidate = f"{line} {word}" if line else word
        if display_width(candidate) <= width:
            line = candidate
            continue
        if line:
            lines.append(line)
        line = word
        if display_width(word) > width:
            lines.append(word)
            line = ""
    if line or not lines:
        lines.append(line)
    return lines


def fit_column_widths(natural_widths, minimum_widths, available_width):
    """Achica primero las columnas más anchas, sin bajar del mínimo de cada una (su palabra más larga)."""
    widths = list(natural_widths)
    excess = sum(widths) - available_width
    for column in sorted(range(len(widths)), key=lambda index: widths[index], reverse=True):
        if excess <= 0:
            break
        reduction = min(excess, widths[column] - minimum_widths[column])
        widths[column] -= reduction
        excess -= reduction
    return widths                                  # si sum(widths) > available_width, apilar


def option_label(emoji: str, word: str, color_enabled: bool) -> str:
    """Sin color (NO_COLOR, TERM=dumb, pipe), la palabra sola: `🚨 PROD` pasa a `PROD`."""
    return f"{emoji} {word}" if color_enabled else word


# Letras grandes de los entornos peligrosos del proyecto: 5 filas del mismo ancho por letra.
BIG_LETTERS = {
    "P": ["████ ", "█   █", "████ ", "█    ", "█    "],
    "R": ["████ ", "█   █", "████ ", "█  █ ", "█   █"],
    "O": [" ███ ", "█   █", "█   █", "█   █", " ███ "],
    "D": ["████ ", "█   █", "█   █", "█   █", "████ "],
}
BIG_LETTER_GAP = " "


def big_text(word: str):
    """Las 5 filas del nombre en letras grandes, o None si falta alguna letra."""
    if any(letter not in BIG_LETTERS for letter in word):
        return None
    return [BIG_LETTER_GAP.join(BIG_LETTERS[letter][row] for letter in word) for row in range(5)]


def render_danger_banner(environment_name: str, subtitle: str, columns: int, color_enabled: bool) -> list:
    """Cartel de entorno peligroso: fondo rojo y letras blancas; sin color, bordes │ y sin fondo."""
    width = min(columns, MAXIMUM_LAYOUT_COLUMNS)
    inner_width = width - 4
    art = big_text(environment_name.upper())
    rows = [""]
    if art and display_width(art[0]) <= inner_width:
        rows += [*art, ""]                         # más angosta que el arte: sin letras grandes
    rows += [*wrap_text(f"{option_label('🚨', environment_name.upper(), color_enabled)} · {subtitle}", inner_width), ""]
    centered = [pad_visible(" " * ((inner_width - display_width(row)) // 2) + row, inner_width) for row in rows]
    if color_enabled:
        return [paint(True, "danger", f"  {row}  ") for row in centered]
    return [f"│ {row} │" for row in centered]


class Spinner:
    """Spinner en un hilo. stop() es idempotente: lo llama quien necesita la terminal y lo llama el final."""

    def __init__(self, stream, label, animate, clock=time.monotonic, interval_seconds=SPINNER_INTERVAL_SECONDS):
        self.stream, self.label, self.animate = stream, label, animate
        self.clock, self.interval_seconds = clock, interval_seconds
        self.note = ""
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._thread = None
        self._is_stopped = False
        self.started_at = clock()

    def elapsed_text(self) -> str:
        total_seconds = int(self.clock() - self.started_at)
        return f"{total_seconds // 60:02d}:{total_seconds % 60:02d}"

    def start(self):
        if not self.animate:
            self.stream.write(f"... {self.label}\n")
            return self
        self.stream.write(HIDE_CURSOR)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def set_note(self, note: str) -> None:
        """Estado durante la espera («reintentando, 2/3»). Sin animación, una línea solo cuando cambia."""
        with self._lock:
            is_new = note != self.note
            self.note = note
        if is_new and note and not self.animate:
            self.stream.write(f"    {note}\n")

    def _run(self) -> None:
        frame_index = 0
        while True:
            frame = SPINNER_FRAMES[frame_index % len(SPINNER_FRAMES)]
            with self._lock:
                note = f" · {self.note}" if self.note else ""
            text = truncate_visible(f"{self.label} {self.elapsed_text()}{note}", terminal_columns(self.stream) - 3)
            self.stream.write(f"{CLEAR_LINE}{frame} {text}")
            self.stream.flush()
            frame_index += 1
            if self._stop_event.wait(self.interval_seconds):   # corta enseguida, sin esperar el intervalo
                return

    def stop(self) -> None:
        with self._lock:
            if self._is_stopped:
                return
            self._is_stopped = True
        self._stop_event.set()
        if self._thread:
            self._thread.join()
            self.stream.write(f"{CLEAR_LINE}{SHOW_CURSOR}")
            self.stream.flush()


@contextmanager
def step(stream, label, animate, clock=time.monotonic):
    """Un paso con spinner. Si termina con cualquier excepción (también Ctrl+C), lo marca ✖ y la relanza.
    Bajo un agente, una sola línea por paso y sin glifos: `Compilar… ok` o `Compilar… error`."""
    is_agent = is_agent_session()
    spinner = Spinner(stream, label, animate and not is_agent, clock)
    if not is_agent:
        spinner.start()
    try:
        yield spinner
    except BaseException:
        spinner.stop()
        stream.write(f"{label}… error\n" if is_agent else f"  {ERROR_GLYPH} {label}\n")
        raise
    spinner.stop()
    stream.write(f"{label}… ok\n" if is_agent else f"  {DONE_GLYPH} {label} · {spinner.elapsed_text()}\n")
```

- La interfaz va a stderr: `ui_stream = sys.stderr`, y el ancho se mide sobre ese stream, no sobre stdout.
- Un prompt que necesita la terminal (el broker de secretos de `interactive-cli-design`) llama a `spinner.stop()` antes de preguntar; el `step` lo vuelve a llamar al final sin efecto.
- `render_table` sigue la forma del kit de Node: `fit_column_widths`, `wrap_text` por celda y, si no entra, filas apiladas.

## 11. Antes y después

Antes: se ve bien una vez, en una sola terminal.

```js
const steps = ['Leer manifiestos', 'Compilar', 'Publicar', 'Verificar'];
const rows = [
  { service: 'api-gateway', version: '3.14.2', status: 'done', duration: '12s' },
  { service: 'billing-worker-eu-central', version: '2.8.0', status: 'changed', duration: '48s' },
  { service: 'notifications', version: '1.9.7', status: 'skipped', duration: '-' },
  { service: 'search-indexer', version: '5.0.0-rc.1', status: 'warning', duration: '1m 03s' },
  { service: 'legacy-importer', version: '0.4.1', status: 'error', duration: '7s' },
];
const dots = { done: 32, changed: 34, skipped: 90, warning: 33, error: 31 };
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

process.stdout.write('\x1b[?25l');
console.log('\x1b[1;36m' + '='.repeat(64) + '\x1b[0m');
for (const step of steps) {
  for (let frame = 0; frame < 15; frame += 1) {
    process.stdout.write(`\r${'|/-\\'[frame % 4]} ${step}`);
    await sleep(100);
  }
  console.log(`\r\x1b[32m●\x1b[0m ${step}`);
}
for (const row of rows) {
  console.log(
    `\x1b[${dots[row.status]}m●\x1b[0m ${row.service.padEnd(30)}${row.version.padEnd(16)}${row.duration.padStart(16)}`,
  );
}
if (process.argv.includes('--json')) console.log(JSON.stringify(rows));
```

Qué falla: escapes en un pipe y en `--json`, cursor oculto para siempre, tabla rota a 40 columnas, una demora inventada de 6 segundos y un estado que solo se distingue por color.

Después: el kit de Node más este cuerpo.

```js
const TOOL_NAME = 'release-status';
const TOOL_VERSION = '2.3.0';
const TOOL_DESCRIPTION = 'Publica los servicios del monorepo y verifica cada despliegue.';
const steps = ['Leer manifiestos', 'Compilar', 'Publicar', 'Verificar'];
const rows = [
  { service: 'api-gateway', version: '3.14.2', status: 'done', duration: '12s' },
  { service: 'billing-worker-eu-central', version: '2.8.0', status: 'changed', duration: '48s' },
  { service: 'notifications', version: '1.9.7', status: 'skipped', duration: '-' },
  { service: 'search-indexer', version: '5.0.0-rc.1', status: 'warning', duration: '1m 03s' },
  { service: 'legacy-importer', version: '0.4.1', status: 'error', duration: '7s' },
];
const columns = [
  { title: 'Servicio', read: (row) => row.service },
  { title: 'Versión', read: (row) => row.version },
  // Bajo un agente, la palabra sola: el glifo es decorativo.
  { title: 'Estado', read: (row) => (uiOutput.isAgent ? THEME.statuses[row.status].word : statusLabel(row.status)), colorOf: (row) => row.status },
  { title: 'Duración', read: (row) => row.duration, alignRight: true },
];
const workMs = Number(process.env.WORK_MS ?? 1500);
const doWork = () => new Promise((resolve) => setTimeout(resolve, workMs));

async function runStep(step, stepIndex) {
  const position = `[${stepIndex + 1}/${steps.length}]`;
  if (uiOutput.isAgent) {
    // Una línea por paso, sin spinner, glifos ni duración aparte.
    try {
      await doWork();
      if (process.argv.includes('--fail') && stepIndex === 2) throw new Error('registry timeout');
    } catch (error) {
      uiOutput.stream.write(`${position} ${step}… error\n`);
      throw error;
    }
    uiOutput.stream.write(`${position} ${step}… ok\n`);
    return;
  }
  uiOutput.stream.write(`${paint(uiOutput, 'muted', position)} ${step}\n`);
  const spinner = startSpinner(uiOutput, step);
  try {
    await doWork();
    if (process.argv.includes('--fail') && stepIndex === 2) throw new Error('registry timeout');
  } finally {
    spinner.stop();
  }
  uiOutput.stream.write(`  ${paint(uiOutput, 'done', statusLabel('done'))} · ${spinner.elapsedText()}\n`);
}

async function main() {
  if (process.argv.includes('--json')) {
    process.stdout.write(`${JSON.stringify(rows)}\n`);
    return;
  }
  if (!uiOutput.isAgent) uiOutput.stream.write(`${renderBox(uiOutput, TOOL_NAME, [TOOL_DESCRIPTION], { version: TOOL_VERSION })}\n`);
  for (const [stepIndex, step] of steps.entries()) await runStep(step, stepIndex);
  uiOutput.stream.write('\n');
  dataOutput.stream.write(`${renderTable(dataOutput, columns, rows)}\n`);
  const summary = [`${rows.length} servicios, 1 con error`, 'Siguiente: pnpm release:notes'];
  // Bajo un agente, el resultado y el próximo comando quedan, sin el recuadro.
  if (uiOutput.isAgent) uiOutput.stream.write(`${summary.join('\n')}\n`);
  else uiOutput.stream.write(`\n${renderBox(uiOutput, 'Listo', summary)}\n`);
}

main().catch((error) => {
  const message = uiOutput.isAgent ? `error: ${error.message}` : `${statusLabel('error')}: ${error.message}`;
  uiOutput.stream.write(`${paint(uiOutput, 'error', message)}\n`);
  process.exitCode = 1;
});
```

Qué cambió: abre con la tarjeta de encabezado (bajo un agente, no: una línea por paso, la palabra del estado sin glifo y el resumen sin recuadro). stdout solo lleva la tabla o el JSON; la tarjeta, los pasos y el resumen van a stderr. El tiempo total es el del trabajo real, a 40 columnas la tabla se apila sin perder datos, y cada estado dice su nombre.

## 12. Verificar

Correr el script real, no una versión escrita para el chequeo.

**Por pipe y a archivo.** Sin escapes, sin `\r` suelto y con todos los datos. En Windows, `\r\n` es un fin de línea normal.

```bash
tool 2>&1 | LC_ALL=C grep -c "$(printf '\033')"   # tiene que dar 0
NO_COLOR=1 tool 2>&1 | LC_ALL=C grep -c "$(printf '\033')"   # tiene que dar 0
tool --json | node -e "JSON.parse(require('fs').readFileSync(0, 'utf8'))"   # JSON válido
```

**En una terminal real, a 120, 80 y 40 columnas, en color y con `NO_COLOR=1`.** Ninguna fila partida, todos los datos a la vista y el tema correcto. A 120 columnas, tablas, recuadros y la tarjeta de encabezado no pasan de 80.

**Ctrl+C durante el spinner.** Cursor visible, línea limpia y estado de salida distinto de 0.

**Un error forzado durante el spinner.** Lo mismo, más una línea de error clara.

**Trabajo de 0 ms.** El script no tarda más que su arranque.

**Casos que los kits tienen que pasar:**

| Caso | Pasa si |
|---|---|
| `truncateVisible` y `renderBox` con texto ya pintado, a 12 y 40 columnas | Ningún escape cortado, el color cerrado y el ancho visible es el pedido |
| Degradé con `🇧🇷` y `👨‍👩‍👧` | La bandera y el emoji se ven enteros; `🇧🇷 BR` mide 5 |
| Tabla con una columna larga (un camino de 6 tramos) a 60 y a 22 columnas | A 60 se parte la celda larga y la tabla se mantiene; a 22, apilada. Ningún dato truncado |
| Recuadro con una URL más ancha que la terminal | La URL va entera y sola en su renglón |
| `tool > archivo` con stderr en una terminal de 40 columnas | La interfaz se dibuja a 40 |
| `NO_COLOR=1` con opciones con emoji | Solo la palabra |
| Producción elegida, a 80, a 24 y sin color | Cartel rojo con letras grandes; a 24, sin letras grandes; sin color, con bordes `│`. Ninguna fila más ancha que la terminal |

**Sin pseudoconsola, en Python.** Lo que no depende de la terminal real se prueba en un test común:

- **Reloj y `sleep` inyectados.** Un `FakeClock` vuelve deterministas las duraciones. `sleep=self.fail` prueba que no hay pausas decorativas; `sleep=delays.append` verifica la secuencia exacta de reintentos sin esperar.
- **`TtyStream`:** un `io.StringIO` que dice ser terminal, para ejercitar el camino con color y animación.
- **Emulador de pantalla mínimo:** interpreta `\n`, `\r`, `ESC[nA` y `ESC[2K`, con el salto diferido en la última columna. Verifica qué queda en pantalla después de redibujar: la pregunta una sola vez, sin restos y ninguna fila más ancha que la terminal.
- **Override del chequeo de terminal** en `can_prompt` para tests, que nunca anula `--no-input`.

```python
import io, re

class FakeClock:
    def __init__(self, now=0.0):
        self.now = now
    def __call__(self):
        return self.now
    def advance(self, seconds):
        self.now += seconds

class TtyStream(io.StringIO):
    def isatty(self):
        return True

SCREEN_CONTROL = re.compile(r"\x1b\[([?\d;]*)([A-Za-z])")

class ScreenEmulator:
    """Lo que queda en pantalla: \\n, \\r, ESC[nA y ESC[2K, con salto diferido en la última columna."""

    def __init__(self, columns):
        self.columns, self.rows, self.row, self.column, self.wrap_pending = columns, [[]], 0, 0, False

    def feed(self, text):
        position = 0
        while position < len(text):
            control = SCREEN_CONTROL.match(text, position)
            if control:
                parameters, command = control.group(1), control.group(2)
                count = int(parameters) if parameters.isdigit() else 1
                if command == "A":
                    self.row, self.wrap_pending = max(self.row - count, 0), False
                elif command == "K" and parameters == "2":
                    self.rows[self.row] = []
                position = control.end()          # ESC[...m, ESC[?25h y el resto no mueven el cursor
                continue
            character = text[position]
            position += 1
            if character == "\n":
                self._next_row()
            elif character == "\r":
                self.column, self.wrap_pending = 0, False
            else:
                self._write(character)

    def _next_row(self):
        self.row, self.column, self.wrap_pending = self.row + 1, 0, False
        while len(self.rows) <= self.row:
            self.rows.append([])

    def _write(self, character):
        if self.wrap_pending:
            self._next_row()
        cells = self.rows[self.row]
        cells.extend(" " * (self.column + 1 - len(cells)))
        cells[self.column] = character
        if self.column == self.columns - 1:
            self.wrap_pending = True               # la terminal recién salta con el próximo carácter
        else:
            self.column += 1

    def lines(self):
        return ["".join(cells).rstrip() for cells in self.rows]
```

El emulador cuenta un carácter por celda: para emojis, medir aparte con `display_width`.


Trampas al automatizar estos chequeos:

- En Windows, `child.kill('SIGINT')` mata el proceso sin correr sus handlers: no equivale a Ctrl+C. Hay que mandar `\x03` a una pseudoconsola real, por ejemplo con `node-pty`.
- ConPTY escribe sus propias secuencias, así que bajo una pseudoconsola no se puede contar escapes. Ese chequeo se hace por pipe. Bajo pseudoconsola, reproducir la salida en un emulador como `@xterm/headless` y leer las celdas.
- Después de Ctrl+C, consultar el cursor en la misma sesión con `[Console]::CursorVisible`.
- Bajo `git-bash.exe` (mintty), un programa nativo ve o no una TTY según la versión de Git for Windows y si usa pseudoconsola. Si no la ve, salir en texto plano es una degradación correcta, no una falla.

Si algo de esto no se puede correr, decirlo en el reporte.
