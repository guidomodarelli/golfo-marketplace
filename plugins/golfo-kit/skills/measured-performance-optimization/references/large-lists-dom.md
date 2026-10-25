# Listas y DOM grande

Cubre el costo del navegador para mantener, recalcular y pintar el DOM: muchos nodos, layouts forzados y animaciones caras. Si lo caro es que React vuelve a renderizar la lista, ver [Renders innecesarios](unnecessary-renders.md); si es cálculo JavaScript, [Main thread y long tasks](main-thread-long-tasks.md).

## Detectar

- **DOM grande**: `document.querySelectorAll('*').length` por `evaluate` o el contador `Nodes` de `Performance.getMetrics`; Lighthouse avisa cuando el DOM es excesivo. Las listas, tablas o grids que renderizan todas las filas (cientos o miles) aunque se vean veinte son la causa más común.
- **Recalculate Style y Layout largos** en el performance trace durante el scroll o la interacción; con *Enable CSS selector stats* activado, el trace muestra qué selectores cuestan más (selectores universales o descendentes profundos, `:has()` amplio).
- **Layout thrashing**: el trace marca *Forced reflow*; en el código, loops que alternan escrituras de estilo y lecturas de layout (`offsetHeight`, `getBoundingClientRect()`, `scrollTop`) en cada iteración.
- **Animaciones que no usan `transform`/`opacity`**: animar `top`, `left`, `width`, `height` o `margin` dispara layout en cada frame; frames perdidos o *Layout* en cada frame del trace.

## Corregir

- **Virtualizar** listas y tablas largas para renderizar solo las filas visibles más un margen (`@tanstack/react-virtual`, `react-window`, o la virtualización del componente de grid). Conservar la accesibilidad: `aria-rowcount`/`aria-rowindex` en grids y búsqueda dentro de la página si el usuario la necesita.
- **`content-visibility: auto`** con `contain-intrinsic-size` en secciones largas fuera de pantalla cuando virtualizar es demasiado; `contain: layout paint` (o `strict`) en widgets cuyo contenido no afecta al resto.
- **Agrupar lecturas y escrituras** de layout: leer todo primero, escribir después, o escribir dentro de `requestAnimationFrame`; usar `ResizeObserver`/`IntersectionObserver` en lugar de medir en cada scroll.
- **Animar con `transform` y `opacity`** (compositor) y reservar `will-change` para el elemento que efectivamente anima.
- Simplificar selectores caros y paginar o cargar progresivamente lo que no necesita estar en el DOM desde el inicio.

## Métricas antes/después

- Cantidad de nodos DOM de la vista con el mismo dataset.
- Duración total de *Recalculate Style* y *Layout* en el trace de la misma interacción o scroll.
- INP solo de la interacción elegible (click, tap o teclado; por ejemplo, seleccionar una fila), o la duración de su long task / LoAF. El scroll no tiene INP: INP excluye el scroll, así que su mejora se mide con frame timing, frames perdidos y las métricas del trace de esta lista.
- Frames perdidos durante el scroll o la animación (frames del trace o LoAF por segundo).
