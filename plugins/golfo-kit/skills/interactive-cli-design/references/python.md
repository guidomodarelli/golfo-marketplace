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

Con `argparse`: `parser.error(mensaje)` sale con 2 y `action="version"` imprime la versión en stdout.

## Se puede preguntar

```python
def can_prompt(no_input: bool) -> bool:
    continuous_integration = os.environ.get("CI", "") not in ("", "0", "false")
    return (
        sys.stdin.isatty()
        and sys.stderr.isatty()
        and not no_input
        and not continuous_integration
        and os.environ.get("TERM") != "dumb"
    )
```

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
```

En Windows no hay una forma de citar que sirva igual en `cmd.exe` y en PowerShell cuando el valor trae `%`, `$`, acento grave o comillas dobles: `cmd.exe` expande `%VAR%` aun entre comillas, y PowerShell, `$var`. Si el valor trae alguno, avisar junto al comando que puede necesitar ajuste según el shell. Una ruta que termina en barra llega a PowerShell con una barra de más, que Windows tolera.

## Trampas

- **Codificación en Windows.** Por pipe, stdout y stderr usan la página de códigos local y un glifo rompe el `print`. Al arrancar:

  ```python
  for stream in (sys.stdout, sys.stderr):
      stream.reconfigure(encoding="utf-8")
  ```

- **`input()`** escribe su texto en stdout. Sin questionary, imprimir la pregunta en stderr y llamar a `input()` sin argumentos.
- **Comando de arranque.** En Windows, `.venv\Scripts\python.exe` no anda con barras normales desde `cmd`. Documentarlo con barras invertidas o con `uv run`.
