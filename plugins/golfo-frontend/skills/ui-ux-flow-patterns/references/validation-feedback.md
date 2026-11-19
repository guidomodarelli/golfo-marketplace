# Validación previa y errores viejos

Detalle para formularios, búsquedas, navegaciones, ediciones, modals, selectors y acciones async. El canal de cada mensaje sale de [feedback-channels.md](feedback-channels.md#tabla-de-decisión); el momento de validar un campo, de [Formularios](feedback-channels.md#formularios).

## Contenido

- [Validar antes de la acción](#validar-antes-de-la-acción)
- [Error del campo o condición del proceso](#error-del-campo-o-condición-del-proceso)
- [Errores viejos y contexto de error](#errores-viejos-y-contexto-de-error)
  - [Notificaciones obsoletas](#notificaciones-obsoletas)
- [Feedback de reporte a soporte](#feedback-de-reporte-a-soporte)
- [Tests](#tests)

## Validar antes de la acción

1. Identificar las interacciones críticas: enviar, buscar, navegar, editar, borrar, cargar en forma async.
2. Definir los inputs obligatorios, los estados permitidos y las condiciones que bloquean la acción.
3. Validar justo antes de ejecutar la acción. Si falla, bloquearla (control deshabilitado o handler que retorna) y no disparar el request.
4. Mostrar el error junto al campo o control que lo originó, con qué falló y cómo corregirlo; nunca solo en la consola ni solo en un toast.
5. Quitar el error cuando el usuario corrige el valor.

En navegación y búsqueda, validar formato y obligatoriedad antes de navegar o consultar. En ediciones, validar obligatorios, longitudes mínimas y rangos permitidos; mientras se escribe se puede mostrar texto de ayuda, pero el error sigue la regla de [Formularios](feedback-channels.md#formularios).

```tsx
function handleSearch() {
  if (!isValidShipmentCode(searchTerm)) {
    setSearchError('Ingresá un código de envío de al menos 6 caracteres');
    return;
  }
  setSearchError(null);
  runSearch(searchTerm);
}
```

## Error del campo o condición del proceso

Antes de pintar un input de rojo, preguntar: **¿esto se corrige editando el valor?**

- **Sí → error del campo.** Obligatorio vacío, formato o longitud incorrectos, fuera de rango, código mal tipeado mientras el desafío sigue vigente. Va junto al campo, el campo sigue editable y el error se va al corregir.
- **No → condición del proceso.** Código o link vencido, intentos agotados, cooldown de reenvío, sesión vencida, cupo o plan agotado, recurso que ya no existe. Editar el valor no la resuelve, así que no se presenta como error de formato: va en el mensaje del paso, formulario o sección, con la acción que sí la resuelve ("Pedir otro código", "Iniciar sesión de nuevo", "Ver planes") a la vista. El campo afectado se limpia o se deshabilita **solo** si ya no sirve, y en ese caso el mensaje dice por qué y qué hacer.

Si la UI no distingue las dos cosas, el usuario corrige una y otra vez algo que no tiene arreglo. Un paso bloqueado por una condición legítima siempre muestra cómo salir y, si hay espera, cuándo.

## Errores viejos y contexto de error

Guardar en estados separados la validación, el error de la operación y el contexto de reporte del error. Cuando el usuario cambia el recurso, el filtro o la operación seleccionada, cierra un modal, empieza un intento nuevo o reintenta, limpiar el mensaje y el contexto del error anterior **antes** de que empiece el nuevo request. Nunca dejar visible el error del recurso A mientras el recurso B carga o ya cargó.

### Notificaciones obsoletas

Lo mismo vale para toasts, banners y mensajes de sección, que viven más que el error que los produjo:

- **Cambio de contexto** (otro recurso, otra pestaña del flujo, otro desafío, cerrar sesión): cerrar los toasts persistentes y los mensajes atados al contexto anterior; las respuestas tardías de ese contexto no generan feedback nuevo.
- **Condición resuelta**: el banner de offline, de integración desconectada o de plan vencido se quita cuando la condición termina, sin esperar a que el usuario lo cierre.
- **Reintento exitoso**: reemplaza el error de esa operación (mismo toast o mensaje), no deja el error viejo al lado del éxito.
- **Repetición**: el mismo error dos veces actualiza el mensaje existente (y puede contar los intentos) en lugar de apilar copias.
- **Al volver a una pantalla**: mostrar el estado actual, no errores de una visita anterior.

## Feedback de reporte a soporte

Usar el componente de reporte de errores del proyecto (por ejemplo, un snackbar conectado al error tracker) solo cuando exista un contexto de error real y el fallo sea accionable o lo bastante inesperado para requerir seguimiento de soporte. Para carga, estados de dominio esperados, advertencias, resultados vacíos y validación, usar los canales comunes. Si falta el contexto de error, usar un fallback seguro y no inventar contexto.

El detalle del reporte puede incluir diagnósticos ricos, buscables y sanitizados, e ids de correlación, pero nunca condiciones crudas, payloads de upstream, objetos de request o response, credenciales, tokens ni PII completa. Los callbacks de reintento deben ser seguros y no duplicar una mutation.

## Tests

Cubrir con tests de comportamiento:

- la acción bloqueada y el error junto al campo cuando la validación falla, y su desaparición al corregir el valor;
- la limpieza del error viejo al cambiar la selección;
- el reemplazo o la limpieza del contexto al reintentar;
- los errores accionables con contexto de error y los inesperados sin reintento;
- los estados esperados que nunca renderizan el componente de reporte;
- una condición del proceso (código vencido, límite alcanzado) que muestra su acción de salida y no deja el campo bloqueado sin explicación;
- una respuesta tardía de un contexto anterior que no pisa el estado ni el feedback del actual;
- el cierre de toasts y banners obsoletos al cambiar de contexto o resolverse la condición.
