# Go

Probado en pseudoconsolas de Windows y Linux con Go 1.27, `cobra` 1.10 y `huh` 1.0. Antes de usar otra versión, mirar su documentación.

## Parser con cobra

```go
type usageError struct{ error }

root := &cobra.Command{
    Use:           "tool",
    Version:       version,
    SilenceUsage:  true,
    SilenceErrors: true,
    Args: func(command *cobra.Command, args []string) error {
        if err := cobra.NoArgs(command, args); err != nil {
            return usageError{err}
        }
        return nil
    },
    RunE: run,
}
root.SetFlagErrorFunc(func(_ *cobra.Command, err error) error {
    return usageError{err}
})
```

- Cobra no fija el exit code: se decide en `main`. Con `SetFlagErrorFunc`, los errores de flags se marcan como de uso. Los errores de `Args` no pasan por ahí: `cobra.NoArgs` solo sale con 1, por eso se envuelve.
- `Version` agrega `--version` y le asigna `-v` si está libre. Para usar `-V`, declarar antes un flag propio llamado `version`.
- `SilenceUsage` evita volcar toda la ayuda ante cada error.
- **Ayuda.** La plantilla de cobra ya alinea comandos en dos columnas con `rpad`, pero no pinta, y las flags llegan como un bloque ya formateado (`FlagUsages`). Para cumplir el formato del `SKILL.md`, registrar funciones con `cobra.AddTemplateFunc` que pinten comandos y flags, armar las filas de flags con `command.LocalFlags().VisitAll`, y pasar la plantilla con `SetUsageTemplate`. Partir las descripciones a 80 columnas como máximo, o al ancho de la terminal si es menor. Pintar solo si `term.IsTerminal(int(os.Stdout.Fd()))` (de `golang.org/x/term`), sin `NO_COLOR` y con `TERM` distinto de `dumb`. Esto no se probó en una pseudoconsola: verificarlo con los casos de [verification.md](verification.md).

```go
func main() {
    err := root.Execute()
    var usage usageError
    switch {
    case err == nil:
    case errors.Is(err, huh.ErrUserAborted):
        fmt.Fprintln(os.Stderr, "Cancelado: no se cambió nada.")
        os.Exit(130)
    case errors.As(err, &usage):
        fmt.Fprintf(os.Stderr, "tool: %v\n", err)
        os.Exit(2)
    default:
        fmt.Fprintf(os.Stderr, "tool: %v\n", err)
        os.Exit(1)
    }
}
```

## Se puede preguntar

```go
func canPrompt(noInput bool) bool {
    ci := os.Getenv("CI")
    continuousIntegration := ci != "" && ci != "0" && ci != "false"
    return term.IsTerminal(int(os.Stdin.Fd())) &&
        term.IsTerminal(int(os.Stderr.Fd())) &&
        !noInput && !continuousIntegration && os.Getenv("TERM") != "dumb"
}
```

`term` es `golang.org/x/term`.

## Widgets

| Widget | `huh` |
|---|---|
| Confirm | `huh.NewConfirm().Title(message).Value(&accepted)` |
| Radio | `huh.NewSelect[string]().Title(message).Options(huh.NewOptions(values...)...).Value(&value)` |
| Lista con búsqueda | `NewSelect` con `.Height(n)`. Filtra con `/`, y `.Filtering(true)` arranca filtrando |
| Multiselect | `huh.NewMultiSelect[string]().Title(message).Options(...).Value(&selected)` |
| Texto | `huh.NewInput().Title(message).Validate(fn).Value(&value)` |
| Secreto | `huh.NewInput().EchoMode(huh.EchoModePassword).Value(&secret)` |

Agrupar con `huh.NewForm(huh.NewGroup(campos...)).Run()`. Agregar al formulario solo los campos sin valor. Un solo grupo muestra todas las preguntas en una pantalla y Enter avanza el foco; para una pregunta por vez, usar un grupo por campo.

## Dibujar en stderr

`huh` dibuja en stderr por default, salvo en modo accesible (`WithAccessible`), que dibuja en stdout. Ese modo se activa solo con `TERM=dumb`. Si se ofrece, agregar `.WithOutput(os.Stderr)`.

## Cancelación

`form.Run()` devuelve `huh.ErrUserAborted` con Ctrl+C.
