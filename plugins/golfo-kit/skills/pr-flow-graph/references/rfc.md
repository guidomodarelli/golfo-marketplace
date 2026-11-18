# Graficar un RFC

Un RFC (o design doc) propone un cambio que todavía no está en el código. El grafo es el mismo que el de un PR: piezas, relaciones y flujo de negocio, con «Hoy» y «Con el RFC» en lugar de «Antes» y «Después». Lo que cambia es la prueba: no hay diff, así que lo que el RFC propone se prueba con la línea del RFC que lo dice, y lo que existe hoy, con su línea en el código.

Este archivo reemplaza los pasos 1 y 3 de `SKILL.md`. El contrato del modelo está en [flow-graph-schema.md](flow-graph-schema.md), sección «Modelo de un RFC», y un modelo completo y válido en [../assets/example-rfc-flow-graph.json](../assets/example-rfc-flow-graph.json), hecho sobre [../assets/example-rfc.md](../assets/example-rfc.md).

## 1. Conseguir el texto del RFC

El script lee el RFC como archivo, y cada línea que citás como evidencia es una línea de ese archivo. Por eso el texto tiene que estar en disco, tal como está escrito:

- **Ya está en el repo** (`docs/rfcs/…`, aunque no esté commiteado): usá esa ruta.
- **Es una URL o vino pegado en el pedido**: traé el texto con las herramientas que tengas (para una página privada, las del servicio donde vive) y guardalo sin reformatear en `pr-flow-graph/rfc.md`. Conservá los encabezados `##`: el script los usa como secciones.
- **No podés leerlo** (la URL pide permisos que no tenés, o el pedido solo dice «el RFC de pagos»): decilo en una línea y pedí el texto o la ruta. Un RFC reconstruido de memoria daría un grafo que nadie puede comprobar.

## 2. Elegir el código de partida

`rfc.codeRef` es la ref del código que el RFC propone cambiar, casi siempre la branch por defecto (`main`). Hacé `git fetch` antes: el script lee el código en esa ref, no en el working tree, para que una branch local a medio hacer no se cuele como «lo que existe hoy».

## 3. Leer el cambio

- Leé el RFC entero y anotá sus secciones `##`: al final, cada una tiene que quedar en el grafo o en `outOfScope`.
- Buscá en el código cada pieza que el RFC nombra (`git grep` en `codeRef`) y leela entera. Seguí cada una **un salto** hacia afuera, igual que en un PR.
- Separá tres grupos: lo que el RFC agrega (no existe todavía), lo que modifica o elimina (existe hoy y el RFC lo cambia), y lo que solo usa sin cambiarlo.

Si el RFC da por existente algo que el código no tiene, o describe el código de hoy distinto de como es, no lo acomodes en el modelo: graficá lo que muestra el código y contalo en una de las dos líneas que podés agregar al reporte (paso 6 de `SKILL.md`). Es justo lo que quien revisa el RFC necesita saber.

## 4. Escribir el modelo

Mismo archivo y mismas reglas que en un PR (`pr-flow-graph/flow-graph.json`, paso 3 de `SKILL.md`), con `rfc` en lugar de `pullRequest` y esta evidencia:

| El elemento | Evidencia que lleva |
|---|---|
| `added` | Solo líneas del RFC (`{ "side": "rfc", "line": N }`). No existe en el código, así que no lleva ninguna línea de código. |
| `modified` o `removed` | La línea del código donde está hoy **y** la línea del RFC que propone el cambio. |
| `unchanged` | La línea del código, si querés que se pueda abrir. Puede sumar la línea del RFC que lo menciona. |
| Relación `verified` que ya existe | La línea de código que la escribe, igual que en un PR. |
| Relación `verified` que el RFC agrega | Una línea del RFC que nombre a **los dos** extremos como los llama el código (o su `symbol`). Si el RFC la describe con otras palabras, o la deducís, es `inferred` con `reason`. |

`change` significa lo que propone el RFC: `added` es una pieza nueva, `modified` una que cambia, `removed` una que desaparece.

En `outOfScope` van secciones del RFC, no archivos: `{ "section": "Alternativas descartadas", "reason": "Opción que el RFC no adopta." }`. Las secciones típicas que quedan fuera son alternativas, riesgos, plan de rollout o preguntas abiertas, cuando no cambian el flujo. Una sección cuenta como «en el grafo» si alguna línea suya es evidencia de un elemento.

## 5. Errores propios del RFC

Los errores comunes con un PR están en la tabla del paso 4 de `SKILL.md`; estos son los del RFC:

| El error dice | Qué hacer |
|---|---|
| `none of its evidence is a line of the RFC` | Sumá `{ "side": "rfc", "line": N }` con la línea que propone ese cambio, o marcalo `unchanged` si el RFC no lo cambia. |
| `does not exist in the code yet` | Lo marcaste `added` y le pusiste una línea de código: si la pieza ya existe es `modified` o `unchanged`; si no existe, sacá esa línea. |
| `so it exists today: add the line of code` | Algo `modified` o `removed` existe hoy: agregá dónde está en el código. |
| `does not exist in <codeRef>` | La ruta no existe en el código de partida. Si es algo que el RFC agrega, su evidencia va solo al RFC. |
| `is blank` o `past the end of the document` | Copiá el número de la línea del RFC tal como está en el archivo guardado. |
| `no RFC line of it names both ends` | Apuntá a la línea del RFC que describe esa relación, poné `symbol` en el nodo si el RFC lo llama distinto, o marcala `inferred` con `reason`. |
| `section(s) that the model does not account for` | Apuntá un elemento a una línea de esa sección, o declarala en `outOfScope` con su título exacto y el motivo. |

## 6. Reportar

Igual que en un PR: pegá `pr-flow-graph-report.md` tal cual. El Mermaid queda listo para pegarlo en el RFC; ofrecé hacerlo y esperá la confirmación.
