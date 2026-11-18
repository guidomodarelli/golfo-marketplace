# Visibilidad del estado del sistema

Fuente única de cómo se le informa al usuario qué pasa con una operación que tarda, espera, reintenta o corre en segundo plano. Los estados y su ciclo de vida están en [Operaciones asíncronas](state-matrix.md#operaciones-asíncronas); el canal de cada mensaje, en la [tabla de decisión](feedback-channels.md#tabla-de-decisión). La política de reintentos y tiempos (cuántos intentos, cuánto se espera, qué datos expone el contrato) es de `async-operation-error-handling`: acá se decide qué ve el usuario de esa política.

## Contenido

- [Principio](#principio)
- [Inventario por operación](#inventario-por-operación)
- [Reintentos visibles](#reintentos-visibles)
- [Límites de tiempo](#límites-de-tiempo)
- [Progreso real o estimación](#progreso-real-o-estimación)
- [Recuperación automática o intervención del usuario](#recuperación-automática-o-intervención-del-usuario)
- [Tests](#tests)

## Principio

Ninguna operación relevante deja al usuario sin saber **qué está pasando**, **qué puede esperar** y **si tiene que hacer algo**. Un spinner que se ve igual cuando la primera respuesta tarda que cuando el sistema ya va por su tercer reintento esconde justo lo que el usuario necesita para decidir si esperar, cancelar o probar otra cosa. Lo contrario también falla: un número que el sistema no sabe («intento 2 de 10», «75 %», «faltan 2 minutos») miente con precisión. Mostrar lo que el sistema sabe, en el lugar de la operación, y nada más: el detalle técnico no ayuda a decidir.

## Inventario por operación

Para cada operación que tarda, espera, reintenta o corre en segundo plano, responder estas preguntas **leyendo el código** (la constante, la configuración, el contrato o el estado que devuelve el backend), no suponiendo. Es parte del [paso 2](../SKILL.md#2-armar-la-matriz-de-estados) y del ítem 2 del modo liviano: se hace aunque nadie pida feedback.

| Pregunta | Dónde se lee | Si el código no lo define |
|---|---|---|
| ¿Por qué estados puede pasar? (pendiente, en cola, reintentando, en segundo plano, completada, error, parcial, incierta, cancelada) | El cliente, el hook o la máquina de la operación; el enum de estado del backend | Diseñar solo los que existen y anotar los descartados |
| ¿Reintenta sola? ¿Hasta cuántos intentos? | La política de reintentos: constante, opción de la librería (`retry` de TanStack Query, `maxAttempts`), configuración del cliente HTTP | Sin máximo: no se muestra un total |
| ¿Tiene un tiempo máximo? | Timeout o deadline explícito de la política, del job o del backend (`expiresAt`, deadline del job). `Retry-After` no es un tope: dice cuánto esperar antes del próximo intento | Sin tope: no se promete un final |
| ¿El avance es medible? | Eventos de progreso, contadores o etapas que informa el backend | Indicador indeterminado con la etapa o el tiempo transcurrido |
| ¿Se puede cancelar y qué deja hecho? | `AbortController`, endpoint de cancelación, estado del job | Si la espera es larga, decir que no se puede cancelar |
| ¿Sigue si el usuario se va? | Si corre en el servidor o en un worker | Avisar antes de salir si se perdería |
| ¿Quién la recupera? | Reintento automático, reanudación o acción del usuario | — |

Las respuestas deciden qué estados entran a la matriz y qué números puede tener el copy. **Los números del feedback salen del mismo dato que usa el código**: el intento actual del estado del reintento, el máximo de la constante u opción que lo ejecuta y el tope del deadline real. El copy los recibe interpolados (`{attempt}`, `{maxAttempts}`), nunca escritos a mano: si el máximo pasa de 3 a 5, el texto cambia solo. Sumar un límite que no existía (cortar el polling después de N fallos seguidos) es una decisión de diseño válida: pasa a ser una constante que el código aplica, y el número sale de ahí. Lo que no se muestra es un número que nada aplica. Si la política vive en otra capa (BFF, job), el contrato la expone como datos (`async-operation-error-handling` (plugin `golfo-engineering`)).

## Reintentos visibles

| Situación | Qué se ve | Acciones |
|---|---|---|
| Primer intento | El pending normal ([Carga](state-matrix.md#carga)) | Las del pending |
| Reintento automático con máximo conocido | El mismo indicador de la operación pasa a «Reintentando (intento 2 de 3)…», en su lugar, sin sumar otro mensaje | Cancelar, si la operación lo permite; «Reintentar ahora» solo si la espera entre intentos se nota y repetir es seguro |
| Reintento automático sin máximo (reconexión, cola que insiste hasta lograrlo) | «Reintentando…» o «Reconectando…», con el tiempo transcurrido o el próximo intento si el código lo sabe (la espera de la política o el `Retry-After`: «Próximo intento en 0:08») | Cancelar o dejarlo seguir en segundo plano |
| Intentos agotados | Pasa a `error`: qué no se hizo, que ya se reintentó («No pudimos sincronizar después de 3 intentos») y qué hacer ahora | «Reintentar» manual, que arranca el ciclo de nuevo con la misma clave de idempotencia |
| Mutación no idempotente | No se reintenta sola: pasa a [resultado incierto](state-matrix.md#recuperación-de-operaciones) | «Comprobar estado» |

- **Visible desde que demora.** El estado de reintento aparece cuando un intento falló y la espera sigue: el usuario tiene que saber que la demora no es la carga normal. Un reintento inmediato que sale bien antes de que el pending se note no necesita aviso.
- **Un indicador que evoluciona**, no uno por intento: el mismo pending, la fila o el [toast de la operación](feedback-channels.md#un-toast-por-operación) cambia de texto. Al lector de pantalla se le anuncia el cambio de fase (empezó a reintentar, se agotaron los intentos), no cada intento.
- **Sin detalle técnico**: ni el código HTTP, ni los milisegundos de espera, ni el nombre de la excepción. El código de referencia corto va solo en el error final ([Error](state-matrix.md#error)).

## Límites de tiempo

- **Con tope conocido** y una espera que puede pasar los ~10 s, decirlo al empezar a esperar o al pasar a reintentar: «Seguimos intentando hasta 3 minutos». Una cuenta regresiva solo si sale del vencimiento real (deadline del job, `expiresAt`), no de un contador local que se desincroniza al recargar o cambiar de pestaña. `Retry-After` alimenta solo la cuenta del próximo intento, nunca el tope: un 503 con `Retry-After: 60` pide esperar 60 s antes de reintentar, no rendirse a los 60 s.
- **Sin tope definido**, no inventar uno. Mostrar en qué está («En cola», «Procesando el archivo»), el tiempo transcurrido si ayuda y cómo seguir sin esperar («Podés seguir usando la app; te avisamos al terminar»).
- **El timeout de un request no es el tope de la operación.** Cada request o consulta de polling tiene su timeout ([Operaciones asíncronas](state-matrix.md#operaciones-asíncronas)) y al vencer lleva a error o a resultado incierto; ese número no se presenta como la duración máxima de un job que sigue en el servidor.
- Al vencer el tope, la UI pasa a error o a resultado incierto con su salida: nunca queda «reintentando» para siempre.

## Progreso real o estimación

| Lo que el sistema sabe | Qué mostrar | Qué no |
|---|---|---|
| Total y avance medibles (bytes, filas, ítems) | Barra determinada o «120 de 340 filas» | — |
| Etapas que informa el backend | «Paso 2 de 4 · Validando filas» | Etapas inventadas para dar movimiento |
| Solo que está en curso | Indicador indeterminado con la etapa o el tiempo transcurrido | Porcentaje, «x de y» o tiempo restante |
| Una estimación medida (tasa real, historial de duraciones) | Marcada como estimación: «unos 2 minutos», «suele tardar menos de 5 minutos» | Una cuenta regresiva exacta |

- Si el avance deja de llegar, decirlo («Sigue en curso · última actualización hace 1 min») en vez de dejar una barra quieta.
- Un conteo que el sistema no sabe (ítems totales, intentos restantes, posición en la cola) no se muestra ni se aproxima.

## Recuperación automática o intervención del usuario

Cada fase dice si el usuario tiene que hacer algo:

| Fase | Mensaje | Canal | Anuncio |
|---|---|---|---|
| El sistema se recupera solo | Qué pasa y que no hace falta hacer nada («Reconectando…», «Reintentando (intento 2 de 3)…») | El indicador de la operación: control, fila, chip o toast de la operación | `role="status"` al entrar en la fase |
| Ya no puede solo | Qué no se hizo, que ya se intentó y la acción concreta | Error junto a la acción o en la región, persistente | `role="status"`; `role="alert"` si bloquea lo que el usuario está haciendo |
| No se sabe si se hizo | «No pudimos confirmar…» con «Comprobar estado» | Igual | Igual |

- Mientras se recupera sola, el resto de la pantalla sigue usable salvo lo que la operación invalida; si puede tardar, ofrecer seguir en segundo plano.
- Cancelar durante un reintento lo detiene. En una lectura vuelve a `idle`; en una mutación que pudo llegar al servidor aplica la regla de [cancelación](state-matrix.md#recuperación-de-operaciones).

## Tests

Cubrir con tests de comportamiento:

- con la política de reintentos real, configurada con un máximo distinto del default, el indicador muestra el intento actual y ese máximo;
- sin máximo ni tope, no aparece ningún total ni cuenta regresiva;
- al agotarse los intentos, pasa a error con la acción manual y el texto dice que ya se reintentó;
- cancelar durante el reintento detiene los intentos (no salen más requests) y libera el control;
- sin avance medible no se renderiza una barra determinada ni un porcentaje;
- el lector de pantalla recibe un anuncio por fase, no uno por intento.
