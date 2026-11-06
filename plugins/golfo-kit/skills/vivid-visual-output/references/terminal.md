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
10. [Antes y después](#10-antes-y-después)
11. [Verificar](#11-verificar)

## 1. Capacidades

Decidir por stream, stdout y stderr por separado, y en este orden. Con `tool | jq`, stdout queda limpio y el spinner sigue vivo en stderr.

| Orden | Señal | Resultado |
|---|---|---|
| 1 | Salida para máquinas (`--json` y similares) | Nunca lleva decoración |
| 2 | Flag explícito de la herramienta (`--color=never`, `--color=always`) | Manda el flag |
| 3 | `NO_COLOR` no vacía, o `TERM=dumb` | Texto plano, aunque esté `FORCE_COLOR` |
| 4 | `FORCE_COLOR=0` o `false` | Texto plano |
| 5 | Otro `FORCE_COLOR` no vacío | Color aun en CI o sin TTY, pero sin animación si no hay TTY |
| 6 | `CI` definida (distinta de `0` y `false`), o stream que no es TTY | Texto plano |
| 7 | Todo lo demás | La mejor profundidad disponible: truecolor, 256, 16 |

Texto plano significa sin ningún escape, sin `\r` suelto y sin animación. El progreso sigue: una línea al empezar cada paso, otra al terminar y un latido cada 20 s en procesos largos.

Trampas de cada plataforma:

- **Node:** `getColorDepth()` devuelve 24 con `CI=1`. Con `NO_COLOR=1 FORCE_COLOR=3` también devuelve 24, y además emite un warning por stderr. Chequear los pasos 1 a 6 antes de llamarla.
- **`FORCE_COLOR=0`:** `Boolean('0')` es `true`, así que un chequeo de veracidad enciende el color. force-color.org dice que cualquier valor no vacío fuerza; la documentación de Node y este contrato tratan `0` como apagado.
- **`NO_COLOR=""`:** no cuenta. El estándar pide que esté presente y no vacía.
- **PowerShell, redirección del proceso:** `$PSStyle.OutputRendering` no aplica a la salida del proceso host, así que `pwsh script.ps1 | cat` no quita los escapes. Hay que decidir antes de escribirlos.
- **PowerShell, captura en la sesión:** con `$datos = ./script.ps1` o `./script.ps1 > archivo`, `IsOutputRedirected` da `false` y `PipelineLength` da 1, y el texto puro llega con sus escapes. Pintar stdout solo cuando la invocación descarta una captura, como hace el kit.
- **bash, `$(...)`:** adentro, el descriptor 1 es un pipe, así que `$(funcion_que_mira_-t_1)` siempre responde que no hay TTY. Guardar `[ -t 1 ]` antes, en el nivel superior.
- **bash, `tput`:** `$(tput cols 2>/dev/null)` deja a `tput` sin ningún descriptor conectado a la terminal y devuelve siempre 80. Leer con `stty size </dev/tty`.

## 2. Anatomía de una corrida

```text
╭────────────────────────────╮
│ release-status · 4 pasos   │   banner: una o dos líneas, sin logos gigantes
╰────────────────────────────╯
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

- El producto de la herramienta (tabla, lista, JSON) va a stdout. Banner, pasos, spinner, resumen y errores van a stderr.
- El resumen dice qué pasó y qué hacer ahora. El código de salida dice lo mismo que el resumen.
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

## 4. Ancho

- Con TTY, leer el ancho real en cada dibujo, porque puede cambiar durante la corrida. Sin TTY no hay ancho: no truncar ni partir nada.
- Si la tabla no entra, pasar a formato apilado: una línea por campo debajo del nombre. Nunca truncar un dato.
- Lo mismo vale para toda línea propia: pasos, errores, banner y el contenido del resumen, también dentro de un recuadro. Partirlas con el mismo ajuste, porque una sola línea larga rompe el recuadro a 40 columnas.
- Lo decorativo sí se recorta: etiqueta del spinner, reglas y bordes. La línea del spinner tiene que medir menos que el ancho, o la terminal la parte y `\r` ya no la borra.
- Medir graphemes y no bytes. `ñ` ocupa una celda; un ideograma, dos.

## 5. Esperas

- **Total conocido:** barra o contador con porcentaje. **Total desconocido:** spinner.
- Mostrar el tiempo transcurrido siempre que la espera pueda superar unos segundos.
- Un cuadro cada 80 a 120 ms, solo con TTY. Antes de escribir cualquier otra línea, parar el spinner y limpiar la suya.
- El trabajo síncrono congela los timers: correrlo en async, en un proceso hijo o en un job.
- La pausa entre cuadros existe solo mientras hay trabajo pendiente. Medir: con trabajo de 0 ms, el script no tarda más que su arranque.

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
const COLUMN_GAP = 2;

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

/** Devuelve la profundidad de color de un stream: 1 (plano), 4, 8 o 24 bits. */
function detectColorDepth(stream, env = process.env) {
  const forceColor = env.FORCE_COLOR;
  if (env.NO_COLOR || env.TERM === 'dumb' || forceColor === '0' || forceColor === 'false') return 1;
  if (forceColor) return { 1: 4, 2: 8, 3: 24 }[forceColor] ?? 4;
  const isContinuousIntegration = env.CI && env.CI !== '0' && env.CI !== 'false';
  if (isContinuousIntegration || !stream.isTTY) return 1;
  return stream.getColorDepth();
}

function createOutput(stream) {
  const depth = detectColorDepth(stream);
  return {
    stream,
    depth,
    canAnimate: depth > 1 && Boolean(stream.isTTY),
    get width() {
      return stream.isTTY ? stream.columns : Infinity;
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
  const characters = [...text];
  const { from, to } = THEME.gradient;
  const painted = characters.map((character, index) => {
    const ratio = index / Math.max(characters.length - 1, 1);
    const rgb = from.map((channel, channelIndex) => Math.round(channel + (to[channelIndex] - channel) * ratio));
    return `${ESCAPE}1;38;2;${rgb.join(';')}m${character}`;
  });
  return `${painted.join('')}${ESCAPE}0m`;
}

const WIDE_CHARACTER = /[\p{Emoji_Presentation}ᄀ-ᅟ⺀-꓏가-힣豈-﫿︰-﹯＀-｠￠-￦]/u;
const graphemeSegmenter = new Intl.Segmenter();

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

/** Prefijo que entra en maximumWidth celdas. Siempre lleva un grapheme, para que el ajuste avance. */
function sliceVisible(text, maximumWidth) {
  let usedWidth = 0;
  let prefix = '';
  for (const { segment } of graphemeSegmenter.segment(text)) {
    usedWidth += WIDE_CHARACTER.test(segment) ? 2 : 1;
    if (prefix && usedWidth > maximumWidth) break;
    prefix += segment;
  }
  return prefix;
}

function truncateVisible(text, maximumWidth) {
  if (visibleWidth(text) <= maximumWidth) return text;
  return `${sliceVisible(text, Math.max(maximumWidth - 1, 1))}…`;
}

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
    while (visibleWidth(line) > width) {
      const fittingPart = sliceVisible(line, width);
      lines.push(fittingPart);
      line = line.slice(fittingPart.length);
    }
  }
  if (line || lines.length === 0) lines.push(line);
  return lines;
}

function statusLabel(statusName) {
  const { glyph, word } = THEME.statuses[statusName];
  return `${glyph} ${word}`;
}

/** Cada columna: { title, read(row), colorOf?(row), alignRight? }. Apila las filas si no entran. */
function renderTable(output, columns, rows) {
  const columnWidths = columns.map(({ title, read }) =>
    Math.max(visibleWidth(title), ...rows.map((row) => visibleWidth(read(row)))),
  );
  const tableWidth = columnWidths.reduce((total, width) => total + width, 0) + COLUMN_GAP * (columns.length - 1);
  if (tableWidth > output.width) return renderStackedRows(output, columns, rows);

  const gap = ' '.repeat(COLUMN_GAP);
  const header = columns
    .map(({ title, alignRight }, index) => paintBold(output, padVisible(title, columnWidths[index], { alignRight })))
    .join(gap);
  const body = rows.map((row) =>
    columns
      .map(({ read, colorOf, alignRight }, index) => {
        const cell = padVisible(read(row), columnWidths[index], { alignRight });
        return colorOf ? paint(output, colorOf(row), cell) : cell;
      })
      .join(gap),
  );
  return [header, ...body].join('\n');
}

function renderStackedRows(output, columns, rows) {
  const [titleColumn, ...detailColumns] = columns;
  return rows
    .flatMap((row) => [
      ...wrapText(titleColumn.read(row), output.width).map((line) => paintBold(output, line)),
      ...detailColumns.flatMap(({ title, read, colorOf }) => {
        const cell = `  ${title}: ${read(row)}`;
        return wrapText(cell, output.width).map((line) => (colorOf ? paint(output, colorOf(row), line) : line));
      }),
      '',
    ])
    .join('\n')
    .trimEnd();
}

function renderBox(output, title, lines) {
  const maximumInnerWidth = Math.max(output.width - 4, 1);
  const innerWidth = Math.min(Math.max(...[title, ...lines].map(visibleWidth)), maximumInnerWidth);
  const border = (text) => paint(output, 'accent', text);
  const toRow = (text, painter = (line) => line) =>
    `${border('│')} ${painter(padVisible(text, innerWidth))} ${border('│')}`;
  return [
    border(`╭${'─'.repeat(innerWidth + 2)}╮`),
    ...wrapText(title, innerWidth).map((line) => toRow(line, (text) => paintGradient(output, text))),
    ...lines.flatMap((line) => wrapText(line, innerWidth)).map((line) => toRow(line)),
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
$script:ColumnGap = '  '
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

function Get-ColorDepth {
  param([Parameter(Mandatory)][bool]$IsRedirected)

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
    Depth        = $depth
    CanAnimate   = ($depth -gt 1) -and (-not $isRedirected)
  }
}

function Get-OutputWidth {
  param([Parameter(Mandatory)][hashtable]$Output)

  if ($Output.IsRedirected) { return [int]::MaxValue }
  try { return [Console]::WindowWidth } catch { return 80 }
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

function Get-VisibleWidth {
  param([AllowEmptyString()][string]$Text = '')

  if (-not $Text) { return 0 }
  $usedCells = 0
  $elements = [System.Globalization.StringInfo]::GetTextElementEnumerator($Text)
  while ($elements.MoveNext()) {
    if ($elements.GetTextElement() -match $script:WideCharacter) { $usedCells += 2 } else { $usedCells += 1 }
  }
  return $usedCells
}

# Prefijo que entra en $Width celdas. Siempre lleva un grapheme, para que el ajuste avance.
function Get-FittingPrefix {
  param([AllowEmptyString()][string]$Text = '', [int]$Width)

  if (-not $Text) { return '' }
  $usedCells = 0
  $prefix = ''
  $elements = [System.Globalization.StringInfo]::GetTextElementEnumerator($Text)
  while ($elements.MoveNext()) {
    $element = $elements.GetTextElement()
    if ($element -match $script:WideCharacter) { $usedCells += 2 } else { $usedCells += 1 }
    if ($prefix -and $usedCells -gt $Width) { break }
    $prefix += $element
  }
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
    while ((Get-VisibleWidth $line) -gt $Width) {
      $fittingPart = Get-FittingPrefix -Text $line -Width $Width
      $lines.Add($fittingPart)
      $line = $line.Substring($fittingPart.Length)
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
  $outputWidth = Get-OutputWidth -Output $Output

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

function Write-Box {
  param([Parameter(Mandatory)][hashtable]$Output, [Parameter(Mandatory)][string]$Title, [Parameter(Mandatory)][AllowEmptyCollection()][string[]]$Lines)

  $widest = (Get-VisibleWidth $Title)
  foreach ($line in $Lines) { $widest = [Math]::Max($widest, (Get-VisibleWidth $line)) }
  $innerWidth = [Math]::Min($widest, [Math]::Max((Get-OutputWidth -Output $Output) - 4, 1))
  $horizontal = ([string][char]0x2500) * ($innerWidth + 2)
  $side = Format-Paint -Output $Output -ColorName accent -Text ([string][char]0x2502)
  Write-Ui (Format-Paint -Output $Output -ColorName accent -Text "$([char]0x256D)$horizontal$([char]0x256E)")
  foreach ($line in (Split-TextToWidth -Text $Title -Width $innerWidth)) {
    Write-Ui "$side $(Format-Paint -Output $Output -ColorName accent -Bold -Text (Format-Pad -Text $line -Width $innerWidth)) $side"
  }
  foreach ($sourceLine in $Lines) {
    foreach ($line in (Split-TextToWidth -Text $sourceLine -Width $innerWidth)) {
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
SPINNER_FRAME_COUNT=10
SPINNER_INTERVAL_SECONDS=0.09
HEARTBEAT_SECONDS=20

color_depth() { # 1 si el stream es una TTY, 0 si no
  if [ -n "${NO_COLOR:-}" ] || [ "${TERM:-}" = dumb ]; then echo 1; return; fi
  case "${FORCE_COLOR:-}" in
    0 | false) echo 1; return ;;
    1) echo 4; return ;;
    2) echo 8; return ;;
    3) echo 24; return ;;
    '') ;;
    *) echo 4; return ;;
  esac
  case "${CI:-}" in
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

# Lee filas separadas por | desde stdin; la primera son los títulos. La columna $3 trae un estado.
render_table() { # profundidad, ancho (0 = sin límite), número de la columna de estado
  awk -F'|' -v depth="$1" -v width="$2" -v status_column="$3" -v esc="$ESC" \
    -v done_code="$(color_code done "$1")" -v skipped_code="$(color_code skipped "$1")" \
    -v changed_code="$(color_code changed "$1")" -v warning_code="$(color_code warning "$1")" \
    -v error_code="$(color_code error "$1")" '
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
    # Parte el texto antes de pintarlo, en un espacio si hay uno: un dato largo no se trunca ni rompe la fila.
    function print_stacked(text, style, cut, position) {
      while (length(text) > width) {
        cut = width
        for (position = width + 1; position > 3; position--) {
          if (substr(text, position, 1) == " ") { cut = position - 1; break }
        }
        print_styled(substr(text, 1, cut), style)
        text = substr(text, cut + 1)
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
        if (length(value) > widest[i]) widest[i] = length(value)
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
          padded = sprintf("%s%" (widest[i] - length(cell[row, i])) "s", cell[row, i], "")
          if (row == 1) padded = bold(padded)
          else if (i == status_column) padded = paint(status[row], padded)
          line = line (i > 1 ? "  " : "") padded
        }
        print line
      }
    }'
}

# Lee las líneas del recuadro desde stdin; la primera es el título.
render_box() { # profundidad, ancho (0 = sin límite)
  awk -v depth="$1" -v width="$2" -v esc="$ESC" -v accent_code="$(color_code accent "$1")" '
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
        else if (length(current) + 1 + length(words[position]) <= inner) current = current " " words[position]
        else { wrapped[++wrapped_count] = current; current = words[position] }
        while (length(current) > inner) {
          wrapped[++wrapped_count] = substr(current, 1, inner)
          current = substr(current, inner + 1)
        }
      }
      wrapped[++wrapped_count] = current
    }
    {
      source[NR] = $0
      if (length($0) > widest) widest = length($0)
    }
    END {
      inner = widest
      if (width > 0 && inner > width - 4) inner = width - 4
      for (row = 1; row <= NR; row++) append_wrapped(source[row])
      print accent("╭" repeat_text("─", inner + 2) "╮")
      for (row = 1; row <= wrapped_count; row++) {
        print accent("│") " " sprintf("%s%" (inner - length(wrapped[row])) "s", wrapped[row], "") " " accent("│")
      }
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
  # Con set -e, un trabajo de varios pasos no sigue con el próximo si Ctrl+C cortó el actual.
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

## 10. Antes y después

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
  { title: 'Estado', read: (row) => statusLabel(row.status), colorOf: (row) => row.status },
  { title: 'Duración', read: (row) => row.duration, alignRight: true },
];
const workMs = Number(process.env.WORK_MS ?? 1500);
const doWork = () => new Promise((resolve) => setTimeout(resolve, workMs));

async function runStep(step, stepIndex) {
  uiOutput.stream.write(`${paint(uiOutput, 'muted', `[${stepIndex + 1}/${steps.length}]`)} ${step}\n`);
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
  uiOutput.stream.write(`${renderBox(uiOutput, `release-status · ${steps.length} pasos`, [])}\n`);
  for (const [stepIndex, step] of steps.entries()) await runStep(step, stepIndex);
  uiOutput.stream.write('\n');
  dataOutput.stream.write(`${renderTable(dataOutput, columns, rows)}\n`);
  uiOutput.stream.write('\n');
  uiOutput.stream.write(
    `${renderBox(uiOutput, 'Listo', [`${rows.length} servicios, 1 con error`, 'Siguiente: pnpm release:notes'])}\n`,
  );
}

main().catch((error) => {
  const message = `${statusLabel('error')}: ${error.message}`;
  uiOutput.stream.write(`${paint(uiOutput, 'error', message)}\n`);
  process.exitCode = 1;
});
```

Qué cambió: stdout solo lleva la tabla o el JSON; los pasos y el resumen van a stderr. El tiempo total es el del trabajo real, a 40 columnas la tabla se apila sin perder datos, y cada estado dice su nombre.

## 11. Verificar

Correr el script real, no una versión escrita para el chequeo.

**Por pipe y a archivo.** Sin escapes, sin `\r` suelto y con todos los datos. En Windows, `\r\n` es un fin de línea normal.

```bash
tool 2>&1 | LC_ALL=C grep -c "$(printf '\033')"   # tiene que dar 0
NO_COLOR=1 tool 2>&1 | LC_ALL=C grep -c "$(printf '\033')"   # tiene que dar 0
tool --json | node -e "JSON.parse(require('fs').readFileSync(0, 'utf8'))"   # JSON válido
```

**En una terminal real, a 80 y a 40 columnas, en color y con `NO_COLOR=1`.** Ninguna fila partida, todos los datos a la vista y el tema correcto.

**Ctrl+C durante el spinner.** Cursor visible, línea limpia y estado de salida distinto de 0.

**Un error forzado durante el spinner.** Lo mismo, más una línea de error clara.

**Trabajo de 0 ms.** El script no tarda más que su arranque.

Trampas al automatizar estos chequeos:

- En Windows, `child.kill('SIGINT')` mata el proceso sin correr sus handlers: no equivale a Ctrl+C. Hay que mandar `\x03` a una pseudoconsola real, por ejemplo con `node-pty`.
- ConPTY escribe sus propias secuencias, así que bajo una pseudoconsola no se puede contar escapes. Ese chequeo se hace por pipe. Bajo pseudoconsola, reproducir la salida en un emulador como `@xterm/headless` y leer las celdas.
- Después de Ctrl+C, consultar el cursor en la misma sesión con `[Console]::CursorVisible`.
- Bajo `git-bash.exe` (mintty), un programa nativo ve o no una TTY según la versión de Git for Windows y si usa pseudoconsola. Si no la ve, salir en texto plano es una degradación correcta, no una falla.

Si algo de esto no se puede correr, decirlo en el reporte.
