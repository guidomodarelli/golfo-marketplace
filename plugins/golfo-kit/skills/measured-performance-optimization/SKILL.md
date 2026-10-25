---
name: measured-performance-optimization
description: 'Mide y optimiza rendimiento web: app lenta, Core Web Vitals, bundle, renders, caching, N+1, memoria que crece o leaks, SSR lento o TTFB alto, long tasks o main thread bloqueado, event loop de Node trabado, listas o DOM grande y jobs periódicos que releen toda una ventana en cada corrida. Usar también sin pedido explícito al crear un flujo nuevo o sumarle a uno existente requests, llamadas, queries o pasos nuevos; no en refactors, fixes ni cambios de copy o estilos que no agregan carga.'
license: MIT
metadata:
  version: "1.6.0"
  author: "Guido Modarelli"
  category: "performance"
  tags: "performance, web-vitals, bundle, caching, n+1, memory-leaks, ttfb, ssr-streaming, long-tasks, loaf, virtualization, dom-size, incremental-sweep, cron, lazy-loading, chrome-devtools, playwright, sentry"
  command: "/measured-performance-optimization"
---

# Measured Performance Optimization

Optimiza una aplicación web de punta a punta (frontend, red, backend y base de datos) con una sola regla central: **toda optimización se mide antes y después**. Un cambio sin medición previa no se puede atribuir, y uno sin medición posterior puede empeorar las cosas sin que nadie lo note: optimizaciones razonables en teoría (memoizar, cachear, partir chunks) a veces suman costo o rompen el flujo.

## Cuándo usar otra skill

- Revisar un diff buscando riesgos de performance sin optimizar ni medir: `review-performance`.
- Detalle de patrones de render en React (`startTransition`, `useMemo`, `React.memo`, equality guards): `react-render-performance-patterns`. Esta skill decide *si* el render es el cuello de botella y mide; esa define *cómo* arreglarlo.
- Arquitectura de fetching SSR/BFF: `refactor-ssr-data-fetching`.
- Mismatches de hidratación: `prevent-ssr-hydration-mismatches`; qué `loading.tsx`, `error.tsx` o `<Suspense>` lleva cada ruta de Next.js App Router: `nextjs-route-ui-boundaries`. Esta skill mide TTFB, streaming e hidratación y enlaza esas reglas en lugar de repetirlas.

## Compatibilidad entre agentes

Las mediciones en navegador (pasos 3 y 6) y el recorrido del flujo (paso 5) usan el mecanismo que exista en la sesión, según la fila «Verificar en un navegador» de [`agent-capabilities.md`](../../references/agent-capabilities.md): buscá la herramienta concreta en la sesión o en `PATH`, no te guíes por el nombre del agente. Lo propio de esta skill:

