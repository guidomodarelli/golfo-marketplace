# Memoria y leaks

Un leak no se ve en una sola carga: aparece como memoria que **sigue creciendo cada vez que se repite el mismo flujo** (abrir y cerrar un modal, navegar entre rutas, procesar requests). Medir siempre por repeticiones, nunca un valor suelto. Cómo tomar cada medición en cada agente: [Memoria, long tasks y event loop](measurement-tools.md#memoria-long-tasks-y-event-loop).

## Detectar

- **Técnica de 3 snapshots**: calentar el flujo una vez, forzar GC y tomar el snapshot 1; repetir el flujo N veces (por ejemplo, 10), forzar GC y tomar el snapshot 2; repetir otras N, forzar GC y tomar el snapshot 3. Los objetos creados entre el 1 y el 2 que siguen vivos en el 3 (vista *Summary* del snapshot 3 filtrada por «Objects allocated between Snapshot 1 and Snapshot 2») son los sospechosos; el panel *Retainers* dice quién los retiene.
- Heap usado después de GC que sube en cada tanda de N repeticiones en vez de estabilizarse. `performance.memory` (solo Chromium, cuantizado) sirve como tendencia; `performance.measureUserAgentSpecificMemory()` es más preciso pero exige `crossOriginIsolated` (COOP + COEP) y puede tardar en resolver.
- **Detached DOM**: nodos `Detached <tag>` en el snapshot (o el perfil *Detached elements* de DevTools) cuya cantidad crece con las repeticiones; casi siempre los retiene un listener, un closure o una referencia en un store.
- **Listeners, timers, subscripciones y observers sin limpiar**: el contador `JSEventListeners` de `Performance.getMetrics` que sube por repetición; `useEffect` que llama a `addEventListener`, `setInterval`, `subscribe`, `IntersectionObserver`/`ResizeObserver`/`MutationObserver` o un WebSocket sin devolver cleanup.
- **Closures que retienen datos grandes**: callbacks guardados (handlers, timers, caches de funciones) que capturan respuestas enteras, buffers o árboles de componentes desmontados.
- **Caches sin límite**: `Map`/objeto a nivel de módulo que agrega una entrada por request, usuario o query y nunca expulsa; en el cliente, stores o caches de datos sin `gcTime`/límite.
- **Node**: `heapUsed` o RSS de `process.memoryUsage()` que crece con carga constante y no baja al cortarla; `MaxListenersExceededWarning` en los logs; heap snapshots del proceso (`--inspect` o `v8.writeHeapSnapshot()`) comparados con la misma técnica de 3 snapshots.

## Corregir

- Todo efecto que registra algo devuelve su cleanup: `removeEventListener` (o un `AbortController` pasado como `{ signal }` a varios listeners y abortado al desmontar), `clearInterval`/`clearTimeout`, `unsubscribe()`, `observer.disconnect()`, `socket.close()`. Los detalles de efectos asíncronos y cancelación de requests viven en `react-data-fetching-best-practices`.
- Cortar la referencia que retiene el nodo o el dato: no guardar elementos del DOM ni respuestas completas en variables de módulo, stores o closures de larga vida; guardar solo los campos o ids que se usan.
- Caches con límite y expulsión: LRU con tamaño máximo y TTL (`lru-cache` en Node, `gcTime` en TanStack Query); `WeakMap`/`WeakRef` cuando la clave es un objeto cuyo ciclo de vida manda otro. Una cache por request vive en el contexto de esa request, no en el módulo.
- En Node, emisores con un listener por request: registrar una vez o usar `once`, y quitar los listeners al terminar la request.

## Métricas antes/después

Medir con el mismo flujo, la misma N y GC forzado antes de cada lectura:

- Heap retenido tras N repeticiones del flujo (delta entre snapshot 1 y snapshot 3, o `JSHeapUsedSize` de `Performance.getMetrics`).
- Cantidad de detached nodes y de listeners activos (`JSEventListeners`) después de las N repeticiones.
- En Node: `heapUsed` y RSS después de N requests o corridas y tras un período sin carga.
