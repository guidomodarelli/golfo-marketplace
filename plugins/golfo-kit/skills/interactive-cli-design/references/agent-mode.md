# Modo agente

Un agente (Claude Code, Codex, Hermes u otro) usa el CLI como una persona apurada que no puede contestar: no ve colores, cada línea le cuesta tokens, corta los comandos largos y, si el CLI pregunta, se cuelga. Este modo convive con el interactivo en el mismo binario y con los mismos flags.

## Índice

1. [Cuándo se activa](#cuándo-se-activa)
2. [Qué cambia](#qué-cambia)
3. [Errores que se corrigen en un intento](#errores-que-se-corrigen-en-un-intento)
4. [`--json`: un documento por corrida](#--json-un-documento-por-corrida)
5. [Cancelar con SIGTERM](#cancelar-con-sigterm)
6. [Que se pueda descubrir](#que-se-pueda-descubrir)

## Cuándo se activa

- **Sin flag `--agent`.** Un agente no conoce una flag propia antes de leer la ayuda, y su primera corrida quedaría en modo humano (y bajo una pseudoconsola, colgada en un prompt). Lo que hace el modo ya tiene sus flags estándar: `--no-input` y `--json`. Un `--agent` sería un alias de los dos, y cada flag se mantiene para siempre. Si un CLI no puede sumar `--json`, `--agent` vale exactamente `--no-input` más salida plana, y se dice en el cambio.
- **Por entorno.** Se activa si la variable de override del CLI vale `1` o `true` (`<TOOL>_AGENT=1`), o si hay una señal de agente en el entorno y el override no vale `0` o `false`. `<TOOL>_AGENT=0` lo apaga, para quien abre una terminal desde un agente y quiere el wizard. Una variable atraviesa wrappers y subprocesos, y sirve en los dos sentidos.
- **Aunque haya terminal.** Algunos agentes corren los comandos en una pseudoconsola: ahí stdin y stderr son TTY y el chequeo dice «persona». En modo agente no se pregunta igual.
- La tabla de señales (con qué se verificó cada una) y `isAgentSession` para cada stack viven en `vivid-visual-output` (`references/terminal.md`, «Modo agente»), porque el mismo dato decide color, animación y tarjeta. `canPrompt` lo llama; no copiarlo en otro lugar.

## Qué cambia

1. **Nunca se bloquea.** Sin prompts, sin pager (`PAGER=cat` para lo propio, `--no-pager` para lo ajeno, como `git`), sin abrir `$EDITOR` ni el navegador, sin «presioná Enter».
2. **Sin login interactivo.** En el broker de secretos ([native-prompts.md](native-prompts.md#del-wrapper-al-programa)), si el secreto no está en el llavero ni sale de la herramienta oficial sin interacción, exit 2 con cómo pasarlo (`--token-file`, la variable) en vez de correr el login: bajo un agente, un login interactivo espera para siempre. El broker lo sabe porque hereda el entorno.
3. **Secretos solo por archivo o variable.** Se leen de `--<dato>-file` o de la variable documentada y nunca se piden. Sin secreto, exit 2 con cómo pasarlo (`error.code: secret_missing`).
4. **Determinismo.** No se usan las respuestas recordadas ([native-prompts.md](native-prompts.md#recordar-respuestas)): a una persona le ahorran tiempo, pero en un agente cambian el resultado sin que nadie lo vea. Tampoco hay defaults implícitos cuando elegir mal cuesta (`SKILL.md`, «Qué preguntar en la fila 6»).
5. **Salida corta y plana, aunque haya pseudoconsola.** Sin tarjeta de encabezado, spinner, color, emojis decorativos ni íconos de Nerd Fonts. En stderr, una línea por paso (`[2/5] Crear el usuario… ok`) y, en las esperas largas, un latido cada 20 s con qué se espera y hasta cuándo. Los kits de `vivid-visual-output` lo aplican con `isAgentSession`.
6. **Confirmaciones solo por flag.** Una acción peligrosa sin su flag (`--force`, `--confirm-prod`) es exit 2, con el flag exacto en el mensaje y la sugerencia de correr antes `--dry-run` (`error.code: confirmation_required`).
7. **Esperas con tope conocido.** Las herramientas de shell de los agentes cortan los comandos largos (suelen tener un timeout de pocos minutos). Si una corrida puede pasar el minuto: decir al empezar cuánto puede tardar como máximo, respetar `--timeout <segundos>` y, al pasar el tope, salir con lo hecho y el comando para seguir (`error.code: timeout`), nunca quedarse colgado.

## Errores que se corrigen en un intento

Un error de uso sale con exit 2 y trae **todo** lo necesario para reintentar sin ir a leer la ayuda:

- **todos** los flags que faltan, no solo el primero;
- para cada uno, sus valores válidos: fijos, o el comando que los lista (`tool --list`) si salen de una fuente viva;
- en qué acción es obligatorio;
- un comando listo para completar.

```text
tool: faltan --scope y --status para crear.
  --scope   release | prod
  --status  ver: tool --site BR --list
Reintentá: tool --site BR --scope <release|prod> --status <estado>
```

Con `--json`, lo mismo va en `error.missing` y `error.retry_command`. El texto y el JSON salen del mismo dato:

```python
import json, shlex, sys

EXIT_USAGE = 2

def missing_flags_error(tool_name, given_arguments, missing, action):
    """`missing`: lista de dicts con flag, values (lista) o values_command, y required_for."""
    def placeholder(item):
        return f"<{'|'.join(item['values'])}>" if item.get("values") else f"<{item['flag'].lstrip('-')}>"
    retry = " ".join([tool_name, *map(shlex.quote, given_arguments), *(f"{item['flag']} {placeholder(item)}" for item in missing)])
    names = [item["flag"] for item in missing]
    listed = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} y {names[-1]}"
    return {
        "code": "missing_flags",
        "message": f"Faltan {listed} para {action}.",
        "missing": missing,
        "retry_command": retry,
    }

def report_usage_error(error, as_json):
    if as_json:
        print(json.dumps({"ok": False, "error": error, "done": [], "resume_command": None}, ensure_ascii=False))
    else:
        print(f"tool: {error['message'][0].lower()}{error['message'][1:]}", file=sys.stderr)
        width = max(len(item["flag"]) for item in error["missing"])
        for item in error["missing"]:
            detail = " | ".join(item["values"]) if item.get("values") else f"ver: {item['values_command']}"
            print(f"  {item['flag']:<{width}}  {detail}", file=sys.stderr)
        print(f"Reintentá: {error['retry_command']}", file=sys.stderr)
    return EXIT_USAGE
```

El `retry_command` lleva los placeholders (`<release|prod>`) a propósito: no es para copiar y correr, sino para completar.

## `--json`: un documento por corrida

- Con `--json`, **stdout lleva exactamente un documento JSON** por corrida, tanto si salió bien como si falló. stderr sigue siendo para personas (progreso y avisos) y no lleva JSON. El exit code es el mismo que sin `--json`.
- La forma es estable y está en la ayuda. Éxito:

```json
{
  "ok": true,
  "data": { "user_id": 123, "resource_id": 456, "status": "active" },
  "warnings": [{ "code": "optional_step_skipped", "message": "No se cargó la identificación (403).", "missing_permission": "example_write" }],
  "record_path": "~/.tool/records/2026-11-13_101500_BR-release_456.md",
  "equivalent_command": "tool --site BR --scope release --status active --user nuevo --email auto"
}
```

Error:

```json
{
  "ok": false,
  "error": {
    "code": "missing_flags",
    "message": "Faltan --scope y --status para crear.",
    "missing": [
      { "flag": "--scope", "values": ["release", "prod"], "required_for": ["create", "dry-run"] },
      { "flag": "--status", "values_command": "tool --site BR --list", "required_for": ["create", "dry-run"] }
    ],
    "retry_command": "tool --site BR --scope <release|prod> --status <estado>"
  },
  "done": [],
  "resume_command": null
}
```

- **`error.code` es una lista cerrada** de constantes en `snake_case`, en la ayuda. El agente decide por el código, no por el texto:

| Código | Cuándo | Campos extra |
|---|---|---|
| `missing_flags` | Faltan datos y no se puede preguntar | `missing`, `retry_command` |
| `invalid_value` | Un valor con forma inválida | `flag`, `values` |
| `unknown_value` | Un valor con buena forma que no existe en la fuente | `flag`, `suggestions`, `values_command` |
| `confirmation_required` | Acción peligrosa sin su flag | `flag`, `dry_run_command` |
| `secret_missing` | No hay secreto y no se puede pedir | `options` (`--token-file`, la variable) |
| `permission_missing` | Falta un permiso obligatorio | `groups` con su link ([preflight.md](preflight.md#reporte-y-exit)) |
| `upstream_unavailable` | El servicio no respondió después de los reintentos | `attempts`, `waited_seconds` |
| `timeout` | Se pasó `--timeout` | `done`, `resume_command` |
| `partial_failure` | Falló después del primer efecto | `done`, `resume_command` |

- **Si falló después de actuar**, `done` lista lo creado con sus IDs reales y `resume_command` trae el comando para seguir con lo mismo ([remote-actions.md](remote-actions.md#registro-de-lo-creado)).
- **Los avisos** de pasos opcionales van en `warnings`, con su `code` y el permiso que falta si la respuesta lo nombra ([remote-actions.md](remote-actions.md#pasos-opcionales)).
- **`--dry-run --json`** devuelve el plan en `data.plan` (`[{ "step": 1, "action": "...", "effects": true }]`), con una rama por valor posible si el servidor decide un dato intermedio.
- **`--check-access`, `--history`, `--list` y `--status <id>`** con `--json` devuelven sus datos con la misma envoltura `ok` / `data`.
- **Sin `--json`**, en modo agente el texto sigue las mismas reglas: errores autosuficientes, una línea por paso.

## Cancelar con SIGTERM

Un agente que corta un comando largo manda `SIGTERM`, no Ctrl+C. El CLI hace lo mismo que con Ctrl+C: limpia, restaura la terminal, lista lo hecho con el comando para seguir y sale con 143 (130 si vino `SIGINT`).

```python
import signal

EXIT_TERMINATED = 143

class Terminated(BaseException):
    """Como KeyboardInterrupt: atraviesa los except Exception y llega a los finally."""

def terminate_like_interrupt():
    def terminate(signal_number, frame):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        raise Terminated
    signal.signal(signal.SIGTERM, terminate)
```

En el punto de entrada, junto a `interrupt_only_once` ([native-prompts.md](native-prompts.md#ctrlc-una-sola-vez)): `except Terminated` imprime lo hecho y sale con `EXIT_TERMINATED`. En Node, `process.on('SIGTERM', ...)` llama a la misma limpieza que `SIGINT`; en bash, `trap 'exit 143' TERM` con la limpieza en el `trap ... EXIT`.

## Que se pueda descubrir

- **Ayuda.** Al final del `--help`, una sección «Uso desde agentes y scripts»: un ejemplo completo sin preguntas, la forma del JSON, la lista de `error.code`, los exit codes y la variable `<TOOL>_AGENT`.
- **`--help --json`**, opcional para CLIs con muchos flags: el esquema de los flags (nombre, tipo, valores, en qué acción es obligatorio, si es secreto). Alcanza con la ayuda en texto si es completa.
- **El comando equivalente** que imprime el modo interactivo es el puente: una persona arma la corrida con el wizard y se la pasa a un agente.
- **En el `README` o el `AGENTS.md`** del proyecto que tiene el CLI, una sección corta de cómo usarlo desde un agente: comando de ejemplo, `--json` y exit codes.
