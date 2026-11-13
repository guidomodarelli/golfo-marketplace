# Prompts propios: menú con filtro, memoria, secretos y Ctrl+C

Para cuando el proyecto no tiene librería de prompts y no conviene sumar una, o la que tiene no filtra ni dibuja en stderr. Lo que sigue salió de dos CLIs reales en Python 3.9+ sin dependencias (`testdriver` de fury_carpincho y `emu` de system-config), probados en pseudoconsolas de macOS. Windows no tiene `termios`: ahí va el menú numerado.

## Índice

1. [Menú con flechas y filtro](#menú-con-flechas-y-filtro)
2. [Trampas del menú](#trampas-del-menú)
3. [Recordar respuestas](#recordar-respuestas)
4. [Secretos](#secretos)
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
import os, select, sys, termios, tty, unicodedata

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

def normalized(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(character for character in decomposed if not unicodedata.combining(character))

def matching(labels: list, query: str) -> list:
    return [index for index, label in enumerate(labels) if normalized(query) in normalized(label)]
```

El dibujo: ocultar el cursor, escribir la pregunta (con el filtro tipeado a la derecha) y una fila por opción. En cada tecla, subir `\033[<n>A` las filas dibujadas y reescribirlas con `\r\033[2K` delante. Si el filtro dejó menos filas, limpiar las que sobran y volver a subir. Al elegir, o en un `finally` si se cancela, borrar todo el menú, mostrar el cursor y escribir la línea `✔ pregunta › respuesta`. Todo va a stderr.

## Trampas del menú

- **Una opción más ancha que la terminal rompe el redibujo.** Ocupa dos filas, el menú sube menos de lo que ocupa y la pregunta queda repetida arriba. Cortar cada fila a `columnas - 1`. La última columna queda libre porque en varias terminales escribir ahí ya pasa a la fila siguiente.
- **Ancho de los emojis.** Cuentan dos columnas. Evitar el selector de variante U+FE0F, que algunas terminales dibujan con un ancho distinto al calculado y desalinea el corte.
- **Dígitos Unicode.** `"²".isdigit()` da `True` e `int("²")` lanza `ValueError`. Para saltar a una opción, aceptar solo `text.isascii() and text.isdigit()`.
- **Esc solo.** Sin el timeout de `select`, el menú se queda esperando el resto de una secuencia que nunca llega.
- **Varias teclas en una lectura.** Comparar el bloque entero contra `"\x1b[B"` o `"\n"` falla cuando llegan juntas: Abajo y Enter dan `"\x1b[B\n"`, y un texto pegado con Enter mete el salto de línea en el filtro. Separar una tecla por vez, como `split_first_key`.
- **Teclas escritas durante el redibujo.** `tty.setcbreak` usa `TCSAFLUSH` por default y descarta lo que quedó en la cola de la terminal entre una lectura y la siguiente: quien teclea rápido pierde letras o el Enter. Pasarle `termios.TCSANOW`.
- **Secuencias que el menú no usa** (flecha derecha, teclas de función) vuelven enteras, como `"\x1b[C"`: ignorarlas en lugar de sumarlas al filtro.
- **Fin de la entrada.** `os.read` devuelve vacío y `readline()` devuelve `""`: tratarlo como cancelación, no como Enter.
- **Letras como atajos.** Con filtro, `j` y `k` son texto. Si el proyecto ya usaba esos atajos, avisarlo en el cambio.

## Recordar respuestas

- **Dónde.** `~/Library/Application Support/<herramienta>/` en macOS, `$XDG_CONFIG_HOME` (o `~/.config`) en Linux y `%APPDATA%` en Windows, con una variable de entorno que cambie la ruta, que además usan los tests.
- **Cómo escribir.** A un temporal del mismo directorio con `mkstemp`, permisos `600` (directorio `700`) y `os.replace`. Dos corridas en paralelo no se pisan a medias, y una corrida cortada no deja un JSON roto.
- **Qué.** El último valor, o los últimos N sin repetir con el más reciente primero. Nunca un secreto: eso va al llavero del sistema.
- **Cómo ofrecerlo.** Primero en el menú, marcado («último usado») y preseleccionado, así Enter lo elige. La respuesta que queda a la vista no lleva la marca.
- **Si falla.** Leer o escribir el archivo es una comodidad: avisar en una línea con la ruta y seguir preguntando como si no existiera. Nunca terminar por eso.

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
