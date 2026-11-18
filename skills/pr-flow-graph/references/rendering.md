# Render del grafo

Leé esto solo para cambiar `assets/flow-graph-template.html`, la librería o los renderers de `scripts/lib/`.

## Decisión

El layout lo calcula **ELK** (`elkjs`, versión fijada en `BROWSER_LIBRARIES` de `scripts/lib/flow-graph-constants.mjs`) y la página dibuja el SVG con código propio.

El problema difícil de este grafo es acomodarlo: es dirigido, tiene ciclos (la vista despacha y vuelve a observar), tiene grupos y necesita etiquetas en las flechas. ELK resuelve las cuatro cosas en un solo cálculo: capas, grupos anidados, ruteo ortogonal que esquiva nodos y lugar reservado para cada etiqueta.

## Alternativas evaluadas (noviembre de 2026)

| Opción | Por qué no |
|---|---|
| Cytoscape.js + `cytoscape-elk` | Se probó primero. El adaptador toma de ELK solo las posiciones de los nodos; Cytoscape dibuja las aristas rectas, que cruzan por encima de otros nodos y tapan etiquetas. |
| Mermaid | Se usa como segunda salida porque GitHub lo dibuja en la descripción del PR. No permite filtros, vista antes/después ni panel de evidencia. |
| React Flow (`@xyflow/react`) | Requiere React y un build; no sirve para un HTML de un solo archivo. Está pensado para editores de diagramas. |
| D3 | Da primitivas, no layout por capas con grupos; habría que escribirlo. |
| Dagre | Layout por capas más liviano, con soporte pobre de grupos y sin lugar para etiquetas de aristas con ruteo ortogonal. |
| Sigma.js, vis-network, G6 | Orientadas a redes grandes con layouts de fuerzas, no a flujos por capas. |

## Límites conocidos

- `elk.bundled.js` pesa alrededor de 1,6 MB. La página lo carga desde el CDN; `--inline-libraries` lo embebe para abrir el archivo sin red.
- `elkjs` se distribuye bajo EPL-2.0. El repositorio no lo incluye: se descarga al generar o al abrir la página.
- El layout corre en el hilo principal. Con el tamaño de grafo que la skill recomienda (hasta unos 40 nodos) tarda milisegundos.
- Los nodos se dibujan como rectángulos con el tipo escrito arriba del nombre, sin una forma por tipo: ELK reserva un rectángulo por nodo y el texto del tipo se lee mejor que una leyenda de formas.

## Diseño de la página

El carácter es papel cálido y tinta, con una sola «corriente» verde azulada que marca lo que fluye y lo que está elegido. Los tokens están al principio de la hoja de estilos de la plantilla; los componentes solo usan tokens.

- **Cada cambio se lee sin color.** Agregado, modificado y eliminado llevan su glifo (`+`, `~`, `−`) en el nodo, en la lista y en la leyenda, además del color. Lo eliminado va punteado y tachado.
- **Piezas y estados se distinguen por forma.** Una pieza de código es una tarjeta con un borde de color; un estado de negocio, una píldora con un punto.
- **El movimiento explica.** Unas cuentas recorren cada relación agregada o modificada en el sentido en que viaja el dato; una relación eliminada no fluye. Al elegir un elemento, lo que no lo toca se atenúa. «Recorrer» sigue las relaciones en el orden del modelo y termina en la última, sin repetirse.
- **Lo que el lector mueve con la mano es instantáneo.** Rueda, arrastre y pinch no se animan; «Ajustar», el zoom por botón o teclado y traer un elemento a la vista se deslizan 240 ms.
- **Con movimiento reducido** no hay cuentas ni deslizamientos y nada queda en bucle; la información es la misma.
- **La verificación está a la vista.** El encabezado dice si el grafo se comprobó contra el código, y el panel lista cada comprobación con su resultado. Un grafo sin comprobar lo dice aunque los filtros estén plegados.
- **Un control que no haría nada no se muestra.** «Ocultar lo que el PR no tocó» dice cuántos elementos oculta y desaparece cuando son cero.

## Pantallas chicas

Por debajo de 52rem de ancho la página cambia tres cosas, para que el canvas ocupe la pantalla:

- El panel de detalle pasa a ser un cajón lateral, cerrado al abrir. Lo abren el botón «Detalle» o tocar un elemento, y lo cierran «Cerrar», el fondo o Escape.
- El momento (antes/después), «ocultar lo que el PR no tocó», la leyenda y el subtítulo se pliegan bajo «Filtros».
- El flujo se acomoda de arriba hacia abajo y abre a un tamaño legible sobre el inicio del flujo, en vez de achicar todo para que entre. «Ajustar» muestra el grafo entero.

En pantallas anchas el panel arranca abierto y «Detalle» lo pliega para darle todo el ancho al canvas.

La selección se resuelve en el evento `click`, no en `pointerup`: en táctil el navegador envía el `click` después de levantar el dedo, y si el cajón ya se hubiera abierto ese `click` caería sobre lo que quedó debajo.

## Verificación

`pnpm run test:pr-flow-graph` cubre el validador, las comprobaciones contra un repo git real, Mermaid, el HTML, el reporte y la compuerta de Lean, y abre la página en Chromium con Playwright para comprobar que el grafo se dibuja, que los filtros cambian lo visible, que la selección muestra la evidencia, que el recorrido avanza y que con movimiento reducido nada queda en bucle.

Los tests del navegador corren con movimiento reducido salvo el que prueba el movimiento: leen posiciones justo después de cada acción y un deslizamiento las haría depender del tiempo.
