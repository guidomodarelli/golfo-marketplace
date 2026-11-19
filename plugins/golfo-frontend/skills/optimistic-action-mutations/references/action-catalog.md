# Catálogo de acciones

Por tipo de operación: clase por defecto, riesgos y patrón. La clase por defecto es un punto de partida: la decide la [tabla de decisión](optimistic-decision.md) con los datos reales de la operación. Los patrones de concurrencia viven en [concurrency-reconciliation.md](concurrency-reconciliation.md); qué ve el usuario en cada estado, en `ui-ux-flow-patterns`.

## Contenido

- [Lectura y obtención de datos](#lectura-y-obtención-de-datos)
- [Escritura y mutaciones](#escritura-y-mutaciones)
- [Reenvío de códigos SMS u OTP](#reenvío-de-códigos-sms-u-otp)
- [Operaciones prolongadas](#operaciones-prolongadas)

## Lectura y obtención de datos

Las lecturas no se muestran como "optimistas": no hay resultado de negocio que anticipar. Lo que se revisa es que la UI no muestre datos de otro contexto ni pierda los que ya tenía.

| Operación | Qué revisar |
|---|---|
| Estado inicial y primera carga | Valor inicial explícito (cargando, no vacío); datos del servidor como verdad; sin parpadeo entre vacío y datos. |
| GET dependiente de parámetros (id, filtro, búsqueda, página) | La respuesta se aplica solo si sus parámetros siguen siendo los actuales (clave de caché o id de pedido); cancelar o ignorar la respuesta del parámetro anterior. |
| Refetch manual y automático (foco, intervalo, reconexión) | Conservar los datos visibles mientras recarga; no pisar una edición local pendiente con datos del refetch; desactivar el refetch mientras hay una mutación optimista sobre esos datos o reconciliar después. |
| Refresh, invalidación y actualización de caché | Invalidar solo las claves afectadas; preferir actualizar la caché con la respuesta de la mutación cuando alcanza para reconstruir el estado; `router.refresh()` o recargar la ruta entera no es la reconciliación por defecto. |
| Paginación, búsqueda y filtros | Respuestas fuera de orden descartadas por clave; mantener la página anterior mientras llega la nueva; un ítem creado de forma optimista aparece donde el usuario lo espera y no se duplica al llegar el refetch. |
| Datos parciales, vacíos, desactualizados u offline | Distinguir "vacío" de "falló" y de "todavía cargando"; marcar lo desactualizado; al reconectar, refetch de lo invalidado. |

## Escritura y mutaciones

| Operación | Clase por defecto | Riesgos y patrón |
|---|---|---|
| Toggle (like, favorito, pin, seguir, marcar leído), voto, reacción, selección de opción | optimistic | Clicks rápidos: aplicar al instante, coalescer y enviar la última intención; contador acotado; rollback al baseline; respuesta vieja descartada ([patrón de toggles y selección](concurrency-reconciliation.md#patrón-de-toggles-y-selección)). |
| POST de creación (comentario, tarea, ítem de lista) | optimistic con id temporal, o pending-first si el servidor calcula datos que la UI muestra | Id temporal reconciliado con el id real; no duplicar al llegar el refetch; doble envío protegido con clave de idempotencia si el servidor la acepta. |
| PUT/PATCH de edición (formulario, campo inline) | pending-first para formularios con validación del servidor; optimistic para campos simples reversibles | Conservar lo escrito ante error; conflictos de versión (409) reconciliados desde el servidor sin perder la edición local. |
| Guardado explícito | pending-first | Botón con pending y sin doble envío; el éxito se muestra con la confirmación. |
| Autoguardado | optimistic sobre el contenido local, pending-first sobre el indicador de guardado | Guardados en orden: uno viejo que responde tarde no pisa uno nuevo (secuencia o versión); debounce del envío, nunca de lo que se ve. |
| DELETE reversible (papelera, archivar, soft delete) | optimistic + deshacer | Quitar de la vista al instante, ofrecer deshacer, restaurar en su posición si falla; no destruir otras operaciones confirmadas en el rollback. |
| DELETE irreversible | server-confirmed | Confirmación previa (`ui-ux-flow-patterns`); el ítem desaparece recién con la confirmación. |
| Reordenamiento y drag-and-drop | optimistic | Baseline del orden completo; enviar el orden final o el movimiento con versión; rollback al orden confirmado, no al visible. |
| Operaciones masivas | pending-first | Resultado por ítem; éxito parcial reconciliado ítem por ítem (`async-operation-error-handling` (plugin `golfo-engineering`)). |
| Envío de formulario, publicación o mensaje | pending-first; mensajes de chat: optimistic con estado de envío | El mensaje queda en el hilo como "enviando" con id del cliente; reintento sin duplicar; nunca marcar "enviado" antes de la confirmación. |
| Reenvío de códigos, invitaciones o notificaciones | pending-first | Ver [Reenvío de códigos SMS u OTP](#reenvío-de-códigos-sms-u-otp). Nunca afirmar que se envió antes de la respuesta. |
| Restablecer contraseña, estado o configuración | server-confirmed | Efecto de seguridad o difícil de compensar; mostrar el resultado autoritativo. |
| Pagos, cobros, suscripciones | server-confirmed | Resultado incierto ante timeout: consultar el estado de la operación antes de permitir repetir; clave de idempotencia. |
| Autenticación, verificación, permisos y roles | server-confirmed | No anticipar acceso ni permisos; el servidor decide. |
| Cancelar, revertir, deshacer | según lo que revierte | Deshacer una acción optimista local antes del envío es local; revertir algo ya confirmado es una mutación nueva con su propia clase. Abortar un request no revierte una escritura que ya llegó. |

## Reenvío de códigos SMS u OTP

Caso de referencia: el código vence con la pantalla abierta y el usuario pide otro. Los estados visibles, el copy y los canales viven en la sección [Verificación por código de `ui-ux-flow-patterns`](../../ui-ux-flow-patterns/references/flow-catalog.md#verificación-por-código-sms-email-u-otp); acá va lo que decide esta skill:

- **Clase pending-first.** El botón "Reenviar" entra en pending al instante, pero nada dice "te enviamos un código" hasta la respuesta del servidor: el envío real del SMS es un efecto externo que no se puede anticipar ni deshacer.
- **Vencido no es error de red.** Expiración y fallo de transporte son ramas distintas de la máquina de estados: la expiración ofrece pedir otro código; el fallo de red ofrece reintentar la misma acción.
- **Un envío a la vez.** Deduplicar el pedido mientras hay uno en curso (guard en el handler, no solo el botón deshabilitado) y respetar el cooldown y el rate limit reales.
- **Datos autoritativos.** Vencimiento, cooldown e intentos restantes salen de la respuesta del servidor (`expiresAt`, `resendAvailableAt`, `Retry-After`), no de un contador local.
- **Desafío vigente.** Cada envío devuelve un id de desafío; la respuesta de un envío o una verificación anterior se descarta si no corresponde al desafío vigente.
- **Errores según contexto.** Un reenvío exitoso limpia el código anterior y su error; un reenvío fallido conserva la salida (reintentar o alternativas) y no promete un envío.
- **Sin bloqueo permanente.** Si una restricción legítima impide reenviar, la UI explica por qué y cuándo podrá hacerlo.

Tests del caso: éxito, expiración, fallo del reenvío, rate limit con espera, respuesta tardía de un envío anterior y reintento posterior.

## Operaciones prolongadas

Se coordinan con `async-operation-error-handling`, dueña de jobs, polling, resultados parciales y reintentos distribuidos. Esta skill revisa solo la parte de la UI:

| Operación | Qué revisar |
|---|---|
| Upload y descarga | Progreso real por archivo; la entidad aparece como pendiente hasta que el servidor la confirma; cancelar un archivo no cancela los demás. |
| Procesamiento asíncrono y jobs | La UI refleja el estado del job del servidor (pending, running, done, failed), no una suposición; el id del job identifica la operación. |
| Polling y seguimiento | Polling con límite y backoff; se detiene al desmontar o al llegar a un estado terminal; respuestas de un job viejo descartadas. |
| Resultados parciales | Reconciliar ítem por ítem; no mostrar éxito total con fallos pendientes. |
| Reintentos y reanudaciones | Reintentar solo lo fallido; con clave de idempotencia si la operación tiene efectos. |
| Operación que sigue en el servidor al salir de la pantalla | Al volver, mostrar el estado real consultado, no el que quedó en memoria; no repetir la operación por haber perdido la respuesta. |