- **Web Vitals de carga**: Lighthouse por terminal sirve en cualquier agente ([comando](../../references/agent-capabilities.md#verificación-en-navegador-por-terminal)); un MCP de Chrome DevTools conectado también.
- **Interacciones, renders y requests**: hace falta evaluar JavaScript con `performance` en la página: Claude in Chrome, un MCP de Playwright o DevTools, `browser_exec` de Hermes o Playwright por terminal. El plugin Chrome de Codex **no mide**: su `evaluate` no expone `performance`; usalo solo para confirmar el flujo (paso 5) y medí por terminal.
- **Memoria, long tasks y event loop**: heap snapshots y contadores de nodos y listeners necesitan CDP (MCP de DevTools o Playwright); en Node, `--inspect` o `process.memoryUsage()` desde cualquier shell. Detalle por agente en [Memoria, long tasks y event loop](references/measurement-tools.md#memoria-long-tasks-y-event-loop).
- Medí antes y después **con el mismo mecanismo y las mismas condiciones**: cambiar de herramienta entre mediciones invalida el delta.

Si no hay ningún mecanismo, aplican la detención del paso 3 y **Sin medir**. Si usaste un fallback o algo quedó sin verificar, sumá **Limitaciones del agente** al reporte.

## Invocación automática por funcionalidad nueva

Además de los pedidos explícitos de optimización, usar esta skill por iniciativa propia cuando el trabajo **agrega carga nueva** a la app: el costo de rendimiento es más barato de evitar al diseñar el flujo que de encontrar después en producción.

**Se activa** cuando el cambio crea un flujo nuevo (página, interacción, endpoint, job) o le suma a uno existente trabajo que antes no hacía, por ejemplo:

- una request o llamada nueva (API propia, servicio externo, server action, fetch en el cliente);
- una query o acceso nuevo a base de datos, sobre todo dentro de un loop o por ítem;
- un paso nuevo dentro del flujo (otro `await` en la cadena, otra pantalla de un wizard, otra validación remota);
- una dependencia de cliente pesada, una imagen grande, un script de terceros, polling o listeners nuevos.

**No se activa** ante cambios que no agregan trabajo por request, render o navegación: refactors sin cambio de comportamiento, fixes que no suman llamadas, copy, estilos, tipos, tests, docs, renombres, ni cambios que quitan carga. Criterio ante la duda: ¿después del cambio el flujo hace algo que antes no hacía (otra llamada, otra query, otro paso, más bytes)? Si no, no aplica.

En este modo la skill acompaña la implementación sin reemplazarla y se acota al costo agregado:

1. **Inventariar la carga nueva**: qué requests, queries, pasos y bytes suma el cambio y en qué flujo crítico (paso 1).
2. **Revisar las señales** de la referencia del área afectada (tabla del paso 4): N+1 por un `await` dentro de un loop, cascadas secuenciales evitables, requests duplicadas o sin cache, listados sin límite, imports pesados en el bundle inicial. Si una señal aparece mientras se diseña, elegir directamente la forma correcta (batch, `WHERE IN`, `Promise.all`, import dinámico) en lugar de implementar la versión lenta para optimizarla después.
3. **Medir el costo agregado** con las condiciones del paso 3:
   - Flujo existente: la línea base es la revisión sin la funcionalidad nueva (medirla antes de agregarla o, si ya está agregada, sobre el commit base) y se compara contra la revisión con la funcionalidad.
   - Flujo nuevo: no hay "antes"; medir el costo absoluto (requests por carga, queries por request, KB de JS agregado, latencia p95) y compararlo con un flujo análogo existente o con el presupuesto del proyecto si lo hay.
4. **Optimizar solo si hay un hallazgo**: aplicar los pasos 4 a 6 a ese hallazgo. Si el costo agregado es razonable, no tocar nada más.
5. **Reportar** con el formato del paso 7, con una fila por carga nueva medida ("Antes" = revisión sin la funcionalidad, o "— (flujo nuevo)").

Si no se puede medir, no bloquear la entrega de la funcionalidad: la detención del paso 3 aplica a pedidos de optimización. Declarar en **Sin medir** qué faltó y cómo medirlo, y dejar las optimizaciones no medidas como hipótesis en **Próximos pasos**, sin aplicarlas.

## Cobertura incremental

Obligatorio en cada ejecución, haya o no registro: seguí el [protocolo de cobertura](../../references/skill-coverage.md#protocolo-de-una-skill) con `--skill measured-performance-optimization` en cada unidad funcional del flujo medido, incluido su paso 1 cuando falta el registro o la unidad (crearlos es parte de la skill; proponer `discover` no alcanza) y el [cierre incompleto](../../references/skill-coverage.md#cierre-incompleto-o-bloqueado) cuando no se puede registrar. Nunca inventar cobertura ni evidencia. El registro evita volver a medir lo que no cambió de carga; nunca reemplaza la medición. Un endpoint, job o query sin página usa `add-unit --kind api|job|backend`.

- **Cuándo consultar.** Al empezar, `check` dice si la unidad tiene cobertura y cuál es su revisión base (`baseline.commit`, que sirve como "antes" si sigue en el historial y la medición no se registró sobre cambios sin commitear; el alcance sugerido lo aclara). En la invocación automática por funcionalidad nueva, volvé a correr `check` después de implementar: lista la carga agregada por parte (`+1 requests`, `+2 awaited steps`, paquete nuevo) y es tu inventario del paso 1.
- **Qué significa cada decisión.** `skip`: desde la última medición solo hubo cambios que no agregan carga (copy, estilos, tipos, refactors) o ninguno; no se vuelve a medir. `incremental`: medí el **flujo completo** antes y después en condiciones comparables, enfocado en la carga que lista `check`; ser incremental reduce qué investigar, no qué medir. `full`: aplicá el flujo obligatorio completo; un flujo nuevo usa `full` con su costo absoluto. Un pedido explícito de auditoría o de optimización completa usa `check --force-full`.
- **Evidencia** después de `begin`: una `measurement` por métrica de la tabla del paso 7 (`--metric`, `--before`, `--after`, `--tool`, `--conditions`; en un flujo nuevo `--baseline-kind new-flow --reference <flujo análogo o presupuesto>`) y los tests con `--exec`. Sin medición real, registrá `partial` con `--limitation` igual que en **Sin medir**: un valor estimado nunca acredita.
- Las optimizaciones descartadas o no medidas no se registran como cobertura: van a **Descartadas** y **Próximos pasos**.

## Flujo obligatorio

Seguir los pasos en orden. Si el usuario pidió solo un área (por ejemplo, "arreglá el N+1"), aplicar el mismo flujo acotado a esa área.

### 1. Definir alcance y flujo crítico

Identificar qué flujo real importa (página, interacción, endpoint, job) y qué métrica lo representa. Sin un flujo concreto, se termina optimizando código frío. Si el usuario no lo dijo, inferirlo del código y de los errores/transacciones lentas de producción, y declararlo como supuesto.

### 2. Elegir herramientas de medición

Detectar qué MCPs y herramientas hay disponibles y usar la más directa para cada área. Leer [references/measurement-tools.md](references/measurement-tools.md) para saber qué mide cada una (Chrome DevTools MCP, Playwright MCP, Sentry MCP) y sus alternativas sin MCP. Si no hay forma de medir algo, decirlo explícitamente: no inventar números ni presentar estimaciones como mediciones.

### 3. Medir la línea base

Antes de tocar el código que se va a optimizar, registrar la línea base del flujo con las mismas condiciones que se usarán después (mismo modo de build de producción y mismos flags, mismo entorno, mismo throttling de CPU/red, misma data, cache fría o caliente declarada), rebuildeando cada revisión del código antes de medirla. Repetir al menos 3 veces las mediciones ruidosas (tiempos de carga, LCP, INP) y reportar la mediana.

Única excepción: se permite agregar antes de la línea base instrumentación solo de medición que no cambie el comportamiento (por ejemplo, un `<Profiler onRender>` cuando no hay React DevTools). Esa instrumentación tiene que ser idéntica en las mediciones de antes y después, y se quita al terminar; no habilita adelantar ningún cambio de la optimización.

Si no se puede medir la línea base (sin runtime, entorno, datos o herramienta) y el usuario pidió optimizar de verdad, detenerse antes de editar código: reportar qué falta para medir y cómo conseguirlo, y no avanzar al paso 5 hasta capturarla.

### 4. Diagnosticar y priorizar

Ordenar los hallazgos por impacto medido en el flujo crítico, no por facilidad. Si no hay medición posible (el usuario pidió solo un plan o prohibió ejecutar), presentar cada hallazgo como hipótesis etiquetada explícitamente, ordenada por impacto estimado con su justificación (la señal observada en el código o en la descripción) y con la medición que la confirmaría; no inventar números. Esto no habilita editar sin línea base (paso 3) y las métricas quedan como pendientes en el reporte (paso 7). Leer solo la referencia del área que corresponda; las señales de detección viven en la sección «Detectar» de cada referencia (o en los bullets «Detectar:» de cada subsección):

| Área | Alcance | Referencia |
|---|---|---|
| Renders innecesarios | Trabajo de render y commits de componentes en el cliente | [references/unnecessary-renders.md](references/unnecessary-renders.md) |
| Bundle y lazy loading | Tamaño y división del JavaScript que se descarga y ejecuta | [references/bundle-lazy-loading.md](references/bundle-lazy-loading.md) |
| Requests y caching | Orden, cantidad y cacheo de requests entre cliente, red y servidor | [references/requests-caching.md](references/requests-caching.md) |
| Queries lentas y N+1 | Acceso a base de datos desde el backend | [references/database-queries-n-plus-one.md](references/database-queries-n-plus-one.md) |
| Imágenes, fuentes y scripts | Carga de imágenes, fuentes web y scripts de terceros | [references/images-fonts-scripts.md](references/images-fonts-scripts.md) |
| Memoria y leaks | Heap que crece al repetir un flujo, detached DOM, listeners/timers/observers sin limpiar y caches sin límite, en cliente y Node | [references/memory-leaks.md](references/memory-leaks.md) |
| SSR, TTFB y streaming | Tiempo hasta el primer byte, streaming con Suspense, tamaño del HTML/payload RSC y costo de la hidratación | [references/ssr-ttfb-streaming.md](references/ssr-ttfb-streaming.md) |
| Main thread y long tasks | Trabajo CPU sincrónico que bloquea el hilo principal del navegador o el event loop de Node | [references/main-thread-long-tasks.md](references/main-thread-long-tasks.md) |
| Listas y DOM grande | Cantidad de nodos, virtualización, layout thrashing, estilos y animaciones caras | [references/large-lists-dom.md](references/large-lists-dom.md) |
| Jobs periódicos con barrido completo | Cron o driver que relee una ventana entera en cada corrida y cuya demora crece con la ventana, no con lo nuevo | [references/incremental-sweep-jobs.md](references/incremental-sweep-jobs.md) |

### 5. Aplicar una optimización a la vez

Hacer un cambio por iteración para poder atribuir el resultado. Mantener el comportamiento: correr los tests relevantes y, si el flujo tiene UI, recorrerlo con la automatización de navegador disponible (por ejemplo, Playwright o Chrome DevTools MCP) o con el runner UI/E2E del proyecto para confirmar que sigue funcionando.

### 6. Medir después y decidir

Rebuildear la revisión modificada con el mismo modo de build y flags, y repetir exactamente la medición del paso 3. Si la mejora no es significativa (dentro del ruido) o algo empeoró, revertir o replantear el cambio en lugar de dejarlo "por las dudas". Volver al paso 4 con el siguiente hallazgo.

### 7. Reportar

Cerrar con este formato:

```markdown
## Resultado de optimización

**Flujo medido:** <página/interacción/endpoint> · **Condiciones:** <build, throttling, data, cache>

| # | Optimización | Métrica | Antes | Después | Delta | Herramienta |
|---|---|---|---|---|---|---|
| 1 | <cambio> | <LCP / INP / TTFB / KB JS / queries por request / heap retenido / p95 ms> | <valor> | <valor> | <%> | <MCP o comando> |

**Descartadas:** <cambios probados que no mejoraron y se revirtieron, con su medición>
**Sin medir:** <qué no se pudo medir y por qué>
**Próximos pasos:** <hallazgos pendientes ordenados por impacto>
**Cobertura:** <siempre: por unidad (creada en esta ejecución o existente), decisión de `check`, resultado de `record` y pendientes; si no se pudo registrar, `incompleta` con el motivo y qué falta>
**Limitaciones del agente:** <solo si faltó una herramienta: qué se usó en su lugar o qué quedó sin medir y cómo obtenerlo>
```

Los valores de "Antes" y "Después" tienen que venir de mediciones reales hechas en la sesión. Cuando el usuario pidió solo un plan o diagnóstico sin editar código, haya o no herramientas de medición, dejar la tabla con la métrica y la herramienta planeadas y "Después" como pendiente, porque no existe una revisión optimizada que medir; "Antes" puede venir de una medición real si hay herramientas y el usuario no prohibió ejecutar, y si no, queda pendiente. Si pidió una optimización real, aplica la detención del paso 3.
