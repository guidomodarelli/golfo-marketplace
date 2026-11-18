# Primitivas por framework

Antes de escribir estado propio, leer `package.json` (o el equivalente del stack) y usar lo que ya está instalado. No instalar una librería ni construir un gestor de estado para una acción que las primitivas existentes resuelven. Verificar la API contra la versión instalada: los nombres de abajo corresponden a las versiones actuales de cada librería.

## React 19

- **`useOptimistic(state, updateFn)`**: muestra la intención mientras dura una Action y vuelve solo al estado real cuando la Action termina, con éxito o error. Llamar al setter dentro de una Action o de `startTransition`. Sirve para optimistic simple dentro de un componente; la reconciliación con el servidor la da el estado real que se actualiza al terminar.
- **Actions y `useActionState`**: formularios y mutaciones con pending integrado (`isPending`) y resultado del servidor; `useFormStatus` para el botón de envío. Encajan con pending-first y server-confirmed.
- **`useTransition`**: pending de una actualización no urgente sin bloquear la UI.
- Para varias entidades en paralelo o secuencias contra respuestas viejas, `useOptimistic` no alcanza solo: guardar intenciones por id en un `useRef` o usar la librería de datos del proyecto.

## TanStack Query (v5)

- **Optimista vía caché**: `onMutate` hace `await queryClient.cancelQueries({ queryKey })` para que un refetch en vuelo no pise la intención, guarda el snapshot con `getQueryData`, aplica `setQueryData` y devuelve `{ previous }`; `onError` restaura `previous` desde el `context`; `onSettled` invalida solo las claves afectadas con `invalidateQueries`.
- **Optimista solo de UI**: mostrar `variables` de la mutación mientras `isPending`, sin tocar la caché; útil cuando la mutación afecta un solo lugar.
- **Serializar mutaciones de la misma entidad**: `scope: { id }` en `useMutation` encola las mutaciones con el mismo scope.
- **Reintentos**: `retry` de las mutaciones viene apagado por defecto; activarlo solo si la operación es idempotente o lleva clave de idempotencia.
- **Lecturas**: `placeholderData: keepPreviousData` (o la función equivalente) conserva la página anterior mientras llega la nueva; las query keys con todos los parámetros evitan aplicar respuestas de otro filtro.

## SWR

- `mutate(key, updater, { optimisticData, rollbackOnError: true, populateCache, revalidate })`: optimista con rollback automático y control de revalidación. `useSWRMutation` acepta las mismas opciones en `trigger`.
- Las keys con parámetros descartan respuestas de otra key; `keepPreviousData` conserva la anterior.

## Redux Toolkit Query

- `onQueryStarted` con `dispatch(api.util.updateQueryData(...))` aplica la intención y devuelve un parche; en el `catch` de `queryFulfilled`, `patchResult.undo()` hace el rollback. `invalidatesTags` dirige la invalidación.

## Apollo Client

- `optimisticResponse` en la mutación y `update` o normalización de caché para reconciliar; Apollo revierte la capa optimista si la mutación falla.

## Next.js (App Router)

- **Server actions** con `useActionState` o `useOptimistic` en el cliente. Devolver desde la action el view model mínimo para reconciliar.
- **Invalidación**: `revalidateTag` o `revalidatePath` acotados a lo que la mutación cambió; `router.refresh()` vuelve a renderizar toda la ruta y no es la reconciliación por defecto. Dónde viven los boundaries lo decide `nextjs-route-ui-boundaries`.

## Otros stacks

- **Vue**: Pinia o TanStack Vue Query con el mismo patrón de snapshot, intención y rollback; `watch` con cleanup para descartar respuestas viejas.
- **Svelte**: stores con snapshot y rollback; `$effect` con cleanup.
- **Flutter / móvil**: el mismo modelo (baseline, intención, secuencia) en el estado del widget o del bloc; las mismas reglas de timeout e idempotencia en el cliente HTTP.

Si el proyecto no tiene ninguna librería de datos, alcanza con estado local más un `ref` de intenciones y secuencias por entidad: no hace falta una máquina de estados formal.
