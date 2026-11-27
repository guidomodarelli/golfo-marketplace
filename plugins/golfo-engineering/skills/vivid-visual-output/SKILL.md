---
name: vivid-visual-output
description: "Usar siempre (con `~/.work`, solo a pedido) al escribir o cambiar código cuya salida mira una persona, aunque el pedido solo hable de la lógica: pantallas, páginas y reportes HTML, rediseños de UI, componentes de React, Vue u otro framework (una tarjeta, una tabla, un formulario), scripts y CLI con salida en terminal, instaladores, wizards, menús, reportes y tareas largas. Hace que se vea muy lindo y con vida (color, tablas, listas, animación), con un piso de calidad y sin imponer estética. En todo componente o pantalla, cargarla junto con ui-ux-flow-patterns: esa decide qué muestra cada estado; esta, cómo se ve. Cubre degradación de color (NO_COLOR, CI, pipes), ancho, spinner, cursor, design tokens, temas, mobile, contraste AA y prefers-reduced-motion. Solo aplica cuando la tarea escribe código: no para responder preguntas ni explicar, y no en backend, migraciones, librerías o tests, ni al sumar una salida que consume otro programa (JSON para jq, datos por pipe, logs estructurados), aunque sea en un CLI."
license: MIT
metadata:
  version: "1.6.0"
  author: "Guido Modarelli"
  category: "developer-experience"
  tags: "terminal, cli, ansi, color, spinner, table, ui, design-tokens, dark-mode, reduced-motion"
  command: "/vivid-visual-output"
  plugin-dependencies: "golfo-cli, golfo-frontend, golfo-web"
---

# Vivid Visual Output

Lo visual tiene que dar gusto: color con intención, tablas alineadas, listas claras y movimiento que acompaña. Esta skill no impone una estética. Fija un piso de calidad y deja libre todo lo demás, gradientes y truecolor incluidos.

Lo aburrido no cumple. Lo lindo que se rompe en un pipe, a 40 columnas o en tema oscuro, tampoco.

## Gate de máquina de trabajo (`~/.work`)

Primer paso, antes de leer cualquier referencia: aplicar el gate de [`references/work-machine-gate.md`](../../references/work-machine-gate.md). Con `~/.work` esta skill corre solo a pedido. Cuenta como pedido explícito, por ejemplo, «mejorá cómo se ve esta salida» o «dale color y vida a este reporte», y también cargarla desde `interactive-cli-design` o `ui-ux-flow-patterns` cuando el usuario pidió esa skill; cambiar la lógica de una pantalla o de un script, no.

## Flujo

