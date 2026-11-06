# Rust

Escrito leyendo el código de `clap` e `inquire`, sin ejecutarlo. Compilar y correr la matriz antes de darlo por bueno, y mirar la documentación de la versión en uso.

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
- Con `ValueEnum`, un valor inválido lista los válidos en el mensaje.
- Un obligatorio se declara `Option<T>`: si no, clap falla antes de poder preguntar. Para los faltantes sin terminal, `Flags::command().error(ErrorKind::MissingRequiredArgument, mensaje).exit()` sale con 2.

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
