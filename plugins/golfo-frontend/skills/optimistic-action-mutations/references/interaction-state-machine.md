# Máquina de estados por interacción

Estados y transiciones que se revisan en cada operación afectada. Es un modelo para razonar, no una dependencia: en una acción trivial alcanza con un `isPending` y un baseline; los nombres se adaptan al framework (`status` de TanStack Query, `useActionState`, un reducer). Qué mensaje y canal recibe cada estado lo decide `ui-ux-flow-patterns` en su [ciclo de vida de operaciones](../../ui-ux-flow-patterns/references/state-matrix.md#operaciones-asíncronas) y su [ficha por canal](../../ui-ux-flow-patterns/references/feedback-channels.md#ficha-por-canal); acá se decide la verdad de los datos, los controles y la recuperación.

## Contenido

- [Camino principal](#camino-principal)
- [Estados](#estados)
- [Transiciones alternativas](#transiciones-alternativas)
- [Reglas de la máquina](#reglas-de-la-máquina)

## Camino principal

```text
idle → validating → pending → optimistic (solo si la clase lo permite) → confirmed
```

- `validating` existe solo si hay validación local antes de enviar; si falla, `validation-error` y no se envía nada.
- `optimistic` existe solo en la clase optimistic: la UI ya muestra la intención mientras el request está en curso. En pending-first y server-confirmed se pasa de `pending` a `confirmed` sin anticipar el resultado.

## Estados

Para cada estado: qué es verdad confirmada, qué se conserva, qué controles quedan, cómo sale el usuario y qué impide que una respuesta vieja lo pise.

| Estado | Verdad y datos | Controles | Recuperación y limpieza | Respuestas viejas |
|---|---|---|---|---|
| `idle` | El baseline es el último estado confirmado por el servidor. | Habilitados (o deshabilitados con el motivo visible). | — | — |
| `validating` | Sin cambios en el baseline; el input del usuario se conserva. | El envío espera el resultado de la validación. | El error de validación anterior se limpia al empezar a validar. | — |
| `validation-error` | Baseline intacto; input conservado. | El campo sigue editable; el envío vuelve a estar disponible al corregir. | Corregir el valor; el error se va al corregir. | — |
| `pending` | Baseline intacto; la intención queda registrada con id de operación y secuencia. | El control que disparó no acepta un segundo envío (guard en el handler, no solo `disabled`); el resto de la pantalla sigue usable salvo lo que la operación invalida. | El error anterior de esta operación se limpia al empezar el intento. | La respuesta se aplica solo si su secuencia es la vigente para esa entidad y operación. |
| `optimistic` | La UI muestra la intención; el baseline se guarda aparte y sigue siendo la verdad confirmada. | Se puede seguir interactuando: nuevas intenciones reemplazan a la anterior y se coalescen o encolan según la semántica. | Si falla: rollback al baseline. | Igual que `pending`; además, una respuesta que no coincide con la última intención se promueve a baseline y la intención vigente se vuelve a aplicar. |
| `confirmed` | La respuesta del servidor pasa a ser el nuevo baseline; la intención pendiente se limpia. | Vuelven a `idle`. | — | Respuestas posteriores de intentos viejos se descartan. |
| `rejected` | El servidor rechazó la acción por una regla (validación, permiso, límite del plan, 403, 422). Baseline intacto o actualizado con lo que el servidor devolvió. | Habilitado si corregir tiene sentido; deshabilitado con el motivo si la regla persiste (permiso, plan). | Rollback de lo optimista; mostrar la regla y la salida (corregir, pedir acceso, cambiar de plan). Reintentar no sirve. | — |
| `failed` | Falló el transporte o el servidor (red, 5xx) y se sabe que no se aplicó. Baseline intacto. | Habilitado para reintentar. | Rollback de lo optimista; input conservado; reintento manual o automático acotado si la operación es idempotente. | — |
| `rolling-back` | Se restaura el baseline de **esta** entidad y operación; no se toca lo que otras operaciones ya confirmaron. | Breve; vuelve a `idle` o `failed`. | El error se mantiene hasta un nuevo intento o un cambio de contexto. | Un rollback no pisa un baseline más nuevo que llegó de otra operación. |
| `retrying` | Mismo id de operación o clave de idempotencia que el intento original. | Sin doble disparo durante el reintento. | Límite de intentos con espera creciente; al agotarse, `failed`. | La respuesta del intento original que llega tarde se reconcilia por id de operación, sin aplicar dos veces. |
| `conflict` | El servidor tiene una versión más nueva (409, ETag). La versión del servidor es la verdad; la edición local se conserva aparte. | Guardar queda bloqueado hasta resolver. | Mostrar la diferencia y dejar elegir: recargar, combinar o sobrescribir si el dominio lo permite. Nunca descartar la edición sin que el usuario lo elija. | La resolución usa la versión vigente, no la del intento que chocó. |
| `cancelled` | Cancelación del cliente. En lecturas, el resultado se descarta. En una mutación que pudo llegar al servidor, el resultado es desconocido: pasa a `unknown-outcome` salvo que el servidor confirme la cancelación. | Habilitados, salvo repetir una mutación cuyo resultado es desconocido. | Limpiar timers e intenciones de la operación cancelada. | Toda respuesta de la operación cancelada se ignora. |
| `offline` | Lo confirmado sigue siendo el baseline; lo hecho offline queda como intención pendiente marcada. | Acciones que no pueden funcionar offline, deshabilitadas con el motivo; las que se pueden encolar, encoladas con clave de idempotencia. | Al reconectar: refetch de lo invalidado y envío ordenado de la cola; lo que falle queda marcado con su reintento. | La cola se reconcilia por id de operación, no por orden de llegada de las respuestas. |
| `unknown-outcome` | Timeout o respuesta perdida en una mutación: el servidor pudo haberla aplicado. Ni el baseline ni la intención son verdad confirmada. | Repetir queda bloqueado; "Comprobar estado" habilitado. | Consultar el estado (id de operación, clave de idempotencia o lectura del recurso) antes de permitir otra ejecución. | La consulta usa el id de la operación, así una respuesta tardía del intento original se reconoce. |
| `reconciling` | Se combina la respuesta o el estado consultado con las intenciones que siguen pendientes. | Según la intención vigente. | Termina en `confirmed`, `optimistic` (si hay una intención más nueva que reenviar) o `conflict`. | Solo aplica datos de la secuencia vigente o más nueva. |
| `partial-success` | Parte de una operación masiva se confirmó y parte no. Lo confirmado pasa al baseline; lo fallido queda con su motivo. | Reintentar solo lo fallido. | Reconciliar ítem por ítem (`async-operation-error-handling` (plugin `golfo-engineering`)). | Cada ítem se reconcilia con su propio id. |

## Transiciones alternativas

| Desde | Evento | Hacia |
|---|---|---|
| `validating` | validación local falla | `validation-error` |
| `pending` / `optimistic` | servidor rechaza por regla | `rejected` → `rolling-back` si había optimismo |
| `pending` / `optimistic` | red o 5xx con fallo conocido | `failed` → `rolling-back` si había optimismo |
| `pending` / `optimistic` | timeout o respuesta perdida en una mutación | `unknown-outcome` → `reconciling` tras consultar |
| `pending` / `optimistic` | 409 o versión vieja | `conflict` |
| `pending` / `optimistic` | usuario cancela, navega, cambia de entidad o desmonta | `cancelled` (lectura) o `unknown-outcome` (mutación que pudo llegar) |
| cualquier estado con intención pendiente | se pierde la conexión | `offline` |
| `offline` | vuelve la conexión | `reconciling` |
| `failed` | reintento | `retrying` → `pending` |
| `optimistic` | nueva intención del usuario sobre la misma entidad | `optimistic` (la última intención gana; flush posterior si hay un request en curso) |
| operación masiva | resultados mixtos | `partial-success` |

## Reglas de la máquina

- **Ningún estado terminal artificial.** `rejected`, `failed`, `conflict`, `unknown-outcome` y `offline` siempre tienen una salida: corregir, reintentar, resolver, comprobar o esperar con el motivo a la vista.
- **El baseline solo lo cambia el servidor.** Una respuesta confirmada, una lectura posterior o un evento del servidor; nunca la intención del usuario ni un valor inferido.
- **El error se limpia al empezar un intento nuevo, al cambiar de recurso o al resolverse**, no por timeout.
- **Cada entidad y operación tiene su propia máquina.** Una falla en un ítem no revierte otro; dos operaciones sobre la misma entidad se ordenan por secuencia.
