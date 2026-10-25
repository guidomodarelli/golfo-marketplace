# Caché server, estado de módulo y orden de await

Fuente de varios patrones: reglas `server-*` y `async-*` de vercel-labs/agent-skills `react-best-practices` (MIT, Vercel), redactadas para esta skill.

## Contenido

- Estado de módulo (regla de correctitud)
- Deduplicación dentro de un request
- Caché entre requests
- I/O estático a nivel de módulo
- Orden de await en route handlers BFF
- Señales de problema

Las secciones de caché y de orden de await son patrones de performance: aplicarlos cuando hay un costo observado (lectura repetida, TTFB alto, waterfall visible en trace). Medir y elegir capa de caché según `measured-performance-optimization` → [requests-caching.md](../../measured-performance-optimization/references/requests-caching.md) y [ssr-ttfb-streaming.md](../../measured-performance-optimization/references/ssr-ttfb-streaming.md). La sección de estado de módulo es regla: aplica siempre.

## Estado de módulo

Scope de módulo en server equivale a memoria compartida por todo el proceso. Renders SSR, Server Components, route handlers y Server Actions corren concurrentemente en ese proceso. Escribir dato de request en variable de módulo y leerlo después permite que request B pise valor de request A antes de que A termine: usuario A recibe datos de B.

```ts
// Incorrecto: identidad compartida entre requests concurrentes.
let activeTenant: Tenant | undefined;
export async function loadDashboard(req) {
  activeTenant = await resolveTenant(req);
  return buildDashboard(); // lee activeTenant después de un await
}

// Correcto: dato de request viaja por argumentos o contexto por request.
export async function loadDashboard(req) {
  const tenant = await resolveTenant(req);
  return buildDashboard(tenant);
}
```

Permitido a nivel de módulo:

- config o asset estático, igual para todos los requests (ver "I/O estático");
- caché diseñada para reuso entre requests, con key que incluye todo lo que hace variar el resultado;
- singletons de proceso (clients HTTP, pools) sin datos mutables de usuario o request.

Para contexto implícito por request usar mecanismo del framework (`res.locals`, `AsyncLocalStorage`, `React.cache()`), nunca `let` global.

## Deduplicación dentro de un request

Si un mismo request resuelve identidad, permisos o una lectura de DB desde varios puntos del árbol (layout, page, componentes server), envolver la función con `React.cache()` para ejecutarla una vez por request.

```ts
import { cache } from 'react';

export const getRequestIdentity = cache(async () => {
  const session = await readSession();
  return session ? loadIdentity(session.userId) : null;
});

export const getFacility = cache(async (facilityId: string) => loadFacility(facilityId));
```

- La key compara argumentos por referencia: pasar primitivos (`getFacility(id)`), no objetos inline (`getFacility({ id })` nunca acierta).
- Vive solo durante el request: no sirve como caché entre usuarios ni reemplaza autorización.
- En Next.js, `fetch` ya se memoiza por request; `React.cache()` cubre DB, auth, filesystem y cómputo.
- Fuera de React Server Components (Express, loaders propios) usar el equivalente por request del stack (`res.locals`, memo en el service instanciado con `req`).

## Caché entre requests

Caché LRU en memoria de proceso (o Redis cuando cada invocación corre aislada) evita repetir lectura cuando requests sucesivos piden mismo dato en segundos. Usarla solo si:

- dato no está personalizado ni depende de permisos (catálogos, config pública, tablas de referencia), o la key incluye identidad/tenant y la política de seguridad lo acepta explícitamente;
- existe invalidación: TTL acotado más invalidación por evento cuando una mutation cambia el dato;
- hay `max` de entradas para acotar memoria.

```ts
const facilityCatalogCache = new LRUCache<string, FacilityCatalog>({
  max: FACILITY_CATALOG_CACHE_MAX_ENTRIES,
  ttl: FACILITY_CATALOG_CACHE_TTL_MS,
});
```

Antes de sumar librería, revisar si proyecto ya tiene capa de caché (framework, CDN, Redis): criterio en [requests-caching.md](../../measured-performance-optimization/references/requests-caching.md).

## I/O estático a nivel de módulo

Font, logo, template o config que no cambia en runtime y es igual para todos los requests se carga una vez al importar módulo, no en cada request. Guardar la promesa y awaitearla en handler.

```ts
const emailTemplatePromise = readFile(EMAIL_TEMPLATE_PATH, 'utf-8');

export async function sendReceipt(order) {
  const template = await emailTemplatePromise;
  return render(template, toReceiptDTO(order));
}
```

Es caso distinto del estado por request: valor inmutable y compartible. No aplicar a archivos que cambian en runtime (usar caché con TTL), a datos por usuario, a secretos que no deben quedar en memoria ni a archivos grandes que inflan memoria del proceso.

## Orden de await en route handlers BFF

Seguridad primero: authentication, schema validation, authorization y ownership siguen ocurriendo antes de cualquier lectura de datos protegidos y antes de cualquier mutation. Paralelizar solo lo que es independiente de esa decisión.

1. **Arrancar temprano, awaitear tarde.** Iniciar promesas independientes (sesión, config pública, catálogo) apenas se conocen sus inputs y awaitear cuando se usan.
2. **Encadenar dependencias parciales** con `.then` en vez de esperar todo el grupo anterior.
3. **No awaitear en ramas descartadas.** Si una rama hace early return (input inválido, recurso inexistente, flag apagado), resolverla antes de esperar trabajo que esa rama no usa.
4. **Condición barata primero.** Evaluar guard sincrónico (props, query validada, estado ya cargado) antes de awaitear flag o valor remoto que se combina con él, salvo que el orden de side effects importe.

```ts
export async function GET(request: Request) {
  const query = parseItemsQuery(request);          // sync: falla antes de cualquier I/O
  if (!query.success) return badRequest(query.error);

  const identityPromise = requireAuthenticatedIdentity(request);
  const publicConfigPromise = loadPublicFeatureConfig(); // no depende de identidad
  const identity = await identityPromise;
  await requireEntityOwnership(identity, query.data.facilityId);

  const itemsPromise = new FeatureService(identity).searchItems(query.data);
  const [publicConfig, items] = await Promise.all([publicConfigPromise, itemsPromise]);
  return Response.json(toBrowserSafeDTO({ publicConfig, items }));
}
```

Nunca iniciar lectura de datos del usuario o mutation antes de autorizar para "ganar tiempo": abre carrera donde trabajo no autorizado ya ocurrió cuando falla el check. Si una promesa arrancada temprano puede quedar sin awaitear por early return, capturar su rechazo (`promise.catch(...)`) para no generar unhandled rejection.

Mismo criterio aplica a Server Actions y loaders SSR. Para paralelizar por composición de Server Components en App Router, ver `nextjs-route-ui-boundaries` → [server-client-split.md](../../nextjs-route-ui-boundaries/references/server-client-split.md).

## Señales de problema

- `let currentUser`, `let tenant` o objeto mutable de módulo asignado dentro de handler, loader o componente server.
- Caché de módulo con key que omite usuario/tenant pero guarda respuesta personalizada.
- Caché sin TTL ni `max`, o mutation que no invalida dato cacheado.
- `React.cache()` llamado con objetos inline como argumento.
- `readFile`/`fetch` de asset estático dentro de cada request.
- Handler con `await` secuenciales entre lecturas independientes.
- `await` de dato remoto antes de early return que no lo usa.
- Lectura de datos protegidos lanzada antes de authorization.
