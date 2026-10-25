# Requests y caching

## Detectar

- Waterfalls: requests que dependen uno del otro sin necesidad (A termina → recién arranca B) en el panel Network o en los spans de Sentry.
- Requests duplicados del mismo recurso en un mismo flujo (varios componentes pidiendo lo mismo, refetch al montar, StrictMode sin dedupe).
- Respuestas sin `Cache-Control`, `ETag` o `Last-Modified`, o assets con hash sin cache inmutable.
- Payloads más grandes de lo que la UI usa (campos sin usar, listas sin paginar), o respuestas sin compresión.
- Polling o refetch demasiado frecuente.

## Corregir

- Paralelizar requests independientes (`Promise.all`) o moverlos al server/BFF para resolverlos en una sola respuesta (ver `refactor-ssr-data-fetching`).
- Deduplicar con la capa de datos que **ya** usa el proyecto: detectarla antes de proponer nada (dependencias en `package.json`, hooks o clients existentes como `useQuery`, `useSWR`, un store o un service con caché propia) y deduplicar con esa. Si no hay ninguna, usar primero la caché del framework: en Next.js, `fetch` con `next: { revalidate, tags }` (o `'use cache'` con `cacheLife`/`cacheTag` cuando el proyecto tiene `cacheComponents`) y `React.cache()` para lecturas server dentro de un request (ver `refactor-ssr-data-fetching` → [server-cache-and-concurrency.md](../../refactor-ssr-data-fetching/references/server-cache-and-concurrency.md)). Sumar una librería nueva solo si el problema medido lo justifica (por ejemplo, mucho estado de servidor compartido entre pantallas con refetch y mutations), y registrarlo como decisión en el reporte con el motivo, nunca como default. Configurar la frescura acorde a qué tan seguido cambia el dato (ver `react-data-fetching-best-practices`): en TanStack Query, `staleTime`; en SWR, que no tiene `staleTime`, `dedupingInterval`, `revalidateIfStale` y `revalidateOnFocus` (ver https://swr.vercel.app/docs/api).
- Headers HTTP: `Cache-Control: public, max-age=31536000, immutable` para assets con hash; `max-age` corto + `stale-while-revalidate` o `ETag` para datos que cambian; `Cache-Control: private, max-age=<corto>` para respuestas personalizadas que pueden quedar solo en la cache del navegador del usuario (`private` impide caches compartidas, pero el navegador igual puede guardarlas); `Cache-Control: no-store` para credenciales, tokens o datos sensibles que no deben persistir en ninguna cache, incluida la del navegador (RFC 9111 §5.2.2.5 y §5.2.2.7).
- Cache en servidor (memoria, Redis, CDN) para lecturas caras y repetidas, con invalidación explícita. Una cache sin estrategia de invalidación es un bug de datos viejos pendiente.
- Reducir payload: paginación, proyección de campos, compresión (`br`/`gzip`).
- Cancelar requests obsoletos (ver `react-data-fetching-best-practices`).

## Métricas antes/después

- Cantidad de requests del flujo y cuántos son duplicados.
- Tiempo total del flujo hasta datos listos (camino crítico del waterfall).
- KB transferidos y tasa de hits de cache (`304`, `Age`, `x-cache`).
- p95 del endpoint en Sentry o en un test de carga.
