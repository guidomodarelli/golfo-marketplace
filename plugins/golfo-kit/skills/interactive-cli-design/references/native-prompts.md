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

Leer una tecla del descriptor en modo cbreak, no de `sys.stdin`: el buffer de `sys.stdin` parte una secuencia de flecha en dos lecturas.

```python
import os, select, sys, termios, tty, unicodedata

KEY_READ_MAX_BYTES = 8                 # una flecha o un carácter UTF-8 de hasta 4 bytes
ESCAPE_SEQUENCE_TIMEOUT_SECONDS = 0.05
ARROWS = {"\x1b[A": "up", "\x1b[B": "down", "\x1bOA": "up", "\x1bOB": "down"}

def read_key(file_descriptor: int) -> str:
    previous = termios.tcgetattr(file_descriptor)
    try:
        tty.setcbreak(file_descriptor)
        key = os.read(file_descriptor, KEY_READ_MAX_BYTES)
        # Un Esc solo no trae más bytes: esperar un instante y seguir, en vez de bloquear.
        if key == b"\x1b" and select.select([file_descriptor], [], [], ESCAPE_SEQUENCE_TIMEOUT_SECONDS)[0]:
            key += os.read(file_descriptor, KEY_READ_MAX_BYTES)
    finally:
        termios.tcsetattr(file_descriptor, termios.TCSADRAIN, previous)
    if not key:
        raise EOFError
    text = key.decode(errors="replace")
    if text == "\x03":
        raise KeyboardInterrupt
    return ARROWS.get(text, {"\r": "enter", "\n": "enter"}.get(text, text))

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

En bash, leer de `/dev/tty` y apagar el eco **antes** de imprimir la pregunta, para que un valor pegado enseguida tampoco se vea. Restaurar la terminal en un `trap`:

```bash
exec 3<>/dev/tty || { echo "tool: falta el token y no hay una terminal para pedirlo: usá --token-file." >&2; exit 2; }
terminal_settings=$(stty -g <&3)
trap 'stty "$terminal_settings" <&3 2>/dev/null' EXIT
trap 'exit 130' INT TERM
stty -echo <&3
printf 'Token (no se muestra): ' >&3
IFS= read -r token <&3 || token=""
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
