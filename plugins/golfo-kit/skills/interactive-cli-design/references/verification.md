# Verificación

Correr el CLI real, no una versión escrita para el chequeo. La herramienta de shell de un agente no tiene terminal: desde ahí solo se prueba el camino sin TTY. Los casos con terminal necesitan una pseudoconsola.

## Índice

1. [Matriz](#matriz)
2. [Sin terminal](#sin-terminal)
3. [Con terminal](#con-terminal)
4. [Python, sin node-pty](#python-sin-node-pty)
5. [Servidor de prueba](#servidor-de-prueba)
6. [Trampas al automatizar](#trampas-al-automatizar)

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

Si el CLI resuelve secretos en un wrapper, chequea permisos, crea recursos por API o los guarda ([remote-actions.md](remote-actions.md), [preflight.md](preflight.md)):

| # | Caso | Dónde | Pasa si |
|---|---|---|---|
| s | Wrapper con broker: un comando sin secreto (`--help`, `--list`, `--history`) y uno con secreto | Ambos | El primero no llama al CLI de login ni al llavero (log del binario falso vacío). El segundo lo pide una sola vez por corrida. `ps` durante la corrida no muestra el valor en ningún argv. El directorio de las FIFOs no existe al terminar, también con Ctrl+C |
| t | Secreto cacheado rechazado por el servicio | Ambos | Se borra del llavero, se pide uno nuevo una sola vez y el flujo sigue. Con `--token-file` explícito rechazado: error claro, sin pedir otro |
| u | `--check-access` con un permiso faltante y otro sin respuesta | Sin terminal | Lista el faltante con su link y el «sin verificar» aparte. Exit distinto de 0. Ningún request de escritura en prod |
| v | Primera alta en un entorno sin un permiso opcional | Con terminal | Chequea solo, pregunta si seguir y, si se sigue, crea con un aviso. La segunda alta en el mismo entorno no vuelve a chequear (salvo en prod) |
| w | Primera alta sin un permiso obligatorio | Sin terminal | No crea nada, muestra el reporte, exit distinto de 0 |
| x | Alta completa y alta cortada después del primer efecto | Ambos | Las dos quedan en el índice. La incompleta, con `▲ incompleto`, los IDs reales y el comando para seguir con el mismo recurso. Archivos con `600` |
| y | Dos corridas que guardan a la vez | Sin terminal | El índice tiene las dos filas, sin Markdown roto. `--history` las muestra, la más nueva primero, sin pedir el secreto |
| z | Un paso opcional responde 403 | Ambos | Aviso con el permiso que falta. El flujo sigue, el resumen lo marca pendiente, exit 0. Un 500 en ese paso antes del recurso principal no se tolera |
| aa | El cambio de estado responde 500 pero se aplicó; otro responde 200 pero quedó en otro estado | Ambos | El primero sigue con aviso. El segundo se detiene diciendo qué se pidió y en qué quedó |
| bb | Valor con buena forma que no existe en la fuente | Sin terminal | Exit 2, sugiere los parecidos y el comando `--list`. Nada creado |
| cc | Producción sin `--confirm-prod`, y con terminal respondiendo Enter | Ambos | Sin terminal: exit 2 antes de cualquier request (el servidor falso no recibe ninguno). Con terminal: cartel rojo, Enter no crea nada; escribiendo `prod`, crea. El resumen muestra `🚨 PROD` |
| dd | La fuente devuelve un dato distinto al enviado | Ambos | El resumen muestra el de la fuente |
| ee | Respuesta 2xx con forma inesperada que trae una contraseña | Ambos | El error no incluye el cuerpo ni la contraseña |
| ff | Menú con etiquetas de color: escribir `m` y después algo que no coincide con nada | Con terminal | Con `m` solo quedan las opciones con «m» en el texto visible. Sin coincidencias se ve «nada coincide…» y Enter no elige. Al cambiar el filtro, el resaltado va a la primera. La pista «escribí para filtrar» está al lado de la pregunta |
| gg | `--dry-run` cuando el valor inicial lo decide el servidor | Sin terminal | Una rama por cada valor inicial posible, sin efectos |
| hh | Registro con un `\|` y un salto de línea en un dato, y después `--history` | Sin terminal | La fila del índice queda alineada y `--history` la muestra con el `\|` original |
| jj | Menú nativo: tipear una tecla mientras se redibuja, o pegar texto | Con terminal | No se pierde ninguna tecla |
| mm | 500, 429, 400 y 2xx inesperado en un GET; 500 en un POST; 503 de API que levanta en un POST | Sin terminal | Se reintentan solo el 500 y el 429 del GET y el 503 del POST, con esperas 1, 2 y 4 (verificadas con `sleep` inyectado). El error dice cuántos intentos |
| nn | Token con un `\n` al final (por ejemplo, pegado) | Ambos | El error no muestra el token |
| oo | `-ssx` cuando existen `-s` y un corto de dos letras | Sin terminal | No se definen cortos de varias letras; si existieran, el test documenta que `-ssx` es `-s sx` |
| pp | `--user-id 5 --user 5`, `--user-id 5 --user 6`, y `-c` con `user: 6` más `--user-id 5` | Sin terminal | Vale, exit 2, y vale con 5 |
| qq | `--history` sin ningún otro flag; `--list` sin los datos de crear | Sin terminal | Corren sin pedir lo de crear |
| rr | Archivo de configuración con JSON roto, una lista en vez de objeto, `null`, un tipo incorrecto y la clave del token | Sin terminal | Error con línea y columna; error de objeto; `null` = ausente; error con el tipo; error que nombra la alternativa al token |
| ss | Wizard que crea | Con terminal | Muestra el plan y confirma; «no» deja exit 0 sin efectos. Con todo por flag no confirma |
| tt | El recurso ya existe | Ambos | Corta con sus IDs, sin crear nada |
| uu | Lo pedido no se puede (recurso nuevo sin tipo disponible) | Ambos | Con terminal pregunta con default «no»; sin terminal corta antes del primer efecto y nombra el flag de la alternativa |
| vv | Archivo de respuestas editado a mano con un valor inválido, en formato viejo y con una clave ajena | Con terminal | Descarta el inválido con aviso, lee el formato viejo, guarda en el nuevo y conserva la clave ajena |
| ww | Dato generado por default con semilla fija | Sin terminal | Pasa la validación, no es degenerado y es el mismo en cada corrida del test |
| aaa | En el menú: Supr, Inicio, un pegado con `\t`; confirm con «x» y con Enter | Con terminal | El filtro no cambia con las teclas especiales; «x» repite la pregunta; Enter toma el default |
| bbb | `CI=False` y `CI=FALSE` con terminal | Con terminal | Pregunta: no cuenta como CI |

Los casos de la salida visual (cortes con color, banderas y ZWJ, tablas con una columna larga, ancho medido en stderr, URLs en un recuadro y emojis sin color) no se repiten acá: están en `vivid-visual-output` (`references/terminal.md`, «Verificar», tabla «Casos que los kits tienen que pasar»).

## Sin terminal

```bash
tool --help; echo "exit=$?"
tool --help | LC_ALL=C grep -c "$(printf '\033')"   # tiene que dar 0: a un pipe, la ayuda va sin color
COLUMNS=40 tool --help                              # las descripciones se parten o se apilan, no se cortan
COLUMNS=120 tool --help | awk 'length > 80' | wc -l  # tiene que dar 0: la tabla no pasa de 80 columnas
tool </dev/null >out.txt 2>err.txt; echo "exit=$?"; cat err.txt
tool --nope </dev/null; echo "exit=$?"
tool --name demo --runtime go </dev/null | LC_ALL=C grep -c "$(printf '\033')"   # tiene que dar 0
```

`tool </dev/null` no impide abrir `/dev/tty`: si el test corre desde la terminal del desarrollador, un wrapper que lee de `/dev/tty` le pregunta a esa terminal y el caso c se cuelga. Lanzarlo en una sesión nueva, sin terminal de control: `setsid tool </dev/null` o, en Python, `subprocess.run(..., stdin=subprocess.DEVNULL, start_new_session=True)`.

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

## Python, sin node-pty

Con `pty` y `termios` de la biblioteca estándar (macOS y Linux; en Windows, WSL).

**Leer teclas sobre `os.openpty()`**, para probar el menú sin lanzar el CLI:

- Apagar `ECHO` en el lado esclavo; si no, el eco llena el maestro, nadie lo lee y `TCSADRAIN` espera para siempre.
- Esperar a que `ICANON` se apague (el prompt entró en cbreak) antes de tipear.
- Leer en un hilo con `join(timeout)`, para detectar una lectura colgada en vez de colgar el test.

**Correr el CLI entero con `pty.fork()`:**

```python
import os, pty, select, signal, time

READ_CHUNK_BYTES = 4096
RUN_LIMIT_SECONDS = 15

def run_in_pty(argv, keys_after=(), limit_seconds=RUN_LIMIT_SECONDS):
    """Corre argv en una pseudoconsola. keys_after: pares (texto en pantalla, teclas a mandar)."""
    process_id, master = pty.fork()
    if process_id == 0:
        os.execvp(argv[0], argv)
    output, pending_keys, deadline = b"", list(keys_after), time.monotonic() + limit_seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            os.kill(process_id, signal.SIGKILL)
            break
        ready, _, _ = select.select([master], [], [], min(remaining, 0.1))
        if ready:
            try:
                chunk = os.read(master, READ_CHUNK_BYTES)
            except OSError:          # en Linux, EIO cuando el hijo ya salió: es fin de la salida
                break
            if not chunk:
                break
            output += chunk
        while pending_keys and pending_keys[0][0].encode() in output:
            os.write(master, pending_keys.pop(0)[1].encode())
    _, status = os.waitpid(process_id, 0)
    os.close(master)
    return os.waitstatus_to_exitcode(status), output.decode(errors="replace")
```

- Ctrl+C es `"\x03"`. A través de un wrapper, aceptar `130` o `-SIGINT`: el Ctrl+C le llega a todo el grupo y el wrapper puede morir por la señal.
- Si el primer Ctrl+C no canceló, volver a mandarlo una vez: a veces se pierde mientras el prompt cambia el modo de la terminal.
- Lo que no necesita pty (duraciones, reintentos, redibujo, camino con color) se prueba con reloj y `sleep` inyectados, un stream que dice ser TTY y un emulador de pantalla mínimo: `vivid-visual-output` (`references/terminal.md`, «Verificar»).

## Servidor de prueba

Si el CLI llama a APIs, los flujos se prueban de punta a punta contra un servidor HTTP local en `127.0.0.1:0` (puerto libre), levantado por el test, que guarda cada request y responde según rutas. Así se prueban el cliente, los reintentos, el parseo de errores y el orden de los pasos sin tocar la red ni mockear la librería HTTP.

- Los binarios externos (CLI de login, `security`) se reemplazan por scripts falsos en el `PATH` del test, que escriben un log y nunca tocan el llavero real.
- El wrapper se prueba en una pseudoconsola con su `main` real, o con uno mínimo que solo pide el secreto y muestra su **origen**, nunca el valor.

```python
import json, re, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

NOT_FOUND_STATUS_CODE = 404

class FakeApiServer:
    def __init__(self):
        self.requests, self.routes = [], []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_class())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def respond(self, method, path_pattern, status, body):
        """`body` puede ser una función `(request) -> (status, cuerpo)` para respuestas con estado."""
        self.routes.insert(0, (method, re.compile(path_pattern), status, body))

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exception_info):
        self.server.shutdown()
        self.server.server_close()

    def _handler_class(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *arguments):
                pass

            def _handle(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw_body = self.rfile.read(length).decode() if length else ""
                request = {"method": self.command, "path": self.path, "body": json.loads(raw_body) if raw_body else None}
                fake.requests.append(request)
                for method, pattern, status, body in fake.routes:
                    if method == self.command and pattern.search(self.path):
                        if callable(body):
                            status, body = body(request)
                        is_text = isinstance(body, str)
                        payload = (body if is_text else json.dumps(body)).encode()
                        self.send_response(status)
                        self.send_header("Content-Type", "text/plain" if is_text else "application/json")
                        self.send_header("Content-Length", str(len(payload)))
                        self.end_headers()
                        self.wfile.write(payload)
                        return
                self.send_response(NOT_FOUND_STATUS_CODE)
                self.send_header("Content-Length", "0")
                self.end_headers()

            do_GET = do_POST = do_PUT = do_DELETE = _handle

        return Handler
```

Checklist de tests de un wrapper con broker (caso s): sesión activa usa el CLI de login sin pedir nada y lo guarda; sesión vencida corre el login y vuelve a pedir; un `--token-file` explícito saltea broker, login y llavero; un comando que no necesita el secreto nunca llama al login ni al llavero; un token fresco del llavero se usa sin el login; uno por vencer se reemplaza; `refresh` lo olvida y pide otro; se guarda por stdin y nunca como argumento; un login fallido pide el token sin eco; se rinde después de tres tokens inválidos; Ctrl+C en el prompt cancela y restaura la terminal; el directorio del broker no queda al terminar.

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
