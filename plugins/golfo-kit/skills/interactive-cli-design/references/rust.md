# Rust

Probado en pseudoconsolas de Windows y Linux con `clap` 4.6 e `inquire` 0.9. Antes de usar otra versión, mirar su documentación.

## Parser con clap

```rust
#[derive(clap::Parser)]
#[command(version, about, after_help = "Sin flags en una terminal, pregunta lo que falta.\nCódigos de salida: 0 ok, 1 falló, 2 uso incorrecto, 130 cancelado.")]
struct Flags {
    #[arg(long)]
    name: Option<String>,
    #[arg(long, value_enum)]
    runtime: Option<Runtime>,
    #[arg(long, value_delimiter = ',')]
    features: Option<Vec<String>>,
    #[arg(long)]
    no_input: bool,
}
```

- Los errores de uso de clap ya salen con 2, y `--help` y `--version` con 0 por stdout.
- **Ayuda.** clap ya arma las dos columnas y apila cuando no entran. Su tope de ancho es 100 columnas: bajarlo a 80 con `#[command(max_term_width = 80)]` (con la feature `wrap_help`). Los colores se fijan con `#[command(styles = HELP_STYLES)]` y `clap::builder::styling::Styles::styled()`: `.header()` y `.usage()` para los títulos, `.literal()` para flags y subcomandos y `.placeholder()` para los `<valores>`. Con la feature `color`, respeta `NO_COLOR` y no pinta en un pipe. `.literal()` pinta igual flags y subcomandos: para que tengan colores distintos, escribir la sección de subcomandos en `help_template` o `after_help` con sus propios estilos. Esto no se probó en una pseudoconsola: verificarlo con los casos de [verification.md](verification.md).
- Con `ValueEnum`, un valor inválido lista los válidos en el mensaje.
- Un obligatorio se declara `Option<T>`: si no, clap falla antes de poder preguntar. Para los faltantes sin terminal, `Flags::command().error(ErrorKind::MissingRequiredArgument, mensaje).exit()` sale con 2; necesita `use clap::{error::ErrorKind, CommandFactory}`.

## Se puede preguntar

```rust
use std::io::IsTerminal;

fn can_prompt(no_input: bool) -> bool {
    let continuous_integration = std::env::var("CI").is_ok_and(|value| !matches!(value.as_str(), "" | "0" | "false"));
    std::io::stdin().is_terminal()
        && std::io::stderr().is_terminal()
        && !no_input
        && !continuous_integration
        && std::env::var("TERM").map_or(true, |term| term != "dumb")
}
```

## Widgets

| Widget | `inquire` |
|---|---|
| Confirm | `Confirm::new(message).with_default(false).prompt()` |
| Radio y lista con búsqueda | `Select::new(message, options).prompt()`. Escribir filtra la lista |
| Multiselect | `MultiSelect::new(message, options).prompt()` |
| Texto | `Text::new(message).with_validator(validator).prompt()` |
| Secreto | `Password::new(message).without_confirmation().prompt()` |

`inquire` dibuja en stderr con su backend por default (`crossterm`), así que no hace falta configurar nada.

## Cancelación

`prompt()` devuelve un `Result`. Distinguir `InquireError::OperationInterrupted` (Ctrl+C) de `InquireError::OperationCanceled` (Esc), y tratar los dos como cancelar:

```rust
fn exit_on_cancel<T>(answer: Result<T, InquireError>) -> T {
    match answer {
        Ok(value) => value,
        Err(InquireError::OperationInterrupted | InquireError::OperationCanceled) => {
            eprintln!("Cancelado: no se cambió nada.");
            std::process::exit(130);
        }
        Err(error) => {
            eprintln!("tool: {error}");
            std::process::exit(1);
        }
    }
}
```

Con el backend `console`, Ctrl+C no vuelve como error: dispara `SIGINT` y hay que manejarlo aparte.

## Trampas

- **Toolchain `windows-gnu`.** Los crates actuales necesitan `dlltool` y `as`, que la toolchain no trae. Instalar MinGW (`scoop install mingw`) o usar la toolchain MSVC. Fijar versiones viejas de `clap` o `inquire` lo esquiva, pero deja el CLI atrasado.