1. **Clasificar la superficie.** Terminal, UI o las dos. Si el cambio no tiene salida visible, terminar acá sin agregar nada. Si solo toca una salida para máquinas (`--json`), el único trabajo es que no le llegue decoración.
2. **Leer lo que ya existe.** Design system, `DESIGN.md`, tokens, helpers de consola, carpetas de constantes y las reglas de `AGENTS.md` o `CLAUDE.md`. Lo que exista se usa, no se reinventa. Una regla más restrictiva del proyecto (solo ASCII, sin color, sin animación) prevalece sobre esta skill.
3. **Fijar el carácter.** Si el proyecto todavía no tiene uno, elegir paleta, glifos y ritmo de animación, y dejarlos como constantes reutilizables en un solo lugar. Elegirlos desde el proyecto (su dominio, su nombre, su público) y no desde un default: dos proyectos distintos no deberían verse iguales, y todo lo de un mismo proyecto sí debería. Los temas de los kits y de los ejemplos solo muestran la forma: copiar sus valores no cumple este paso, así que siempre se reemplazan. En terminal, usá una paleta chica y coherente desde el lanzador hasta el resumen: un acento para título, foco y contador (`[1/42]`), primer plano para texto común y colores semánticos para éxito, aviso y error. Distinguí papeles similares con peso o intensidad, no con más matices: [references/terminal.md](references/terminal.md#papeles-con-una-paleta-chica).
4. **Cargar solo la referencia del medio.**
   - Terminal: [references/terminal.md](references/terminal.md).
   - UI: [references/web-ui.md](references/web-ui.md), junto con las [skills vecinas](#skills-vecinas) que el cambio pida. Nombrar cuáles se usan y, si alguna no está disponible, decirlo.
5. **Construir sobre el piso de calidad** de la sección siguiente.
6. **Verificar ejecutando.** Cada referencia termina con sus chequeos. Decir qué corrió, qué dio y qué no se pudo correr: lo que no se corrió no está verificado.

En un cambio puntual, aplicar el piso a lo que el cambio toca y con el carácter que ya existe. No rediseñar lo demás: sugerirlo al final.

## Piso de calidad

- **Con vida, sin demora.** Una animación acompaña una espera real, nunca la crea. En terminal compatible, preferí un spinner de puntos Braille (`⠋⠙⠹⠸…`) con tiempo transcurrido; conservá el mismo ritmo y aspecto entre lanzador y programa. Si se requiere ASCII, usá un equivalente de una celda. Nada de `sleep` decorativos ni efectos de máquina de escribir; sin TTY, conservá el progreso en texto plano.
- **El texto común es neutro.** En terminal, dejar párrafos, preguntas, etiquetas inactivas y texto de progreso en el primer plano predeterminado (blanco en un perfil oscuro; no forzar blanco sobre fondo claro). Reservar color para títulos, marcadores de paso, verbos de acción, foco y estados. Mantener el color visible en cada paso importante: por ejemplo, `Consultar scopes` en el acento y `· aplicación` en el primer plano. Aplicar la misma regla desde el lanzador hasta el resumen; ni teñir todo de un único acento ni dejar el cuerpo sin señales visuales. Si cada acción de un menú tiene un emoji inequívoco, usarlo junto al nombre en TTY, nunca en vez del nombre.
- **Se entiende sin color ni animación.** Cada estado lleva símbolo y palabra, y el color solo refuerza. Quien usa `NO_COLOR`, un lector de pantalla, movimiento reducido o una impresión en blanco y negro recibe la misma información.
- **Los lotes se cierran por resultado.** Agrupar resultados en secciones con título y contador (errores, por verificar / pendientes, hechos y omitidos), y mostrar solo las secciones con datos. Para omisiones repetidas, escribir el motivo una sola vez y listar los recursos debajo. Conservar identificador y detalle por error; no esconder resultados ambiguos ni mezclarlos con éxitos.
- **Los datos quedan limpios.** La decoración nunca llega a una salida parseable (pipes, `--json`, TSV/CSV), y degradar la presentación nunca pierde datos: lo que no entra se reacomoda, no se trunca; en terminal angosta, apilar campos. Al revés tampoco: no reutilizar filas TSV/CSV como presentación de un plan o confirmación humana; en TTY, mostrar candidatos con encabezados, agrupar omisiones por motivo y separar errores.
- **Consistencia por constantes.** Colores, glifos y tiempos salen de un solo lugar. Cambiar el carácter del proyecto no toca la lógica.
- **Fallar también se ve bien.** Un error o una interrupción deja la terminal o la pantalla como estaban, con un mensaje claro y un estado de salida correcto.

## Dependencias

Usar primero lo que el proyecto ya tiene, después lo nativo de la plataforma. Proponer una librería nueva solo como decisión explícita. Si el proyecto ya usa una librería de color o spinners, verificar que respete la precedencia de [references/terminal.md](references/terminal.md#1-capacidades): varias dejan color en CI o le dan prioridad a `FORCE_COLOR`.

## Skills vecinas

Esta skill decide cómo se ve. No repite lo que ya tiene dueña:

- `ui-ux-flow-patterns`: qué mostrar en cada estado, qué canal de feedback usar y qué copy escribir.
- `semantic-html-a11y`: elementos nativos, nombres accesibles, teclado y foco.
- `mobile-first-responsive-layout`: unidades, breakpoints y escalas responsivas.
- `interactive-cli-design`: flags, cuándo preguntar, widgets y códigos de salida de un CLI.

## Cierre

Sumar al reporte, en pocas líneas: el carácter usado o reusado, los chequeos que corrieron con su resultado y los que no se pudieron correr con su motivo.
