# RFC 0042: Cancelar un pedido antes del envío

Estado: propuesto

## Contexto

Hoy un pedido solo se consulta con `getOrder`, que lo lee con `findById`; no hay forma de cancelarlo.

## Propuesta

- Nueva función `cancelOrder` que lee el pedido con `findById` y rechaza un pedido ya enviado.
- Nueva ruta `POST /orders/:id/cancel` en `orderRoutes` que llama a `cancelOrder`.
- El pedido pendiente pasa a «Cancelado» cuando el cliente toca «Cancelar pedido».

## Alternativas descartadas

Borrar el pedido en lugar de marcarlo como cancelado: se pierde el historial.

```md
## Esto es un ejemplo dentro de un bloque de código, no una sección
```
