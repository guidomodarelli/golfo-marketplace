---
name: interactive-cli-design
description: "Diseña e implementa CLIs con flags y modo interactivo: decide el modo según argumentos, TTY y CI, fija las flags mínimas (--help, --version, --no-input y las condicionales), da paridad entre cada flag y su pregunta, elige el widget según el dato (confirm, radio, lista con búsqueda, multiselect, input, secreto) y cierra exit codes, stdout/stderr y Ctrl+C, verificando en una pseudoconsola real. Usar siempre, sin pedido explícito, al crear o modificar un CLI, subcomando, script con argumentos, wizard, instalador o menú que reciba o pregunte datos, en Node, Python, Go, Rust, bash, zsh o PowerShell, aunque el pedido solo diga agregar un flag, «que pregunte si falta un dato» o «hacelo interactivo». Cómo se ve la salida (color, spinner, tablas) es de vivid-visual-output: no usar para retocar solo eso. Tampoco en TUIs de pantalla completa, scripts sin entradas ni slash commands de agentes."
license: MIT
metadata:
  version: "1.0.0"
  author: "Guido Modarelli"
  category: "developer-experience"
  tags: "cli, flags, interactive, prompts, wizard, tty, exit-codes, node, python, go, rust, shell"
  command: "/interactive-cli-design"
---

# Interactive CLI Design

Un CLI increíble sirve a dos públicos con el mismo comando: a una persona le pregunta lo que falta, y a un script nunca lo deja colgado. Esta skill fija ese contrato y lo prueba en una pseudoconsola real, porque un prompt que funciona por pipe no prueba nada.

## Flujo

