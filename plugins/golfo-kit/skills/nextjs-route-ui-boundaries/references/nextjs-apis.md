# Catálogo de APIs de Next.js para rutas rápidas y resilientes

Verificado contra la documentación de Next.js 16.3. Las marcadas **experimental** requieren un flag en `next.config.*` y pueden cambiar: usarlas solo si el proyecto ya las activa o si el usuario acepta activarlas. Antes de usar cualquiera, confirmar su firma en `node_modules/next/dist/docs/` de la versión instalada.

Cada fila dice **cuándo aporta valor**, no solo qué hace. Proponer una API solo cuando resuelve un problema concreto del árbol analizado.

## Índice

1. Archivos especiales de ruta
2. Navegación, prefetch e instant navigation
3. Hooks de cliente para chrome y estado de navegación
4. Control de flujo en render (404, 403, redirects, errores)
5. Datos runtime y cache (Cache Components)
6. Mutaciones e invalidación
7. Metadata, SEO e imágenes generadas
8. Componentes optimizados (`Link`, `Image`, `Form`, `Script`, fuentes, `dynamic`)
9. Configuración de `next.config.*` relevante
10. Trabajo fuera del render y observabilidad

## 1. Archivos especiales de ruta

| API | Aporta valor cuando |
|---|---|
| `layout.tsx` | Chrome persistente entre rutas hermanas; no se re-renderiza al navegar. |
| `template.tsx` | Hay que remontar hijos o mostrar el fallback de Suspense en cada navegación. |
| `loading.tsx` | El segmento espera datos; muestra un skeleton instantáneo y prefetcheable. |
| `error.tsx` / `global-error.tsx` | Contener fallos de un segmento / del root layout. |
| `not-found.tsx` | Recurso inexistente con UI contextual (junto con `notFound()`). |
| `forbidden.tsx` / `unauthorized.tsx` (**experimental**, `authInterrupts`) | UI de 403/401 distinta de 404. |
| `default.tsx` | Fallback de un slot paralelo al recargar o al no haber match; evita 404 en slots. |
| Route groups `(grupo)` | Varios shells (plataforma, marketing, auth) sin afectar la URL; múltiples root layouts. |
| Parallel routes `@slot` | Regiones independientes de una misma URL, cada una con su loading y error (dashboards, paneles laterales). |
| Intercepting routes `(.)ruta` | Detalle en modal sobre la lista y página completa al recargar o compartir el link. |
| `route.ts` | Endpoint HTTP del mismo origen (BFF, webhooks); no para datos del primer render de una página. |
| Archivos de metadata (`opengraph-image`, `icon`, `sitemap`, `robots`, `manifest`) | Metadata generada por segmento sin código en el layout. |
| Route segment config `export const instant` | Declarar que la navegación al segmento debe ser instantánea y que Next.js marque lo que la bloquea (o `false` para optar fuera, con justificación). |
| Route segment config `export const prefetch` | Ajustar por segmento la estrategia de prefetch (por ejemplo `'partial'`). |
| Route segment config `dynamicParams`, `maxDuration`, `runtime`, `preferredRegion` | Rutas con `generateStaticParams` que deben dar 404 para params desconocidos (`dynamicParams = false`), rutas lentas, edge vs node, región cercana a la base de datos. |

## 2. Navegación, prefetch e instant navigation

| API | Aporta valor cuando |
|---|---|
| `<Link prefetch>` | Prefetch del shell y del `loading.tsx` del destino. Activar `prefetch={true}` solo en links críticos si el proyecto lo desactiva por defecto. |
| `partialPrefetching` (config) | Prefetch solo de las partes estáticas de cada ruta por defecto; junto con Cache Components habilita navegaciones instantáneas. |
| `cacheComponents` (config) | Habilita `"use cache"`, static shell + streaming y la validación de datos runtime fuera de `<Suspense>`. |
| `useLinkStatus()` | Feedback inline en el link clickeado mientras la navegación está pendiente (prefetch desactivado o lento). Complementa, no reemplaza, `loading.tsx`. |
| `useRouter()` | Navegación programática (`push`, `replace`, `prefetch`, `refresh`, `back`). Preferir `<Link>` para navegación declarativa. |
| `<Form action="/ruta">` | Búsquedas y filtros que actualizan `searchParams`: prefetch del loading del destino, navegación cliente y funciona sin JS. |
| `typedRoutes` (config) | Hrefs tipados en `Link` y `router.push`: detecta links rotos al mover rutas o route groups. |
| `staleTimes` (**experimental**) | Ajustar cuánto reutiliza el router los segmentos cacheados en cliente. |
| `useOffline()` + `useOffline` config (**experimental**) | Banner o fallback offline y reintento automático de navegaciones y Server Actions. |

