# Verificación

Correr el CLI real, no una versión escrita para el chequeo. La herramienta de shell de un agente no tiene terminal: desde ahí solo se prueba el camino sin TTY. Los casos con terminal necesitan una pseudoconsola.

## Índice

1. [Matriz](#matriz)
2. [Sin terminal](#sin-terminal)
3. [Con terminal](#con-terminal)
4. [Trampas al automatizar](#trampas-al-automatizar)

## Matriz

| # | Caso | Dónde | Pasa si |
|---|---|---|---|
| a | `--help`, `-h`, `--version` | Sin y con terminal | Exit 0, salida en stdout, sin preguntas. La ayuda lista todas las flags en dos columnas alineadas. Con terminal, comandos y flags en colores distintos; a pipe, a 40 columnas o con `NO_COLOR=1`, sin escapes, las mismas columnas y ninguna descripción cortada |
| b | Sin argumentos | Con terminal | Aparecen los prompts. Con teclas reales, el resultado es idéntico al de la llamada con flags, y el comando impreso lo reproduce |
| c | Sin argumentos | Sin terminal | No se cuelga, exit 2, stderr nombra los flags faltantes, nada escrito |
| d | Todo por flags | Con terminal | Cero prompts, exit 0 |
| e | Falta un solo dato | Con terminal | Pregunta solo ese |
| f | Ctrl+C en el primer prompt y en el último | Con terminal | Exit 130, cursor visible, ningún archivo |
| g | Flag desconocido y valor inválido | Sin y con terminal | Exit 2, error en stderr con los valores válidos, stdout vacío, sin caer a preguntar |
| h | stdout a pipe o archivo, y `NO_COLOR=1` | Ambos | Sin secuencias de escape en la salida. Con `tool > archivo` en una terminal, los prompts se ven y el archivo solo tiene datos |
| i | Sin argumentos, si puede correr sin flags | Ambos | Corre directo, sin prompts |
| j | `--no-input` y `CI=1` con datos faltantes | Con terminal | Como c |
| k | Acción peligrosa sin el flag | Sin terminal | Falla y no cambia nada |
| l | Multiselect vacío, si vale | Con terminal | El comando impreso lo reproduce sin preguntar |
| m | Flag abreviado (`--tok`) | Sin terminal | Exit 2, como un flag desconocido |
| n | Secreto pasado como `--x v`, `--x=v`, `-xv` y por variable | Ambos | El valor no aparece en la salida, en el comando equivalente ni en lo que se guarda |
| o | Lista con filtro: escribir parte de una opción y Enter | Con terminal | Elige esa opción. Sin color, el menú es numerado |
| p | Segunda corrida, si recuerda respuestas | Con terminal | La anterior aparece primero y Enter la elige. Con el archivo ilegible, avisa y pregunta igual |
| q | Ctrl+C dos veces seguidas | Con terminal | Un solo aviso, exit 130, sin traceback |
| r | Ctrl+C o falla después del primer efecto | Con terminal | Lista lo que quedó hecho y el comando para seguir |

## Sin terminal

```bash
tool --help; echo "exit=$?"
tool --help | LC_ALL=C grep -c "$(printf '\033')"   # tiene que dar 0: a un pipe, la ayuda va sin color
COLUMNS=40 tool --help                              # las descripciones se parten o se apilan, no se cortan
tool </dev/null >out.txt 2>err.txt; echo "exit=$?"; cat err.txt
tool --nope </dev/null; echo "exit=$?"
tool --name demo --runtime go </dev/null | LC_ALL=C grep -c "$(printf '\033')"   # tiene que dar 0
```

## Con terminal

`node-pty` abre una pseudoconsola real en Windows, macOS y Linux. Instalarlo en un directorio temporal, nunca como dependencia del proyecto, salvo que los tests ya lo usen. Trae binarios para Windows y macOS: un aviso de pnpm sobre scripts de build ignorados no impide usarlo ahí. En Linux se compila al instalarlo: hacen falta `build-essential` y `python3`, y usar `npm install`, porque pnpm no corre el build. Sin compilador, el módulo `pty` de Python o `script -qec` cumplen el mismo papel.

```js
// pty-check.cjs: espera un texto en pantalla y recién entonces manda las teclas.
const pty = require('node-pty');

const ENTER = '\r';
const ARROW_DOWN = '\x1b[B';
const SPACE = ' ';
const CONTROL_C = '\x03';
const KEY_DELAY_MS = 150;
const EXIT_LIMIT_MS = 15000;

const stripEscapes = (text) => text.replace(/\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07/g, '');
const delay = (milliseconds) => new Promise((done) => setTimeout(done, milliseconds));

async function runInPty(file, args, steps, env = {}) {
  const child = pty.spawn(file, args, { cols: 120, rows: 40, cwd: process.cwd(), env: { ...process.env, ...env } });
  let raw = '';
  let seenUpTo = 0;
  let exitCode = null;
  child.onData((chunk) => {
    raw += chunk;
  });
  const exited = new Promise((done) => {
    child.onExit((event) => {
      exitCode = event.exitCode;
      done();
    });
  });
  for (const { waitFor, send } of steps) {
    const startedAt = Date.now();
    while (exitCode === null && !waitFor.test(stripEscapes(raw.slice(seenUpTo)))) {
      if (Date.now() - startedAt > EXIT_LIMIT_MS) return { exitCode, raw, stuckAt: String(waitFor) };
      await delay(50);
    }
    seenUpTo = raw.length;
    await delay(KEY_DELAY_MS);
    for (const keys of send) {
      if (exitCode === null) child.write(keys);
      await delay(KEY_DELAY_MS);
    }
  }
  await Promise.race([exited, delay(EXIT_LIMIT_MS)]);
  return { exitCode, raw, cursorHidden: raw.lastIndexOf('\x1b[?25l') > raw.lastIndexOf('\x1b[?25h') };
}

(async () => {
  const result = await runInPty(process.execPath, ['tool.js'], [
    { waitFor: /Nombre/, send: [`demo${ENTER}`] },
    { waitFor: /Runtime/, send: [ARROW_DOWN, ENTER] },
    { waitFor: /Features/, send: [SPACE, ARROW_DOWN, SPACE, ENTER] },
  ]);
  console.log(result.exitCode, result.cursorHidden, result.stuckAt ?? '');
  console.log(stripEscapes(result.raw));
  process.exit(0);
})();
```

Para el caso f, mandar `CONTROL_C` en el paso del prompt elegido y comprobar exit 130, `cursorHidden` en `false` y que no quedó ningún archivo.

Para `tool > archivo` en una terminal, lanzar el shell dentro de la pseudoconsola. En Windows, los argumentos van como un solo string para que `node-pty` no escape las comillas: `pty.spawn('cmd.exe', '/d /s /c "node tool.js > out.txt"', options)`.

## Trampas al automatizar

- **Ctrl+C.** En Windows, `child.kill('SIGINT')` mata el proceso sin correr sus handlers. Mandar `\x03` a la pseudoconsola.
- **Escapes bajo ConPTY.** ConPTY escribe sus propias secuencias, así que bajo pseudoconsola no se cuentan escapes: ese chequeo se hace por pipe. Para saber si hay color en un prompt, reproducir la salida en `@xterm/headless` y mirar las celdas con `isFgDefault()` e `isBgDefault()`.
- **Cursor.** Gana la última secuencia entre `\x1b[?25l` y `\x1b[?25h` del flujo crudo.
- **Teclas antes de tiempo.** Un menú puede pintarse después de la pregunta, y el texto mandado a un menú se pierde o se cuela en el prompt siguiente. Esperar un texto de la opción, no solo de la pregunta, si hace falta.
- **Primer dibujo lento.** `gum` y otras apps de Bubble Tea le preguntan a la terminal su color de fondo, y un PTY sin emulador no contesta: en Linux tardaron unos 5 s en dibujar. No es lentitud del CLI, pero las teclas mandadas antes se pierden.
- **Formularios de `huh`.** Un grupo con varios campos muestra todas las preguntas a la vez: mandar las teclas en el orden de los campos, no según la última pregunta en pantalla. El filtro de una lista se abre con `/`.
- **`TERM` heredado.** Si el proceso padre no tiene terminal, `TERM` puede llegar vacío o como `dumb`, y el CLI no va a preguntar. Definir `TERM=xterm-256color` en el entorno de la pseudoconsola.
- **`bash` en Windows.** Desde `cmd.exe`, `bash` a secas puede ser el lanzador de WSL. Usar la ruta de Git Bash.
- **`node-pty` mantiene vivo al proceso.** Terminar con `process.exit()`. En Windows, llamar a `kill()` sobre un hijo que ya salió imprime `AttachConsole failed`.
- **Comando con un `.cmd` o sin extensión.** `pty.spawn` necesita un ejecutable real. Para `pnpm`, `npm` o un script, pasar por `cmd.exe /d /s /c`.
- **mintty.** Bajo `git-bash.exe`, un programa nativo puede no ver una terminal y comportarse como en el caso c. No es una falla del CLI.

Si algo de esto no se puede correr, decirlo en el reporte.
