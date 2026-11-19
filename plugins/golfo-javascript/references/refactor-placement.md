# Dónde va un refactor: mismo PR o capa de stacked PR

Fuente canónica del criterio que usan las skills de refactor (`constants-refactor`, `refactor-modularize-code`, `typed-errors-refactor`, `simplify-code`) para decidir si un refactor viaja con la feature o en una capa propia de un stacked PR. `stacked-pr` (plugin `golfo-github`) lo usa para crear esa capa. Este archivo solo decide **dónde** va el refactor. **Cómo** refactorizar lo define cada skill.

## Por qué importa

Un PR de feature que también mueve, renombra o reorganiza código existente mezcla dos preguntas en un mismo diff: qué comportamiento cambió y qué solo se movió. El revisor tiene que separarlas a mano, el refactor no se puede revertir sin la feature y el diff crece por movimientos que no aportan comportamiento. Una capa de refactor separa las dos cosas. Pero cada capa tiene un costo fijo (CI, review, rebases), así que no conviene abrirla para un cambio chico.

## Criterio

Clasificar cada refactor por **qué código toca** y **qué relación tiene con la feature**, y aplicar la primera fila que encaje:

| Caso | Dónde va | Qué hacer |
|---|---|---|
| Código que la propia feature agrega o reescribe en este PR | Mismo PR | Aplicarlo sin preguntar. Escribir bien el código nuevo no es un refactor aparte. |
| Refactor de código existente que la feature necesita para poder hacerse (extraer un módulo que después extiende, un contrato que después consume) | Capa **debajo** de la feature | Sugerir una capa preparatoria. La feature queda encima y su diff muestra solo el cambio de comportamiento. |
| Limpieza de código existente fuera del alcance de la feature, o un refactor que infla el diff (moves, renames, cambios mecánicos en muchos archivos) | Capa **encima** de la feature | Sugerir una capa de refactor posterior, con la feature como base. |
| Refactor chico de código existente, pegado a las líneas que la feature ya toca | Mismo PR | Aplicarlo y mencionarlo en la descripción del PR. |

Un refactor "infla el diff" cuando sus líneas se acercan o superan a las de la feature, o cuando toca archivos que la feature no tocaría. Ante la duda entre "chico" y "capa", elegir mismo PR: una capa de más cuesta más que un párrafo en la descripción.

## Cuándo sugerir y cuándo no

- **Sugerir, nunca crear por cuenta propia.** Proponer la capa en una línea (qué refactor, si va debajo o encima y por qué) y esperar el sí del usuario. Crear ramas y PRs extra es un efecto remoto que el usuario tiene que pedir.
- **Solo si hay una feature en curso.** Si el pedido es solo refactorizar, no hay capa que separar: el refactor es el PR.
- **No en flujos no interactivos ni con alcance cerrado**, como loops de auto-fix, closeout de comentarios de review o fixes en clones efímeros. Ahí el alcance ya está fijado y un PR extra sería un efecto que nadie pidió. Aplicar lo que entra en el alcance y dejar el resto como sugerencia fuera de alcance en el reporte.
- **Si el usuario ya decidió**, no volver a preguntar. "Hacelo en el mismo PR" o "separalo" mandan sobre la tabla.

## Si el usuario acepta la capa

Crearla con `stacked-pr` (plugin `golfo-github`), en su modo de capa de refactor:

- **Encima**: la rama de refactor sale del head de la feature y su PR usa la rama de la feature como base.
- **Debajo**: la rama de refactor sale de la base de la feature, y la feature se rebasa sobre ella. Reescribir la rama de la feature necesita autorización explícita.

Si `stacked-pr` no está instalado, explicar el criterio y dejar que el usuario cree la capa a mano. No improvisar el flujo de stack.
