# Jobs periódicos: barrido incremental con cursor monótono

## Qué es el problema

Un job periódico (cron, driver o worker con tick fijo) relee en cada corrida una ventana completa (por ejemplo, todas las fuentes de las últimas 24 h) para encontrar lo poco que cambió. El costo y la demora crecen con el tamaño de la ventana y no con la cantidad de filas nuevas.

Ejemplo: la ventana ocupa S páginas, cada tick procesa una página y el job certifica ("todo lo anterior a T ya se examinó") recién al terminar el barrido completo. Una fila nueva espera entre S+1 y 2S ticks, según en qué página del barrido en curso entre: si llega justo después de que el barrido pasó por su posición, tiene que esperar a que termine ese barrido y al siguiente. Con la ventana creciendo, la demora crece sin que haya más trabajo real.

## Detectar

- Un job que pagina por toda la ventana en cada corrida y casi todo lo que lee sale `existing`, `unchanged`, `skipped` o equivalente.
- La latencia de punta a punta (evento → efecto del job) crece con el tamaño de la ventana o con la cantidad de filas, no con las filas nuevas.
- Un corte de certificación o marca de "procesado hasta" que se ancla al inicio del barrido completo.
- Una página fija por tick con un presupuesto de corrida que no alcanza para recorrer la ventana.

## Medir antes

- Filas examinadas frente a filas nuevas por corrida (la proporción muestra cuánto trabajo es redundante).
- Páginas por barrido y ticks por barrido.
- Demora de punta a punta (evento → certificación o efecto) frente a la cantidad de filas de la ventana: medirla con al menos dos tamaños de ventana para mostrar que crece con ella.
- Tiempo y queries por corrida, con la misma data y el mismo entorno que se usarán después (paso 3 de la skill).

## Corregir: barrido incremental

**Precondición: trabajo de una sola vez por fila.** Un cursor sobre la fecha de creación sirve cuando cada fila se procesa una vez y no vuelve a necesitarlo: filas append-only, o cuyo resultado no cambia después de procesarse bien. Si el barrido completo también detecta cambios en filas existentes (un update del payload, un cambio en la fuente externa), el cursor de creación las excluye para siempre una vez que la frontera las pasa: la tabla de reintentos solo guarda fallos y la red de seguridad solo cubre inserciones. En ese caso, antes de migrar, hace falta un cursor de cambios que capture todo update relevante (por ejemplo, un `changed_at` mantenido por trigger en cada update, con el mismo fence que la creación, o un changefeed o replicación lógica), y la validación tiene que incluir un update sobre una fila ya procesada.

**Frontera persistida y monótona.** Guardar la última posición examinada como una tupla de orden completa (por ejemplo, `created_at, id`, más las columnas que hagan falta para que el orden sea total). La frontera solo avanza, y el storage tiene que impedir que retroceda (por ejemplo, `UPDATE ... SET frontier = $new WHERE frontier < $new` o un `CHECK`/trigger), para que dos corridas concurrentes o un deploy viejo no la pisen hacia atrás.

**Horizonte fijo por barrido.** Al empezar, cada barrido fija un horizonte (`now`) y lee solo lo que está después de la frontera y hasta ese horizonte, paginando con keyset sobre la misma tupla (`WHERE (created_at, id) > ($frontier_created_at, $frontier_id) AND created_at <= $horizon ORDER BY created_at, id`). Al terminar, la frontera avanza al horizonte. Un barrido sin novedades también certifica: avanza la frontera hasta el horizonte aunque no haya leído ninguna fila.

**Reintentos solo de lo que falló.** Las filas que no se pudieron procesar (fuente no disponible, error transitorio) van a una tabla de reintentos aparte, que se reexamina una vez por barrido. Con eso:

- La certificación se limita a justo antes del reintento pendiente más antiguo: `certified_until = min(horizon, oldest_pending_retry - ε)`. La frontera de lectura puede avanzar, pero lo que se declara "terminado" no puede saltar por encima de un fallo pendiente.
- Excluir de la lectura de filas nuevas las que ya tienen reintento pendiente, para no examinar dos veces lo mismo en un barrido.
- Una fila sale de la tabla de reintentos cuando se procesa bien o cuando se descarta de forma explícita (con log y motivo), nunca en silencio.

