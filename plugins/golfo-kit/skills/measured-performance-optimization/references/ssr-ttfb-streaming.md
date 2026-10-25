# SSR, TTFB y streaming

Esta referencia mide cuánto tarda el servidor en mandar el primer byte y la página útil, y cuánto cuesta hidratarla. No redefine reglas de otras skills:

- Dónde y cómo se pide cada dato en server o BFF (orden, loopback, DTOs): [«Reglas SSR-first»](../../refactor-ssr-data-fetching/SKILL.md#reglas-ssr-first) de `refactor-ssr-data-fetching`.
- Qué `loading.tsx` o `<Suspense>` lleva cada segmento de Next.js App Router: [loading.tsx](../../nextjs-route-ui-boundaries/references/decision-rules.md#loadingtsx) y [Suspense granular](../../nextjs-route-ui-boundaries/references/decision-rules.md#suspense-granular) de `nextjs-route-ui-boundaries`.
- Diferencias entre el HTML del server y el primer render del cliente: `prevent-ssr-hydration-mismatches`.

## Detectar

- **TTFB alto con awaits seriales**: el handler, loader o Server Component espera varias llamadas independientes una tras otra antes de devolver nada. Confirmarlo con spans de Sentry, un header `Server-Timing` temporal por fase o `curl -w '%{time_starttransfer}'` repetido.
- **Sin streaming**: todo el HTML llega de una vez al final aunque haya partes lentas y otras listas. `curl -N` muestra si los chunks llegan progresivamente. Causas frecuentes: no hay boundaries de Suspense alrededor de lo lento, SSR propio que responde en `onAllReady` en lugar de `onShellReady` (`renderToPipeableStream`), o un proxy/compresión que bufferea la respuesta (por ejemplo `proxy_buffering` de nginx).
- **Payload grande**: HTML de cientos de KB, payload RSC (`self.__next_f.push(...)`) o props serializadas (`__NEXT_DATA__`, estado precargado) con listas completas o campos que la UI no usa. Qué datos nunca se serializan: [«Serialize only browser-safe data»](../../prevent-ssr-hydration-mismatches/SKILL.md#serialize-only-browser-safe-data).
- **Hidratación cara**: long tasks largas justo después de FCP atribuidas a la hidratación de React, mucho JS de componentes cliente para contenido estático, TBT alto con LCP aceptable.

## Corregir

- Arrancar en paralelo las llamadas independientes (`Promise.all`, o iniciar las promesas antes del primer `await`) y no esperar en el server lo que no forma parte del primer viewport.
- Partir la página en un shell rápido más regiones lentas dentro de `<Suspense>` para que se envíen por streaming; en SSR propio, empezar a enviar en `onShellReady`. Verificar que ningún proxy o middleware bufferee la respuesta.
- Reducir lo serializado: proyectar solo los campos que la UI renderiza, paginar listas y no pasar a componentes cliente objetos enteros cuando alcanzan unos pocos campos.
- Reducir lo que se hidrata: mantener en server el contenido estático y bajar a cliente solo la hoja interactiva (ver [server-client-split.md](../../nextjs-route-ui-boundaries/references/server-client-split.md#patrones-de-composición)); diferir widgets que no están en el primer viewport con [lazy loading](bundle-lazy-loading.md#corregir).

## Métricas antes/después

- TTFB (mediana de varias corridas con `curl` o `responseStart` de la entrada `navigation`), FCP y LCP con el mismo throttling.
- Tamaño del HTML y del payload RSC o de las props serializadas (comprimido y sin comprimir).
- Costo de hidratación: TBT y cantidad y duración de long tasks durante la carga.
