# Reglas de decisión por archivo especial

Jerarquía de render de un segmento (de afuera hacia adentro):

```text
layout.tsx
  template.tsx
    error.tsx        ← boundary de error
      loading.tsx    ← boundary de Suspense
        not-found.tsx
        page.tsx / layout.tsx del segmento hijo
```

Consecuencias que guían todas las decisiones:

- `error.tsx` y `loading.tsx` de un segmento **no** cubren el `layout.tsx` ni el `template.tsx` del mismo segmento. Lo que falla o espera en el layout lo captura el boundary del segmento padre.
- En una navegación cliente solo se re-renderiza lo que está debajo del layout compartido entre origen y destino. Un boundary ubicado arriba de ese punto no se muestra durante la transición.

## layout.tsx compartido

Señales para extraer un layout:

- Dos o más `page.tsx` hermanas repiten el mismo wrapper (sidebar, header de sección, tabs, breadcrumbs base, contenedor con el mismo ancho).
- Varias páginas montan el mismo provider de contexto.
- Al navegar entre esas páginas, la chrome "parpadea" o pierde estado (scroll del sidebar, input de búsqueda global).

Cómo agruparlas:

- Si comparten prefijo de URL (`/settings/profile`, `/settings/billing`), el layout va en `app/settings/layout.tsx`.
- Si no comparten prefijo (`/dashboard`, `/members`, `/payments` con el mismo shell), usar un route group: `app/(platform)/layout.tsx`. Los grupos tampoco cambian la URL y permiten tener otro shell para `app/(marketing)/`.
- Un layout por nivel de chrome: shell global de la app → layout de sección (tabs de la sección) → páginas. No mezclar las tabs de una sección en el shell global.

Qué no hacer en un layout:

- Leer `searchParams`: el layout no se re-renderiza al cambiar la query y quedaría desactualizado. La UI que depende de la query va en la página o en un componente cliente con `useSearchParams` dentro de `<Suspense>`.
- Esperar datos lentos sin `<Suspense>` propio: bloquea la navegación de todas las páginas hijas y `loading.tsx` del mismo segmento no lo cubre.
- Leer `params` en server cuando el proyecto usa navegaciones instantáneas o Cache Components: preferir resolver el parámetro en la página o en una isla cliente con `useParams` dentro de `<Suspense>`, según indique la doc de la versión instalada y las convenciones del proyecto.
- Usar el layout para resetear estado por página: eso es `template.tsx`.

## loading.tsx

Ponerlo en un segmento cuando su `page.tsx` (o un layout hijo) espera algo antes de pintar: queries, `await params`, `cookies()`, `headers()`, fetch sin cache.

