# Main thread y long tasks

Cubre trabajo CPU sincrónico que bloquea el hilo principal del navegador o el event loop de Node, sin importar si lo dispara un render. Si el trabajo pesado es el render de React, priorizar actualizaciones con `startTransition` o `useDeferredValue` está en [Pattern 1](../../react-render-performance-patterns/SKILL.md#pattern-1--split-urgent-from-non-urgent-with-starttransition) de `react-render-performance-patterns`, y los commits largos en [Renders innecesarios](unnecessary-renders.md).

## Detectar

- **Long Animation Frames (LoAF)**: un `PerformanceObserver` con `{ type: 'long-animation-frame', buffered: true }` registra los frames de más de 50 ms con `duration`, `blockingDuration` y `scripts[]` (`sourceURL`, `invoker`, `duration`), que dicen qué función bloqueó. Solo existe en Chromium. Antes de observar, chequear `PerformanceObserver.supportedEntryTypes`: si incluye `longtask` pero no `long-animation-frame`, `longtask` da la duración sin atribución; si no incluye ninguno de los dos (Firefox, Safari), el observer no registra nada aunque el hilo se bloquee, así que cero entradas no significa cero long tasks: medir con el profiler de performance nativo de ese navegador.
- Performance trace de la interacción: tareas largas en *Main* dominadas por *Evaluate script* o *Function call* propias (no por *Recalculate Style* ni *Layout*, que son de [Listas y DOM grande](large-lists-dom.md)).
- Señales en el código: `JSON.parse` de respuestas grandes, `sort`/`filter`/`reduce` sobre miles de filas en cada interacción, cálculos, parseo de CSV/Markdown, compresión o criptografía en el hilo principal.
- **Node**: `perf_hooks.monitorEventLoopDelay()` con p99 alto bajo carga, latencia que sube para todas las rutas cuando una sola procesa algo pesado, profiling de CPU con `--inspect` o `--cpu-prof` dominado por una función síncrona.

## Corregir

- **Partir el trabajo** en chunks y ceder el hilo entre ellos: `await scheduler.yield()` donde exista (Chromium) y, si no, `await new Promise((resolve) => setTimeout(resolve, 0))`. Ceder también después de la actualización visible de una interacción, antes del trabajo que no la necesita.
- **Diferir lo no urgente** a `requestIdleCallback` (con fallback a `setTimeout` donde no exista) o a después de la interacción.
- **Mover el cálculo a un Web Worker** (`new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' })`) cuando es CPU puro y dura más que un frame aun partido; dibujo pesado en canvas con `OffscreenCanvas` (`transferControlToOffscreen()`). Medir también el costo de copiar datos al worker: para buffers grandes, transferirlos en vez de clonarlos.
- **Reducir el trabajo** antes de moverlo: no recalcular en cada tecla lo que no cambió, filtrar o paginar en el servidor, estructuras de búsqueda O(1) (ver [Pattern 6](../../react-render-performance-patterns/SKILL.md#pattern-6--use-o1-lookup-structures-inside-hot-paths)).
- **Node**: mover CPU pesado a `worker_threads` (o un pool como `piscina`) o a un job fuera del request; partir loops largos con `setImmediate`; preferir APIs asíncronas o en streaming a sus variantes `*Sync`.

## Métricas antes/después

- INP de la interacción y TBT de la carga, con el mismo throttling de CPU.
- Cantidad de long tasks o LoAF del flujo y su `duration`/`blockingDuration` máxima y total.
- En Node: p99 del event loop delay (`monitorEventLoopDelay`, en ms) y p95 de las rutas afectadas bajo la misma carga.
