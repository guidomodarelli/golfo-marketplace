# bash, zsh y PowerShell

Probado en pseudoconsolas con bash y `gum` 0.17 en Windows (Git Bash) y Linux, con `zsh` en Linux y con PowerShell 7 en Windows. PowerShell en Linux no se probó.

## bash y zsh

`getopts` no entiende flags largos. Usar un `case`:

```bash
#!/usr/bin/env bash
TOOL_NAME=tool
VERSION=1.0.0
EXIT_USAGE=2
EXIT_CANCELLED=130

print_help() {
  printf '%sUso:%s %s%s%s %s--name%s %s<valor>%s [%s--no-input%s]\n\n' \
    "$HELP_TITLE" "$HELP_RESET" "$HELP_COMMAND" "$TOOL_NAME" "$HELP_RESET" "$HELP_FLAG" "$HELP_RESET" "$HELP_VALUE" "$HELP_RESET" "$HELP_FLAG" "$HELP_RESET"
  printf '%sOpciones%s\n' "$HELP_TITLE" "$HELP_RESET"
  help_row "$HELP_FLAG" '-n, --name' '<valor>' 'Nombre del proyecto. Obligatorio sin terminal.'
  help_row "$HELP_FLAG" '--no-input' '' 'No pregunta nunca: falla si falta un dato.'
  help_row "$HELP_FLAG" '-h, --help' '' 'Muestra esta ayuda.'
}

usage_error() {
  printf '%s: %s\n' "$TOOL_NAME" "$1" >&2
  exit "$EXIT_USAGE"
}

while [ $# -gt 0 ]; do
  case "$1" in
    -h | --help) print_help; exit 0 ;;
    -V | --version) printf '%s\n' "$VERSION"; exit 0 ;;
    --no-input) no_input=1 ;;
    -n | --name) [ $# -ge 2 ] || usage_error "$1 necesita un valor"; name=$2; shift ;;
    --name=*) name=${1#*=} ;;
    --) shift; break ;;
    -*) usage_error "no reconozco $1. Corré $TOOL_NAME --help." ;;
    *) break ;;
  esac
  shift
done

can_prompt() {
  [ -t 0 ] && [ -t 2 ] && [ -z "${no_input:-}" ] && [ "${TERM:-}" != dumb ] || return 1
  is_agent_session && return 1 # aunque haya pseudoconsola
  case "$(printf '%s' "${CI:-}" | tr '[:upper:]' '[:lower:]')" in '' | 0 | false) return 0 ;; *) return 1 ;; esac
}
```

`is_agent_session` es la del kit de `vivid-visual-output` (`references/terminal.md`, «Modo agente»): si el proyecto no usa el kit, copiar solo esa función con su tabla de señales. Bajo un agente no se pregunta aunque stdin y stderr sean terminales ([agent-mode.md](agent-mode.md)).

### Ayuda en dos columnas y con color

`help_row` arma cada fila: el nombre pintado a la izquierda y la descripción partida en su columna, o sangrada debajo si la terminal es angosta. Solo pinta si stdout es una terminal, sin `NO_COLOR` y con `TERM` distinto de `dumb`. Definir este bloque antes del bucle de flags, que llama a `print_help`. `fold` cuenta bytes: una `ó` parte la línea un poco antes, nunca después. Si los nombres traen caracteres no ASCII, usar `render_table` de `vivid-visual-output`.

```bash
# El carácter del proyecto: reemplazar estos valores, solo muestran la forma.
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ] && [ "${TERM:-}" != dumb ]; then
  HELP_TITLE=$'\033[1m' HELP_COMMAND=$'\033[36m' HELP_FLAG=$'\033[33m' HELP_VALUE=$'\033[2m' HELP_RESET=$'\033[0m'
else
  HELP_TITLE='' HELP_COMMAND='' HELP_FLAG='' HELP_VALUE='' HELP_RESET=''
fi
HELP_NAME_COLUMNS=24          # ancho de la columna izquierda, sangría incluida
HELP_MIN_DESCRIPTION_COLUMNS=24
HELP_MAXIMUM_COLUMNS=80        # la tabla nunca es más ancha, aunque la terminal sí lo sea

# help_row <color> <nombre> <valor o ''> <descripción>: una fila de dos columnas.
help_row() {
  # $(tput cols) devuelve siempre 80 dentro de $(...): leer el ancho de /dev/tty.
  local plain="$2${3:+ $3}" columns="${COLUMNS:-$(stty size 2>/dev/null </dev/tty | cut -d' ' -f2)}"
  case "$columns" in '' | *[!0-9]*) columns=$HELP_MAXIMUM_COLUMNS ;; esac
  [ "$columns" -gt "$HELP_MAXIMUM_COLUMNS" ] && columns=$HELP_MAXIMUM_COLUMNS
  local width=$(( columns - 1 - HELP_NAME_COLUMNS )) indent first=1 line
  printf '  %s%s%s' "$1" "$2" "$HELP_RESET"
  [ -n "$3" ] && printf ' %s%s%s' "$HELP_VALUE" "$3" "$HELP_RESET"
  if [ "$width" -lt "$HELP_MIN_DESCRIPTION_COLUMNS" ] || [ $(( ${#plain} + 4 )) -gt "$HELP_NAME_COLUMNS" ]; then
    printf '\n'; indent=4; width=$(( columns - 1 - indent )); first=0
  else
    indent=$HELP_NAME_COLUMNS
  fi
  while IFS= read -r line; do
    if [ "$first" -eq 1 ]; then
      printf '%*s%s\n' $(( HELP_NAME_COLUMNS - 2 - ${#plain} )) '' "$line"; first=0
    else
      printf '%*s%s\n' "$indent" '' "$line"
    fi
  done < <(printf '%s\n' "$4" | fold -s -w "$width" | sed 's/ *$//')
}
```

