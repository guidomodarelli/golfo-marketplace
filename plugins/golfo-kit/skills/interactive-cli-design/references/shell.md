# bash, zsh y PowerShell

La parte de PowerShell se probó con pwsh 7. La de bash y `gum` se escribió leyendo el código de `gum`, sin ejecutarla: correr la matriz antes de darla por buena.

## bash y zsh

`getopts` no entiende flags largos. Usar un `case`:

```bash
#!/usr/bin/env bash
TOOL_NAME=tool
EXIT_USAGE=2
EXIT_CANCELLED=130

usage_error() {
  printf '%s: %s\n' "$TOOL_NAME" "$1" >&2
  exit "$EXIT_USAGE"
}

while [ $# -gt 0 ]; do
  case "$1" in
    -h | --help) print_help; exit 0 ;;
    -V | --version) printf '%s\n' "$VERSION"; exit 0 ;;
    --no-input) no_input=1 ;;
    --name) [ $# -ge 2 ] || usage_error '--name necesita un valor'; name=$2; shift ;;
    --name=*) name=${1#*=} ;;
    --) shift; break ;;
    -*) usage_error "no reconozco $1. Corré $TOOL_NAME --help." ;;
    *) break ;;
  esac
  shift
done

can_prompt() {
  [ -t 0 ] && [ -t 2 ] && [ -z "${no_input:-}" ] && [ "${TERM:-}" != dumb ] || return 1
  case "${CI:-}" in '' | 0 | false) return 0 ;; *) return 1 ;; esac
}
```

### Widgets con gum

`gum` dibuja en stderr e imprime el resultado en stdout, así que `$(...)` funciona. Sale con 130 si se cancela, y `gum confirm` sale con 1 si la respuesta es no.

| Widget | Comando |
|---|---|
| Confirm | `gum confirm "$message" --default=false` |
| Radio | `gum choose --header "$message" a b c` |
| Lista con búsqueda | `printf '%s\n' "${values[@]}" \| gum filter` |
| Multiselect | `gum choose --no-limit --header "$message" a b c` (espacio o `x` marca) |
| Texto | `gum input --placeholder "$message"` |
| Secreto | `gum input --password` |

Propagar la cancelación en cada pregunta, o el script sigue con un valor vacío:

```bash
runtime=$(gum choose --header 'Runtime' node python go) || exit "$EXIT_CANCELLED"
```

`gum` puede no estar instalado. Si el proyecto no lo exige, comprobarlo con `command -v gum` y caer a lo nativo.

### Sin gum

Escribir la pregunta en stderr y leer de la terminal. El menú de `select` en bash ya va a stderr; un secreto se lee con `read -rs`. Para que sirva también en zsh, evitar `read -p`, que allí significa otra cosa:

```bash
printf 'Nombre: ' >&2
IFS= read -r name || exit "$EXIT_CANCELLED"
```

## PowerShell

Respetar el idioma: `-Name`, no `--name`. El contrato es el mismo.

```powershell
param(
  [string]$Name,
  [string]$Runtime,
  [switch]$NoInput,
  [Parameter(ValueFromRemainingArguments)][string[]]$Unknown
)

$ExitUsage = 2
$AllowedRuntimes = @('node', 'python', 'go')

function Exit-WithUsageError([string]$Message) {
  [Console]::Error.WriteLine("tool: $Message")
  exit $ExitUsage
}

if ($Unknown) { Exit-WithUsageError "no reconozco $($Unknown -join ' ')." }
if ($Runtime -and $Runtime -notin $AllowedRuntimes) {
  Exit-WithUsageError "-Runtime no acepta '$Runtime'. Valores válidos: $($AllowedRuntimes -join ', ')."
}

$isContinuousIntegration = $env:CI -and $env:CI -ne '0' -and $env:CI -ne 'false'
$canPrompt = -not [Console]::IsInputRedirected -and -not [Console]::IsErrorRedirected -and -not $NoInput -and -not $isContinuousIntegration
```

| Widget | Nativo |
|---|---|
| Confirm y radio | `$Host.UI.PromptForChoice($title, $message, $choices, $defaultIndex)`, con `$choices` de tipo `[System.Management.Automation.Host.ChoiceDescription[]]` y un `&` antes de la tecla de cada opción |
| Multiselect y lista | `Read-Host` con valores separados por coma, y validarlos |
| Secreto | `Read-Host -AsSecureString` |

Trampas:

- **Un parámetro desconocido no falla.** En un script sin `[CmdletBinding()]`, `pwsh -File x.ps1 -Nope` termina con 0 y no dice nada. `ValueFromRemainingArguments` lo atrapa.
- **`[ValidateSet]` sale con 1**, no con 2. Para respetar el contrato, validar a mano como arriba.
- **`[Parameter(Mandatory)]` no conviene** en los datos que se preguntan: el host pregunta a su manera y no deja nombrar los flags faltantes.
- **Datos con `Write-Output` y lo demás con `[Console]::Error`.** `Write-Host` termina en el stdout del proceso cuando la salida se redirige.
- **Ctrl+C.** `trap` no corre. Restaurar el estado en `try/finally`; la sección «Kit de PowerShell» de `references/terminal.md` en `vivid-visual-output` tiene un envoltorio listo, si está disponible.
