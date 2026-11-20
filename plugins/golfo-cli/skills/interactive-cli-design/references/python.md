# Python

Probado en pseudoconsolas de Windows y Linux con Typer 0.27, questionary 2.1 y prompt_toolkit 3.0. Antes de usar otra versión, mirar su documentación.

Usar lo que el proyecto ya tenga. `argparse` es nativo y da `-h`, exit 2 y errores de uso sin dependencias. Typer suma tipos y una ayuda más linda.

## Parser con Typer

```python
import typer

app = typer.Typer(
    add_completion=False,
    pretty_exceptions_enable=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)

def show_version(requested: bool) -> None:
    if requested:
        typer.echo(VERSION)
        raise typer.Exit()

@app.command(help="Qué hace. Sin flags en una terminal, pregunta lo que falta. Códigos de salida: ...")
def main(
    name: Annotated[Optional[str], typer.Option("--name", help="...")] = None,
    features: Annotated[Optional[list[str]], typer.Option("--features", help="...")] = None,
    no_input: Annotated[bool, typer.Option("--no-input", help="...")] = False,
    version: Annotated[bool, typer.Option("--version", "-V", callback=show_version, is_eager=True, help="...")] = False,
) -> None:
    ...
```

- `add_completion=False` saca `--install-completion`, que nadie pidió.
- Por default Typer no acepta `-h`: hace falta `help_option_names`.
- Un parámetro obligatorio se declara `Optional` con default `None`. Si no, Typer falla antes de poder preguntar.
- `len(sys.argv) == 1` distingue la invocación sin argumentos, que abre el wizard completo.

