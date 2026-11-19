# Matriz de flujo de errores async

## Modelo de boundary

| Boundary | Responsabilidad | Puede conservar | No debe cruzar |
|---|---|---|---|
| Input/command | Validar caller y tamaño/duplicados | código de validación, campos allowlisted | payload raw sin validar |
| Producer/orchestrator | Dividir trabajo y mantener identidad | chunk index seguro, límites, reservation | retry ilimitado o mutación duplicada |
| Upstream adapter | Traducir proveedor a razón estable | status/código upstream, diagnóstico interno | body/headers/response raw |
| Domain service | Decidir semántica de operación | código, estado parcial, runs seguros, `cause` interno | depender de copy o HTTP para dominio |
| API/BFF | Elegir contrato público | status mapeado, DTO allowlisted, ErrorUX seguro | `cause`, stack, request/response completa |
| Browser client/worker | Validar DTO público del middleend y preservar progreso; consumir upstream sin revalidarlo | partial result, unresolved IDs, cancelación | response raw, secretos, PII |
| UI/consumer | Feedback y acción recuperable | copy localizado, retry/resume controlado | mensaje upstream sin mapear, toast por abort |
| Logs/telemetry | Diagnóstico | etapa, operación, código, status, conteos, IDs permitidos | payloads, tokens, cookies, PII |

Una causa puede mapear distinto en cada boundary. Por ejemplo, timeout de transporte puede ser `dependency-unavailable` en service, `503` o fallback seguro en API y “resultado no confirmado; consultar antes de reintentar” en UI. No imponer esos valores si el repositorio tiene un contrato distinto.

## Precedencia de clasificación

Usar esta secuencia salvo contrato documentado que justifique otra:

1. Shape inválido generado por adapter.
2. Razón/código estable del dominio o proveedor.
3. Status estructurado.
4. Código de transporte.
5. Mensaje como heurística limitada.
6. Fallback seguro.

Casos que deben tener tests de regresión:

- respuesta 422/400 con mensaje que contiene `timeout` → rechazo de validación, no timeout;
- 401/403 → autorización upstream, no unavailable genérico;
- 429 → rate limit, con política explícita de espera;
- timeout sin status → timeout de transporte;
- status 5xx sin razón → dependency unavailable;
- shape incompleto → upstream invalid response, no éxito parcial inventado.

## Estados de operación

Distinguir estados conceptuales, aunque el proyecto use otros nombres:

```text
NOT_STARTED
  ├─ STARTED(progress identifiers)
  ├─ REJECTED(before mutation)
  └─ START_UNKNOWN(reconciliation required)

STARTED
  ├─ PROCESSING
  ├─ TERMINAL_SUCCESS
  ├─ TERMINAL_WITH_ITEM_FAILURES
  ├─ PARTIAL(known completed + unresolved)
  ├─ DEADLINE_EXCEEDED(reconcile/resume)
  ├─ INVALID_PAYLOAD
  └─ CANCELED(no user-facing error)
```

`START_UNKNOWN` y `DEADLINE_EXCEEDED` no autorizan crear otra mutación automáticamente. Primero consultar por correlation/run id o seguir el mecanismo de reconciliación existente.

## Partial success

Conservar de forma explícita y separada:

- resultados por item ya terminales;
- identificadores de runs/jobs aceptados y aún procesando;
- chunks aceptados/rechazados, solo como contadores consistentes;
- errores de preflight que no fueron enviados upstream;
- razón allowlisted del primer fallo representativo;
- `cause` solo en servidor y logs controlados.

Al combinar respuestas, usar identidad de item/run para deduplicar y definir precedencia de outcomes. No transformar “no se recibió respuesta” en `failed` sin evidencia. No convertir partial en éxito total.

## Mapping público

Construir una proyección independiente por salida:

```ts
const publicError = {
  code: publicCode,
  message: localizedOrSafeMessage,
  ...(status !== undefined ? { status } : {}),
  ...(unresolvedIds.length ? { unresolvedIds } : {}),
};
```

El ejemplo es conceptual: `status` suele viajar en HTTP y no dentro del body. La proyección real debe seguir el framework. `unresolvedIds` solo es válido si IDs están permitidos por contrato y no son PII.

Para logs, registrar datos estructurados mínimos y sanitizados. Para UI, resolver copy desde código/razón estable y traducible; usar mensaje raw únicamente si el contrato lo declara seguro y localizado.