## 3. Hooks de cliente para chrome y estado de navegación

Usarlos dentro de islas cliente pequeñas, nunca para convertir el contenedor entero en cliente.

| API | Aporta valor cuando |
|---|---|
| `usePathname()` | Resaltar el link activo del sidebar o el header. |
| `useSelectedLayoutSegment()` / `useSelectedLayoutSegments()` | Tab activa de una sección o breadcrumbs desde el layout, sin leer `searchParams`. |
| `useParams()` | Leer `[slug]` en un componente cliente montado en un layout (envuelto en `<Suspense>` si el proyecto usa instant navigation). |
| `useSearchParams()` | Inputs de filtros controlados por la URL; requiere `<Suspense>` en server. |
| `useReportWebVitals()` | Enviar LCP, CLS e INP al sistema de métricas para medir el efecto de skeletons y boundaries. |

## 4. Control de flujo en render

| API | Aporta valor cuando |
|---|---|
| `notFound()` | El recurso no existe; renderiza el `not-found.tsx` más cercano. Para recursos dinámicos, llamarlo después del lookup aunque esté dentro de `<Suspense>`: con el streaming iniciado la respuesta sale 200 con `<meta name="robots" content="noindex">`. Solo si se requiere un HTTP 404 real (compliance, analytics), chequear antes de que empiece el streaming o en `proxy`. Ver [decision-rules.md](decision-rules.md#not-foundtsx-forbidden-unauthorized). |
| `redirect()` / `permanentRedirect()` | Redirigir desde Server Components, Server Actions o Route Handlers (307/303 vs 308). |
| `forbidden()` / `unauthorized()` (**experimental**) | 403/401 con su archivo especial; mejor que ocultar con 404. |
| `catchError()` (`next/error`) | Error boundary a nivel componente (widget, gráfico, embed) sin `error.tsx` de ruta; integra `retry` de Next.js. |
| `unstable_rethrow()` | Dentro de un `try/catch` que envuelve código que puede llamar `notFound()`, `redirect()` o APIs dinámicas: re-lanza los errores internos de Next.js para no tragárselos. |
| `error.tsx` props `retry` / `reset` | `retry` vuelve a pedir y renderizar el segmento; `reset` solo limpia el estado. |

## 5. Datos runtime y cache (Cache Components)

| API | Aporta valor cuando |
|---|---|
| `cookies()` / `headers()` | Leer estado inicial de la UI (sidebar colapsado, tema, locale) en server para que el primer HTML salga correcto. Son datos runtime: dentro de `<Suspense>`. |
| `connection()` | Un componente necesita salida por request (`Math.random()`, `new Date()`) sin leer cookies ni headers. Reemplaza `unstable_noStore`. |
| `io()` | Con Cache Components, marcar valores síncronos no deterministas que no deben quedar en el static shell. |
| `"use cache"` | Cachear una función o componente (catálogos, contenido editorial, navegación común) para que entre al static shell y no necesite skeleton. |
| `"use cache: private"` | Cachear en memoria del browser una función que lee cookies o headers cuando no es práctico sacar esa lectura. |
| `"use cache: remote"` | Compartir la cache entre instancias en un handler remoto. |
| `cacheLife()` | Definir la vida de la cache (`'minutes'`, `'hours'`, `'max'` o perfiles propios). |
| `cacheTag()` | Etiquetar entradas para invalidarlas selectivamente después de una mutación. |
| `fetch` con `next: { revalidate, tags }` | Sin Cache Components, cachear y etiquetar requests HTTP. |
| `generateStaticParams()` | Prerenderizar en build las rutas dinámicas conocidas; combinado con `dynamicParams = false` da 404 inmediato. |
| `next/root-params` | Leer params del root layout (por ejemplo `[locale]`) en cualquier Server Component sin pasarlos por props. |
| `draftMode()` | Previsualizar contenido de un CMS sin desactivar la cache para todos. |

## 6. Mutaciones e invalidación

| API | Aporta valor cuando |
|---|---|
| Server Actions (`"use server"`) | Mutaciones desde formularios o botones sin crear un `route.ts`; funcionan sin JS en formularios. Son endpoints públicos: validación, authentication, authorization y ownership van dentro de cada action ([«Server Actions son endpoints públicos»](../../refactor-ssr-data-fetching/SKILL.md#server-actions-son-endpoints-públicos) de `refactor-ssr-data-fetching`). |
| `updateTag()` | Read-your-own-writes: después de crear o editar, la UI muestra el dato nuevo en la misma respuesta. Solo en Server Actions. |
| `revalidateTag(tag, profile)` | Contenido donde una demora breve es aceptable (stale-while-revalidate). Usar la firma de dos argumentos; la de uno está deprecada. |
| `revalidatePath()` | Invalidar una ruta entera cuando no hay tags. |
| `refresh()` | Refrescar el router cliente desde una Server Action sin invalidar cache. |
| `useActionState`, `useFormStatus`, `useOptimistic` (React) | Estado pendiente, errores de validación y UI optimista de la acción, en vez de skeletons. |
| `serverActions` (config) | Límite de body y orígenes permitidos de las Server Actions. |

## 7. Metadata, SEO e imágenes generadas

| API | Aporta valor cuando |
|---|---|
| `metadata` / `generateMetadata()` | Título y descripción por segmento; en streaming Next.js decide si bloquear o streamear según el bot. No escribir `<title>` a mano en layouts. |
| `generateViewport()` | `themeColor` o `colorScheme` dependientes de la ruta. |
| `ImageResponse` / `opengraph-image.tsx` | OG images generadas por recurso (tribu, curso). |
| `sitemap.ts`, `robots.ts`, `manifest.ts` | Archivos de SEO y PWA generados desde datos. |
| `htmlLimitedBots` (config) | Ajustar qué bots reciben metadata bloqueante. |

## 8. Componentes optimizados

| API | Aporta valor cuando |
|---|---|
| `next/image` | Imágenes con tamaño declarado (sin CLS), lazy loading, formatos modernos; `priority`/`preload` solo para la imagen LCP. |
| `next/font` | Fuentes self-hosted sin layout shift ni request externo. |
| `next/script` | Scripts de terceros con estrategia (`afterInteractive`, `lazyOnload`) fuera del camino crítico. |
| `next/dynamic` | Cargar en diferido islas cliente pesadas (charts, editores, mapas) con un `loading` del tamaño final; `ssr: false` solo si la librería no soporta SSR. |
| `<Form>` | Ver sección 2. |

## 9. Configuración relevante de `next.config.*`

| Opción | Aporta valor cuando |
|---|---|
| `cacheComponents`, `partialPrefetching` | Ver sección 2. |
| `authInterrupts` (**experimental**) | Habilita `forbidden()` y `unauthorized()`. |
| `typedRoutes` | Ver sección 2. |
| `reactCompiler` | Memoización automática de componentes cliente; reduce re-renders de islas sin `useMemo` manual. |
| `optimizePackageImports` | Librerías de íconos o UI con muchos exports que inflan el bundle de las islas. |
| `inlineCss`, `cssChunking` | Ajustar la entrega de CSS cuando el CSS bloquea el primer render. |
| `logging` | Ver en dev los fetches y su estado de cache para detectar waterfalls. |
| `images` | Dominios remotos, tamaños y formatos de `next/image`. |

## 10. Trabajo fuera del render y observabilidad

| API | Aporta valor cuando |
|---|---|
| `after()` | Logging, analytics o side effects que no deben retrasar la respuesta (Server Components, Server Actions, Route Handlers, proxy). |
| `instrumentation.ts` (`register`, `onRequestError`) | Reportar errores de server con contexto; `onRequestError` captura lo que muestra `error.tsx` con su `digest`. |
| `instrumentation-client.ts` | Inicializar monitoreo o analytics en el cliente antes de la hidratación. |
| `proxy.ts` (antes `middleware.ts`) | Chequeos rápidos antes de renderizar (redirect de auth, rewrite a not-found para devolver 404 real); no fetchear contenido completo ahí. |
| `userAgent()` | Decidir variantes en el proxy según dispositivo, sin hacerlo en cliente. |
