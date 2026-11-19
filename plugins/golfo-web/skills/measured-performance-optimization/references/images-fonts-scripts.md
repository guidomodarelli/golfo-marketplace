# Imágenes, fuentes y scripts

## Imágenes

- Detectar: el elemento LCP del trace es una imagen, imágenes servidas más grandes que su tamaño renderizado, formatos JPEG/PNG pesados, CLS por imágenes sin dimensiones.
- Corregir:
  - Formatos modernos (AVIF/WebP) y `srcset`/`sizes` para servir el tamaño adecuado; usar el componente del framework si existe (`next/image`).
  - `width`/`height` o `aspect-ratio` para reservar espacio y evitar CLS.
  - `loading="lazy"` solo debajo del primer viewport; la imagen LCP va sin lazy y con una sola estrategia de prioridad: `fetchpriority="high"` o un preload, no ambos. Un `<link rel="preload" as="image">` manual de una imagen responsive lleva `imagesrcset` e `imagesizes` idénticos al `srcset`/`sizes` del `<img>`; un preload con solo `href` puede bajar el fallback mientras el `<img>` elige otro candidato y descargar la imagen dos veces. Sin eso, usar solo `fetchpriority="high"`.
  - Con `next/image`, revisar la versión de `next` del proyecto: en Next.js 16 o posterior usar `preload` (reemplaza a `priority`, deprecado) o `fetchPriority="high"`, nunca ambos; en versiones anteriores, `priority`.
- Medir: KB de imágenes de la página, LCP, CLS.

## Fuentes

- Detectar: texto invisible mientras carga la fuente (FOIT), saltos de layout al cambiar de fuente, muchas variantes o pesos cargados.
- Corregir:
  - `font-display: swap` (u `optional`) y `preload` de la fuente del texto principal; un `<link rel="preload" as="font">` manual lleva siempre `crossorigin` (y `type="font/woff2"`) para coincidir con el modo CORS del pedido de `@font-face`, o el navegador descarta el preload y descarga la fuente dos veces.
  - Formato WOFF2, subset de caracteres, menos pesos; fuentes variables cuando reemplazan varias variantes.
  - Self-hosting o el optimizador del framework (`next/font`) para evitar conexiones extra a terceros.
  - Fallback con métricas ajustadas (`size-adjust`, `ascent-override`) para reducir CLS.
- Medir: KB de fuentes, CLS, tiempo hasta texto visible.

## Scripts

- Detectar: scripts render-blocking en `<head>`, scripts de terceros (analytics, chat, tags, A/B testing) con long tasks en el trace, scripts que se cargan en páginas que no los usan.
- Corregir:
  - `defer` o `async` según si importa el orden; estrategias del framework (`next/script` con `lazyOnload`/`afterInteractive`).
  - Cargar terceros en idle o tras interacción (facade para chats y videos embebidos).
  - Eliminar scripts sin uso y revisar tags duplicados.
- Medir: TBT/INP, cantidad de long tasks atribuidas a terceros, KB de JS de terceros.

## Resource hints de React DOM

Fuente: regla `rendering-resource-hints` de vercel-labs/agent-skills `react-best-practices` (MIT, Vercel), adaptada.

- Detectar: en el waterfall de la carga, el DNS/TCP/TLS de un origen crítico (API, CDN, fuentes) arranca recién cuando el JS lo pide; recursos que el server ya sabe que se van a usar se descubren tarde (fuente referenciada desde CSS, stylesheet o script cargado por un componente).
- Corregir: con React 19 (o el App Router), llamar las APIs de `react-dom` desde el componente que conoce el recurso, también desde Server Components, en vez de escribir `<link>` a mano: `prefetchDNS(origin)` para un origen que se usará más tarde; `preconnect(origin)` para uno que se usa enseguida (pocos: cada conexión abierta compite); `preload(href, { as, ... })` para un recurso crítico de esta página (fuente con `crossOrigin`, imagen LCP con las reglas de [Imágenes](#imágenes)); `preinit(href, { as: 'style' })` o `{ as: 'script' }` para un stylesheet o script que tiene que ejecutarse temprano; `preloadModule`/`preinitModule` para módulos ES, por ejemplo en hover de un link a la próxima ruta. React deduplica los hints repetidos.
- No preloadear lo que la página no usa (consume ancho de banda del camino crítico y Chrome avisa que el recurso se precargó sin usarse) ni duplicar con un `<link>` manual del mismo recurso.
- Medir: inicio de la conexión o de la descarga del recurso en el waterfall, LCP y tiempo hasta texto visible con el mismo throttling.
