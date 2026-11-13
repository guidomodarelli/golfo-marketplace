---
name: interactive-cli-design
description: "Diseña e implementa CLIs con flags y modo interactivo: decide el modo según argumentos, TTY y CI, fija las flags mínimas (--help, --version, --no-input y las condicionales), da paridad entre cada flag y su pregunta, elige el widget según el dato (confirm, radio, lista con búsqueda, multiselect, input, secreto) y cierra exit codes, stdout/stderr y Ctrl+C, verificando en una pseudoconsola real. Usar siempre, sin pedido explícito, al crear o modificar un CLI, subcomando, script con argumentos, wizard, instalador o menú que reciba o pregunte datos, en Node, Python, Go, Rust, bash, zsh o PowerShell, aunque el pedido solo diga agregar un flag, «que pregunte si falta un dato» o «hacelo interactivo». Cómo se ve la salida (color, spinner, tablas) es de vivid-visual-output: no usar para retocar solo eso. Tampoco en TUIs de pantalla completa, scripts sin entradas ni slash commands de agentes."
license: MIT
metadata:
  version: "1.1.0"
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
| 3 | Exige un subcomando y no se pasó ninguno | Con terminal, menú de subcomandos, y se sigue evaluando desde la fila 4 con el elegido. Sin terminal, ayuda breve en stderr | 2 sin terminal |
| 4 | No falta nada obligatorio | Corre directo, sin prompts | 0 o 1 |
| 5 | Falta algo y no se puede preguntar | Falla enseguida, sin colgarse, y nombra en una línea **todos** los flags faltantes | 2 |
| 6 | Falta algo y hay terminal | Pregunta y al final imprime el comando equivalente | 0, 1 o 130 |

**Valores que se validan contra datos vivos** (una lista que trae una API, los AVDs instalados, los estados de un entorno) solo se conocen después de consultar. Si el valor tiene la forma correcta pero no existe ahí: con terminal, avisar y preguntarlo de la lista real; sin terminal, exit 2 con los valores válidos. Un valor con forma inválida sigue siendo la fila 2.

**Se puede preguntar** solo si stdin y stderr son terminales, no se pasó `--no-input`, `CI` no está definida (o vale `0` o `false`) y `TERM` no es `dumb`. Se mira stderr y no stdout porque ahí se dibujan los prompts: `tool > plan.json` sigue siendo interactivo y el archivo queda limpio.

**Puede correr sin flags** el CLI cuyos parámetros tienen todos un default seguro y que, corrido así, no destruye, no publica y no cobra (`git status`, `ls`). Si el default haría algo difícil de deshacer, no es seguro: va por la fila 6.

**Qué preguntar en la fila 6:**

