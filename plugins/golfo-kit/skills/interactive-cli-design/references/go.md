# Go

Escrito leyendo el código de `cobra` y `huh`, sin ejecutarlo. Compilar y correr la matriz antes de darlo por bueno, y mirar la documentación de la versión en uso.

## Parser con cobra

```go
root := &cobra.Command{
    Use:           "tool",
    Version:       version,
    SilenceUsage:  true,
    SilenceErrors: true,
    Args:          cobra.NoArgs,
    RunE:          run,
}
root.SetFlagErrorFunc(func(_ *cobra.Command, err error) error {
    return usageError{err}
})
```

- Cobra no fija el exit code: se decide en `main`. Con `SetFlagErrorFunc`, los errores de flags se pueden marcar como de uso. Los errores de `Args` no pasan por ahí: envolverlos también.
- `Version` agrega `--version` y le asigna `-v` si está libre. Para usar `-V`, declarar antes un flag propio llamado `version`.
- `SilenceUsage` evita volcar toda la ayuda ante cada error.

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

Agrupar con `huh.NewForm(huh.NewGroup(campos...)).Run()`. Agregar al formulario solo los campos sin valor.

## Dibujar en stderr

`huh` dibuja en stderr por default, salvo en modo accesible (`WithAccessible`), que dibuja en stdout. Ese modo se activa solo con `TERM=dumb`. Si se ofrece, agregar `.WithOutput(os.Stderr)`.

## Cancelación

`form.Run()` devuelve `huh.ErrUserAborted` con Ctrl+C.