1. **Leer lo que existe.** Parser de argumentos, librería de prompts, helpers de consola, carpeta de constantes y reglas de `AGENTS.md` o `CLAUDE.md`. Usar primero lo que el proyecto ya tiene, después lo nativo del lenguaje. Una dependencia nueva es una decisión explícita y se dice en el reporte. En un cambio puntual, aplicar estas reglas a lo que el cambio toca y sugerir el resto al final.
2. **Inventariar los parámetros.** Por cada uno: nombre, tipo, valores válidos, si es obligatorio, su default y si es secreto o destructivo. De esa tabla salen las flags, los widgets, la validación y la ayuda.
3. **Decidir el modo** con la tabla de la sección siguiente.
4. **Cargar la referencia del stack** de la sección [Stacks](#stacks).
5. **Implementar en tres capas** ([Paridad](#paridad)).
6. **Verificar ejecutando** con [references/verification.md](references/verification.md). Lo que no se corrió no está verificado.
7. **Cerrar** con el reporte de la sección [Cierre](#cierre).

## Decisión de modo

Evaluar en orden. Gana la primera fila que aplica.

| # | Situación | Comportamiento | Exit |
|---|---|---|---|
| 1 | `--help`, `-h` o `--version` | Imprime en stdout y nunca pregunta ni actúa, aunque vengan otros flags | 0 |
| 2 | Flag desconocido o valor inválido | Error en stderr con el flag y los valores válidos. stdout vacío. No cae a preguntar, aunque haya terminal: el usuario dio un dato explícito y hay que decirle que está mal | 2 |
| 3 | No falta nada obligatorio | Corre directo, sin prompts | 0 o 1 |
| 4 | Falta algo y no se puede preguntar | Falla enseguida, sin colgarse, y nombra en una línea **todos** los flags faltantes | 2 |
| 5 | Falta algo y hay terminal | Pregunta y al final imprime el comando equivalente | 0, 1 o 130 |
| 6 | Tiene subcomandos y no se pasó ninguno | Con terminal, menú de subcomandos y sigue con el elegido. Sin terminal, ayuda breve en stderr | 0 o 2 |

**Se puede preguntar** solo si stdin y stderr son terminales, no se pasó `--no-input`, `CI` no está definida (o vale `0` o `false`) y `TERM` no es `dumb`. Se mira stderr y no stdout porque ahí se dibujan los prompts: `tool > plan.json` sigue siendo interactivo y el archivo queda limpio.

**Puede correr sin flags** el CLI cuyos parámetros tienen todos un default seguro y que, corrido así, no destruye, no publica y no cobra (`git status`, `ls`). Si el default haría algo difícil de deshacer, no es seguro: va por la fila 5.

**Qué preguntar en la fila 5:**

- Sin ningún argumento: el wizard completo, obligatorios y opcionales, con el default preseleccionado.
- Con algún flag: solo lo obligatorio que falta. Quien ya pasó flags no quiere un interrogatorio; lo opcional toma su default.
- Un solo valor posible: no preguntar, usarlo e informarlo.

## Flags

**Universales.** Todo CLI lleva `-h, --help` y `--version`. Si puede preguntar, también `--no-input`. El corto de versión es opcional y conviene `-V`, porque `-v` es ambiguo entre verbose y versión.

**Condicionales.** Solo si el CLI hace eso. Cada flag se mantiene para siempre, así que lo que no se necesita no se agrega.

| Si el CLI… | Flag |
|---|---|
| Tiene defaults o confirmaciones que un script quiera aceptar | `-y, --yes`. Lo obligatorio sin default sigue fallando |
| Pisa o borra algo | `-f, --force`, en lugar de la confirmación |
| Hace cambios grandes o remotos, difíciles de revisar después | `-n, --dry-run` |
| Da una salida que consume otro programa | `--json` |
| Escribe un archivo | `-o, --output`, con `-` para stdout |
| Lee un archivo | Aceptar `-` para stdin |
| Hace mucho ruido de progreso | `-q, --quiet` |
| Recibe un secreto | `--<dato>-file <ruta>` o stdin |
| Tiene un multiselect | `--<dato> a,b`, repetible, con `none` para la lista vacía |

**Forma:**

- Usar un parser de verdad. A mano se pierden `--x=valor`, `--`, los errores y los flags en cualquier orden.
- Toda flag tiene nombre largo. Los cortos, solo para las frecuentes.
- Preferir flags a posicionales, salvo el operando principal (`cp origen destino`).
- Usar los nombres de la lista estándar de [clig.dev](https://clig.dev/#arguments-and-flags) antes de inventar uno.

**Ayuda.** Va a stdout y tiene, en este orden: qué hace en una línea, uno o dos ejemplos, las flags con su default y valores válidos, qué pasa sin flags y los códigos de salida. Cada subcomando tiene la suya.

## Paridad

Lo que garantiza que preguntar y pasar flags den el mismo resultado es que la acción no sepa de dónde vino cada valor:

```text
parseFlags(argv)        → valores parciales. Error de uso: exit 2
resolveMissing(valores) → pregunta lo que falta, o exit 2 si no se puede
run(valores)            → actúa
```

- **Cada pregunta tiene su flag, y cada flag de dato su pregunta.** El prompt nunca es la única entrada.
- **Una sola validación.** La misma función valida el flag y el prompt, con los valores válidos en constantes.
- **Preguntar todo antes de actuar.** Sin efectos hasta la última respuesta. Así Ctrl+C no deja nada a medias. Escribir archivos a un temporal y renombrar.
- **Imprimir el comando equivalente** en stderr cuando se preguntó algo. Tiene que reproducir el resultado sin una sola pregunta, con comillas dobles (las simples fallan en `cmd.exe`) y con `none` si un multiselect quedó vacío. Un secreto se muestra como `--token-file <ruta>`, nunca su valor.

## Widget según el dato

| Dato | Widget | Flag | Cuidado |
|---|---|---|---|
| Sí o no | Confirm | `--x`, `--no-x` | Default: la opción segura |
| Pocas opciones exclusivas | Radio (select) | `--x <valor>` | Con hasta 7 opciones se leen de un vistazo |
| Muchas opciones o dinámicas | Lista con búsqueda | `--x <valor>` | Sin filtro, 20 opciones son 20 flechazos |
| Varias opciones | Multiselect | `--x a,b` | Decir qué tecla marca. Decidir si vacío vale: varias librerías lo prohíben por default |
| Lista libre | Input separado por comas, o pregunta repetida | `--x a,b` | Mostrar lo acumulado |
| Texto o número | Input con validación | `--x <valor>` | El error va junto al prompt y no lo cierra |
| Ruta | Input con autocompletado, si la librería lo tiene | `--x <ruta>` | Validar que exista si se va a leer |
| Secreto | Input enmascarado | `--x-file <ruta>` o stdin | Nunca por argv: queda en `ps` y en el historial. Por variable de entorno también se filtra |
| Acción peligrosa | Confirm con default «no». Si es grave, escribir el nombre | `--force` o `--confirm=<nombre>` | Sin terminal y sin el flag: exit 2, nunca seguir |

## Contrato de salida

- **stdout lleva datos. stderr, todo lo demás:** prompts, progreso, avisos y errores. Varias librerías dibujan en stdout por default, y ahí `tool | jq` se rompe. Cada referencia dice si hay que cambiarlo y cómo.
- **Códigos de salida**, documentados en la ayuda: `0` bien, `1` falló, `2` uso incorrecto (también datos faltantes sin terminal), `130` cancelado. Una falla propia del dominio puede tener su código si un script necesita distinguirla.
- **Cancelar.** Ctrl+C sale con 130, deja el cursor visible y dice que no se cambió nada. Cada librería avisa distinto, y un aviso sin chequear sigue el wizard con basura: revisar cada prompt.
- **Errores.** Una línea con qué falló y qué hacer: el flag, los valores válidos y `Corré tool --help`. El stack trace, solo detrás de `--debug`.

Cómo se ve todo esto (paleta, spinner, tablas, ancho, `NO_COLOR`) es de la skill `vivid-visual-output`: cargarla si está disponible. Si no, respetar al menos `NO_COLOR` y no mandar secuencias de escape a un pipe.

## Stacks

Cargar solo la referencia del stack en uso. Cada una tiene parser, detección de terminal, widgets, dibujo en stderr, cancelación y trampas.

| Stack | Parser | Prompts | Referencia |
|---|---|---|---|
| Node | `node:util` `parseArgs` | `@clack/prompts` o `@inquirer/prompts` | [references/node.md](references/node.md) |
| Python | Typer o `argparse` | `questionary` | [references/python.md](references/python.md) |
| Go | `cobra` | `huh` | [references/go.md](references/go.md) |
| Rust | `clap` | `inquire` | [references/rust.md](references/rust.md) |
| bash, zsh, PowerShell | `case` o `param` | `gum` o lo nativo | [references/shell.md](references/shell.md) |

En otro stack, aplicar el mismo contrato y leer la documentación actual de sus librerías antes de usar su API.

## Cierre

Sumar al reporte, en pocas líneas: las flags elegidas y por qué, los casos de la matriz que corrieron con su resultado y los que no se pudieron correr con su motivo. Si el proyecto tiene tests, dejar automatizados los casos sin terminal, que no necesitan un PTY.

## Fuentes

Las reglas se apoyan en [clig.dev](https://clig.dev), las [POSIX Utility Syntax Guidelines](https://pubs.opengroup.org/onlinepubs/9799919799/basedefs/V1_chap12.html), los [GNU Coding Standards](https://www.gnu.org/prep/standards/html_node/Command_002dLine-Interfaces.html), [no-color.org](https://no-color.org) y el comportamiento real de `gh` y `create-vite`. Ante una duda que esta skill no cubre, leer esas fuentes en vez de improvisar.