## Riesgo principal: confirmaciones tardías

Una transacción fija el timestamp de una fila (`created_at = now()`) y confirma tarde. Mientras tanto, el barrido leyó hasta un horizonte posterior a ese timestamp y avanzó la frontera: la fila aparece detrás de la frontera y ningún barrido la vuelve a leer. Es una pérdida silenciosa, no una demora.

Opciones, de mejor a peor:

1. **Fence de lock.** Elegir una fila de lock que todo escritor y el lector compartan (por ejemplo, la fila padre o una fila de control por partición). Todo escritor toma `FOR SHARE` sobre ella **antes** de fijar el timestamp; el lector toma `FOR UPDATE` sobre la misma fila **antes** de leer el reloj para fijar el horizonte, en `READ COMMITTED`. El `FOR UPDATE` espera a que confirmen o aborten los escritores en curso, así que cualquier fila con timestamp ≤ horizonte ya es visible cuando el lector la busca, y los escritores que empiezan después obtienen un timestamp posterior al horizonte. En `REPEATABLE READ` o superior el snapshot puede ser anterior al lock y el fence no protege. Ojo con el reloj: en Postgres `now()` devuelve el inicio de la transacción y queda fijo aunque el lock se obtenga mucho después. Poner el lock como primera sentencia no alcanza: esa sentencia puede quedar bloqueada hasta después de que el lector fije el horizonte, y `now()` seguiría devolviendo un instante anterior. Ambos lados tienen que leer el reloj después de obtener el lock, con `clock_timestamp()` (o pasando ese valor como parámetro), nunca con `now()` ni `CURRENT_TIMESTAMP`.
2. **xmin del snapshot.** Ordenar la frontera por xid en lugar de por timestamp: guardar el xid de cada fila (`pg_current_xact_id()` en Postgres) y barrer rangos semiabiertos `xmin_anterior <= xid AND xid < xmin_actual`, donde `xmin_actual` es el xmin del snapshot del lector (`pg_snapshot_xmin(pg_current_snapshot())`), con un cursor de paginación aparte dentro del rango. Al terminar, persistir `xmin_actual` como límite inferior inclusivo del barrido siguiente: con un límite estricto (`xid > frontera`), la transacción cuyo xid es igual al xmin, la activa más antigua, se saltearía al confirmar entre barridos. El xmin no sirve para acotar una frontera de timestamp: Postgres asigna el xid recién en la primera escritura, así que una transacción que empezó con lecturas, obtiene su xid después del snapshot e inserta con `created_at = now()` deja la fila detrás de una frontera `(created_at, id)` ya avanzada. Funciona sin tocar a los escritores, pero es más complejo, depende del motor y una transacción larga no relacionada frena todo el barrido; validar la intercalación de una transacción que lee primero y escribe después, y la de la transacción igual al xmin anterior que confirma entre dos barridos.
3. **Margen de tiempo** (leer hasta `now - margen`). Solo es correcto si existe un límite real de duración de transacción que garantice que nada confirma más tarde que el margen. `idle_in_transaction_session_timeout` no lo garantiza: corta sesiones ociosas, no transacciones activas ni largas. `statement_timeout` tampoco acota la transacción completa. Sin ese límite, el margen solo baja la probabilidad de perder filas y agrega demora fija.

**Red de seguridad.** Sumar, con cualquiera de las opciones, un mecanismo que recupere las filas tardías si el fence o el xmin tienen un hueco. Un trigger que solo compara contra la frontera leída al insertar tiene una carrera: con frontera 10, un escritor inserta con timestamp 15, el trigger ve 10 y no encola nada, y la transacción sigue abierta; el lector no ve la fila, barre hasta 20 y avanza la frontera antes de que el escritor confirme. La fila se pierde sin reintento. Dos formas correctas:

- **Trigger serializado con el avance de la frontera.** El trigger `AFTER INSERT` (y `UPDATE` de las columnas de la tupla, si pueden cambiar) toma `FOR SHARE` sobre la fila que guarda la frontera antes de compararla, y encola como reintento la fila si su timestamp ≤ frontera. El avance de la frontera toma `FOR UPDATE` sobre esa misma fila y, ya con el lock, vuelve a leer el rango entre la frontera anterior y el horizonte nuevo antes de escribirla: el `FOR UPDATE` esperó a que confirmaran los escritores que compararon contra la frontera vieja, así que sus filas son visibles en esa relectura, y los que llegan después comparan contra la frontera nueva.
- **Outbox transaccional incondicional.** Cada inserción encola su id en una tabla outbox en la misma transacción, sin comparar timestamps, y el barrido consume el outbox. No depende del reloj ni de la frontera; cuesta una escritura extra por fila.

Medir los huecos del mecanismo principal según la forma elegida. Con el trigger serializado, cada fila que encola es una fila que el barrido no vio: si el conteo es distinto de cero, hay un hueco. Con el outbox entra toda inserción por diseño, así que su volumen no indica nada; contar solo las filas del outbox que el barrido principal todavía no había procesado cuando se consumieron.

## Migración desde barrido completo

Al pasar de barrido completo a incremental, inicializar la frontera y revisar el progreso derivado (certificaciones, marcas de "procesado hasta"). Si el estado anterior no registraba qué filas fallaron, no se pueden reconstruir los reintentos pendientes: reiniciar el progreso derivado (frontera al inicio de la ventana y certificación vacía) para que el primer barrido incremental relea la ventana una vez y encole los fallos, en lugar de certificar huecos.

## Alternativa más débil

Leer varias páginas por corrida (o todas las que entren en el presupuesto) acota la demora sin cambiar el modelo, pero el costo sigue siendo O(ventana) por corrida y crece con ella. Contra una base remota, con latencia por query, el barrido completo puede no entrar en el presupuesto de la corrida y la demora vuelve a crecer. Sirve como paliativo inmediato, no como solución.

## Métricas antes/después

- Filas examinadas por corrida: O(ventana) → O(filas nuevas + reintentos pendientes).
- Demora de punta a punta: de S+1 a 2S ticks → independiente del tamaño de la ventana. Separar dos demoras:
  - **Procesamiento:** con capacidad suficiente (filas nuevas por tick ≤ filas que entran en el presupuesto de un tick), una fila nueva se procesa en uno o dos ticks. Una ráfaga de N filas por encima de esa capacidad necesita al menos ⌈N / capacidad por tick⌉ ticks: el incremental quita las lecturas redundantes, no el presupuesto de procesamiento.
  - **Certificación:** además depende de los reintentos, porque no avanza más allá del reintento pendiente más antiguo. Mientras una fuente siga sin responder, la certificación queda bloqueada; medir y alertar la antigüedad del reintento más viejo.
- Queries y tiempo por corrida con la misma data.

## Validar

- Un test que reproduzca la demora con el modelo anterior (por ejemplo, una ventana de más de 50 filas con página de 25 y una fila nueva que necesita más de un barrido) y pruebe con el modelo incremental que, sin reintentos pendientes y dentro de la capacidad por tick, la misma fila se certifica dentro de la cota.
- Un test con una ráfaga mayor que la capacidad de un tick que pruebe que se drena en ⌈N / capacidad por tick⌉ ticks sin saltear filas.
- Tests contra la base real (Postgres u otro motor real, no mocks del driver) para:
  - el fence: un escritor que fijó el timestamp y confirma después de que el lector pidió el lock no queda detrás de la frontera, incluido un escritor cuya primera sentencia queda bloqueada por el `FOR UPDATE` del lector;
  - los reintentos: una fila no disponible se reintenta, bloquea la certificación hasta procesarse y no se examina dos veces en el mismo barrido;
  - la fila tardía: una inserción con timestamp ≤ frontera la recupera la red de seguridad y el siguiente barrido la procesa, incluida la intercalación en la que el escritor inserta con timestamp > frontera y confirma después de que el lector avanzó la frontera;
  - la monotonía: un intento de retroceder la frontera no la modifica;
  - si las filas pueden cambiar después de procesarse, un update sobre una fila ya procesada vuelve a entrar por el cursor de cambios.