- Cada segmento que espera necesita su `loading.tsx`. El del padre cubre la carga directa de la URL, pero no la navegación entre hermanos, que solo re-renderiza desde el layout compartido hacia abajo.
- Si varios hijos comparten la forma, reexportar: `export { default } from "../loading";`.
- Si la página tiene bloques con latencias distintas, combinar `loading.tsx` (shell de la página) con `<Suspense>` por bloque dentro de `page.tsx`. Así el título y los filtros salen enseguida y la tabla hace streaming.
- Con streaming, la respuesta ya salió con status 200: un `notFound()` o `redirect()` que ocurre después de que se renderizó un fallback (`loading.tsx` o `<Suspense>`) se resuelve dentro del contenido streameado, no con el status HTTP. Ver el tradeoff y cuándo hace falta un 404 real en [not-found.tsx](#not-foundtsx-forbidden-unauthorized).

No ponerlo cuando la página es estática o cacheada: agregaría un flash innecesario.

## Suspense granular

Usar `<Suspense>` dentro de una página o layout cuando:

- Un bloque es independiente del resto y más lento (un gráfico, un feed, contadores).
- Un layout necesita datos runtime para una parte (items del sidebar que dependen del usuario): envolver solo esa parte.
- Un componente cliente usa `useSearchParams()`: en server suspende, necesita boundary.

No usarlo cuando el bloque es barato o no tiene sentido mostrarlo a medias.

Cada boundary con un skeleton de su bloque, no uno genérico. Iniciar los fetches en paralelo (no en cascada) y pasar las promesas a los hijos cuando el framework lo permite.

## error.tsx

- Es un Client Component (`"use client"`). Recibe `error` (con `digest` para cruzar con los logs del server) y una función para reintentar (`retry` en versiones recientes, que vuelve a pedir y renderizar; `reset` solo limpia el estado sin re-fetch). Verificar el nombre en la doc instalada.
- Ubicarlo en el segmento más bajo que todavía da contexto: el error de la tabla de miembros no debería borrar el sidebar ni el header de la tribu. Un `error.tsx` en `app/(platform)/[slug]/` cubre a todas sus páginas hijas; agregar uno más específico solo si el mensaje o la acción de recuperación cambia.
- No mostrar `error.message` de errores de server: en producción viene genérico y en desarrollo puede filtrar detalles. Mostrar copy seguro, una acción de reintentar y una salida (volver al inicio de la sección).
- Loggear con el sistema de observabilidad del proyecto en un efecto, incluyendo `digest`.
- No repetir el mismo `error.tsx` en cada hoja: el del segmento padre ya cubre a los hijos.
- Errores de un componente puntual (un widget de terceros, un gráfico, un embed) se contienen con un error boundary de componente (`catchError` de `next/error` o el patrón del proyecto), no con un `error.tsx` de ruta.
- `global-error.tsx` en la raíz, una sola vez, es obligatorio para cubrir errores del root layout. Define su propio `<html>` y `<body>`, no hereda estilos globales ni el tema de la app y no admite `metadata`.

## not-found.tsx, forbidden, unauthorized

- `not-found.tsx` en el segmento dinámico cuyo recurso puede no existir (`[slug]`, `[id]`), con copy y salida contextual ("Esta tribu no existe" + link al listado). Un `app/not-found.tsx` raíz para URLs que no matchean ninguna ruta.
- Para recursos dinámicos, la existencia se conoce recién después del lookup: esperar la query y llamar `notFound()` con el resultado, aunque ese `await` esté dentro de `<Suspense>` o debajo de un `loading.tsx`. El lugar idiomático es la función de acceso a datos que espera el componente. Así el shell y el skeleton siguen visibles mientras se busca el recurso.
- Tradeoff: si el body ya empezó a streamearse, la respuesta sale con HTTP 200 y Next.js agrega `<meta name="robots" content="noindex">` al HTML; algunos crawlers la marcan como "soft 404", pero no se indexa. Es el comportamiento esperado por defecto.
- Reservar el chequeo previo al streaming para cuando hace falta un HTTP 404 real (compliance, analytics): verificar la existencia antes de cualquier fallback de Suspense y de cualquier `await` que suspenda, o hacerlo en `proxy`, reescribiendo los slugs inexistentes a una ruta not-found o respondiendo 404. Mantener ese chequeo rápido y sin traer el contenido completo.
- No envolver `notFound()` en un `try/catch` que lo trague; si el `try/catch` hace falta, re-lanzar con `unstable_rethrow()`.
- Distinguir "no existe" de "no tenés permiso": si la versión soporta `forbidden()` / `unauthorized()` con sus archivos, usarlos; si no, una página de acceso denegado explícita. No devolver 404 para ocultar permisos salvo que sea una decisión de seguridad documentada.

## template.tsx

Solo cuando se necesita que los hijos se remonten en cada navegación: resetear un formulario al cambiar de item, re-disparar una animación de entrada o un efecto de tracking por página, o mostrar el fallback de `<Suspense>` en cada navegación. Si ninguno aplica, es un layout: por defecto un template remonta en cada navegación y pierde las ventajas del layout (estado y DOM preservados).

## Parallel e intercepting routes

- Slots paralelos (`@modal`, `@panel`) cuando una misma URL muestra regiones independientes que cargan o fallan por separado: cada slot puede tener su `loading.tsx` y `error.tsx`. Agregar `default.tsx` en cada slot para que la recarga directa no dé 404.
- Intercepting routes (`(.)photo/[id]`) para abrir un detalle como modal sobre la lista y como página completa al recargar.

## Anti-patrones a reportar

| Anti-patrón | Por qué es un problema | Corrección |
|---|---|---|
| `loading.tsx` con texto o spinner centrado | Salto de layout y no anticipa el contenido | Skeleton con la forma de la página |
| `loading.tsx` solo en el segmento padre | Navegación entre hermanos queda congelada | `loading.tsx` por segmento hoja que espera |
| Fetch lento en `layout.tsx` sin `<Suspense>` | Bloquea todas las páginas hijas | Moverlo a la página o envolverlo en `<Suspense>` |
| `"use client"` en `layout.tsx` o en el sidebar entero | Todo el árbol de chrome se hidrata y viaja como JS | Islas cliente mínimas |
| `useEffect` + `fetch` para datos del primer render | Pantalla vacía, waterfall, doble request | Server Component que espera los datos + skeleton |
| Un único `error.tsx` en la raíz | Cualquier error borra toda la app | `error.tsx` por sección |
| `error.tsx` mostrando `error.message` | Filtra detalles internos | Copy seguro + `digest` en logs |
| El mismo wrapper copiado en varias páginas | Remonta y pierde estado al navegar | `layout.tsx` o route group |
| `searchParams` leído en un layout | Valor stale al cambiar la query | Leerlo en la página |
