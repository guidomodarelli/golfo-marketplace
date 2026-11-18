# Regla de uso del feedback de error con reporte a soporte

Algunos proyectos tienen un componente de UI que, además de mostrar el error, lo registra en el sink de diagnóstico de soporte del proyecto (por ejemplo un snackbar o toast conectado a un error tracker). Ese componente es un canal de feedback de errores + registro, no un reemplazo general de los mensajes, snackbars o estados de negocio comunes.

## Usar el componente de reporte únicamente cuando

- existe un contexto de error real generado por el adapter/server de la integración de soporte;
- ocurrió un fallo accionable o inesperado que requiere registro, diagnóstico, soporte o seguimiento, por ejemplo dependencia no disponible, request fallida, partial/unresolved operation, fallo terminal o excepción inesperada;
- el mensaje público puede ser breve, localizado y separado del detail técnico;
- `retry` se habilita solo cuando ejecuta una operación segura/idempotente o una reanudación explícita; un error inesperado sin retry sigue pudiendo usar el componente para registrar el fallo;
- el `detail` técnico puede ser amplio y útil para diagnóstico, pero debe componerse desde una allowlist segura y sanitizada.

Patrón esperado (los nombres dependen del proyecto):

```tsx
<ErrorReportingSnackbar
  show={Boolean(errorMessage && errorContext)}
  message={translate('No pudimos completar la operación. Intentá nuevamente.')}
  errorContext={errorContext}
  isRetryEnabled
  retry={retryOperation}
/>
```

## No usarlo para

- loading, preflight en curso o progreso (mensaje común o `role="status"`);
- estados informativos o warnings esperados del dominio;
- listas vacías, ausencia de resultados o filtros sin coincidencias;
- validación esperable de input antes de ejecutar una operación;
- estados `PROCESSING`, `NO_PROCESS_CHANGE` o `EXTERNAL_REQUIREMENT_PENDING` cuando el resultado es válido y no existe un fallo accionable;
- errores sin contexto de error válido: usar fallback visual seguro y log server-side, sin inventar contexto.

## Detail técnico rico, seguro y trazable

El detail enviado al sink de soporte puede incluir tanta información diagnóstica como sea útil, siempre como proyección allowlisted y sanitizada:

- operación, etapa, categoría y outcome;
- código de error público/interno, status HTTP y upstream status;
- dependencia y route template sin query sensible;
- claves de contexto, engine, atributos allowlisted evaluados y estados `supported/unavailable/unsupported`;
- conteos seguros (`operator_count`, `pending_operator_count`), límites y reintentos;
- `request_id`, `correlation_id`, `trace_id` o `span_id` cuando el contrato real los provea;
- resumen estructurado de la condición solo si elimina secretos, payloads, valores sensibles y PII.

No enviar la condición raw completa, payload upstream, request/response completos, headers, cookies, tokens, secretos, PII completa ni dumps del usuario. Si soporte necesita esos datos, resolverlos server-side usando el `request_id`/Error ID, no publicarlos en el detail.

## Contexto y ciclo de vida

- Obtener el contexto de error desde response/error normalizado; nunca construirlo con payload raw en el componente.
- Limpiar `errorMessage` y `errorContext` al cambiar de recurso/operación, cerrar modal o iniciar un retry para no mostrar un error viejo sobre una selección nueva.
- Mantener un único evento por fallo: no renderizar múltiples componentes de reporte para el mismo error en componentes anidados.
- Mantener `detail` técnico allowlisted y searchable: operación, etapa, categoría, código, dependencia, status, conteos seguros y correlación. No incluir condición completa, request/response, payload upstream, secretos ni datos sensibles del usuario.
- Si el sink de soporte falla, preservar la operación y mostrar el fallback común; registrar el fallo del sink sin generar un segundo error de negocio.

## Tests obligatorios

- Error accionable con contexto de error → muestra el componente de reporte, mensaje público seguro y retry esperado.
- Error inesperado con contexto de error → muestra el componente de reporte con detail rico aunque no exista retry seguro.
- Error sin contexto → muestra fallback visual sin intentar registrar un contexto inventado.
- Loading/informativo/estado de negocio esperado → no renderiza el componente de reporte.
- Cambio de selección, cierre y retry → limpia contexto anterior y evita errores stale.
- El response/log no contiene `request`, `response`, headers, tokens, payload raw, condición completa ni PII.