- Sin ningún argumento: el wizard completo, obligatorios y opcionales, con el default preseleccionado.
- Con algún flag: solo lo obligatorio que falta. Quien ya pasó flags no quiere un interrogatorio; lo opcional toma su default.
- Un solo valor posible: no preguntar, usarlo e informarlo.
- Lo que vino por flag no se vuelve a preguntar ni se pisa, aunque la pregunta siguiente dependa de él. El comando equivalente trae los dos: lo pasado y lo respondido.
- **Ordenar por dependencia.** Primero lo que cambia las opciones o el riesgo de lo que sigue: si el entorno decide qué regiones existen, el entorno va antes que la región. Así ninguna respuesta invalida una anterior.
- **Recordar lo que se repite.** Si una respuesta suele ser la misma entre corridas (el último AVD, el mail de siempre), ofrecerla primero y que Enter la elija. Se guarda solo en la máquina, nunca un secreto, y si el archivo no se puede leer se avisa y se pregunta como siempre: [references/native-prompts.md](references/native-prompts.md#recordar-respuestas).
- **Sin defaults implícitos cuando elegir mal cuesta** (producción contra test, crear contra reusar). Con flags se elige siempre, y para «lo de siempre» hay un valor con nombre (`--user nuevo`, `--email auto`), así un script lo dice explícito y no por omisión.

## Flags

**Universales.** Todo CLI lleva `-h, --help` y `--version`. Si puede preguntar, también `--no-input`. El corto de versión es opcional y conviene `-V`, porque `-v` es ambiguo entre verbose y versión.

**Condicionales.** Solo si el CLI hace eso. Cada flag se mantiene para siempre, así que lo que no se necesita no se agrega.

| Si el CLI… | Flag |
|---|---|
| Tiene defaults o confirmaciones que un script quiera aceptar | `-y, --yes`. Lo obligatorio sin default sigue fallando |
| Pisa o borra algo | `-f, --force`, en lugar de la confirmación |
| Hace cambios grandes o remotos, difíciles de revisar después | `-n, --dry-run`. Muestra el plan aunque falle una lectura que no es imprescindible: los pasos que conoce y el error, en vez de no mostrar nada |
| Lee los valores de un archivo de configuración | `-c, --config <ruta>`. El archivo pasa por la misma validación que los flags, y los flags pisan lo del archivo |
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
- **Sin abreviaturas de flags.** Varios parsers aceptan `--tok` por `--token` (`argparse` por default; desactivarlo con `allow_abbrev=False`). Una abreviatura que hoy es única deja de serlo al sumar un flag, y un secreto pasado como `--tok=x` se escapa del filtro que lo saca del comando guardado.
- Usar los nombres de la lista estándar de [clig.dev](https://clig.dev/#arguments-and-flags) antes de inventar uno.

**Ayuda.** Va a stdout y tiene, en este orden: qué hace en una línea, uno o dos ejemplos, las flags con su default y valores válidos, qué pasa sin flags y los códigos de salida. Cada subcomando tiene la suya. Siempre con este formato, aunque el parser traiga otro:

- **Todo lo que tiene descripción va en una tabla de dos columnas**: subcomandos, flags, argumentos, variables de entorno y códigos de salida. A la izquierda el nombre (`-n, --name <valor>`), a la derecha la descripción con su default y valores válidos. La izquierda se alinea a la más ancha de su sección. La descripción larga se parte dentro de su columna; si la terminal es tan angosta que no entra, se apila (el nombre en una línea y la descripción sangrada debajo), nunca se trunca.
- **Comandos y flags con colores distintos**, en la tabla, en la línea de uso y en los ejemplos: el programa y sus subcomandos en un color, las flags en otro, los `<valores>` atenuados y los títulos de sección en negrita. Los colores salen de las constantes del proyecto (de `vivid-visual-output` si está disponible).
- **Sin color, el mismo formato.** Si stdout no es una terminal, hay `NO_COLOR` o `TERM=dumb`, la ayuda sale sin secuencias de escape y con las mismas dos columnas: `tool --help | less` y `tool --help > ayuda.txt` se leen igual.

Cada referencia de stack dice cómo lograrlo con su parser.

## Paridad

Lo que garantiza que preguntar y pasar flags den el mismo resultado es que la acción no sepa de dónde vino cada valor:

```text
parseFlags(argv)        → valores parciales. Error de uso: exit 2
resolveMissing(valores) → pregunta lo que falta, o exit 2 si no se puede
run(valores)            → actúa
```

- **Cada pregunta tiene su flag, y cada flag de dato su pregunta.** El prompt nunca es la única entrada.
- **Una sola validación.** La misma función valida el flag, el prompt y el archivo de configuración, con los valores válidos en constantes.
- **Preguntar todo antes de actuar.** Sin efectos hasta la última respuesta. Así Ctrl+C no deja nada a medias. Escribir archivos a un temporal y renombrar. Decidir también, antes del primer efecto, lo que puede hacer fallar un paso posterior: si el tercer paso no se va a poder hacer con lo elegido, preguntarlo o fallar antes de crear el primero.
- **Imprimir el comando equivalente** en stderr cuando se preguntó algo. Tiene que reproducir el resultado sin una sola pregunta, con `none` si un multiselect quedó vacío y con las comillas de la plataforma: simples en POSIX, que dejan el valor literal, y dobles en Windows, donde `cmd.exe` no entiende las simples. Las referencias de Node y Python traen el helper y sus límites. Un secreto se muestra como `--token-file <ruta>`, nunca su valor, en ninguna de sus formas (`--token x`, `--token=x`, `-tx`, la variable de entorno) ni en el comando que se guarda en un archivo. Si no entra en el ancho de la terminal, partirlo entre argumentos con ` \` (POSIX), nunca a mitad de un valor.

## Widget según el dato

| Dato | Widget | Flag | Cuidado |
|---|---|---|---|
| Sí o no | Confirm | `--x`, `--no-x` | Default: la opción segura |
| Pocas opciones exclusivas | Radio (select) | `--x <valor>` | Con hasta 7 opciones se leen de un vistazo |
| Muchas opciones o dinámicas | Lista con búsqueda | `--x <valor>` | Sin filtro, 20 opciones son 20 flechazos. Escribir filtra sin importar mayúsculas ni acentos, así que las letras no son atajos (`j`/`k`). Sin librería: flechas con `termios` y respaldo numerado, según [native-prompts.md](references/native-prompts.md) |
| Varias opciones | Multiselect | `--x a,b` | Decir qué tecla marca. Decidir si vacío vale: varias librerías lo prohíben por default |
| Lista libre | Input separado por comas, o pregunta repetida | `--x a,b` | Mostrar lo acumulado |
| Texto o número | Input con validación | `--x <valor>` | El error va junto al prompt y no lo cierra |
| Ruta | Input con autocompletado, si la librería lo tiene | `--x <ruta>` | Validar que exista si se va a leer |
| Secreto | Input enmascarado | `--x-file <ruta>` o stdin | Nunca por argv: queda en `ps` y en el historial. Por variable de entorno también se filtra |
| Acción peligrosa | Confirm con default «no». Si es grave, escribir el nombre | `--force` o `--confirm=<nombre>` | Sin terminal y sin el flag: exit 2, nunca seguir |

- **Cada respuesta queda a la vista.** Al elegir, borrar el menú y dejar una línea `✔ pregunta › respuesta`, con la respuesta sin las marcas de la etiqueta («último usado», «por defecto»). Así se lee qué se eligió sin que el menú ocupe la pantalla.
- **Sin librería de prompts** (o cuando la del proyecto no filtra ni dibuja en stderr): menú propio con flechas, filtro y respaldo numerado en [references/native-prompts.md](references/native-prompts.md).
- **Un secreto se pide recién cuando hace falta**, no al arrancar: un comando que no lo usa no lo pide. Se lee de la terminal (no de stdin, que puede ser un pipe), con el eco apagado **antes** de mostrar la pregunta, para que un valor pegado enseguida tampoco se vea. Si se cachea, va al llavero del sistema y con margen de vencimiento: [references/native-prompts.md](references/native-prompts.md#secretos).

## Contrato de salida

- **stdout lleva datos. stderr, todo lo demás:** prompts, progreso, avisos y errores. Varias librerías dibujan en stdout por default, y ahí `tool | jq` se rompe. Cada referencia dice si hay que cambiarlo y cómo.
- **Códigos de salida**, documentados en la ayuda: `0` bien, `1` falló, `2` uso incorrecto (también datos faltantes sin terminal), `130` cancelado. Una falla propia del dominio puede tener su código si un script necesita distinguirla.
- **Cancelar.** Ctrl+C sale con 130, deja el cursor visible y dice que no se cambió nada. Cada librería avisa distinto, y un aviso sin chequear sigue el wizard con basura: revisar cada prompt. Desde el segundo Ctrl+C, ignorarlo: si no, corta el aviso o muestra un traceback mientras se cierra. Un wrapper de shell que delega en otro programa no se corta con el primero: lo deja manejar al hijo y solo espera su exit code.
- **Cancelar o fallar después de actuar.** Si ya hubo efectos, decir «no se cambió nada» es falso. Listar qué quedó hecho (con sus identificadores) y el comando para seguir desde ahí con lo mismo, en vez de empezar de cero.
- **Esperas largas.** Si un servicio tarda en responder porque está levantando (escalado a cero, 503 transitorio), reintentar con intervalo y tope, decir en el paso qué se espera y hasta cuándo, y que Ctrl+C siga cortando. Un chequeo que no respondió no es un «ok»: se informa aparte y no sale con 0.
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
| Cualquiera, sin librería de prompts | El del stack | Menú propio con filtro, memoria de respuestas, secretos y Ctrl+C | [references/native-prompts.md](references/native-prompts.md) |

En otro stack, aplicar el mismo contrato y leer la documentación actual de sus librerías antes de usar su API.

## Cierre

Sumar al reporte, en pocas líneas: las flags elegidas y por qué, los casos de la matriz que corrieron con su resultado y los que no se pudieron correr con su motivo. Si el proyecto tiene tests, dejar automatizados los casos sin terminal, que no necesitan un PTY.

## Fuentes

Las reglas se apoyan en [clig.dev](https://clig.dev), las [POSIX Utility Syntax Guidelines](https://pubs.opengroup.org/onlinepubs/9799919799/basedefs/V1_chap12.html), los [GNU Coding Standards](https://www.gnu.org/prep/standards/html_node/Command_002dLine-Interfaces.html), [no-color.org](https://no-color.org) y el comportamiento real de `gh` y `create-vite`. Ante una duda que esta skill no cubre, leer esas fuentes en vez de improvisar.
