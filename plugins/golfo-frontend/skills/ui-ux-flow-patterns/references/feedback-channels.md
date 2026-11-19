# Canales de feedback

Fuente única de qué canal usar para cada evento, cuándo confirmar o deshacer y cómo hacerlo accesible. Los criterios salen de las guías de Material, Carbon, Polaris, Primer, GOV.UK y NN/g citadas en [sources.md](sources.md).

## Contenido

- [Canales](#canales)
- [Tabla de decisión](#tabla-de-decisión)
- [Ficha por canal](#ficha-por-canal)
- [Toasts](#toasts)
  - [Toast persistente y descartable](#toast-persistente-y-descartable)
  - [Un toast por operación](#un-toast-por-operación)
- [Confirmar o deshacer](#confirmar-o-deshacer)
- [Formularios](#formularios)
- [Accesibilidad del feedback](#accesibilidad-del-feedback)

## Canales

Ordenados de menos a más interruptivo:

| Canal | Persistencia | Para qué |
|---|---|---|
| **Cambio directo de la UI** | — | La acción se ve en su resultado: el ítem aparece en la lista, el toggle cambia, el contador sube. Es el mejor feedback; muchas veces no hace falta otro. |
| **Inline junto al control** | Hasta que se resuelve | Estado de un control o campo: pending del botón, "Guardado" al lado de un autosave, error de un campo. |
| **Mensaje de formulario o sección** | Hasta que se resuelve o se reintenta | Resultado general de una operación que afecta a todo el formulario, paso o sección y no a un campo: el servidor rechazó el envío, una condición del proceso impide seguir (código vencido, cupo agotado), resumen de errores al enviar. Va arriba del formulario o dentro de la sección, con su acción de salida. |
| **Badge / indicador** | Mientras dure el estado | Conteos y estados de un objeto ("3 sin leer", chip "Pendiente"). No es interactivo ni reemplaza un mensaje. |
| **Toast temporal** | Se va solo (con pausa al hover/foco) | Confirmación breve de una acción que no está a la vista, el "Deshacer" de una acción reversible aunque su resultado sí se vea, o un fallo puntual y transitorio que no deja nada pendiente, con como mucho **una** acción (normalmente "Deshacer" o "Ver"). |
| **Toast persistente y descartable** | Hasta que el usuario lo cierra o actúa | Error o evento accionable que necesita tiempo de lectura o una acción ("Reintentar") cuando el usuario ya no está en el contexto donde lo disparó. Tiene cierre con una X accesible y nunca es la única salida de un estado bloqueante ([reglas](#toast-persistente-y-descartable)). |
| **Banner / alerta inline de página o sección** | Hasta que se resuelve o se descarta | Condición persistente que afecta a la página: offline, plan vencido, integración desconectada, error que hay que resolver, aviso del sistema. |
| **Diálogo modal** | Bloquea hasta decidir | Decisión que el usuario **tiene** que tomar ahora: confirmar algo irreversible, resolver un conflicto, sesión vencida. |
| **Página / región dedicada** | Es el estado | Not found, sin permiso, error total, confirmación final de un proceso largo (pago realizado, solicitud enviada). |

## Tabla de decisión

Antes de elegir, ubicar el evento en seis ejes; son los que separan un canal de otro:

| Eje | Pregunta | Empuja hacia |
|---|---|---|
| Origen | ¿Lo causó el input del usuario, una condición del proceso, la red, el servidor o un permiso? | Input → campo; proceso → formulario o sección; red o servidor → donde estaba la acción; permiso → región o página |
| Duración | ¿Termina con el evento o sigue vigente? | Puntual → toast o inline; vigente → banner o mensaje de sección que se quita al resolverse |
| Alcance | ¿Un campo, un formulario o sección, la página o toda la app? | El canal vive en la región afectada, no más arriba |
| Severidad | ¿Informa, advierte, impide seguir o puede perder datos? | Impide seguir → mensaje en la región con su salida; riesgo irreversible → diálogo |
| Contexto | ¿El usuario sigue mirando donde actuó o ya se fue? | Sigue ahí → inline o la propia UI; se fue → toast |
| Recuperación | ¿Qué hace el usuario ahora: nada, corregir, reintentar, esperar, pedir acceso? | Sin acción → temporal; con acción → persistente hasta que actúe |

Recorrer en orden y quedarse con la primera respuesta que aplique:

1. **¿Es el cierre exitoso de un flujo largo o con consecuencias?** (pago, envío de solicitud, alta de cuenta) → página o paso de confirmación con qué pasó, qué sigue y un comprobante.
2. **¿El usuario tiene que decidir antes de seguir y la acción no se puede deshacer?** → diálogo de confirmación ([confirmar o deshacer](#confirmar-o-deshacer)).
3. **¿Es sobre un campo o control concreto?** (validación, guardado de un campo, pending) → inline junto al control.
4. **¿Afecta a todo el formulario, paso o sección, o es una condición del proceso que impide seguir?** (el servidor rechazó el envío, el código venció, se agotaron los intentos) → mensaje de formulario o sección con la acción de salida a la vista. No pintar un campo de rojo por algo que no se corrige editándolo ([error del campo o condición del proceso](validation-feedback.md#error-del-campo-o-condición-del-proceso)).
5. **¿El resultado ya se ve en pantalla donde el usuario está mirando y la acción no necesita "Deshacer"?** (el ítem aparece, el valor cambia) → cambio directo de la UI, sin toast. Agregar un toast acá es ruido. **Excepción:** si es una acción reversible que se hace de inmediato y se ofrece deshacer (archivar, mover, quitar una etiqueta, mandar a la papelera; ver [confirmar o deshacer](#confirmar-o-deshacer)), el cambio directo de la UI va acompañado de un toast con "Deshacer" aunque el resultado esté a la vista: ese toast no confirma, da la salida.
6. **¿Falló una acción y el usuario ya no está en el contexto donde la hizo?** → toast persistente y descartable **con acción** ("Reintentar"), o un banner si el problema persiste.
7. **¿Es una condición que sigue vigente y requiere atención o acción?** (error que persiste, offline, falta configurar algo, cuota casi llena) → banner en la página o sección afectada. No toast: un toast que desaparece no sirve para algo que sigue pasando. Un fallo de red **puntual** (una petición que no salió, con la conexión de vuelta) es otra cosa: error junto a la acción o toast temporal con "Reintentar", sin banner.
8. **¿Es la confirmación de una acción que salió bien pero cuyo resultado no está a la vista?** (se envió una invitación, se archivó y el ítem desapareció, se copió al portapapeles, terminó un proceso en segundo plano) → toast temporal, con "Deshacer" si la acción es reversible.
9. **¿Es un conteo o estado de un objeto?** → badge o chip.

Si dos canales parecen válidos, elegir el **menos interruptivo** que garantiza que el usuario lo vea y pueda actuar. No hay regla de "todo éxito o todo error va en toast": el canal sale de estos ejes, y un mismo evento puede llevar dos canales con roles distintos (el mensaje en la sección es la salida; un toast opcional solo avisa).

## Ficha por canal

Elegido el canal, esta tabla fija el resto de la decisión: dónde va, cuánto dura, si se cierra a mano, qué salida ofrece, qué controles siguen activos, qué se limpia y cómo se anuncia.

| Canal | Ubicación | Duración | Cierre manual | Recuperación | Controles | Qué limpiar o restaurar | Anuncio |
|---|---|---|---|---|---|---|---|
| Cambio directo de la UI | El objeto que cambió | Es el nuevo estado | — | Deshacer si es reversible (vía toast) | Todos | Pending del control | Si el cambio no es obvio para un lector, `role="status"` con el resultado |
| Inline de campo | Debajo del campo, asociado con `aria-describedby` y `aria-invalid` | Hasta que el valor es válido | No | Corregir el campo | Campo y envío habilitados | Se quita al corregir, según el momento de validar ([Formularios](#formularios)) | Lo lee el campo al enfocarse; el resumen de errores mueve el foco al enviar |
| Mensaje de formulario o sección | Arriba del formulario o dentro de la sección | Hasta resolver, reintentar o cambiar de contexto | No (se va solo al resolverse) | Acción visible en el mismo mensaje ("Pedir otro código", "Reintentar") | Los que permiten salir habilitados; los que no sirven en esa condición, deshabilitados con el motivo | Errores de campo que ya no aplican y el mensaje al reintentar o cambiar de recurso | `role="alert"` si aparece tras enviar y bloquea; si no, `role="status"` |
| Toast temporal | Región de toasts del proyecto, sin tapar la acción ni el teclado en móvil | ~4–6 s; ~5–10 s con "Deshacer"; pausa al hover o foco | Opcional | Como mucho una acción, también alcanzable por otro camino | No bloquea nada | Se reemplaza, no se apila, si llega otro de la misma operación | `role="status"` (polite) |
| Toast persistente y descartable | Misma región | Hasta cerrar o actuar | Sí, X con nombre accesible y `Escape` con foco dentro | Una acción concreta ("Reintentar", "Ver errores") | No bloquea nada | Se cierra solo si la condición se resolvió o el contexto cambió ([notificaciones obsoletas](validation-feedback.md#notificaciones-obsoletas)) | `role="status"`; `role="alert"` solo si es urgente |
| Banner | Arriba de la página o de la sección afectada | Mientras la condición siga vigente | Solo si es informativo; uno que bloquea no se descarta | Acción que resuelve la condición o explica cuándo se resuelve | Los que no funcionan en esa condición, deshabilitados con el motivo | Se quita al resolverse la condición, con un aviso breve de vuelta a la normalidad si ayuda | `role="status"`; `role="alert"` si aparece por una pérdida que afecta lo que el usuario está haciendo |
| Diálogo | Modal centrado | Hasta decidir | `Escape` y "Cancelar" equivalen a no hacer nada | Las dos opciones con verbo y objeto | Solo los del diálogo | Al cerrar, foco al disparador o al siguiente control lógico | Foco al abrir; título y descripción asociados |
| Página o región dedicada | Reemplaza la región, con la chrome intacta | Es el estado | — | Volver, reintentar, pedir acceso, iniciar sesión | Navegación siempre disponible | Estado previo de la región | Título de la región o de la página como encabezado |

## Toasts

Usar cuando:

- confirman una acción completada fuera de la vista o en segundo plano;
- ofrecen deshacer una acción reversible recién hecha;
- avisan que terminó un proceso largo que el usuario dejó corriendo.

No usar para:

- errores de validación o de un campo (van inline);
- información crítica que hay que leer o resolver (va en banner o diálogo);
- confirmar algo que ya es visible en pantalla (salvo para ofrecer "Deshacer" de una acción reversible: ahí el toast es la vía de deshacer, no una confirmación redundante);
- mensajes largos (más de ~1–2 líneas) o con más de una acción;
- reemplazar el estado de error de una región que no cargó.

Reglas:

- Mostrar de a uno; si se encolan, agrupar ("3 pagos archivados") en vez de apilar diez.
- Duración: ~4–6 s para confirmaciones, ~5–10 s si tienen "Deshacer"; pausar el temporizador con hover o foco. **Los toasts de error con acción no se descartan solos.**
- Copy corto con objeto concreto: "Invitación enviada a ana@…", no "Operación exitosa".
- Tipo por intención: neutro (acuse de una acción), éxito (resultado esperado), info, advertencia, error. Si el proyecto define su propio mapa de tipos (por ejemplo un `toast.promise` para escrituras async), usar ese.
- Para escrituras async, preferir el patrón loading → éxito/error en un solo toast (promise) en lugar de un toast de "Guardando…" y otro de "Guardado" ([un toast por operación](#un-toast-por-operación)).
- La acción de un toast tiene que ser alcanzable con teclado antes de que desaparezca, y no puede ser el único camino a esa acción (ofrecer también deshacer desde la papelera o el historial).

### Toast persistente y descartable

Para un error o evento accionable que no cabe en 5 segundos: "No pudimos enviar la invitación a ana@… · Reintentar".

- **No se descarta solo.** Se va cuando el usuario lo cierra, ejecuta su acción, o la condición deja de existir (el reintento salió bien en otro lado, el usuario cambió de contexto).
- **Cierre con una X accesible**: botón real con nombre ("Cerrar aviso"), alcanzable con `Tab`, área táctil de al menos 24×24 px y `Escape` cuando el foco está en el toast.
- **Una acción concreta** con verbo ("Reintentar", "Ver los 2 archivos con error"), segura de repetir: si la operación no es idempotente, la acción consulta el estado antes de volver a ejecutar ([resultado incierto](state-matrix.md#recuperación-de-operaciones)).
- **No es la única salida de un estado bloqueante.** Si la región o el paso quedaron trabados (un formulario que no puede enviarse, un código vencido), la salida vive **en esa región**; el toast solo avisa y puede faltar. Cerrar el toast nunca deja al usuario sin forma de seguir.
- **No reemplaza el mensaje de la región afectada**: si el usuario sigue en el formulario o la sección donde falló, el error va ahí ([tabla de decisión](#tabla-de-decisión), pasos 3 y 4).

### Un toast por operación

Una operación que justifica feedback global tiene **un** toast con identidad estable (el id de la operación) que evoluciona: loading → éxito o error. No crear uno por estado.

- El toast de loading aparece solo si la operación tarda lo bastante para notarse (mismo umbral de ~300 ms que [Carga](state-matrix.md#carga)); si termina antes, aparece directamente el resultado.
- Al pasar a éxito toma la duración del toast temporal; al pasar a error con acción, se vuelve persistente y descartable.
- Un reintento **actualiza** el mismo toast (vuelve a loading) en lugar de sumar otro, y un éxito posterior reemplaza al error anterior de esa operación.
- Si la operación queda obsoleta (el usuario cambió de recurso, la respuesta llegó tarde para otro contexto), el toast se cierra y la respuesta no produce feedback nuevo.
- Si el resultado ya se ve en la UI donde el usuario está mirando, la operación no necesita toast global: basta el pending del control y el cambio de la UI ([tabla de decisión](#tabla-de-decisión), paso 5).

## Confirmar o deshacer

| Situación | Patrón |
|---|---|
| Reversible y frecuente (archivar, mover, quitar una etiqueta, marcar leído) | Hacer **de inmediato** + toast con "Deshacer" (5–10 s). Sin diálogo: los diálogos frecuentes se aceptan por reflejo. |
| Reversible con papelera o soft delete | Hacer + toast "Movido a la papelera" con "Deshacer"; borrado definitivo desde la papelera. |
| Irreversible y de impacto moderado | Diálogo con título que nombra el objeto ("¿Eliminar el curso 'Álgebra'?"), consecuencia concreta ("Se borrarán 12 lecciones y el progreso de 40 alumnos"), botón destructivo con verbo y objeto ("Eliminar curso") y foco inicial en "Cancelar". |
| Irreversible y de alto impacto (borrar cuenta, organización, base de datos) | Diálogo que pide **escribir el nombre** del recurso para habilitar el botón. |
| Envío que no se puede editar después (mensaje, pago) | Ventana de "Deshacer" corta antes de enviar de verdad (estilo "Deshacer envío" de Gmail) o paso de revisión previo. |
| Acción masiva destructiva | Indicar cuántos ítems afecta en el botón y en la confirmación ("Eliminar 23 pagos"). |

Nunca confirmar con "¿Estás seguro?" + "Sí / No": el diálogo tiene que poder entenderse leyendo solo el botón.

### Confirmación inline

Si el proyecto ya usa confirmación inline para acciones destructivas (su `DESIGN.md` o el resto de la pantalla lo hacen), usarla en lugar del diálogo, con las mismas exigencias de contenido. Si no la usa, quedarse con el diálogo de la tabla anterior: mezclar dos patrones de confirmación en un mismo producto obliga a aprender los dos.

- **Casilla de consentimiento junto al botón destructivo.** El botón queda deshabilitado hasta marcarla, y su texto dice por qué (no solo el estado gris). La etiqueta nombra el recurso afectado y su impacto concreto: "Entiendo que mientras «Soporte» esté suspendida no se envían avisos ni códigos", no "Confirmo la acción".
- **El consentimiento vale para una sola decisión.** Atarlo al id y la versión del recurso, a la acción y a su motivo. Cambiar de recurso, de acción o de motivo, recibir una lectura nueva del recurso o terminar la acción lo desmarca: un consentimiento dado para otro estado no autoriza este.
- **Aviso fijo cuando la acción afecta al recurso en uso** (el activo, el seleccionado, el que hoy atiende a los usuarios). Va en la sección, antes del botón, con texto y no solo color, porque hay que leerlo antes de confirmar. Distinguir explícitamente las acciones que **conservan el lugar** del recurso (suspender, pausar: se puede reanudar y nada lo reemplaza) de las que **lo liberan** (retirar, eliminar: otro recurso o ninguno ocupa su lugar), y decir cuál es.
- **Varios recursos con roles distintos** (activo y candidato, principal y respaldo): el selector muestra el rol y el estado de cada uno. No preseleccionar una acción destructiva sobre el recurso en uso. Si el usuario llega al panel desde una próxima acción ("Retirá la candidata vencida"), preseleccionar el recurso que esa acción nombra.
- **Roles que coinciden en un mismo recurso** (el candidato también es el seleccionado): el texto no promete que "el otro no cambia"; describe el efecto sobre los dos roles.
- **Foco después del éxito.** Si el control que tenía el foco desaparece (la fila retirada, el botón del recurso eliminado), mover el foco al siguiente control lógico, por ejemplo el campo del formulario que lo reemplaza, y no dejarlo caer en el `body`.
- **Resultado de la escritura** por el canal async del proyecto (toast de progreso que pasa a éxito o error, por ejemplo `toast.promise`), salvo que el proyecto defina otro. El aviso fijo describe la condición; el toast, el resultado.

## Formularios

- Validar al salir del campo (blur) o al enviar, no mientras se escribe; si se valida en vivo, esperar a que el usuario deje de tipear (~500 ms) y nunca marcar error en un campo que todavía no tocó.
- Mostrar el error **junto al campo** (debajo, asociado con `aria-describedby`), con texto que dice cómo corregirlo, y no solo con color.
- Al enviar con errores: resumen arriba del formulario con links a cada campo y foco en el resumen o en el primer campo con error.
- Al corregir, el error del campo desaparece en el momento (no esperar a reenviar).
- Botón de envío en pending mientras se procesa; volver a habilitarlo ante error, conservando lo escrito.
- Al guardar bien: si el usuario se queda en la pantalla, inline "Cambios guardados" o toast; si se navega al resultado, el resultado es el feedback (más un toast si el objeto nuevo no es obvio).
- Formularios largos: avisar antes de salir con cambios sin guardar; autosave con indicador "Guardando… / Guardado" cuando el flujo lo permite.

## Accesibilidad del feedback

- Mensajes de estado (WCAG 4.1.3) anunciados sin mover el foco: el contenedor `role="status"` / `aria-live="polite"` existe **antes** de que llegue el mensaje y el texto se inyecta dentro. `role="alert"` (assertive) solo para errores urgentes.
- Diálogos: foco al abrir en el primer control seguro (Cancelar en destructivos), foco atrapado dentro, `Escape` cierra, foco vuelve al disparador al cerrar.
- Estado y error nunca solo por color: icono + texto ("Error:" o el mensaje).
- Spinners y skeletons con texto accesible del estado; el botón en pending conserva su nombre accesible (o lo cambia a "Guardando…").
- Animaciones de entrada y salida dentro de lo que defina el proyecto y respetando `prefers-reduced-motion`.
- **Tiempo suficiente** (WCAG 2.2.1): lo que se descarta solo pausa con hover y foco, y nada con una acción necesaria desaparece antes de que se pueda alcanzar con teclado; si el mensaje hay que leerlo o actuar, es persistente.
- **Toasts que no roban el foco**: se anuncian por la live region y se alcanzan con `Tab` (o el atajo de la región de toasts del proyecto). Al cerrarlos, el foco vuelve a donde estaba.
- **Sin anuncios duplicados ni repetidos**: un evento se anuncia una vez. Si el error ya está en el campo o la sección, el toast opcional no repite el mismo texto en otra live region; un reintento que falla igual actualiza el mensaje existente en lugar de apilar otro idéntico.
- **`role="alert"` es la excepción**: pérdida de datos inminente, sesión por vencer, error que bloquea justo después de enviar. Confirmaciones, progreso y avisos van en `role="status"`.
- **Foco después de un error**: al enviar con errores, foco al resumen o al primer campo; ante un error de sección tras enviar, el mensaje se anuncia y el foco queda en el control que permite salir o en el mensaje si tiene `tabindex="-1"`. Nunca dejar el foco en un control que se deshabilitó.
- **Móvil**: el toast no tapa el teclado virtual, el botón principal ni el campo con error (respetar la safe area); las acciones de toasts y banners tienen área táctil de al menos 24×24 px (WCAG 2.5.8); nada que aparezca oculta el control enfocado (WCAG 2.4.11).
- **El trabajo sobrevive al error**: tras cualquier fallo se conservan los inputs, la selección y el scroll; solo se limpia lo que el usuario debe volver a ingresar por seguridad (contraseña, código vencido).
