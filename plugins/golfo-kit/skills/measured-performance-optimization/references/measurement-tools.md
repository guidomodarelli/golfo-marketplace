# Herramientas de medición

Usar la herramienta que mida la métrica del flujo crítico con menos fricción. Verificar qué MCPs están conectados en la sesión antes de planificar; si uno no está, usar la alternativa y decirlo en el reporte.

## Chrome DevTools MCP — laboratorio de frontend

Sirve para medir carga e interacción en un browser real:

- **Performance trace** con throttling de CPU y red: LCP, CLS, INP/TBT, long tasks y qué script o render las causa, duración de *Recalculate Style* y *Layout*, reflows forzados y TTFB del documento.
- **Network**: tamaño transferido y descomprimido, prioridad de recursos, y el timing y los headers de cada request para aplicar los criterios de [Requests y caching → Detectar](requests-caching.md#detectar).
- **Coverage** (si está disponible): JS y CSS que se descarga pero no se ejecuta en la ruta.
- **Console**: warnings de hydration, errores y logs de timing.

Las condiciones de medición y la cantidad de repeticiones las define el [paso 3 del flujo](../SKILL.md#3-medir-la-línea-base); en DevTools se traducen en el throttling de CPU y red y en el estado de la cache (por ejemplo, CPU 4x y red "Fast 4G", cache deshabilitada para carga fría).

## Playwright MCP — flujos reales y regresiones

Sirve para recorrer el flujo como lo haría un usuario y repetirlo de forma idéntica:

- Navegar, tipear, filtrar, paginar y medir tiempos. Para interacciones del cliente (filtrar, paginar, abrir un panel) usar `performance.now()`, `performance.mark()`/`performance.measure()` o un `PerformanceObserver` del tipo de entrada que corresponda (`event`, `resource`, `longtask`). `page.evaluate(() => performance.getEntriesByType('navigation'))` sirve solo para la carga del documento: no mide interacciones posteriores.
- Contar requests del flujo escuchando eventos de red, para aplicar los criterios de [Requests y caching → Detectar](requests-caching.md#detectar).
- Confirmar que la optimización no rompió el flujo (el paso 5 del flujo principal).

## Sentry MCP — producción

Sirve para encontrar qué vale la pena optimizar y confirmar el efecto con usuarios reales:

- Transacciones más lentas por p75/p95 y su desglose de spans.
- Issues de performance (N+1 queries, consultas lentas, render-blocking, assets grandes) que Sentry detecta automáticamente.
- Web Vitals de campo por página.
- Después del deploy, comparar el mismo período/tráfico antes y después.

Los datos de producción complementan al laboratorio: el laboratorio atribuye un cambio, producción confirma que importa.

## Memoria, long tasks y event loop

Estas mediciones necesitan más que leer `performance`: heap snapshots, GC forzado y contadores del navegador salen del protocolo de DevTools (CDP). Elegir el mecanismo con la fila «Verificar en un navegador» de [`agent-capabilities.md`](../../../references/agent-capabilities.md) y usar el mismo en antes y después:

- **Heap y detached DOM en el navegador**: si el MCP de Chrome DevTools de la sesión expone una herramienta de heap snapshot (buscala por nombre y leé su schema), usarla con la [técnica de 3 snapshots](memory-leaks.md#detectar). Si no, Playwright (MCP o por terminal) con `const cdp = await context.newCDPSession(page)`: `HeapProfiler.collectGarbage` antes de cada lectura, `Performance.enable` + `Performance.getMetrics` para `JSHeapUsedSize`, `Nodes` y `JSEventListeners`, y `HeapProfiler.takeHeapSnapshot` para guardar el `.heapsnapshot` y abrirlo en DevTools. `performance.memory` por `evaluate` solo da una tendencia aproximada (Chromium, sin GC forzado).
- **Long tasks y LoAF**: por `evaluate`, registrar antes de la interacción un `PerformanceObserver` de `long-animation-frame` (y `longtask` como respaldo) que acumule las entradas en `window`, disparar la interacción y leerlas después; o tomar un performance trace. Claude in Chrome, los MCP de DevTools o Playwright, `browser_exec` y Playwright por terminal sirven; el plugin Chrome de Codex no, porque su `evaluate` no expone `performance` ni `PerformanceObserver`.
- **Node (memoria y event loop)**: cualquier agente con shell. Arrancar el proceso del proyecto con `--inspect` (cómo prepararlo y adjuntar el debugger sin alterar el arranque real: [`node-runtime-debugging`](../../node-runtime-debugging/SKILL.md#flujo)) y tomar heap snapshots o perfiles de CPU desde DevTools (`chrome://inspect`); sin debugger, `v8.writeHeapSnapshot()`, `process.memoryUsage()` y `--expose-gc` + `global.gc()` antes de cada lectura, o `perf_hooks.monitorEventLoopDelay()` leyendo `percentile(99)` (en nanosegundos) durante la misma carga. Esa instrumentación es solo de medición: idéntica antes y después y se quita al terminar ([paso 3](../SKILL.md#3-medir-la-línea-base)).

Los heap snapshots pueden contener datos de usuarios, tokens o respuestas completas: guardarlos fuera del repo, no adjuntarlos al reporte ni a un PR y borrarlos al terminar.

## Alternativas sin MCP

| Necesidad | Alternativa |
|---|---|
| Web Vitals de laboratorio | `npx lighthouse <url> --output=json`, con las repeticiones y la agregación del [paso 3 del flujo](../SKILL.md#3-medir-la-línea-base). Comando completo y flags verificados en [Verificación en navegador por terminal](../../../references/agent-capabilities.md#verificación-en-navegador-por-terminal) |
| Interacciones y recorrido del flujo sin MCP | Playwright por terminal con el Chrome instalado (misma sección): `performance.mark()`/`measure()` y `PerformanceObserver` dentro de `page.evaluate` |
| Tamaño de bundle | Output del build del framework, `source-map-explorer`, `@next/bundle-analyzer`, `rollup-plugin-visualizer`, `webpack-bundle-analyzer` |
| Renders | Ver [Renders innecesarios → Detectar](unnecessary-renders.md#detectar) |
| Queries | Ver [Queries lentas y N+1 → Detectar](database-queries-n-plus-one.md#detectar), [Queries lentas que no son N+1](database-queries-n-plus-one.md#queries-lentas-que-no-son-n1) y [Métricas antes/después](database-queries-n-plus-one.md#métricas-antesdespués) |
| Tiempos de endpoint | `autocannon`, `k6`, `hey`, o `curl -w '%{time_total}'` repetido |
| TTFB, streaming y tamaño del HTML | `curl -s -o /dev/null -w '%{time_starttransfer} %{size_download}' <url>` repetido (con `--compressed` para el tamaño comprimido) y `curl -N` para ver si los chunks llegan progresivamente; ver [SSR, TTFB y streaming](ssr-ttfb-streaming.md#detectar) |
| Memoria, nodos DOM y listeners | Playwright por terminal con una sesión CDP; ver [Memoria, long tasks y event loop](#memoria-long-tasks-y-event-loop) |
| Long tasks y LoAF | `PerformanceObserver` dentro de `page.evaluate` con Playwright por terminal; ver la misma sección |

`autocannon`, `k6` y `hey` generan tráfico concurrente: usarlos solo contra entornos locales o de staging. Contra producción, únicamente con autorización explícita del usuario y límites acotados (target exacto, concurrencia o VUs, y duración); sin esa autorización, medir producción solo con datos pasivos (Sentry) o requests individuales con `curl`.