**Ayuda con `argparse`.** Ya arma las dos columnas, parte la descripción dentro de la suya y la apila debajo cuando el nombre es más ancho que `max_help_position` (24 por default). Por default ocupa todo el ancho de la terminal: limitarlo a 80 con `width`, en el mismo `formatter_class=functools.partial(argparse.HelpFormatter, max_help_position=HELP_NAME_COLUMNS, width=min(shutil.get_terminal_size().columns, MAXIMUM_HELP_COLUMNS))`. Desde Python 3.14 también la pinta (`color=True` es el default) y respeta `NO_COLOR`, `FORCE_COLOR` y la salida a un pipe: flags largos en cian, cortos y subcomandos en verde, `metavar` en amarillo. Como deja del mismo verde las flags cortas y los subcomandos, y la regla es un color por papel (`SKILL.md`, «Ayuda»), o en 3.13 y anteriores, que no pintan, escribir la ayuda con un helper propio (como el de [node.md](node.md#ayuda)): los métodos de `HelpFormatter` son privados y pintarlos ahí se rompe entre versiones. Con Typer, verificar en una pseudoconsola que su ayuda con `rich` cumpla el formato del `SKILL.md`.

Con `argparse`: `parser.error(mensaje)` sale con 2 y `action="version"` imprime la versión en stdout. Crear el parser con `allow_abbrev=False`: por default acepta `--tok` por `--token`. Sus mensajes de error están en inglés; si el CLI habla otro idioma, sobrescribir `error()` y traducir los más comunes (`unrecognized arguments`, `expected one argument`, `not allowed with argument`).

- **El `-h` también viene en inglés** («show this help message and exit»). Crear el parser con `add_help=False` y sumar `parser.add_argument("-h", "--help", action="help", default=argparse.SUPPRESS, help="muestra esta ayuda y sale")`. Hacerlo en el `__init__` de una subclase de `ArgumentParser` (la misma que sobrescribe `error()` y la ayuda) alcanza para todos los subcomandos: `add_subparsers` crea los suyos con la clase del padre.
- **`--help` gana siempre (fila 1).** argparse procesa en orden: `tool check --json=x --help` falla por `--json=x` antes de llegar a `--help`. Buscar `-h`, `--help` y `--version` en los argumentos anteriores a `--` antes de parsear, y si aparece el nombre de un subcomando, mostrar su ayuda.
- **Subcomando que falta (fila 3).** Con `add_subparsers(required=True)`, argparse sale con su error antes de que el CLI pueda abrir el menú. Declararlo sin `required` y, si el subcomando quedó en `None`, abrir el menú (con terminal) o escribir la ayuda breve en stderr y salir con 2. Lo elegido se vuelve a parsear con el mismo parser y con los argumentos que ya vinieron: `parser.parse_args([*argumentos, elegido])`. Así corre con los mismos defaults que escrito a mano y no se pierden los flags globales que la persona ya pasó: `tool --config staging.toml --dry-run` y elegir `deploy` es `tool --config staging.toml --dry-run deploy`, no `tool deploy` con la config y el `--dry-run` por default. Como no vino subcomando, esos argumentos son todos del parser principal y van antes del elegido. El comando equivalente los lleva también.

## Se puede preguntar

```python
def can_prompt(no_input: bool, is_terminal=None) -> bool:
    """`is_terminal` es para tests: reemplaza el chequeo de terminal, pero nunca anula --no-input ni el modo agente."""
    continuous_integration = os.environ.get("CI", "").lower() not in ("", "0", "false")   # CI=False no es CI
    has_terminal = is_terminal if is_terminal is not None else sys.stdin.isatty() and sys.stderr.isatty()
    return (
        has_terminal
        and not no_input
        and not is_agent_session()          # aunque haya pseudoconsola
        and not continuous_integration
        and os.environ.get("TERM") != "dumb"
    )
```

`is_agent_session` es la del kit de `vivid-visual-output` (`references/terminal.md`, «Modo agente»). Si el proyecto conserva helpers de consola propios en lugar del kit (`vivid-visual-output` reusa lo que ya existe), sumarles solo esa función con su tabla de señales. Bajo un agente no se pregunta aunque stdin y stderr sean terminales ([agent-mode.md](agent-mode.md)).

## Widgets

| Widget | `questionary` |
|---|---|
| Confirm | `questionary.confirm(message, default=False, output=output)` |
| Radio y lista | `questionary.select(message, choices=values, output=output)` |
| Multiselect | `questionary.checkbox(message, choices=values, output=output)`. Acepta la lista vacía |
| Texto | `questionary.text(message, validate=fn, output=output)`. `fn` devuelve `True` o el texto del error |
| Secreto | `questionary.password(message, output=output)` |
| Sugerencias | `questionary.autocomplete(message, choices=values, output=output)`. Es texto libre: validar el resultado |

## Dibujar en stderr

questionary dibuja en stdout por default. En Windows, además, `create_output(stdout=sys.stderr)` no alcanza: prompt_toolkit consulta siempre el handle de stdout y `tool > archivo` falla con `NoConsoleScreenBufferError`. Crear la salida recién cuando se va a preguntar, porque sin consola también falla:

```python
from prompt_toolkit.data_structures import Size
from prompt_toolkit.output import ColorDepth, Output, create_output
from prompt_toolkit.output.vt100 import Vt100_Output

STD_ERROR_HANDLE = -12
ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004

def create_prompt_output() -> Output:
    if sys.platform != "win32":
        return create_output(stdout=sys.stderr)
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    kernel32.GetStdHandle.restype = wintypes.HANDLE
    handle = kernel32.GetStdHandle(STD_ERROR_HANDLE)
    mode = wintypes.DWORD()
    kernel32.GetConsoleMode(handle, ctypes.byref(mode))
    kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)

    def read_size() -> Size:
        size = os.get_terminal_size(sys.stderr.fileno())
        return Size(rows=size.lines, columns=size.columns)

    return Vt100_Output(sys.stderr, read_size, term="xterm", default_color_depth=ColorDepth.from_env(), enable_cpr=False)
```

## Cancelación

Usar `unsafe_ask()`. `ask()` atrapa Ctrl+C, imprime un mensaje **en stdout** y devuelve `None`, que después se confunde con un dato vacío.

```python
try:
    runtime = questionary.select("Runtime", choices=RUNTIMES, output=prompt_output).unsafe_ask()
except KeyboardInterrupt:
    typer.echo("Cancelado: no se cambió nada.", err=True)
    raise typer.Exit(EXIT_CANCELLED) from None
```

Atrapar `KeyboardInterrupt` dentro del comando: sin eso, Typer lo convierte en `Aborted!` con exit 1.

## Errores de uso

```python
def fail_usage(message: str) -> typer.Exit:
    typer.echo(f"{TOOL_NAME}: {message}", err=True)
    return typer.Exit(EXIT_USAGE)

raise fail_usage(f'--runtime no acepta "{value}". Valores válidos: {", ".join(RUNTIMES)}.')
```

## Comando equivalente

Las comillas dependen de la plataforma. En POSIX, `shlex.quote` deja el valor literal. En Windows pone comillas simples, que `cmd.exe` no entiende, y el comando impreso falla ahí.

```python
WINDOWS_SAFE_TOKEN = re.compile(r"^[\w@+=:,./\\-]+$")

def quote_for_shell(value: str) -> str:
    if sys.platform != "win32":
        return shlex.quote(value)
    if WINDOWS_SAFE_TOKEN.match(value):
        return value
    # En Windows una barra solo se duplica antes de una comilla o al final del argumento.
    escaped = re.sub(r'(\\*)"', r'\1\1\\"', value)
    escaped = re.sub(r"(\\+)$", r"\1\1", escaped)
    return f'"{escaped}"'

TERMINAL_ICON = "\uf120"  # nf-fa-terminal
TERMINAL_ICON_FALLBACK = "$"
COMMAND_INDENT = "  "

def print_equivalent_command(tool_name: str, command_arguments: list[str]) -> None:
    """Al final de una corrida con preguntas: el ícono va en el título y el comando solo, para copiarlo."""
    uses_nerd_font = sys.stderr.isatty() and os.environ.get("NERD_FONT") != "0"
    icon = TERMINAL_ICON if uses_nerd_font else TERMINAL_ICON_FALLBACK
    command = " ".join([tool_name, *map(quote_for_shell, command_arguments)])
    print(f"\n{icon} Para repetirlo sin preguntas:\n{COMMAND_INDENT}{command}", file=sys.stderr)
```

En Windows no hay una forma de citar que sirva igual en `cmd.exe` y en PowerShell cuando el valor trae `%`, `$`, acento grave o comillas dobles: `cmd.exe` expande `%VAR%` aun entre comillas, y PowerShell, `$var`. Si el valor trae alguno, avisar junto al comando que puede necesitar ajuste según el shell. Una ruta que termina en barra llega a PowerShell con una barra de más, que Windows tolera.

## Trampas

- **Codificación en Windows.** Por pipe, stdout y stderr usan la página de códigos local y un glifo rompe el `print`. Al arrancar:

  ```python
  for stream in (sys.stdout, sys.stderr):
      stream.reconfigure(encoding="utf-8")
  ```

  Si otro programa lee esa salida con la página de códigos local (cp1252 en un `.bat`, Windows PowerShell 5.1), le llega UTF-8 y lo muestra roto. En ese caso, en vez de reconfigurar, adaptar el texto al encoding del stream: el glifo pasa a su equivalente ASCII (`✔` → `+`, `╭─╮` → `+-+`), después se le sacan las tildes y, como último recurso, queda `?`. Además, `--json` va con `ensure_ascii=True` cuando stdout no es UTF-8: escapes `\uXXXX` que cualquier consumidor lee sin perder datos. Para reproducirlo, `python -I` no sirve: ignora `PYTHONIOENCODING` (implica `-E`). Usar `-X utf8` para forzar UTF-8, o sacar la variable del entorno del hijo para ver la página de códigos real.

- **Ancho de la terminal.** `shutil.get_terminal_size()` consulta stdout: con `tool > archivo`, la interfaz en stderr se dibuja a 80 columnas aunque la terminal tenga 40. Medir sobre el stream donde se dibuja, con `os.get_terminal_size(sys.stderr.fileno())` y respaldo a `COLUMNS` y a 80 (`terminal_columns` del kit de Python de `vivid-visual-output`). Lo mismo para el `width` del formatter de `argparse`, que dibuja en stdout. Una pseudoconsola recién creada informa **0** columnas: tratar 0 como desconocido y usar el respaldo, o cada fila del menú se corta a una columna.
- **Ctrl+C y `ThreadPoolExecutor`.** Al salir, Python espera los hilos del executor: un Ctrl+C durante requests lentos deja el CLI colgado hasta que vencen. Para trabajo que se tiene que poder cortar, hilos `daemon=True` con un `threading.Event` de corte. Los que corren procesos hijos (hooks) miran ese evento y terminan el árbol de procesos (`taskkill /T /F /PID` en Windows, `os.killpg` en POSIX). Antes de salir, esperarlos un plazo corto común.
- **`SIGBREAK`.** Existe solo en Windows (Ctrl+Break). Registrarlo junto a `SIGINT` con el mismo handler, si `hasattr(signal, "SIGBREAK")`. Es además la forma de probar el Ctrl+C sin pseudoconsola: [verification.md](verification.md#trampas-al-automatizar).
- **`argparse` y los cortos de varias letras.** Con `-s` y `-ss`, `-ssx` se lee como `-s sx`: los cortos van de una letra ([flags-and-config.md](flags-and-config.md#cortos-de-una-letra)).
- **`urllib` y el token.** Un token con un `\n` pegado hace que `http.client` lance un `ValueError` con el valor de la cabecera en el mensaje. Envolverlo sin el mensaje (`from None`): [remote-actions.md](remote-actions.md#errores-sin-datos-sensibles). Reintentos y su secuencia testeable: [remote-actions.md](remote-actions.md#reintentos).
- **Tests de un CLI interactivo** (`start_new_session`, `openpty`, `pty.fork`, reloj inyectado): [verification.md](verification.md#python-sin-node-pty).
- **`input()`** escribe su texto en stdout. Sin questionary, imprimir la pregunta en stderr y llamar a `input()` sin argumentos.
- **Sin questionary y con listas largas**, un menú propio con filtro: [native-prompts.md](native-prompts.md).
- **Comando de arranque.** En Windows, `.venv\Scripts\python.exe` no anda con barras normales desde `cmd`. Documentarlo con barras invertidas o con `uv run`.
