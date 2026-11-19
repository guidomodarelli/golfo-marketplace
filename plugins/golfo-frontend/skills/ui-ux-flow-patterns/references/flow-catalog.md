# Catálogo de flujos

Por tipo de flujo: componentes típicos, estados críticos, feedback esperado y productos que lo resuelven bien. Los nombres de componentes son roles: usar el equivalente de la librería del proyecto. Para qué mostrar en cada estado, ver [state-matrix.md](state-matrix.md); para el canal de cada evento, [feedback-channels.md](feedback-channels.md).

## Contenido

- [Colección: lista, tabla o grilla](#colección-lista-tabla-o-grilla)
- [Búsqueda](#búsqueda)
- [Detalle de un recurso](#detalle-de-un-recurso)
- [Formulario de creación o edición](#formulario-de-creación-o-edición)
- [Guardado: manual, autosave y en segundo plano](#guardado-manual-autosave-y-en-segundo-plano)
- [Edición concurrente y conflictos](#edición-concurrente-y-conflictos)
- [Wizard, onboarding y flujos de varios pasos](#wizard-onboarding-y-flujos-de-varios-pasos)
- [Acción destructiva o masiva](#acción-destructiva-o-masiva)
- [Upload de archivos](#upload-de-archivos)
- [Importación, exportación y descargas](#importación-exportación-y-descargas)
- [Dashboard](#dashboard)
- [Settings](#settings)
- [Permisos y límites del plan](#permisos-y-límites-del-plan)
- [Autenticación](#autenticación)
  - [Verificación por código (SMS, email u OTP)](#verificación-por-código-sms-email-u-otp)
- [Pago y checkout](#pago-y-checkout)
- [Inbox y notificaciones](#inbox-y-notificaciones)
- [Chat y tiempo real](#chat-y-tiempo-real)
- [Acciones rápidas: toggles, likes, favoritos](#acciones-rápidas-toggles-likes-favoritos)
- [Escenarios de feedback y recuperación](#escenarios-de-feedback-y-recuperación)

## Colección: lista, tabla o grilla

- **Componentes**: header con título + contador + acción primaria ("Nuevo …"); toolbar con búsqueda, filtros (chips removibles de los activos) y orden; tabla (datos comparables, columnas) o lista/cards (contenido heterogéneo o visual); paginación numerada con total, o "Cargar más"/scroll infinito para feeds; selección con barra de acciones masivas; menú de acciones por fila.
- **Estados críticos**: carga inicial y recarga al filtrar o paginar ([Carga](state-matrix.md#carga)); vacío de primera vez y vacío por filtro ([Vacío](state-matrix.md#vacío)); error de la tabla ([Error](state-matrix.md#error)).
- **Feedback**: el ítem nuevo aparece en la lista ([Con datos](state-matrix.md#con-datos)); archivar, borrar y acciones masivas según [Confirmar o deshacer](feedback-channels.md#confirmar-o-deshacer).
- **Detalles que marcan diferencia**: header de tabla y barra de acciones masivas fijos al scrollear; filtros, orden y página en la URL; volver del detalle a la misma posición; números alineados a la derecha; fila entera clickeable con un link real para abrir en otra pestaña.
- **Referencias**: GitHub Issues (filtros como query editable, contadores abiertos/cerrados), Linear (vistas guardadas, atajos, optimistic UI), Stripe Dashboard (chips de estado, filtros por fecha y monto).

## Búsqueda

- **Componentes**: input con icono, botón de limpiar y atajo (`/` o `Cmd+K`); dropdown de sugerencias con resultados agrupados, término resaltado y navegación con flechas; recientes al enfocar el campo vacío; opción "Buscar '…'" al final; página de resultados con contador y filtros.
- **Estados críticos**: foco con campo vacío (recientes o sugeridas, nunca un dropdown vacío); escribiendo (debounce ~200–300 ms, cancelar pedidos viejos para que una respuesta lenta no pise a la nueva); sin resultados ([Vacío](state-matrix.md#vacío)), con corrección del término si aplica; error que conserva el término ([Error](state-matrix.md#error)).
- **Feedback**: contador de resultados anunciado como mensaje de estado ([Accesibilidad del feedback](feedback-channels.md#accesibilidad-del-feedback)).
- **Referencias**: Algolia/DocSearch (resultados agrupados, recientes y favoritos), Linear y Vercel (`Cmd+K` como paleta de comandos que también ejecuta acciones), Slack (filtros por persona, canal y fecha).

## Detalle de un recurso

- **Componentes**: breadcrumb o "Volver" al listado; título con estado (chip) y acciones primarias; secciones o tabs; panel lateral de metadatos; actividad o historial.
- **Estados críticos**: carga del título y de las secciones ([Carga](state-matrix.md#carga)); not found cuando el recurso no existe y sin permiso cuando existe y no puede verse; secciones que cargan y fallan por separado ([Error](state-matrix.md#error)).
- **Feedback**: edición inline con guardado por campo; cambios de estado visibles en el chip y en la actividad. Canal de cada uno en [Tabla de decisión](feedback-channels.md#tabla-de-decisión).
- **Referencias**: Stripe (página de un pago con timeline de eventos), Linear (issue con propiedades en el panel y edición inline), Notion (propiedades como base de datos editable).

## Formulario de creación o edición

- **Componentes**: labels visibles (no solo placeholder), help text antes del error, campos agrupados con títulos, opcionales marcados (o requeridos, lo que sea minoría), botón primario con verbo + objeto y secundario "Cancelar"; drawer o diálogo para formularios cortos sin salir del contexto, página para los largos.
- **Estados críticos**: inicial (valores por defecto razonables, foco en el primer campo), validación, enviando, error del servidor y éxito según [Formularios](feedback-channels.md#formularios) y [Error](state-matrix.md#error).
- **Feedback**: ver [Formularios](feedback-channels.md#formularios). Al crear: navegar al recurso nuevo o mostrarlo en la lista. Al editar: quedarse en la pantalla.
- **Detalles**: avisar cambios sin guardar al salir; autosave para documentos; no deshabilitar el botón de envío sin decir qué falta (mejor dejarlo activo y mostrar los errores al enviar).
- **Referencias**: GOV.UK (labels claros, error summary con links a campos, "Check your answers"), Stripe Checkout (validación al salir del campo, formato automático de tarjeta).

## Guardado: manual, autosave y en segundo plano

- **Manual** (botón "Guardar cambios"): pending en el botón, inputs editables o bloqueados solo si editarlos durante el guardado los perdería; éxito inline ("Cambios guardados") si el usuario se queda, error en el formulario conservando todo ([Operaciones asíncronas](state-matrix.md#operaciones-asíncronas)).
- **Autosave** (documentos, notas, settings largos): indicador inline persistente cerca del título o del campo con tres estados, "Guardando…", "Guardado hace un momento" y "No se pudo guardar · Reintentar". Sin toasts por cada guardado. Si falla varias veces o se corta la red, el indicador pasa a banner ("Tus cambios se guardan en este dispositivo hasta reconectar") y avisar antes de salir con cambios sin sincronizar. Guardar con debounce y en orden: un guardado viejo que responde tarde no pisa uno más nuevo.
- **En segundo plano** (el usuario sigue trabajando o se va): el control vuelve a `idle` de inmediato, un ítem o chip muestra "Procesando", y el resultado llega por toast si el usuario ya no está ahí o por el cambio del ítem si sigue mirándolo.
- **Referencias**: Google Docs y Notion (indicador de guardado sin toasts), Figma (aviso de cambios sin sincronizar al estar offline).

## Edición concurrente y conflictos

- **Componentes**: aviso de quién más está editando (presencia) cuando hay edición simultánea; diálogo o panel de conflicto con "Tu versión" frente a "Versión actual" y acciones explícitas.
- **Estados críticos**: guardado rechazado por versión vieja (409 o ETag que no coincide, según [Errores HTTP](state-matrix.md#errores-http)); recurso borrado por otro mientras se editaba (404).
- **Feedback y salida**: mensaje de formulario o diálogo que dice qué cambió y quién, con "Recargar y perder mis cambios", "Revisar diferencias" y, solo si el dominio lo permite, "Sobrescribir". Los cambios del usuario nunca se descartan sin que lo elija; si el recurso ya no existe, ofrecer copiar lo escrito.
- **Referencias**: Google Docs y Figma (presencia y fusión en tiempo real), GitHub (conflicto al editar un archivo con cambios nuevos), Confluence (aviso de edición simultánea).

## Wizard, onboarding y flujos de varios pasos

- **Componentes**: stepper o indicador "Paso 2 de 4" con títulos de pasos; una pregunta o tema por paso; "Atrás" que conserva lo cargado y "Continuar"; paso de revisión ("Revisá tus datos") con links "Cambiar"; página de confirmación con qué sigue. Para onboarding de producto: checklist corto (≤5 ítems) persistente y salteable, datos de ejemplo o plantillas, tours de ≤5 pasos que se pueden saltar y reabrir.
- **Estados críticos**: progreso guardado al salir (autosave o "Guardar y seguir después"); validación por paso antes de avanzar; error al enviar al final sin perder pasos previos ([Error](state-matrix.md#error)); pasos salteados que quedan pendientes en el checklist en vez de perderse.
- **Feedback**: el stepper marca completados; la confirmación final es una página ([Tabla de decisión](feedback-channels.md#tabla-de-decisión)).
- **Referencias**: GOV.UK (one thing per page, check answers, confirmation page con número de referencia), Stripe Connect onboarding (pasos con estado y retomar luego), Notion/Linear (onboarding con plantillas y workspace de ejemplo).

## Acción destructiva o masiva

- **Componentes**: acción en menú secundario o zona de peligro (no al lado del primario); botón con estilo destructivo; diálogo de confirmación o toast con deshacer según [la regla](feedback-channels.md#confirmar-o-deshacer); papelera o archivo.
- **Estados críticos**: pending del botón del diálogo ([Carga](state-matrix.md#carga)); error que deja el diálogo abierto con el motivo ([Error](state-matrix.md#error)); éxito parcial en masivas ("Se eliminaron 18 de 20. 2 no se pudieron eliminar: ver") con acceso a los fallidos.
- **Referencias**: Gmail (archivar + "Deshacer"), GitHub (escribir el nombre del repo para borrarlo, danger zone), Primer (guía de borrado sin confirmación para acciones reversibles).

## Upload de archivos

- **Componentes**: drop zone con borde visible, estado de hover al arrastrar y botón/`input type=file` de respaldo; tipos y tamaño máximo visibles **antes** de elegir; lista por archivo con nombre, tamaño, progreso, estado y acciones (cancelar, reintentar, quitar); preview de imágenes.
- **Estados críticos**: validación al seleccionar (tipo y tamaño, antes de subir); progreso por archivo ([Carga](state-matrix.md#carga)); fallo individual con reintento sin rehacer el lote; éxito parcial del lote; offline o red lenta ([Offline y datos desactualizados](state-matrix.md#offline-y-datos-desactualizados)).
- **Feedback**: estado anunciado como mensaje de estado ([Accesibilidad del feedback](feedback-channels.md#accesibilidad-del-feedback)); al terminar, el archivo aparece donde se usa.
- **Por archivo**: progreso real junto a cada archivo (bytes enviados, no tiempo); "Reintentar" en el que falló conserva el archivo elegido; "Cancelar" aborta solo ese. Un archivo: el estado vive en su fila y el botón de enviar el formulario espera a que termine. Varios: resumen del lote ("8 de 10 subidos · 2 con error") con acceso a cada fallido y su motivo (tipo, tamaño, red), y "Reintentar fallidos" sin volver a subir los exitosos ([`partial_success`](state-matrix.md#operaciones-asíncronas)).
- **Referencias**: Google Drive (panel de subidas con progreso por archivo y reanudación), Dropbox, GitHub (arrastrar imagen al editor con placeholder "Uploading…" en el texto).

## Importación, exportación y descargas

- **Descarga inmediata** (archivo chico ya generado): link o botón con nombre, formato y tamaño ("Descargar CSV · 120 KB"); el navegador es el feedback, sin toast.
- **Exportación generada** (tarda): pending en el botón y después proceso en segundo plano con progreso por filas o pasos si se puede medir; al terminar, toast con "Descargar" si el usuario se fue, o el link en el lugar si sigue ahí; email o centro de descargas para exportaciones muy largas. Cancelar visible. Si falla, toast persistente con "Reintentar" y el motivo.
- **Importación**: validar formato y columnas antes de procesar (errores por fila con número de fila y motivo, descargables si son muchos); vista previa con "Importar 240 filas"; progreso real; resultado parcial con "Se importaron 230 de 240" y el detalle de las 10 rechazadas para corregirlas y reimportar solo esas. Si se cancela, decir qué quedó importado.
- **Referencias**: Stripe (exportes en segundo plano con aviso al terminar), Shopify (importación de productos con vista previa y errores por fila), Airtable (importación CSV con mapeo de columnas).

## Dashboard

- **Componentes**: KPIs con valor, período y comparación; gráficos con período seleccionable; listas de "requiere atención"; cada widget en su propio boundary.
- **Estados críticos**: carga, vacío y error por widget ([Carga](state-matrix.md#carga), [Vacío](state-matrix.md#vacío), [Error](state-matrix.md#error)), con el vacío explicado en vez de un cero engañoso; datos desactualizados ([Offline y datos desactualizados](state-matrix.md#offline-y-datos-desactualizados)).
- **Referencias**: Stripe (resumen con comparación de períodos), Vercel (estado de deployments con tiempo relativo), Plausible (métricas simples con período en la URL).

## Settings

- **Componentes**: navegación por secciones; cada sección con su guardado explícito, o guardado por control para toggles; zona de peligro separada al final.
- **Estados críticos**: cambios sin guardar visibles (botón habilitado solo con cambios, aviso al salir); guardando y error por sección ([Formularios](feedback-channels.md#formularios), [Error](state-matrix.md#error)); toggles que fallan vuelven a su valor con el motivo.
- **Feedback**: toggle con efecto inmediato y formulario con botón según [Tabla de decisión](feedback-channels.md#tabla-de-decisión) y [Formularios](feedback-channels.md#formularios).
- **Referencias**: GitHub settings (secciones con su botón, danger zone), Linear (preferencias con efecto inmediato).

## Permisos y límites del plan

- **Sin permiso para ver**: región "sin permiso" con qué existe, quién puede dar acceso y "Pedir acceso" ([Vacío](state-matrix.md#vacío), 403 en [Errores HTTP](state-matrix.md#errores-http)).
- **Sin permiso para una acción**: preferir mostrar la acción deshabilitada con el motivo (tooltip accesible o texto) si saber que existe ayuda, u ocultarla si no; si el servidor la rechaza igual, mensaje junto a la acción, sin reintento.
- **Límite del plan o cuota**: aviso preventivo en banner al acercarse ("Usaste 9 de 10 proyectos"); al alcanzarlo, la acción explica el límite y ofrece la salida (mejorar el plan, liberar espacio, contactar al administrador si el usuario no puede pagar). Nunca dejar que el usuario complete un formulario largo para recién rechazarlo por el plan.
- **Plan vencido o integración desconectada**: banner persistente en las páginas afectadas con la acción que lo resuelve, que se quita al resolverse.
- **Referencias**: Notion y Linear (pedir acceso a una página), Vercel y GitHub (avisos de uso del plan y límites con la acción para ampliarlos).

## Autenticación

- **Componentes**: un formulario mínimo; proveedores sociales; "Mostrar contraseña"; recuperar contraseña; mensajes que no revelan si una cuenta existe cuando eso importa para la seguridad.
- **Estados críticos**: enviando; credenciales incorrectas (mensaje genérico, input conservado salvo la contraseña); cuenta bloqueada o no verificada con la salida concreta; sesión vencida que vuelve al lugar donde estaba el usuario ([Error](state-matrix.md#error)).
- **Referencias**: Slack y Notion (magic link con pantalla "Revisá tu email" que dice a qué dirección se envió y permite reenviar), GitHub (2FA con alternativas visibles).

### Verificación por código (SMS, email u OTP)

Caso de referencia: en un flujo de solicitud de acceso, al vencer el código SMS el input quedaba bloqueado con un mensaje rojo fijo y sin forma clara de pedir otro. Un código vencido es una **condición del proceso**, no un error de formato del input ([error del campo o condición del proceso](validation-feedback.md#error-del-campo-o-condición-del-proceso)): el usuario nunca debe quedar atrapado.

- **Componentes**: a dónde se envió el código (número o email enmascarado) con "Cambiar"; input de código (`inputmode="numeric"`, `autocomplete="one-time-code"`, pegado del código completo); botón "Verificar"; "Reenviar código" con su estado; alternativas cuando el SMS no llega.
- **Estados**:

| Estado | Qué se ve | Input y controles | Salida |
|---|---|---|---|
| Esperando código | Destino enmascarado y, si el backend lo informa, cuánto falta para que venza | Input editable; "Reenviar" según el cooldown real | Ingresar el código |
| Verificando | Pending en "Verificar" | Input de solo lectura mientras dura; sin doble envío | Resultado |
| Incorrecto (el desafío sigue vigente) | Error junto al campo: "El código no coincide. Revisalo e intentá de nuevo"; intentos restantes si el backend los informa | Input editable con el valor seleccionado para reescribir | Corregir y verificar |
| Vencido | Mensaje del paso: "El código venció" con "Pedir otro código" visible en el mismo mensaje; toast descartable opcional, nunca como única salida | Input deshabilitado o vaciado **porque ya no sirve**, con el motivo; "Pedir otro código" habilitado | Reenviar |
| Reenviando | Pending en "Reenviar código" ("Enviando…") | No se puede volver a pedir mientras dura | Resultado del reenvío |
| Reenvío exitoso | "Te enviamos un código nuevo a ••• 4821" en `role="status"` | Input limpio, habilitado y enfocado; se borran el código anterior, su error y el mensaje de vencido; temporizador y desafío nuevos desde la respuesta del backend | Ingresar el código nuevo |
| Reenvío fallido | Mensaje del paso: "No pudimos enviar el código" con "Reintentar"; **no** decir que se envió | Se conserva la salida ("Reintentar", alternativas) | Reintentar o alternativa |
| Cooldown o límite (429) | "Podés pedir otro código en 0:45" (o la hora) si el backend lo informa; si no, que se podrá más tarde | "Reenviar" deshabilitado con ese motivo visible; se habilita solo al vencer | Esperar o alternativa |
| Intentos agotados o desafío bloqueado | Qué pasó y qué sigue ("Por seguridad, pedí un código nuevo" o "Esperá 15 minutos") | Verificar deshabilitado con el motivo | La salida que permita la política de seguridad |
| Error de conexión | Junto a "Verificar" o "Reenviar": "No pudimos conectar. Probá de nuevo" | Input conservado | Reintentar la misma acción |

- **Reglas**:
  - Distinguir incorrecto, vencido, verificando, reenviando, límite de intentos y error de conexión: cada uno tiene copy, canal y salida propios. Si el backend no los diferencia, pedir que lo haga antes que adivinar en el cliente.
  - El temporizador, el cooldown y el límite salen del estado real del backend (vencimiento, `Retry-After`, intentos restantes), no de un contador local que se desincroniza al recargar o cambiar de pestaña.
  - Cada envío crea un desafío con su id; la respuesta tardía de un reenvío o una verificación de un desafío anterior se descarta y no pisa el código ni los mensajes del vigente ([recuperación de operaciones](state-matrix.md#recuperación-de-operaciones)).
  - Alternativas cuando no llega el SMS: corregir el número, recibir por llamada o email, códigos de respaldo o contactar a soporte, según lo que el producto ofrezca.
  - La UX no debilita la seguridad: no revelar si el número o la cuenta existen cuando importa, no saltear límites de intentos ni cooldowns, no aceptar códigos vencidos ni ampliar su vigencia desde el cliente. Si una restricción bloquea, se explica; no se quita.
- **Referencias**: GitHub y Google (2FA con alternativas y códigos de respaldo), Stripe y WhatsApp (reenvío con cuenta regresiva y cambio de número), NIST SP 800-63B (límites de intentos y vigencia de autenticadores).

## Pago y checkout

- **Componentes**: resumen del pedido siempre visible con total final (sin sorpresas al último paso); campos con formato automático; métodos guardados; botón con el monto ("Pagar $12.000").
- **Estados críticos**: procesando ([Carga](state-matrix.md#carga)) con aviso de no cerrar; rechazo con el motivo accionable (fondos, datos, otro medio) según [Error](state-matrix.md#error); resultado pendiente o asíncrono (transferencia, revisión) con qué esperar; éxito con página de confirmación y comprobante.
- **Feedback**: la confirmación es una página dedicada (y email) según [Tabla de decisión](feedback-channels.md#tabla-de-decisión).
- **Rechazado**: mensaje en el formulario de pago con el motivo accionable, datos conservados (salvo el código de seguridad si el proveedor lo exige) y "Usar otro medio".
- **Pendiente**: página o estado que dice qué se espera (acreditación, revisión), cuánto suele tardar (como [estimación](system-status.md#progreso-real-o-estimación), nunca como plazo exacto) y cómo se avisará; sin botón de pagar de nuevo.
- **Resultado incierto** (timeout, cierre de la ventana, respuesta perdida): "No pudimos confirmar el pago" con "Comprobar estado"; nunca reintentar el cobro automáticamente ni ofrecer "Pagar de nuevo" sin consultar el estado de la operación (id o clave de idempotencia) ([recuperación de operaciones](state-matrix.md#recuperación-de-operaciones)).
- **Referencias**: Stripe Checkout, Shopify checkout (total visible, validación al salir del campo, estados de pago pendiente).

## Inbox y notificaciones

- **Componentes**: badge de no leídas en el acceso; lista con leído/no leído distinguible; acciones rápidas (marcar leído, archivar) con deshacer; filtros (todas, menciones, no leídas); "Marcar todo como leído".
- **Estados críticos**: vacío vaciado por el usuario ([Vacío](state-matrix.md#vacío)); nuevas notificaciones mientras se mira la lista (aviso "3 nuevas" para insertarlas, sin mover lo que el usuario está leyendo).
- **Referencias**: GitHub notifications (agrupación por repo, done + undo), Gmail (inbox cero, archivar + deshacer), Linear inbox.

## Chat y tiempo real

- **Componentes**: composer que conserva el borrador; mensajes con estados enviando/enviado/fallido; indicador de escribiendo; presencia; separadores de fecha y "nuevos mensajes".
- **Estados críticos**: mensaje fallido con "Reintentar" ([Error](state-matrix.md#error)); reconexión ([Offline y datos desactualizados](state-matrix.md#offline-y-datos-desactualizados)) y resincronización; historial paginado hacia arriba sin saltos de scroll; llegada de mensajes con el scroll fuera del final (aviso "Nuevos mensajes ↓" en vez de saltar).
- **Envío fallido**: el mensaje queda en el hilo, en su lugar, marcado "No enviado" con "Reintentar" y "Eliminar" junto a él (no en un toast); el texto nunca se pierde. Cada mensaje lleva un id del cliente para que el reintento no lo duplique.
- **Reconexión del socket**: tras unos segundos sin conexión, indicador discreto "Reconectando…" (banner si sigue caído); al volver, pedir lo que llegó mientras tanto, reenviar en orden los pendientes y quitar el indicador sin anunciar cada mensaje recuperado.
- **Referencias**: Slack, WhatsApp Web, Discord (estados de envío y reconexión).

## Acciones rápidas: toggles, likes, favoritos

- **Componentes**: el control mismo cambia de estado al instante (optimistic), con contador si aplica.
- **Estados críticos**: falla del servidor que revierte el control con un toast de error breve ([Error](state-matrix.md#error)); clics repetidos coalescidos.
- **Feedback**: el cambio del control es el feedback, sin toast de éxito ([Tabla de decisión](feedback-channels.md#tabla-de-decisión)).
- **Implementación**: ver la skill `optimistic-action-mutations`.
- **Referencias**: Linear (cambios de estado instantáneos), GitHub (star), X/Instagram (like).

## Escenarios de feedback y recuperación

Índice de navegación, no un resumen: cada fila enlaza el escenario con la sección que lo describe y con las secciones canónicas donde se definen el canal, la duración, el estado del control y la salida. Las reglas (reintentos, códigos HTTP, duraciones, qué se conserva) se leen solo en esas secciones; los canales, en la [ficha por canal](feedback-channels.md#ficha-por-canal).

| Escenario | Dónde se definen canal, duración, control y salida |
|---|---|
| [Guardado manual](#guardado-manual-autosave-y-en-segundo-plano) | [Operaciones asíncronas](state-matrix.md#operaciones-asíncronas), [Formularios](feedback-channels.md#formularios) |
| [Autosave](#guardado-manual-autosave-y-en-segundo-plano) | [Operaciones asíncronas](state-matrix.md#operaciones-asíncronas), [Ficha por canal](feedback-channels.md#ficha-por-canal) |
| [Guardado o tarea en segundo plano](#guardado-manual-autosave-y-en-segundo-plano) | [Recuperación de operaciones](state-matrix.md#recuperación-de-operaciones), [Toast persistente y descartable](feedback-channels.md#toast-persistente-y-descartable) |
| [Envío de formulario](#formulario-de-creación-o-edición) | [Validar antes de la acción](validation-feedback.md#validar-antes-de-la-acción), [Formularios](feedback-channels.md#formularios), [Operaciones asíncronas](state-matrix.md#operaciones-asíncronas) |
| [Error de campo frente a error general](validation-feedback.md#error-del-campo-o-condición-del-proceso) | [Tabla de decisión](feedback-channels.md#tabla-de-decisión), [Ficha por canal](feedback-channels.md#ficha-por-canal) |
| [Error de red puntual](state-matrix.md#recuperación-de-operaciones) | [Offline y datos desactualizados](state-matrix.md#offline-y-datos-desactualizados), [Tabla de decisión](feedback-channels.md#tabla-de-decisión) |
| [Offline persistente](state-matrix.md#offline-y-datos-desactualizados) | [Ficha por canal](feedback-channels.md#ficha-por-canal) |
| [Upload de un archivo o varios](#upload-de-archivos) | [Operaciones asíncronas](state-matrix.md#operaciones-asíncronas) |
| [Descarga, importación y exportación](#importación-exportación-y-descargas) | [Operaciones asíncronas](state-matrix.md#operaciones-asíncronas), [Recuperación de operaciones](state-matrix.md#recuperación-de-operaciones) |
| [Proceso largo](state-matrix.md#operaciones-asíncronas) | [Recuperación de operaciones](state-matrix.md#recuperación-de-operaciones), [Tabla de decisión](feedback-channels.md#tabla-de-decisión) |
| [Reintento con backoff](state-matrix.md#recuperación-de-operaciones) | [Reintentos visibles](system-status.md#reintentos-visibles), [Error](state-matrix.md#error), [Errores HTTP](state-matrix.md#errores-http) |
| [Espera con tope o sin límite](system-status.md#límites-de-tiempo) | [Progreso real o estimación](system-status.md#progreso-real-o-estimación), [Recuperación automática o intervención del usuario](system-status.md#recuperación-automática-o-intervención-del-usuario) |
| [Sesión expirada (401)](state-matrix.md#errores-http) | [Error](state-matrix.md#error), [Ficha por canal](feedback-channels.md#ficha-por-canal) |
| [Permisos insuficientes (403) y límites del plan](#permisos-y-límites-del-plan) | [Errores HTTP](state-matrix.md#errores-http), [Error](state-matrix.md#error) |
| [No encontrado (404)](state-matrix.md#errores-http) | [Ficha por canal](feedback-channels.md#ficha-por-canal) |
| [Conflicto de edición (409)](#edición-concurrente-y-conflictos) | [Errores HTTP](state-matrix.md#errores-http) |
| [Rechazo de datos (422)](state-matrix.md#errores-http) | [Formularios](feedback-channels.md#formularios) |
| [Demasiados intentos (429)](state-matrix.md#errores-http) | [Error](state-matrix.md#error) |
| [Falla del servidor (5xx)](state-matrix.md#errores-http) | [Recuperación de operaciones](state-matrix.md#recuperación-de-operaciones) |
| [OTP incorrecto, vencido, reenviado o limitado](#verificación-por-código-sms-email-u-otp) | [Error del campo o condición del proceso](validation-feedback.md#error-del-campo-o-condición-del-proceso), [Errores HTTP](state-matrix.md#errores-http) |
| [Acción optimista con rollback](#acciones-rápidas-toggles-likes-favoritos) | [Operaciones asíncronas](state-matrix.md#operaciones-asíncronas), [Tabla de decisión](feedback-channels.md#tabla-de-decisión) |
| [Eliminación reversible](feedback-channels.md#confirmar-o-deshacer) | [Ficha por canal](feedback-channels.md#ficha-por-canal), [Toasts](feedback-channels.md#toasts) |
| [Pago rechazado, pendiente o incierto](#pago-y-checkout) | [Recuperación de operaciones](state-matrix.md#recuperación-de-operaciones), [Operaciones asíncronas](state-matrix.md#operaciones-asíncronas) |
| [Mensaje de chat fallido y reconexión](#chat-y-tiempo-real) | [Recuperación de operaciones](state-matrix.md#recuperación-de-operaciones), [Offline y datos desactualizados](state-matrix.md#offline-y-datos-desactualizados) |
| [Resultado ya visible en la UI](feedback-channels.md#tabla-de-decisión) | [Ficha por canal](feedback-channels.md#ficha-por-canal) |
| [Error persistente que requiere intervención](feedback-channels.md#tabla-de-decisión) | [Ficha por canal](feedback-channels.md#ficha-por-canal) |
| [Errores viejos y notificaciones obsoletas](validation-feedback.md#notificaciones-obsoletas) | [Errores viejos y contexto de error](validation-feedback.md#errores-viejos-y-contexto-de-error) |
