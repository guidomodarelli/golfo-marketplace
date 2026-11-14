# Prompts propios: menú con filtro, memoria, secretos y Ctrl+C

Para cuando el proyecto no tiene librería de prompts y no conviene sumar una, o la que tiene no filtra ni dibuja en stderr. Lo que sigue salió de dos CLIs reales en Python 3.9+ sin dependencias (`testdriver` de fury_carpincho y `emu` de system-config), probados en pseudoconsolas de macOS. Windows no tiene `termios`: ahí va el menú numerado.

## Índice

1. [Menú con flechas y filtro](#menú-con-flechas-y-filtro)
2. [Trampas del menú](#trampas-del-menú)
3. [Recordar respuestas](#recordar-respuestas)
4. [Secretos](#secretos) · [Del wrapper al programa](#del-wrapper-al-programa)
5. [Ctrl+C una sola vez](#ctrlc-una-sola-vez)

## Menú con flechas y filtro

Usar flechas solo si stdin es una terminal, hay color (sin `NO_COLOR`, `TERM` distinto de `dumb`) y existe `termios`. Si no, menú numerado: las opciones con su número, `(por defecto)` en la preseleccionada, Enter vacío la elige y un número fuera de rango repite la pregunta con el rango válido.

Las teclas:

| Tecla | Efecto |
|---|---|
| ↑ / ↓ | Mueve el resaltado dentro de lo visible, en círculo |
| Enter | Elige la resaltada. Si el filtro no dejó nada, no hace nada |
| Letras o texto pegado | Se suman al filtro. Sin mayúsculas ni acentos: `mexico` encuentra `México` |
| Backspace | Borra la última letra del filtro |
| Esc | Limpia el filtro |
| Un dígito, con el filtro vacío | Salta a esa opción |
| Ctrl+C | `KeyboardInterrupt`, que el programa convierte en exit 130 |

Leer del descriptor en modo cbreak, no de `sys.stdin`: el buffer de `sys.stdin` parte una secuencia de flecha en dos lecturas. Un `os.read` puede traer varias teclas juntas (flecha y Enter, o un texto pegado), así que `KeyReader` guarda lo leído y devuelve una tecla por llamada: una secuencia de escape completa o un carácter UTF-8. Lo que sobra queda para la llamada siguiente.

```python
import os, re, select, sys, termios, tty, unicodedata

KEY_READ_MAX_BYTES = 64                # lo que haya llegado: varias teclas o un texto pegado
ESCAPE_SEQUENCE_TIMEOUT_SECONDS = 0.05
ESCAPE = b"\x1b"
ESCAPE_SEQUENCE_INTRODUCERS = (b"[", b"O")
ARROWS = {b"\x1b[A": "up", b"\x1b[B": "down", b"\x1bOA": "up", b"\x1bOB": "down"}
ENTER_KEYS = {"\r": "enter", "\n": "enter"}

def escape_sequence_length(data: bytes) -> int:
    """Largo de la secuencia que empieza en data, o 0 si todavía está incompleta."""
    if len(data) < 2:
        return 0
    if data[1:2] not in ESCAPE_SEQUENCE_INTRODUCERS:
        return 1                       # Esc seguido de otra tecla: el Esc va solo
    for index in range(2, len(data)):
        if 0x40 <= data[index] <= 0x7E:  # byte final de la secuencia
            return index + 1
    return 0

def utf8_length(first_byte: int) -> int:
    if first_byte >> 5 == 0b110:
        return 2
    if first_byte >> 4 == 0b1110:
        return 3
    if first_byte >> 3 == 0b11110:
        return 4
    return 1

def split_first_key(data: bytes) -> tuple:
    """Separa la primera tecla de lo leído. Devuelve ("", data) si todavía está incompleta."""
    if not data:
        return "", data
    if data.startswith(ESCAPE):
        length = escape_sequence_length(data)
        if not length:
            return "", data
        sequence = data[:length]
        return ARROWS.get(sequence, sequence.decode(errors="replace")), data[length:]
    length = utf8_length(data[0])
    if len(data) < length:
        return "", data
    text = data[:length].decode(errors="replace")
    return ENTER_KEYS.get(text, text), data[length:]

class KeyReader:
    """Devuelve una tecla por llamada. Lo que sobra de cada lectura queda para la siguiente."""

    def __init__(self, file_descriptor: int):
        self.file_descriptor = file_descriptor
        self.pending = b""

    def _read_more(self, timeout=None) -> bool:
        if timeout is not None and not select.select([self.file_descriptor], [], [], timeout)[0]:
            return False
        chunk = os.read(self.file_descriptor, KEY_READ_MAX_BYTES)
        if not chunk:
            raise EOFError
        self.pending += chunk
        return True

    def read_key(self) -> str:
        previous = termios.tcgetattr(self.file_descriptor)
        try:
            # TCSANOW: el default (TCSAFLUSH) descarta lo tecleado mientras el menú se redibujaba.
            tty.setcbreak(self.file_descriptor, termios.TCSANOW)
            key, rest = split_first_key(self.pending)
            while not key:
                # Un Esc solo no trae más bytes: esperar un instante y seguir, en vez de bloquear.
                timeout = ESCAPE_SEQUENCE_TIMEOUT_SECONDS if self.pending.startswith(ESCAPE) else None
                if not self._read_more(timeout):
                    key, rest = "\x1b", self.pending[1:]
                    break
                key, rest = split_first_key(self.pending)
        finally:
            termios.tcsetattr(self.file_descriptor, termios.TCSADRAIN, previous)
        self.pending = rest
        if key == "\x03":
            raise KeyboardInterrupt
        return key

ANSI_ESCAPE_PATTERN = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_PATTERN.sub("", text)

def normalized(text: str) -> str:
    # Sin quitar los escapes, «m» o un dígito coinciden con el código de color de la etiqueta.
    decomposed = unicodedata.normalize("NFD", strip_ansi(text).casefold())
    return "".join(character for character in decomposed if not unicodedata.combining(character))

def matching(labels: list, query: str) -> list:
    return [index for index, label in enumerate(labels) if normalized(query) in normalized(label)]

def typed_text(key: str) -> str:
    """Lo que una tecla suma al filtro: nada si es una secuencia de escape, y solo caracteres imprimibles."""
    if key.startswith("\x1b"):
        return ""
    return "".join(character for character in key if character.isprintable())
```

Con etiquetas de color, `matching(["\x1b[32m🧪 release\x1b[0m", "\x1b[31m🚨 prod\x1b[0m", "México"], "m")` da `[2]`, y con `"3"` da `[]`.

El dibujo: ocultar el cursor, escribir la pregunta y una fila por opción. En cada tecla, subir `\033[<n>A` las filas dibujadas y reescribirlas con `\r\033[2K` delante. Si el filtro dejó menos filas, limpiar las que sobran y volver a subir. Al elegir, o en un `finally` si se cancela, borrar todo el menú, mostrar el cursor y escribir la línea `✔ pregunta › respuesta`. Todo va a stderr.

- **Que se sepa que se puede filtrar.** Al lado de la pregunta va una pista atenuada, `(↑/↓ y Enter · escribí para filtrar)`: los menús de flechas no suelen filtrar, y sin la pista nadie prueba a escribir. Lo tipeado va a la derecha de la pista, después de `›`, en el color de acento y en negrita.
- **Filtro sin resultados.** No dejar la lista vacía: una fila atenuada `nada coincide: Backspace borra, Esc limpia`. Enter y las flechas no hacen nada hasta que haya resultados.
- **El resaltado vuelve a la primera coincidencia** cada vez que cambia el filtro (al escribir, con Backspace o con Esc). Si conserva la posición anterior, con menos filas queda fuera de rango o sobre una opción que no se ve.
- **Cuando el color es parte del dato** (producción en rojo, test en verde), la fila resaltada conserva su color y se marca solo con `›` y negrita, en vez de pintarse entera del acento. La línea `✔ pregunta › respuesta` también lo conserva. En los demás menús, la resaltada va entera en el acento, sin los colores propios.
- **Medir sin escapes.** El corte de cada fila a `columnas - 1` mide sobre `strip_ansi(label)`, con la misma función que el filtro.

Las pistas son constantes, como el resto del copy:

```python
ARROW_MENU_HINT = "↑/↓ y Enter · escribí para filtrar"
FILTER_NO_MATCHES = "nada coincide: Backspace borra, Esc limpia"
```

**Menú numerado sin default.** Si ninguna opción es la preseleccionada, Enter vacío no elige nada ni se muestra «(por defecto)»: repite la pregunta. El menú con flechas siempre tiene una opción resaltada, así que ahí Enter elige la que se ve.

**Confirm.** Acepta las respuestas del idioma y las inglesas (`s`, `si`, `sí`, `y`, `yes` / `n`, `no`), marca el default con mayúscula (`[S/n]` o `[s/N]`) y toma Enter vacío como el default. Otra respuesta repite la pregunta («Respondé s o n.»): tomarla como «no» confunde a quien escribió `x` por error.

```python
YES_ANSWERS = {"s", "si", "sí", "y", "yes"}
NO_ANSWERS = {"n", "no"}

def confirm(question: str, default: bool, read_line=input) -> bool:
    marks = "[S/n]" if default else "[s/N]"
    while True:
        print(f"{question} {marks} ", end="", file=sys.stderr, flush=True)
        answer = read_line().strip().casefold()
        if not answer:
            return default
        if answer in YES_ANSWERS:
            return True
        if answer in NO_ANSWERS:
            return False
        print("Respondé s o n.", file=sys.stderr)
```

## Trampas del menú

- **Una opción más ancha que la terminal rompe el redibujo.** Ocupa dos filas, el menú sube menos de lo que ocupa y la pregunta queda repetida arriba. Cortar cada fila a `columnas - 1`. La última columna queda libre porque en varias terminales escribir ahí ya pasa a la fila siguiente.
- **Ancho de los emojis.** Cuentan dos columnas. Evitar el selector de variante U+FE0F, que algunas terminales dibujan con un ancho distinto al calculado y desalinea el corte.
- **Dígitos Unicode.** `"²".isdigit()` da `True` e `int("²")` lanza `ValueError`. Para saltar a una opción, aceptar solo `text.isascii() and text.isdigit()`.
- **Esc solo.** Sin el timeout de `select`, el menú se queda esperando el resto de una secuencia que nunca llega.
- **Varias teclas en una lectura.** Comparar el bloque entero contra `"\x1b[B"` o `"\n"` falla cuando llegan juntas: Abajo y Enter dan `"\x1b[B\n"`, y un texto pegado con Enter mete el salto de línea en el filtro. Separar una tecla por vez, como `split_first_key`.
- **Teclas perdidas.** `tty.setcbreak` y `tty.setraw` usan `TCSAFLUSH` por default y vacían lo que quedó en la cola de la terminal entre una lectura y la siguiente: quien teclea rápido o pega texto pierde letras o el Enter. Pasarles `termios.TCSANOW`, o entrar en cbreak una sola vez por menú (antes del bucle, restaurando en el `finally`).
- **Secuencias que el menú no usa** (flecha derecha, Supr `\x1b[3~`, Inicio, Fin, F1) vuelven enteras: ignorarlas. Al filtro se suman solo caracteres imprimibles (`typed_text`), así un pegado con `\n` o `\t` no ensucia la búsqueda.
- **Etiquetas con color.** Filtrar y medir sobre el texto sin escapes; si no, `m` o un dígito coinciden con el código de color.
- **Fin de la entrada.** `os.read` devuelve vacío y `readline()` devuelve `""`: tratarlo como cancelación, no como Enter.
- **Letras como atajos.** Con filtro, `j` y `k` son texto. Si el proyecto ya usaba esos atajos, avisarlo en el cambio.

## Recordar respuestas

- **Dónde.** `~/Library/Application Support/<herramienta>/` en macOS, `$XDG_CONFIG_HOME` (o `~/.config`) en Linux y `%APPDATA%` en Windows, con una variable de entorno que cambie la ruta, que además usan los tests.
- **Cómo escribir.** A un temporal del mismo directorio con `mkstemp`, permisos `600` (directorio `700`) y `os.replace`. Dos corridas en paralelo no se pisan a medias, y una corrida cortada no deja un JSON roto.
- **Qué.** El último valor, o los últimos N sin repetir con el más reciente primero. Nunca un secreto: eso va al llavero del sistema.
- **Cómo ofrecerlo.** Primero en el menú, marcado («último usado») y preseleccionado, así Enter lo elige. La respuesta que queda a la vista no lleva la marca.
- **Si falla.** Leer o escribir el archivo es una comodidad: avisar en una línea con la ruta y seguir preguntando como si no existiera. Nunca terminar por eso. Un archivo ilegible no impide guardar: se reemplaza por uno nuevo, con aviso.
- **Validar lo leído.** El archivo se edita a mano o viene de una versión vieja. Cada valor recordado pasa por la misma validación que el flag y el prompt antes de ofrecerse: los inválidos se descartan con un aviso y se ofrecen los válidos. Un estado guardado tipo «ya verificado» con una forma desconocida cuenta como **no** verificado.
- **Cambios de formato.** El formato viejo se sigue leyendo (una clave `last_email` vieja se toma como lista de uno) y se reemplaza al guardar, sin pedir nada. Cada escritura relee el archivo, cambia solo su clave y conserva las demás.

Lo que el CLI crea (no lo que el usuario responde) va a un registro aparte, con lock entre procesos: [remote-actions.md](remote-actions.md#registro-de-lo-creado).

## Secretos

Pedirlo recién cuando un paso lo necesita: `--help`, `--dry-run` o un comando de solo lectura no lo piden. Antes de preguntar, buscarlo sin molestar, en este orden: el flag `--<dato>-file` o la variable documentada, el llavero del sistema (si le queda margen antes de vencer), y la herramienta oficial de login (`gh auth token`, `fury get-token`). Recién después, la terminal.

En bash, leer de `/dev/tty` y apagar el eco **antes** de imprimir la pregunta, para que un valor pegado enseguida tampoco se vea. Restaurar la terminal apenas termina la lectura, así las preguntas siguientes vuelven a mostrar lo que se escribe, y además en un `trap` por si la lectura se corta:

```bash
exec 3<>/dev/tty || { echo "tool: falta el token y no hay una terminal para pedirlo: usá --token-file." >&2; exit 2; }
terminal_settings=$(stty -g <&3)
trap 'stty "$terminal_settings" <&3 2>/dev/null' EXIT
trap 'exit 130' INT TERM
stty -echo <&3
printf 'Token (no se muestra): ' >&3
IFS= read -r token <&3 || token=""
stty "$terminal_settings" <&3
printf '\n' >&3
```

- Validar la forma (sin espacios, no vacío) y dar unos pocos intentos antes de fallar.
- En Python, `getpass.getpass(stream=sys.stderr)` ya lee de la terminal sin eco.
- **Llavero de macOS sin argv.** `security add-generic-password -w <secreto>` deja el valor en la lista de procesos. Mandar el comando por stdin a `security -i`. Leerlo con `security find-generic-password -s <servicio> -a <cuenta> -w`.
- Si el servicio rechaza el valor cacheado, borrarlo del llavero y pedir uno nuevo, una sola vez.

### Del wrapper al programa

Cuando un wrapper de shell resuelve el secreto (llavero, `acme get-token`, login, prompt) y el programa real está en otro lenguaje, las salidas obvias son malas: por argv queda en `ps` y en el historial; por variable de entorno queda en `/proc/<pid>/environ` y lo heredan todos los hijos; resolverlo siempre al arrancar pide login en `--help`, `--list` o `--history`. Y si el wrapper mira los argumentos para adivinar qué comandos lo necesitan, esa lógica queda duplicada y las dos copias se separan.

La salida: un **broker** en el wrapper que el programa consulta por FIFO solo cuando lo necesita.

- El wrapper crea un directorio privado con `mktemp -d`, le da `chmod 700` y adentro dos FIFOs con `mkfifo -m 600` (pedidos y respuestas). En el `trap ... EXIT` las borra junto con el broker y sus hijos: `pkill -TERM -P <pid>` antes de `kill <pid>`, para que un prompt en curso restaure la terminal.
- Lanza el broker en segundo plano y exporta **solo las rutas** de las FIFOs y el PID del broker, nunca el secreto.
- Protocolo de una línea por mensaje. Pedido: `get` o `refresh`. Respuesta: `interactive` (opcional: avisa que va a usar la terminal) y después `token <origen> <valor>` o `error`. Después de `interactive`, el broker **espera** que el programa conteste `ready` por la FIFO de pedidos, una vez que detuvo su spinner y limpió la línea: si pregunta antes, el `CLEAR_LINE` del spinner borra la pregunta.
- El broker no hace nada hasta el primer pedido. Entonces busca sin molestar (llavero con margen de vencimiento, herramienta oficial de login) y recién después usa la terminal (login interactivo, prompt sin eco).
- `refresh`: el servicio rechazó el valor cacheado. El broker lo borra del llavero y consigue uno nuevo, una sola vez. Solo se renueva un valor que vino del llavero o del login; uno pasado a mano se respeta y su rechazo es un error.
- **Qué comandos necesitan el secreto lo decide solo el programa.** El wrapper no mira los argumentos.
- Un `--token-file` o una variable explícita gana: el programa ni consulta al broker, que no toca el llavero ni la herramienta de login.
- El programa abre la FIFO de pedidos con `O_WRONLY | O_NONBLOCK`. Si da `ENXIO` (el broker todavía no la abrió), reintenta con un intervalo corto mientras el broker siga vivo (`os.kill(pid, 0)`). Si murió, error claro, sin colgarse.
- La respuesta se lee con `select` y un intervalo corto, chequeando que el broker siga vivo: así Ctrl+C sigue funcionando mientras se espera.
- El margen de vencimiento se mide leyendo el `exp` del JWT sin validar la firma (el servidor la valida igual). El valor llega al chequeo por **stdin**, nunca como argumento.

```bash
BROKER_DIRECTORY="$(mktemp -d "${TMPDIR:-/tmp}/tool-secret.XXXXXX")"
chmod 700 "$BROKER_DIRECTORY"
mkfifo -m 600 "$BROKER_DIRECTORY/requests" "$BROKER_DIRECTORY/responses"
BROKER_PROCESS_ID=""
cleanup_broker() {
	if [[ -n "$BROKER_PROCESS_ID" ]]; then
		pkill -TERM -P "$BROKER_PROCESS_ID" 2>/dev/null || true   # primero los hijos (prompt, login)
		kill "$BROKER_PROCESS_ID" 2>/dev/null || true
		wait "$BROKER_PROCESS_ID" 2>/dev/null || true
	fi
	rm -rf "$BROKER_DIRECTORY"
}
trap cleanup_broker EXIT

# cached_secret, official_login_secret, interactive_secret, store_secret y forget_secret son del proyecto:
# llavero, `acme get-token`, el prompt sin eco de arriba.
run_secret_broker() {
	local requests="$1" responses="$2" secret="" source="" request looked=""
	while true; do
		# El kill del cleanup interrumpe el read: sin silenciarlo imprime «Interrupted system call».
		{ IFS= read -r request <"$requests"; } 2>/dev/null || continue
		exec 4>"$responses"
		if [[ -z "$looked" ]]; then
			looked="yes"
			if secret="$(cached_secret)"; then source="cache"
			elif secret="$(official_login_secret)"; then source="login"; store_secret "$secret"
			else secret=""; fi
		fi
		if [[ "$request" == "refresh" ]]; then
			forget_secret
			if secret="$(official_login_secret)"; then source="login"; store_secret "$secret"; else secret=""; fi
		fi
		if [[ -z "$secret" ]]; then
			printf 'interactive\n' >&4
			{ IFS= read -r request <"$requests"; } 2>/dev/null || true   # «ready»: el spinner ya no dibuja
			if secret="$(interactive_secret)"; then source="interactive"; store_secret "$secret"; else secret=""; fi
		fi
		if [[ -n "$secret" ]]; then printf 'token %s %s\n' "$source" "$secret" >&4; else printf 'error\n' >&4; fi
		exec 4>&-
	done
}

run_secret_broker "$BROKER_DIRECTORY/requests" "$BROKER_DIRECTORY/responses" &
BROKER_PROCESS_ID=$!
export TOOL_SECRET_REQUESTS="$BROKER_DIRECTORY/requests"
export TOOL_SECRET_RESPONSES="$BROKER_DIRECTORY/responses"
export TOOL_SECRET_BROKER_PID="$BROKER_PROCESS_ID"
set +e
trap ':' INT          # Ctrl+C lo maneja el programa; el wrapper solo espera su exit code
python3 "$SCRIPT_DIRECTORY/src/main.py" "$@"
exitCode=$?
set -e
exit "$exitCode"
```

El cliente, en Python:

```python
import errno, os, select, time

POLL_INTERVAL_SECONDS = 0.05
READ_CHUNK_BYTES = 4096

class SecretBrokerError(Exception):
    pass

class SecretBroker:
    def __init__(self, requests_path, responses_path, broker_process_id, sleep=time.sleep):
        self.requests_path, self.responses_path = requests_path, responses_path
        self.broker_process_id, self.sleep = broker_process_id, sleep

    def _is_alive(self):
        try:
            os.kill(self.broker_process_id, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def _send(self, line):
        while True:
            try:
                descriptor = os.open(self.requests_path, os.O_WRONLY | os.O_NONBLOCK)
                break
            except OSError as open_error:
                if open_error.errno != errno.ENXIO or not self._is_alive():
                    raise SecretBrokerError("SecretBroker:request: el broker no está disponible.") from None
                self.sleep(POLL_INTERVAL_SECONDS)
        try:
            os.write(descriptor, f"{line}\n".encode())
        finally:
            os.close(descriptor)

    def request(self, kind, on_interactive=lambda: None):
        """`kind` es "get" o "refresh". Devuelve (secreto, origen)."""
        self._send(kind)
        descriptor = os.open(self.responses_path, os.O_RDONLY | os.O_NONBLOCK)
        buffer = b""
        try:
            while True:
                ready, _, _ = select.select([descriptor], [], [], POLL_INTERVAL_SECONDS)
                chunk = os.read(descriptor, READ_CHUNK_BYTES) if ready else b""
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    response_kind, _, rest = line.decode().partition(" ")
                    if response_kind == "interactive":
                        on_interactive()          # detener el spinner y limpiar su línea
                        self._send("ready")       # recién ahora el broker pregunta
                    elif response_kind == "token":
                        source, _, secret = rest.partition(" ")
                        return secret, source
                    else:
                        raise SecretBrokerError("SecretBroker:request: no se pudo conseguir el secreto (ver el mensaje de arriba).")
                if not chunk:
                    if not self._is_alive():
                        raise SecretBrokerError("SecretBroker:request: el broker terminó sin responder.")
                    self.sleep(POLL_INTERVAL_SECONDS)
        finally:
            os.close(descriptor)
```

Trampas:

- **Login vencido que mezcla mensajes con el token.** Un CLI de login (`acme get-token`) con la sesión vencida escribe en stdout los mensajes del login y el token. Validar que la salida completa coincida con el patrón del token (`^(Bearer )?[A-Za-z0-9._~+/=-]+$`) antes de usarla. El error nunca incluye el valor: solo cuántas líneas tenía.
- **Llavero de macOS:** por stdin a `security -i`, como arriba.
- **Probarlo:** con binarios falsos en el `PATH` del test, que escriben un log y nunca tocan el llavero real ([verification.md](verification.md#servidor-de-prueba)).

## Ctrl+C una sola vez

El primer Ctrl+C cancela y los siguientes se ignoran. Si no, uno repetido corta el aviso de cancelación o muestra un traceback de `threading._shutdown` mientras Python cierra. Instalarlo solo en el punto de entrada, nunca al importar: en los tests cambiaría el Ctrl+C del runner.

```python
import signal

def interrupt_only_once():
    def interrupt(signal_number, frame):
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        raise KeyboardInterrupt
    signal.signal(signal.SIGINT, interrupt)
```

Un wrapper de bash que lanza el programa real no tiene que morir con el primer Ctrl+C, porque la terminal se lo manda a los dos. Con `trap ':' INT` antes de lanzarlo, el wrapper espera el exit code del hijo, que es quien informa la cancelación, y después limpia.

Con un spinner en un hilo, detenerlo y restaurar el cursor en un `finally`, así también se restaura al cancelar.
