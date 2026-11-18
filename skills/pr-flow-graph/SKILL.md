---
name: pr-flow-graph
description: >-
  Convierte un pull request en un grafo visual e interactivo del flujo que
  toca: qué piezas de la arquitectura agregó, modificó o eliminó (vistas,
  acciones, dispatcher, stores, servicios) y cómo cambia el flujo de negocio
  (estados y transiciones). Genera un HTML con vistas de cambios y de negocio,
  antes y después, y evidencia archivo:línea comprobada contra el diff, más
  diagramas Mermaid para la descripción del PR y, si se pide, un modelo formal
  en Lean 4 que solo se muestra si compila. Usar con /pr-flow-graph o al pedir
  "graficá este PR", "grafo del flujo del PR", "diagrama de lo que cambia esta
  branch", "visualizá el flujo de estos cambios", "mostrame cómo queda el flujo
  con este PR" o "modelo formal del flujo", en cualquier stack (Android con
  Flux o MVVM, Redux, backend). No sirve para diagramas de toda la
  arquitectura sin un PR o diff, ni para revisar bugs del PR (eso es
  code-review).
license: MIT
metadata:
  version: "1.1.0"
  author: "Guido Modarelli"
  category: "code-review"
  tags: "pull-request, graph, flow, visualization, mermaid, elk, state-machine, lean"
  command: "/pr-flow-graph"
---

# PR Flow Graph

Un PR se revisa archivo por archivo, pero se entiende como flujo. Esta skill arma ese flujo una sola vez, en un modelo JSON, y de ahí salen todas las vistas: el grafo interactivo, los diagramas Mermaid, el modelo formal y el reporte final.

Tu trabajo es escribir el modelo. Todo lo demás lo hace y lo comprueba `scripts/flow-graph.mjs`: abre cada línea de evidencia, la compara con el diff, cuenta los cambios y escribe el reporte. Por eso el modelo no se da por bueno hasta que el script lo acepta, y ningún número del reporte lo calculás vos.

## Entrada

1. El PR es lo que sigue a `/pr-flow-graph`: un número, una URL de GitHub o una branch.
2. Sin argumento, usá la branch actual contra su base (`gh pr view --json baseRefName,headRefName,title,url` si tiene PR; si no, la base por defecto del repo).
3. Si no hay diff contra la base, decilo en una línea y terminá: sin cambios no hay grafo de PR.

Flags opcionales en el pedido: `--lean` (o "con modelo formal") agrega el modelo en Lean 4; `--offline` embebe la librería en el HTML.

## Flujo de trabajo

### 1. Leer el cambio

- Listá los archivos del PR (`gh pr diff <n> --name-only` o `git diff --name-only <base>...HEAD`) y guardá la lista: en el paso 3 cada archivo tiene que quedar en el grafo o en `outOfScope`.
- Tomá el diff completo (`gh pr diff <n>` o `git diff <base>...HEAD`).
- Leé los archivos tocados enteros, no solo los hunks: una relación suele estar en una línea que el diff no muestra.
- Seguí cada pieza tocada **un salto** hacia afuera (quién la llama, a quién llama) para ubicarla en el flujo. Más lejos que eso no: el grafo es del PR, no de la aplicación.

### 2. Reconocer la arquitectura

Mirá cómo el repo nombra y conecta sus piezas y elegí el perfil que mejor lo describe en [references/architecture-profiles.md](references/architecture-profiles.md) (Flux unidireccional, Redux, MVVM, capas de backend). El perfil dice qué `kind` usar para cada pieza y qué relaciones buscar. Si el repo usa una librería propia o una variante, describila por lo que hace: los nombres de los nodos son los del código, el perfil solo aporta el vocabulario.

### 3. Escribir el modelo

Escribí `pr-flow-graph/flow-graph.json` en la raíz del repo analizado, siguiendo [references/flow-graph-schema.md](references/flow-graph-schema.md). Copiá la forma de [assets/example-flow-graph.json](assets/example-flow-graph.json), que es un modelo completo y válido.

Estas reglas sostienen la confianza en el grafo. El script las comprueba una por una, así que conviene cumplirlas al escribir:

| Regla | Cómo cumplirla |
|---|---|
| **Evidencia real.** Todo elemento agregado, modificado o eliminado lleva `{ path, line }`. | Copiá la ruta y el número de línea del archivo abierto, no de memoria. Lo agregado apunta a una línea que el diff agrega; lo eliminado, a una línea que el diff quita, con `"side": "base"`. |
| **Verificado o inferido.** Una relación es `verified` solo si su evidencia es la línea que la escribe. | Esa línea, o las dos de arriba o abajo, tienen que nombrar al otro extremo (la llamada, el dispatch, la suscripción). Si la dedujiste por inyección de dependencias, un bus de eventos o una convención, es `inferred` y lleva `reason`. |
| **Nada sin explicar.** Cada archivo del PR está en el grafo o en `outOfScope`. | Recorré la lista del paso 1. Lo que no aporta al flujo (tests, docs, versiones, lockfiles) va en `outOfScope` con el motivo. |
| **Dos flujos distintos.** `nodes` y `edges` son piezas de código; `businessFlow` es lo que vive el usuario. | Estados y disparadores con palabras de producto («Guardando», «Tocar el corazón»), sin nombres de clases, y `summary` con una frase sobre qué cambia. En un refactor puro, omití `businessFlow`. |

