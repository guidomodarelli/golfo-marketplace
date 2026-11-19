# Diferencias entre versiones que cambian las decisiones

Confirmar siempre contra `node_modules/next/dist/docs/` de la versión instalada. Esta tabla solo indica qué mirar.

| Tema | Qué verificar | Impacto en la decisión |
|---|---|---|
| Props de `error.tsx` | Si existe `retry` además de `reset` (16.x documenta `retry` como la opción por defecto: vuelve a pedir y renderizar; `reset` solo limpia el estado). | Usar `retry` para el botón de reintentar cuando exista. |
| `params` / `searchParams` | Si son promesas (`await params`) — lo son desde 15. | Esperarlos dentro del boundary del segmento que los usa. |
| Cache Components (`cacheComponents: true`) | Si está activo en `next.config.*`. | Los datos runtime en un layout deben ir en su propio `<Suspense>` o el build falla. `loading.tsx` pasa a ser un `<Suspense>` común. Contenido cacheado con `"use cache"` entra al static shell y no necesita skeleton. |
| Instant navigation / Partial Prefetching | `partialPrefetching`, segment config `instant`. | Cada segmento que espera necesita su propio boundary; validar con las herramientas de la guía `instant-navigation.md`. No desactivar la validación para tapar un layout que bloquea. |
| `forbidden()` / `unauthorized()` | Si están disponibles y si requieren flag experimental. | Usarlos para acceso denegado en lugar de `notFound()`. |
| `catchError` | Si existe la función para boundaries a nivel componente. | Contener errores de widgets sin un `error.tsx` de ruta. |
| `global-error.tsx` | No hereda estilos ni tema. | Incluir estilos mínimos y el tema dentro del archivo. |
| `middleware` → `proxy` | Nombre del archivo de proxy en la versión. | Chequeos rápidos de existencia (404 real) antes de streamear. |

Sin `node_modules` instalado, leer la versión de `package.json` y consultar la doc oficial de esa versión en nextjs.org antes de escribir código.