Los subcomandos van en su propia sección con `help_row "$HELP_COMMAND" init '' 'Crea el proyecto.'`.

### Widgets con gum

`gum` dibuja en stderr e imprime el resultado en stdout, así que `$(...)` funciona. Sale con 130 si se cancela, y `gum confirm` sale con 1 si la respuesta es no.

Para instalarlo: `winget install charmbracelet.gum`, `scoop install charm-gum` o `go install github.com/charmbracelet/gum@latest`. Cuidado con `scoop install gum`: instala otra herramienta, `kordamp/gm`.

| Widget | Comando |
|---|---|
| Confirm | `gum confirm "$message" --default=false` |
| Radio | `gum choose --header "$message" a b c` |
| Lista con búsqueda | `gum filter --header "$message" "${values[@]}"`. Con las opciones por pipe, en Windows no termina |
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

Un secreto se lee de `/dev/tty` con el eco apagado antes de la pregunta, y un wrapper que lanza otro programa deja que el hijo maneje Ctrl+C: [native-prompts.md](native-prompts.md#secretos). Si el wrapper consigue el secreto para ese programa, se lo da por FIFO cuando lo pide, nunca por argv ni por variable de entorno: [Del wrapper al programa](native-prompts.md#del-wrapper-al-programa).

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
$canPrompt = -not [Console]::IsInputRedirected -and -not [Console]::IsErrorRedirected -and -not $NoInput -and -not $isContinuousIntegration -and -not (Test-AgentSession)
```

`Test-AgentSession` es la del kit de `vivid-visual-output` (`references/terminal.md`, «Modo agente»): si el proyecto no usa el kit, copiar solo esa función con su tabla de señales. Bajo un agente no se pregunta aunque stdin y stderr sean terminales ([agent-mode.md](agent-mode.md)).

| Widget | Nativo |
|---|---|
| Confirm y radio | `$Host.UI.PromptForChoice($title, $message, $choices, $defaultIndex)`, con `$choices` de tipo `[System.Management.Automation.Host.ChoiceDescription[]]` y un `&` antes de la tecla de cada opción |
| Multiselect y lista | `Read-Host` con valores separados por coma, y validarlos |
| Secreto | `Read-Host -AsSecureString` |

Trampas:

- **La ayuda de `Get-Help` no tiene color ni la tabla del contrato.** Si el script tiene un `-Help`, escribirla con `Write-Output` y los colores de `$PSStyle` (PowerShell 7.2 o posterior), con la misma lógica que `help_row`. `OutputRendering` no limpia un string que ya trae `$PSStyle.Foreground.Yellow` interpolado: a un archivo llegan los escapes. Usar strings vacíos en lugar de los colores si `[Console]::IsOutputRedirected`, si está `$env:NO_COLOR` o si `$PSStyle.OutputRendering` vale `PlainText`.
- **Un parámetro desconocido no falla.** En un script sin `[CmdletBinding()]`, `pwsh -File x.ps1 -Nope` termina con 0 y no dice nada. `ValueFromRemainingArguments` lo atrapa.
- **`[ValidateSet]` sale con 1**, no con 2. Para respetar el contrato, validar a mano como arriba.
- **`[Parameter(Mandatory)]` no conviene** en los datos que se preguntan: el host pregunta a su manera y no deja nombrar los flags faltantes.
- **Datos con `Write-Output` y lo demás con `[Console]::Error`.** `Write-Host` termina en el stdout del proceso cuando la salida se redirige.
- **Ctrl+C en `Read-Host` y `PromptForChoice`.** El script termina con **exit 0**, como si hubiera salido bien, y `trap` no corre. Arrancar con el código de cancelación y bajarlo al final:

  ```powershell
  $exitCode = 130
  try {
    $name = Read-Host 'Nombre'
    $exitCode = 0
  } finally {
    exit $exitCode
  }
  ```

- **Lectura tecla por tecla.** Para menús con flechas, `[Console]::TreatControlCAsInput = $true` y `[Console]::ReadKey($true)`: Ctrl+C llega con `KeyChar` 3, y ahí se sale con `exit 130`. Volver a dejar el valor en `$false` antes de salir. `[Console]::In.ReadLine()` devuelve `$null` con Ctrl+C.