Inventar una relación verificada es el peor error posible acá: el revisor va a confiar en ella. Ante la duda, `inferred` con su `reason`.

Ordená `nodes` y `edges` en el orden en que ocurre el flujo: el grafo y su recorrido paso a paso siguen ese orden.

### 4. Validar y generar

Desde la raíz del repo analizado:

```bash
node <skill>/scripts/flow-graph.mjs render pr-flow-graph/flow-graph.json --repo .
```

`--repo` es obligatorio: es lo que distingue un grafo comprobado de uno que solo tiene buena forma. Necesita que el clon tenga las dos refs del PR; si falta alguna, hacé `git fetch` antes. En un PR ya mergeado, cuya branch pudo borrarse, poné en `headRef` y `baseRef` los commits exactos (el merge commit y su padre). Agregá `--inline-libraries` si se pidió `--offline` y `--lean pr-flow-graph/FlowModel.lean` si hay modelo formal.

**Si el comando falla (código de salida 1), no hay grafo todavía.** Cada línea `[error]` dice dónde está el problema y cómo se arregla. Corregí el modelo y volvé a correr, las veces que haga falta:

| El error dice | Qué hacer |
|---|---|
| `does not exist in …` o `is past the end of the file` | Abrí el archivo y copiá la ruta y la línea correctas. Si el archivo fue eliminado, agregá `"side": "base"`. |
| `none of its evidence is a line the pull request added` (o `removed`) | Apuntá a una línea que el diff muestre como agregada o quitada, o cambiá `change` a `modified` o `unchanged` si eso es lo cierto. |
| `does not name the other end` | Apuntá a la línea que escribe la relación. Si el código usa otro nombre para la pieza, ponelo en `symbol` del nodo. Si no existe tal línea, la relación es `inferred` con `reason`. |
| `changed N file(s) that the model does not account for` | Agregá cada archivo como evidencia de un elemento, o listalo en `outOfScope` con su motivo. |
| `Must be "added" because the node … is added` | Una relación que toca algo agregado es agregada; una que toca algo eliminado es eliminada. |

No edites los archivos generados, no saltees un error y no uses `--skip-repo-check` para esquivar uno: esa opción existe solo para cuando no hay clon, y deja el grafo marcado como «sin verificar».

Cuando termina bien, el comando escribe junto al modelo `pr-flow-graph.html`, `pr-flow-graph.md` y `pr-flow-graph-report.md`, e imprime sus rutas y el resultado de cada comprobación como JSON en stdout.

### 5. Modelo formal (solo si se pidió)

Seguí [references/formal-model.md](references/formal-model.md). El modelo se escribe a partir de `businessFlow`, y `render --lean` lo incluye únicamente si Lean lo compila, no usa `sorry` y nombra todos los estados. Si Lean no está instalado o el modelo no pasa, queda fuera del grafo y el reporte lo dice; no lo presentes como verificado.

### 6. Reportar

Leé `pr-flow-graph/pr-flow-graph-report.md` y pegá su contenido **tal cual** como respuesta final. Ya trae las rutas, las cantidades, las relaciones inferidas, lo que quedó fuera y qué se verificó. No recalcules ni reescribas esas líneas.

Después del reporte podés agregar, como máximo, dos líneas propias: algo que viste en el PR y que el grafo no muestra, o una relación inferida que conviene confirmar primero.

No pegues el Mermaid en el PR ni publiques nada por tu cuenta: ofrecé hacerlo y esperá la confirmación.

## Antes de terminar

- [ ] `render` terminó con código 0 y **con** `--repo`.
- [ ] El reporte pegado es el archivo generado, sin cambios.
- [ ] Si se pidió modelo formal, el reporte dice «incluido» o dice por qué no.

## PRs grandes

Con más de unos 40 nodos el grafo deja de leerse. Antes de llegar ahí:

- Dejá como nodos solo las piezas que el PR toca y sus vecinos directos.
- Agrupá por módulo o capa con `groups`.
- Si el PR mezcla flujos independientes, generá un modelo por flujo (`flow-graph-<flujo>.json`, cada uno en su carpeta de salida con `--out`). Cada modelo declara en `outOfScope` los archivos que cubre otro.

## Herramientas

El layout lo calcula [ELK](https://github.com/kieler/elkjs) (capas, ruteo ortogonal y lugar de las etiquetas) y la página dibuja el SVG. La elección, el diseño de la página y las alternativas descartadas están en [references/rendering.md](references/rendering.md); leelo solo si vas a cambiar la plantilla o la librería.
