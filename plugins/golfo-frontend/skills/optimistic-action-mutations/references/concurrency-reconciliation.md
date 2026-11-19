# Concurrencia y reconciliación

Patrones para que una UI responda rápido sin perder la verdad del servidor. Se aplican según la clase de cada operación ([decisión](optimistic-decision.md)) y con las primitivas del proyecto ([primitivas](framework-primitives.md)).

## Contenido

- [Baseline e intención](#baseline-e-intención)
- [Respuestas viejas y fuera de orden](#respuestas-viejas-y-fuera-de-orden)
- [Doble envío, deduplicación e idempotencia](#doble-envío-deduplicación-e-idempotencia)
- [Timeout, pérdida de respuesta y cancelación](#timeout-pérdida-de-respuesta-y-cancelación)
- [Rollback](#rollback)
- [Conflictos, ids temporales e invalidación](#conflictos-ids-temporales-e-invalidación)
- [Limpieza, contexto y reconexión](#limpieza-contexto-y-reconexión)
- [Patrón de toggles y selección](#patrón-de-toggles-y-selección)
- [Contrato del servidor](#contrato-del-servidor)
- [Checklist de tests](#checklist-de-tests)
- [Nombres](#nombres)
- [Evitar](#evitar)

## Baseline e intención

- **Separar lo confirmado de lo intentado.** El `baseline` es el último estado persistido que devolvió el servidor; la intención (`intended…`) es lo que el usuario pidió. La UI muestra la intención en optimistic y el baseline en lo demás.
- **Intenciones pendientes por entidad y operación** (`entityId` + tipo de operación), nunca un único flag global: dos ítems de una lista mutan en paralelo sin pisarse.
- **Capturar el baseline una sola vez por intención pendiente**, del estado persistido, no del visible: después de varios clicks el visible ya es optimista.
- Guardar timers, secuencias e intenciones en refs o estado fuera del render cuando el framework lo permite.

## Respuestas viejas y fuera de orden

- Cada intento lleva una **secuencia**, un **id de operación** o una **versión** del recurso. Solo la respuesta del intento vigente actualiza la UI; una respuesta más vieja se descarta o, si es una confirmación válida, se promueve a baseline y se vuelve a aplicar la intención vigente.
- En lecturas dependientes de parámetros, la respuesta se aplica solo si sus parámetros (ruta, entidad, filtro, página) siguen siendo los actuales; usar `AbortController` o la cancelación de la librería para no procesarla.
- Respuestas de otra ruta, otra entidad o una pantalla desmontada no producen estado ni feedback.

## Doble envío, deduplicación e idempotencia

- **Guard en el handler**, no solo `disabled` en el botón: Enter, doble toque, otra pestaña o un re-render pueden disparar dos veces. Mientras haya una operación en curso para esa entidad y operación, el segundo disparo se ignora o se coalesce.
- **Debounce y coalescing solo si la semántica lo permite**: un toggle o un autosave pueden enviar solo la última intención; un pago, un envío de mensaje o un reenvío de código no se coalescen ni se reemplazan. No hay una política universal de debounce.
- **Claves de idempotencia** en mutaciones con efectos cuando se van a reintentar (pagos, envíos, altas): el mismo intento lleva la misma clave en todos sus reintentos, así el servidor no lo aplica dos veces.
- **Reintentos automáticos acotados** (pocos intentos, espera creciente con jitter) y solo si la operación es idempotente o lleva clave; nunca ilimitados.

## Timeout, pérdida de respuesta y cancelación

- **Timeout no es fallo.** Si el request venció o la respuesta se perdió, la operación pudo ejecutarse. Pasar a resultado desconocido y resolverlo antes de repetir: consultar el estado con el id de operación o la clave de idempotencia, o releer el recurso. Solo cuando se confirma que no se aplicó, reintentar.
- **Abortar no es deshacer.** `AbortController` corta el request del cliente pero no revierte una escritura que ya llegó al servidor. En una mutación, cancelar sin confirmación del servidor deja el resultado desconocido; en una lectura, solo se descarta la respuesta.
- **Cancelación lógica**: al cancelar, navegar o cambiar de recurso, marcar la operación como cancelada para ignorar sus respuestas y limpiar sus timers.

## Rollback

- **Restaurar el baseline capturado**, no un valor inferido ni el visible anterior.
- **Acotado a la entidad y operación que falló**: el rollback no destruye operaciones de otras entidades ni confirmaciones que llegaron mientras tanto. Si el baseline cambió por otra confirmación, restaurar ese nuevo baseline.
- **Preservar input, scroll, foco y contexto** durante el fallo: el usuario no pierde lo que escribió ni su lugar.
- Limpiar la intención pendiente y su timer, y dejar una salida (reintentar, corregir).

## Conflictos, ids temporales e invalidación

- **Conflictos** (409, ETag, versión vieja): la versión del servidor manda; la edición local se conserva aparte hasta que el usuario elija cómo resolver.
- **Ids temporales**: un ítem creado de forma optimista usa un id del cliente (`tempId`) hasta que el servidor devuelve el definitivo; al reconciliar, reemplazar el id en caché, selección, foco y rutas, y no duplicar el ítem cuando llega el refetch.
- **Invalidación dirigida**: si la respuesta alcanza para reconstruir el estado, actualizar la caché con ella; si no, invalidar solo las claves afectadas. Recargar la ruta entera no es la reconciliación por defecto.
- **Sesión**: si cambia la sesión o el usuario, descartar intenciones pendientes de la sesión anterior y refetch de lo que dependía de ella.

## Limpieza, contexto y reconexión

- Limpiar timers, intenciones y suscripciones al desmontar, al navegar y al cambiar de entidad o de alcance.
- Al reconectar: refetch de lo invalidado y envío ordenado de lo encolado offline con su clave de idempotencia; lo que falle queda marcado con su reintento.
- Al volver a una pantalla cuya operación siguió en el servidor, mostrar el estado consultado, no el de memoria.

## Patrón de toggles y selección

Para acciones rápidas y repetibles (like, pin, voto, reacción, favorito, seguir, selección de opción):

1. **Identificar la forma de la acción**: toggle (`likedByViewer`, `isPinned`), selección (ids de opción, filtros, ranking), acción con contadores (conteos, porcentajes) o acción que cambia el orden (pin, timestamps).
2. **Modelar la intención pendiente por id de entidad**: campos `baseline…` del último estado persistido, campos `intended…` de la última acción, `isRequestInFlight` y `shouldFlushAfterRequest` cuando llega input durante un request en curso.
3. **Aplicar el estado optimista al instante**: invertir booleanos desde el estado visible, contadores con aritmética acotada (`Math.max(0, nextCount)`), recalcular derivados (porcentajes) sobre el total optimista y reordenar si la acción cambia el orden.
4. **Debounce del flush, no del feedback visual**: limpiar el timer de esa entidad, programar el flush con una constante con nombre; al hacer flush, omitir el request si la intención volvió al baseline; si hay un request en curso, marcar `shouldFlushAfterRequest` y salir.
5. **Reconciliar la respuesta**: validar su forma; ignorar respuestas viejas de otra ruta, alcance o entidad; si coincide con la última intención, aplicarla y limpiar la intención; si el usuario cambió de intención mientras tanto, promover la respuesta a nuevo baseline, volver a aplicar la intención vigente y hacer flush otra vez. El servidor es la fuente de verdad para contadores, timestamps, permisos y estados.
6. **Rollback intencional**: restaurar el baseline capturado, limpiar la intención y el timer, y mostrar un error seguro y específico (advertencia para límites de negocio, error para fallos inesperados).

## Contrato del servidor

- Devolver el **view model mínimo** para reconciliar la UI afectada: en toggles, el booleano persistido, conteos y un estado estable; en acciones con orden, timestamps o campos de orden; en selecciones, ids seleccionados, conteos, porcentajes, totales y estado del viewer. No forzar un refresh completo de la ruta cuando el cliente puede reconciliar con la respuesta.
- **Escrituras seguras ante reintentos y concurrencia**: inserts/deletes idempotentes o upserts para toggles, transacciones en mutaciones de varios pasos, constraints de unicidad, locks (advisory o equivalentes) en reemplazos por usuario o recurso, y releer el agregado después de escribir para devolver valores persistidos.
- Aceptar una **clave de idempotencia** en mutaciones con efectos y exponer una forma de **consultar el estado** de una operación cuando el resultado puede quedar desconocido.
- Devolver una **versión** (o ETag) si hay edición concurrente, y rechazar con conflicto cuando no coincide.
- Nunca devolver errores crudos del proveedor o de la base a la UI.

## Checklist de tests

- El estado optimista aparece inmediatamente después de la interacción (solo en la clase optimistic); en pending-first, el pending aparece y el resultado no.
- Interacciones rápidas repetidas se coalescen en la última intención significativa; volver al baseline cancela el request innecesario.
- Una respuesta que coincide con la última intención limpia el estado pendiente; una más vieja se promueve a baseline y dispara otro flush.
- Un fallo de red o de validación restaura el baseline capturado sin tocar otras entidades.
- Un rechazo por regla de negocio muestra advertencia y conserva la verdad del servidor.
- Un timeout pasa a resultado desconocido y consulta antes de repetir; el doble envío no duplica efectos.
- Respuestas de una ruta, entidad o alcance anterior se ignoran.
- Timers e intenciones se limpian al desmontar o resetear.
- Tests del servidor cubren idempotencia, constraints, fallos de permisos, conflictos y relectura del agregado.

## Nombres

Nombres explícitos que describen la acción y el estado, en inglés aunque el copy esté localizado:

- `PendingLikeIntent`, `PendingPinIntent`, `PendingPollVoteIntent`
- `baselineLikedByViewer`, `baselineLikeCount`, `intendedLikedByViewer`
- `clearLikeDebounceTimer`, `schedulePendingLikeIntentFlush`, `flushPendingLikeIntent`
- `applyMessageLikeState`, `applyMessagePinState`, `updateMessagePoll`
- `getOptimisticPollVote`, `getOptimisticPinnedAt`

Usar constantes con nombre para delays de debounce, límites, estados y claves de copy.

## Evitar

- Debounce del estado visual.
- Usar el estado visible como dato de rollback después de varios clicks.
- Pisar una intención más nueva con una respuesta más vieja.
- Usar un refresh completo de la página como reconciliación por defecto.
- Reintentar a ciegas una mutación con efectos después de un timeout.
- Mockear librerías de UI o de plataforma para probar el patrón: probar el comportamiento observable en el borde del componente o del caso de uso.
- Mostrar errores crudos del proveedor o de la base en la UI.
