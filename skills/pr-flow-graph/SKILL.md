---
name: pr-flow-graph
description: >-
  Convierte un pull request en un grafo visual e interactivo del flujo que
  toca: qué piezas de la arquitectura agregó, modificó o eliminó (vistas,
  acciones, dispatcher, stores, servicios) y cómo cambia el flujo de negocio
  (estados y transiciones). Genera un HTML con vistas de cambios y de negocio,
  antes y después, y evidencia archivo:línea en cada elemento, más diagramas
  Mermaid para pegar en la descripción del PR y, si se pide, un modelo formal
  en Lean 4 que solo se muestra si compila. Usar con /pr-flow-graph o al pedir
  "graficá este PR", "grafo del flujo del PR", "diagrama de lo que cambia esta
  branch", "visualizá el flujo de estos cambios", "mostrame cómo queda el flujo
  con este PR" o "modelo formal del flujo", en cualquier stack (Android con
  Flux o MVVM, Redux, backend). No sirve para diagramas de toda la
  arquitectura sin un PR o diff, ni para revisar bugs del PR (eso es
  code-review).
license: MIT
metadata:
  version: "1.0.0"
  author: "Guido Modarelli"
  category: "code-review"
  tags: "pull-request, graph, flow, visualization, mermaid, elk, state-machine, lean"
  command: "/pr-flow-graph"
---

# PR Flow Graph

Un PR se revisa archivo por archivo, pero se entiende como flujo. Esta skill arma ese flujo una sola vez, en un modelo JSON, y de ahí salen todas las vistas: el grafo interactivo, los diagramas Mermaid y el modelo formal. Como todas salen del mismo modelo, no se contradicen.

## Entrada

1. El PR es lo que sigue a `/pr-flow-graph`: un número, una URL de GitHub o una branch.
2. Sin argumento, usá la branch actual contra su base (`gh pr view --json baseRefName,headRefName,title,url` si tiene PR; si no, la base por defecto del repo).
3. Si no hay diff contra la base, decilo en una línea y terminá: sin cambios no hay grafo de PR.

Flags opcionales en el pedido: `--lean` (o "con modelo formal") agrega el modelo en Lean 4; `--offline` embebe la librería en el HTML.

## Flujo de trabajo

### 1. Leer el cambio

- Tomá el diff completo (`gh pr diff <n>` o `git diff <base>...HEAD`) y la lista de archivos.
- Leé los archivos tocados enteros, no solo los hunks: una relación suele estar en una línea que el diff no muestra.
- Seguí cada pieza tocada **un salto** hacia afuera (quién la llama, a quién llama) para ubicarla en el flujo. Más lejos que eso no: el grafo es del PR, no de la aplicación. Lo que queda fuera se nombra en el reporte final.

### 2. Reconocer la arquitectura

Mirá cómo el repo nombra y conecta sus piezas y elegí el perfil que mejor lo describe en [references/architecture-profiles.md](references/architecture-profiles.md) (Flux unidireccional, Redux, MVVM, capas de backend). El perfil dice qué `kind` usar para cada pieza y qué relaciones buscar. Si el repo usa una librería propia o una variante, describila por lo que hace: los nombres de los nodos son los del código, el perfil solo aporta el vocabulario.

### 3. Escribir el modelo

Escribí `pr-flow-graph/flow-graph.json` en la raíz del repo analizado, siguiendo [references/flow-graph-schema.md](references/flow-graph-schema.md). [assets/example-flow-graph.json](assets/example-flow-graph.json) es un modelo completo de referencia.

Tres reglas sostienen la confianza en el grafo, y el validador las exige:

- **Evidencia.** Todo elemento agregado, modificado o eliminado lleva al menos un `{ path, line }` que lo demuestra. Sin eso, el lector no puede comprobar nada y el grafo vale lo que una opinión.
- **Verificado o inferido.** Una relación es `verified` solo si hay una línea de código que la escribe (una llamada, un dispatch, una suscripción). Si la dedujiste por inyección de dependencias, un bus de eventos, reflexión o una convención de nombres, es `inferred` y lleva `reason`. Inventar una arista verificada es el peor error posible acá: el revisor va a confiar en ella.
- **Dos flujos distintos.** `nodes` y `edges` describen piezas de código. `businessFlow` describe lo que vive el usuario o el negocio (estados como «Guardando» o «Pago rechazado» y los eventos que llevan de uno a otro), con sus palabras y sin nombres de clases. Si el PR no cambia comportamiento observable (un refactor puro), omití `businessFlow` y decilo.

Ordená `nodes` y `edges` en el orden en que ocurre el flujo: el grafo se acomoda siguiendo ese orden.

### 4. Validar y generar

```bash
node <skill>/scripts/flow-graph.mjs render pr-flow-graph/flow-graph.json --repo .
```

`--repo` abre cada evidencia en la versión que nombra (`base` o `head`) y rechaza el modelo si el archivo o la línea no existen: es lo que distingue una evidencia real de una inventada. Necesita que el clon tenga las dos refs del PR; si falta alguna, hacé `git fetch` antes. En un PR ya mergeado, cuya branch pudo borrarse y cuya base siguió avanzando, poné en `baseRef` y `headRef` los commits exactos (el merge commit y su padre): con el nombre de la branch base las líneas ya no coincidirían. Agregá `--inline-libraries` si se pidió `--offline` y `--lean pr-flow-graph/FlowModel.lean` si hay modelo formal. El comando valida, genera `pr-flow-graph.html` y `pr-flow-graph.md` junto al modelo e imprime sus rutas como JSON en stdout.

Si la validación falla, corregí el modelo según cada mensaje y volvé a correr. No edites el HTML generado ni saltees el validador: un error ahí es una afirmación sin respaldo.

### 5. Modelo formal (solo si se pidió)

Seguí [references/formal-model.md](references/formal-model.md). El modelo se escribe a partir de `businessFlow`, y `render --lean` lo incluye únicamente si Lean lo compila y no usa `sorry`. Si Lean no está instalado o el modelo no compila, queda fuera del grafo y lo informás tal cual; no lo pegues en el reporte como si estuviera verificado.

### 6. Reportar

Cerrá con este formato:

```markdown
**Grafo:** <ruta de pr-flow-graph.html>
**Mermaid para el PR:** <ruta de pr-flow-graph.md>

- **Cambios:** <N agregados, N modificados, N eliminados> en <arquitectura>
- **Flujo de negocio:** <qué cambia para el usuario en una frase, o «sin cambios observables»>
- **Relaciones inferidas:** <cuántas y cuáles conviene que un humano confirme>
- **Fuera del grafo:** <qué partes del PR no se graficaron y por qué>
- **Modelo formal:** <incluido / no pedido / no incluido: motivo>
```

No pegues el Mermaid en el PR ni publiques nada por tu cuenta: ofrecé hacerlo y esperá la confirmación.

## PRs grandes

Con más de unos 40 nodos el grafo deja de leerse. Antes de llegar ahí:

- Dejá como nodos solo las piezas que el PR toca y sus vecinos directos.
- Agrupá por módulo o capa con `groups`.
- Si el PR mezcla flujos independientes, generá un modelo por flujo (`flow-graph-<flujo>.json`, cada uno en su carpeta de salida con `--out`) y decilo en el reporte.

## Herramientas

El layout lo calcula [ELK](https://github.com/kieler/elkjs) (capas, ruteo ortogonal y lugar de las etiquetas) y la página dibuja el SVG. La elección y las alternativas descartadas están en [references/rendering.md](references/rendering.md); leelo solo si vas a cambiar la plantilla o la librería.
