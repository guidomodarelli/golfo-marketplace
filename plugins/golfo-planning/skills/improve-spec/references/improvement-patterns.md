# Patrones de mejora

Transformaciones típicas de un spec narrativo a uno implementable. Los fragmentos son ilustrativos: muestran la forma del cambio, no contenido para copiar. El contenido real sale del spec y del codebase del usuario.

## 1. De prosa de flujo a pasos con gate y error

Antes:
> Si tiene key, se consulta el recurso y si está finalizado se crea el ticket. Si no, lanza un error.

Después:
> 4. Si `resourceKey` presente:
>    - Llamar **N1** `getResource(resourceKey, draft.getVersion())`.
>    - Si `status != FINISHED` → `BadRequestException("Resource version {v} is not FINISHED. Current status: {s}")`.
> 5. Crear ticket.

Qué se ganó: número de paso, llamada exacta, condición exacta, tipo de error y contenido del mensaje.

## 2. Fuente confiable de cada dato sensible

Antes:
> Se usa el id del usuario como requester-id.

Después (en `Must` y `Must Not`):
> - `requester-id` sale exclusivamente de `{objeto server-side}.getXxx()`. Nunca de datos del request.
> - La versión sale de `{objeto leído del servicio}`, no de input del usuario.

Qué se ganó: el implementador no puede tomar el valor del body/query por comodidad.

## 3. Orden y propagación de fallos

Antes:
> Si se promueve correctamente, se promueve el contexto.

Después:
> - N2 se llama **antes** de C2. Si N2 falla, la excepción se propaga y C2 no se ejecuta. El manejo existente en `{Servicio.método}` ya transiciona el estado a ERROR; no modificarlo.

## 4. Reutilizar patrón existente en vez de describir uno nuevo

Después de explorar el codebase:
> **Patrón a seguir:** `{Cliente.métodoExistente}` — mismo pool, config de scope y fail-closed (5xx/transporte → 503).

Y una constraint: "Todos los métodos nuevos del cliente siguen el mismo manejo de errores que `{métodoExistente}`".

## 5. Límites explícitos

- `Must Not`: operaciones que un flujo no hace aunque otro sí (p. ej. rollback solo lee estado, no promueve).
- `Out of Scope`: casos que quedan igual (entidades sin el dato opcional) y supuestos de diseño (p. ej. "se asume correlación versión A = versión B; no se agrega campo explícito").
- No revalidar respuestas upstream ni duplicar validaciones que el boundary de entrada ya hace; decir dónde está esa validación.

## 6. Endpoints nuevos: contrato mínimo

De un `curl` con host de entorno y respuesta completa a:

```
GET {config.base-path}/v1/resources/{key}?scope={scope}&version={version}
```

| Campo | Tipo | Uso |
| :-- | :-- | :-- |
| `status` | String | Gate del flujo |
| `active` | Boolean | Gate de rollback |

Qué se ganó: path parametrizado con la config real del repo, sin hosts de entorno, y solo los campos que el flujo consume.

## 7. Verify accionable

Antes: "Verificar que funcione".

Después:
> **Verify:** unit test — (a) status FINISHED → continúa; (b) DEPRECATED + active → continúa; (c) DEPRECATED + inactive → `BadRequestException`; (d) sin key → N1 no se llama. `mvn test -Dtest=FooServiceTest` pasa.
