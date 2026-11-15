# Matriz de estados

Fuente única de qué mostrar en cada estado de una región que trae datos o ejecuta acciones. Los tiempos y criterios salen de las fuentes de [sources.md](sources.md).

## Contenido

- [Estados](#estados)
- [Carga](#carga)
  - [Skeleton](#skeleton)
- [Vacío](#vacío)
- [Con datos](#con-datos)
- [Error](#error)
  - [Errores HTTP](#errores-http)
- [Operaciones asíncronas](#operaciones-asíncronas)
  - [Recuperación de operaciones](#recuperación-de-operaciones)
- [Offline y datos desactualizados](#offline-y-datos-desactualizados)
- [Copy de los estados](#copy-de-los-estados)
- [Anti-patrones](#anti-patrones)

## Estados

| Estado | Cuándo ocurre | Pregunta que responde la UI |
|---|---|---|
| Carga inicial | Primera vez que la región pide datos | ¿Qué va a aparecer acá? |
| Recarga / refetch | Ya hay datos y se piden de nuevo (filtro, paginado, refresco) | ¿Lo que veo sigue siendo válido? |
| Vacío: primera vez | El usuario todavía no creó nada | ¿Para qué sirve esto y cómo empiezo? |
| Vacío: sin resultados | Un filtro o búsqueda no devuelve nada | ¿Por qué no hay nada y cómo amplío? |
| Vacío: vaciado por el usuario | Completó o borró todo (inbox cero, carrito vacío) | ¿Terminé? ¿Qué sigue? |
| Vacío: sin permiso o no disponible | Existe contenido pero el usuario no puede verlo, o la feature no está configurada | ¿Qué me falta para acceder? |
| Con datos: uno | Un solo ítem | ¿La UI sigue teniendo sentido con uno? |
| Con datos: muchos | Cientos o miles, textos largos | ¿Puedo encontrar lo que busco? |
| Parcial | Algunas partes cargaron y otras no | ¿Qué es confiable y qué falló? |
| Error total | No se pudo cargar la región | ¿Es mi culpa? ¿Puedo reintentar? |
| Error de acción | Falló una mutación (guardar, borrar, enviar) | ¿Se perdió lo que hice? ¿Qué hago? |
| Offline / desactualizado | Sin red o datos viejos | ¿Lo que veo es actual? ¿Se guarda lo que hago? |

No todas las regiones tienen todos los estados: descartar uno explícitamente ("esta lista nunca está vacía porque siempre existe el dueño") es una decisión válida; olvidarlo no.

## Carga

Elegir el indicador por **duración esperada** y **si se conoce la forma del resultado**:

| Espera | Indicador |
|---|---|
| < ~300 ms | Nada. Un loader que parpadea unas decenas de ms se lee como un glitch. Si el indicador ya apareció, mantenerlo un mínimo (~300–600 ms) para que no destelle. |
| ~300 ms – ~2 s, layout conocido | **Skeleton** con la forma final (mismas filas, columnas, alturas) para evitar saltos de layout. |
| Acción puntual en un control | **Pending en el control**: el botón conserva su ancho, muestra spinner o texto en gerundio ("Guardando…") y queda deshabilitado para evitar el doble envío. |
| Espera corta sin forma predecible | Spinner chico **en el lugar** donde va a aparecer el resultado, nunca bloqueando la pantalla entera. |
| > ~10 s o medible (upload, export, import) | **Barra de progreso determinada** con porcentaje o pasos, opción de cancelar y, si es largo, permitir seguir usando la app y avisar al terminar. Una barra falsa que se clava destruye la confianza. |

Reglas:

- **Recarga ≠ carga inicial.** Con datos ya visibles, no volver al skeleton: mantener los datos anteriores con un indicador sutil (opacidad reducida, barra fina arriba, spinner en el control que disparó la recarga) y bloquear solo lo que no es válido. Volver al skeleton hace perder el lugar y el scroll.
- Cargar por **región**: la chrome (navegación, header, filtros) aparece al instante y cada bloque carga por su cuenta; un bloque lento no bloquea a los demás.
- Texto plano ("Cargando…") o un spinner centrado en la página son aceptables solo cuando no existe forma conocida (por ejemplo una pantalla de redirección).

### Skeleton

El skeleton anticipa **qué va a aparecer y dónde**: sirve si el usuario reconoce la forma del contenido y si esa forma no salta al llegar los datos. Si no cumple las dos cosas, es ruido que se mueve.

**Cuándo sí:** carga inicial de una región con layout conocido (lista, tabla, tarjetas, detalle, formulario de edición que se precarga, widget de dashboard) cuya espera supera ~300 ms. En Next.js con App Router es el fallback natural de `loading.tsx` o de un `<Suspense>` de esa región; dónde va cada boundary lo decide `nextjs-route-ui-boundaries`.

**Cuándo no:**

| Situación | En lugar del skeleton |
|---|---|
| Acción en un control (guardar, enviar, borrar) | Pending en el control |
| Recarga, filtro o paginado con datos visibles | Datos anteriores con indicador sutil ([regla de recarga](#carga)) |
| Espera < ~300 ms | Nada |
| Layout desconocido o muy variable | Spinner chico o texto en el lugar del resultado |
| Proceso largo y medible | Barra de progreso determinada |
| Respuesta vacía o con error | El vacío o el error correspondientes: el skeleton nunca los reemplaza |

**Cómo hacerlo:**

- **Misma forma que el contenido final**: mismas columnas y alturas de fila, avatar, título y metadatos en su lugar, mismos radios y espaciados del sistema de diseño. Usar el `Skeleton` del proyecto, no uno nuevo.
- **Cantidad realista**: tantas filas como el tamaño de página o la cantidad típica, no una pantalla llena si suelen venir tres. Anchos de texto variados (por ejemplo 60–90 %) en lugar de bloques idénticos.
- **Lo estático se renderiza real**: títulos, encabezados de tabla, toolbar, filtros y botones de crear aparecen desde el inicio y siguen usables; solo se esquematiza lo que depende de los datos.
- **Una región, un skeleton**: cada región que carga por su cuenta tiene el suyo y se resuelve sola; nunca un skeleton de página entera que tape la navegación.
- **Sin salto al reemplazarlo**: el contenido ocupa el mismo espacio que el skeleton (sin layout shift); sin fades largos.
- **Sin parpadeo**: si los datos suelen llegar rápido, mostrarlo recién después de ~150–300 ms; una vez visible, mantenerlo un mínimo (~300–500 ms).
- **Siempre termina**: el skeleton sale a datos, vacío o error; si el pedido falla o vence, pasa al error con reintento, nunca queda "cargando" para siempre.
- **Accesible**: `aria-busy="true"` en la región, el skeleton con `aria-hidden` y un texto de estado para lectores ("Cargando pagos") en una live region; el foco nunca entra en un placeholder; con `prefers-reduced-motion`, sin shimmer (opacidad fija).
- **Testeado**: aparece en la carga inicial, no reaparece al recargar, y se reemplaza por datos, vacío o error.

## Vacío

Todo estado vacío responde **qué es esto, por qué está vacío y qué hacer ahora**, con una acción concreta. Un vacío no es un error: tono neutro o alentador.

| Tipo | Qué mostrar | Acción |
|---|---|---|
| Primera vez | Título que explica el valor ("Todavía no hay cursos"), una línea de para qué sirve, ilustración opcional y sobria | CTA primario para crear el primero; opcional: importar, plantilla o datos de ejemplo, link a ayuda |
| Sin resultados (filtro/búsqueda) | Repetir el término o los filtros activos ("No hay pagos que coincidan con 'marzo' y 'Pendiente'") | "Limpiar filtros" o quitar filtros de a uno; sugerencias de búsqueda; ofrecer crear el ítem buscado si corresponde |
| Vaciado por el usuario | Mensaje de cierre positivo ("Estás al día") | Siguiente paso natural o nada; no un CTA de "crear" agresivo |
| Sin permiso | Qué existe y qué falta ("Solo los administradores pueden ver los pagos") | Pedir acceso, contactar al dueño o volver; nunca un 404 genérico si el recurso existe y el usuario puede saberlo |
| Feature sin configurar | Qué habilita configurar la feature | CTA a la configuración |

Reglas:

- Mantener la **chrome de la colección** (título, botón de crear, filtros) también en el vacío: si los filtros desaparecen cuando no hay resultados, el usuario no puede quitarlos.
- El vacío por filtro **no** reutiliza el copy de primera vez ("Creá tu primer pago" cuando hay 300 pagos filtrados es falso).
- Un vacío dentro de un bloque chico (widget de dashboard, sección de detalle) es una línea de texto con, como mucho, un link; el empty state grande es para la región principal.
- Diferenciar "vacío" de "todavía cargando" y de "falló": mostrar el vacío solo con una respuesta exitosa sin ítems.

## Con datos

- Probar con **uno** (que no se vea roto un grid de una sola card, que el plural del contador sea correcto) y con **muchos** (paginación o carga incremental, contador total, texto largo truncado con el valor completo accesible, números alineados a la derecha en tablas).
- Mostrar dónde está el usuario en el conjunto ("1–25 de 312") y conservar filtros, orden, página y scroll al volver de un detalle (en la URL cuando se puede compartir).
- Ítems recién creados aparecen donde el usuario los espera (arriba o resaltados un momento), no perdidos en la página 7.

## Error

| Tipo | Canal | Contenido |
|---|---|---|
| Error total de la región | Reemplaza **solo la región** que falló, con la chrome intacta | Qué falló en lenguaje del usuario, botón "Reintentar"; si persiste, camino alternativo (soporte, código de referencia) |
| Error parcial | El bloque que falló muestra su propio error; lo demás queda usable | Igual que el total, acotado al bloque |
| Error de acción (mutación) | Cerca del control que la disparó, o toast con acción si el usuario ya se fue de ahí | Qué no se hizo, que **lo ingresado no se perdió**, cómo reintentar |
| Validación | Inline en el campo + resumen en el formulario al enviar | Ver [validation-feedback.md](validation-feedback.md) y [feedback-channels.md](feedback-channels.md#formularios) |
| Recurso inexistente / sin permiso | Página o región dedicada (not found, forbidden) | Qué pasó y a dónde ir |
| Sesión vencida | Diálogo o redirección que **preserva** el trabajo en curso | Reingresar y volver al mismo lugar |

Reglas:

- **Nunca perder input**: tras un error, el formulario conserva lo escrito y el botón vuelve a estar habilitado.
- Clasificar antes de mostrar: error de red (reintentar), del usuario (corregir), de permisos (pedir acceso), del servidor (reintentar más tarde). Cada clase tiene un copy y una acción distintos.
- No mostrar mensajes crudos del proveedor, stack traces ni ids internos; sí un código o id de referencia corto que soporte pueda buscar.
- Reintentos automáticos solo para operaciones idempotentes y con límite; mostrar que se está reintentando, con el intento y el máximo solo si la política los define ([reintentos visibles](system-status.md#reintentos-visibles)).
- **Nunca un callejón**: si una acción queda deshabilitada por una restricción legítima (límite de intentos, cooldown, permiso, plan), el motivo y la forma de seguir están a la vista ("Podés pedir otro código en 0:45", "Pedile acceso a un administrador"), no solo el control gris.

### Errores HTTP

El código no se muestra; decide el canal, el copy y la salida. Es un punto de partida: si el backend devuelve un código de dominio más preciso, manda ese.

| Código | Qué significa para el usuario | Canal y salida | Qué se conserva |
|---|---|---|---|
| 401 | La sesión venció o no existe | Diálogo o redirección a iniciar sesión que vuelve al mismo lugar; nunca un error genérico | El trabajo en curso (borrador local o reenvío después de reingresar) |
| 403 | Está identificado pero no puede hacer esto | Región "sin permiso" para contenido; inline o mensaje de sección para una acción, con quién puede dar acceso | Todo; no reintentar |
| 404 | El recurso no existe o ya no existe | Región o página dedicada con a dónde ir; si desapareció mientras se editaba, mensaje que lo dice y ofrece copiar lo escrito | Lo escrito, para no perderlo |
| 409 | Conflicto: otro lo cambió, o ya existe | Mensaje de formulario o diálogo que muestra la diferencia y deja elegir (recargar, sobrescribir si se permite, combinar); "ya existe" va junto al campo | Los cambios del usuario |
| 422 | El servidor rechazó datos válidos en forma | Errores por campo si vienen mapeados; si no, mensaje de formulario | Todo el formulario |
| 429 | Demasiados intentos | Inline o mensaje de sección con cuándo se puede volver a intentar (de `Retry-After` o del backend); la acción se habilita sola al vencer | Todo; sin reintento automático antes de tiempo |
| 5xx | Falla del servidor | Error de la región o junto a la acción con "Reintentar"; si persiste, banner y código de referencia | Todo; reintento automático solo si la operación es idempotente |
| Timeout o sin respuesta | No se sabe si llegó | Para lecturas, error con reintento; para mutaciones, [resultado incierto](#recuperación-de-operaciones) | Todo |

## Operaciones asíncronas

Ciclo de vida de guardar, enviar, eliminar, subir, importar, exportar o lanzar una tarea en segundo plano. Esta sección decide **qué ve y puede hacer el usuario** en cada estado; la propagación de errores entre capas, jobs, batches y polling es de `async-operation-error-handling`.

| Estado | Control que la disparó | Qué se ve | Qué se limpia o conserva |
|---|---|---|---|
| `idle` | Habilitado (o deshabilitado con el motivo visible) | Nada extra | — |
| `pending` | [Pending en el control](#carga); nombre accesible conservado o cambiado al gerundio, con `aria-disabled` para que siga enfocable | Progreso real si es medible; el resto de la pantalla sigue usable salvo lo que la operación invalida | El error anterior de esta operación se quita **al empezar** el intento |
| `retrying` (reintento automático) | Igual que `pending`, sin aceptar un segundo envío; cancelar habilitado si la operación lo permite | El mismo indicador pasa a «Reintentando», con el intento y el máximo solo si la política los define ([reintentos visibles](system-status.md#reintentos-visibles)) | Todo lo ingresado; el error del intento fallido no se muestra mientras se reintenta |
| En cola o en segundo plano | Vuelve a `idle` si la operación sigue en el servidor | Chip o fila «En cola» o «Procesando», con la etapa si el backend la informa; el resultado llega por su canal al terminar ([en segundo plano](flow-catalog.md#guardado-manual-autosave-y-en-segundo-plano)) | El id de la operación, para consultar su estado |
| `success` | Vuelve a `idle` (o desaparece si la acción ya no aplica) | El resultado por su canal ([tabla de decisión](feedback-channels.md#tabla-de-decisión)) | Inputs que ya se guardaron; marca de "sin guardar" |
| `error` | Vuelve a habilitarse | Qué no se hizo y cómo seguir, junto a la acción o en la región | **Todo lo ingresado** se conserva |
| `cancelled` | Vuelve a `idle` en lecturas o si el servidor confirmó la cancelación; si una mutación pudo llegar y no hay confirmación, pasa a `unknown` | Estado anterior a la operación, con un aviso breve solo si hubo efectos parciales ("Se importaron 40 filas antes de cancelar") | Lo que el usuario tenía antes; en mutaciones, el id de la operación hasta confirmar su estado |
| `partial_success` | Habilitado para reintentar **solo lo fallido** | Cuántos salieron y cuántos no, con acceso a cada fallido y su motivo | Los ítems exitosos quedan hechos; los fallidos siguen seleccionados o listados |
| `unknown` (resultado incierto) | Deshabilitado para repetir hasta saber; habilitado "Comprobar estado" | "No pudimos confirmar si se envió" con la acción de comprobar | Todo; nunca mostrar éxito ni ofrecer un reintento ciego |

Reglas:

- **Doble envío**: el control deshabilitado no alcanza (Enter, doble toque, otra pestaña); el handler ignora un segundo disparo mientras haya una operación en curso y las mutaciones críticas mandan una clave de idempotencia si el backend la acepta.
- **El control se libera siempre** al terminar, fallar o cancelar. Si queda deshabilitado por una restricción real (cooldown, permiso), lo dice.
- **Progreso real o ninguno**: barra determinada solo con progreso medible (bytes, filas, pasos), junto al archivo o proceso; si no se puede medir, indicador indeterminado con texto del paso actual. Nada de barras que avanzan por tiempo ni spinners infinitos: toda espera de un request tiene un timeout que la lleva a error o a resultado incierto. Ese timeout no es el tope de la operación, y un tiempo restante solo se muestra como estimación medida ([límites de tiempo](system-status.md#límites-de-tiempo), [progreso real o estimación](system-status.md#progreso-real-o-estimación)).
- **Procesos largos** (más de ~10 s): cancelar visible, permitir seguir usando la app y avisar al terminar por el canal que corresponda ([tabla de decisión](feedback-channels.md#tabla-de-decisión), paso 8).

### Recuperación de operaciones

| Situación | Qué hacer |
|---|---|
| Timeout de lectura | Error de la región con "Reintentar"; conservar los datos previos si los había |
| Timeout o corte en una mutación | Tratarlo como **resultado incierto**: consultar el estado (por id de operación o clave de idempotencia) antes de ofrecer repetir; si no se puede consultar, decir que no se sabe y cómo verificarlo ("Revisá tus pagos antes de intentar de nuevo") |
| Error de red puntual | Error junto a la acción con "Reintentar"; banner solo si la conexión sigue caída ([offline](#offline-y-datos-desactualizados)) |
| Error del servidor | "Reintentar" manual; reintento automático solo para operaciones idempotentes, con límite (2–3 intentos) y espera creciente con jitter, mostrando el reintento ([reintentos visibles](system-status.md#reintentos-visibles)) |
| Cancelación | En lecturas, abortar la petición (`AbortController` o equivalente), volver a `idle` y descartar la respuesta abortada. En una mutación que pudo llegar al servidor, abortar en el cliente no prueba que el servidor se detuvo: volver a `idle` solo si el servidor confirma la cancelación (endpoint de cancelación o estado del job); si no, conservar el id de la operación y pasar a **resultado incierto** con "Comprobar estado" antes de permitir otra ejecución, sin ocultar un resultado que sí se completó |
| Respuestas duplicadas o desordenadas | Cada intento lleva un id; solo la respuesta del intento vigente actualiza la UI. Una respuesta tardía de un intento viejo, de otro recurso o de otro desafío se descarta sin feedback |
| Navegación durante la operación | Si la operación sigue en el servidor, dejarla terminar y avisar del resultado por toast; si se perdería trabajo sin guardar, avisar antes de salir; al volver, mostrar el estado real, no el de antes |
| Mutación no idempotente que falló | Nunca reintentarla automáticamente: si hay riesgo de duplicar (pago, envío, alta), resultado incierto y comprobar antes |

## Offline y datos desactualizados

- Avisar con un **banner persistente** mientras dure ("Sin conexión. Los cambios se guardarán al reconectar" o "Mostrando datos de hace 2 horas") y quitarlo solo al recuperarse.
- **Puntual ≠ offline**: una petición que falló con la conexión disponible es un error de esa acción (inline o toast con "Reintentar"), no un banner de "Sin conexión". El banner aparece cuando la conexión sigue caída (evento `offline`, fallos consecutivos o el socket cerrado) y se va solo al volver.
- Marcar los ítems pendientes de sincronizar y no fingir éxito de algo que no llegó al servidor.
- Si una acción no puede funcionar offline, deshabilitarla con el motivo visible, no dejar que falle.
- **Al reconectar**: quitar el banner, anunciar una vez "Conexión restablecida" en `role="status"`, sincronizar lo pendiente (cola con claves de idempotencia) y refrescar los datos sin volver al skeleton; lo que falle al sincronizar queda marcado con su reintento.

## Copy de los estados

- **Qué pasó + qué hacer ahora.** "No pudimos guardar los cambios. Revisá tu conexión y probá de nuevo." mejor que "Error 500".
- Botones con verbo + objeto: "Crear curso", "Guardar cambios", "Eliminar 3 pagos". Evitar "Aceptar", "OK", "Enviar" genéricos, sobre todo en diálogos destructivos.
- Sin culpa ni alarma: "Ese email ya está registrado" y no "Email inválido!!". Sin jerga técnica (`null`, `timeout`, `403`).
- Sentence case, frases cortas, sin signos de exclamación en errores.
- Mismo término para el mismo concepto en toda la app ("miembro" en todos lados, no "miembro", "usuario" y "participante").
- El idioma y el tono los define el producto; las fuentes de UX writing del proyecto mandan.

## Anti-patrones

- Pantalla en blanco mientras carga o cuando la lista está vacía.
- Spinner de página completa para una acción en un botón.
- Volver al skeleton en cada recarga, perdiendo scroll y contexto.
- Skeleton con otra forma que el contenido (la página salta al cargar) o de página entera que oculta la navegación y los filtros.
- Skeleton que nunca termina porque el error o el vacío no tienen su propio estado.
- Mostrar "No hay resultados" mientras todavía está cargando o cuando el pedido falló.
- Empty state de primera vez cuando el vacío es por un filtro.
- Error genérico sin reintento, o que reemplaza toda la pantalla incluida la navegación.
- Borrar el formulario después de un error.
- Toast como único lugar donde aparece un error que el usuario necesita resolver.
- Input bloqueado con un mensaje rojo fijo y ninguna acción para salir (un código vencido sin "Pedir otro código").
- Un toast de "Guardando…" y otro de "Guardado" para la misma operación, o toasts apilados del mismo error.
- Barra de progreso que avanza por tiempo, o spinner sin timeout.
- Spinner mudo mientras el sistema reintenta, o un «intento 2 de 10», un porcentaje o un tiempo restante que el código no conoce ([visibilidad del estado](system-status.md)).
- Reintentar automáticamente un pago, un envío o un alta que puede haberse completado.
