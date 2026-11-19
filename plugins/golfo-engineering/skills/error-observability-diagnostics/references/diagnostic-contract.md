# Contrato de diagnóstico y observabilidad

## Tres proyecciones

| Salida | Objetivo | Debe contener | Prohibido |
|---|---|---|---|
| Público/UI | Acción segura para quien usa el producto | mensaje breve, código público, acción/retry permitido | stack, causa, payload, mensaje upstream raw |
| Sink de diagnóstico de soporte | Seguimiento de soporte cuando el proyecto lo integra | team/código allowlisted, operación, etapa, razón, dependencia, status, detalle searchable, correlation ID permitido | request/response, headers, secretos, PII, causa raw |
| Log operativo | Investigación en sink real del repo | severidad, operación, etapa, código, outcome, dependencia, route template, status, IDs de correlación, duración, contadores, mensaje sanitizado | objetos `req`/`res`/`error`, tokens, cookies, passwords, URL sensible, payload completo |
| Métrica | Tendencias, alertas y SLO | counter/histogram, operación, etapa, outcome, categoría, dependencia, status family, scope | IDs, mensaje, stack, URL, PII, tags libres |

El sink de soporte y los logs pueden compartir código estable y correlación, pero no son copias. Métricas no sustituyen detalle diagnóstico.

## Evento interno allowlisted

```ts
interface SafeDiagnosticEvent {
	schemaVersion: string;
	service: string;
	environment?: string;
	operation: string;
	stage: string;
	outcome: string;
	errorCode: string;
	errorCategory: string;
	dependency?: string;
	routeTemplate?: string;
	httpMethod?: string;
	statusCode?: number;
	upstreamStatus?: number;
	retryable?: boolean;
	attempt?: number;
	requestId?: string;
	correlationId?: string;
	traceId?: string;
	spanId?: string;
	operationId?: string;
	runId?: string;
	durationMs?: number;
	counts?: { total?: number; succeeded?: number; failed?: number; unresolved?: number };
	sanitizedMessage?: string;
}
```

El tipo es conceptual. Cada repo debe reducirlo a campos que realmente conoce. Validar status, contadores, IDs, longitud y caracteres antes de emitir. No agregar `error: unknown`, `request`, `response` o `metadata` arbitraria.

## Ownership de eventos

Emitir evento cuando una capa clasifica o cierra una fase relevante:

- start accepted/rejected;
- dependency failure o invalid response;
- partial/unresolved;
- terminal failure;
- retry/reconciliation outcome;
- cancelación explícita o sink failure relevante.

Un rethrow no crea evento duplicado. Crear nuevo evento solo si cambia `stage`, `outcome`, dependencia o acción operativa. Fallos esperados repetitivos deben agregarse por métricas y logs con deduplicación.

## Severidad

| Caso | Severidad sugerida |
|---|---|
| transición esperada | info |
| diagnóstico de bajo volumen | debug/trace |
| input inválido, partial, unresolved, retry diferido | warn |
| dependencia caída, payload inválido, operación fallida, sink fallido relevante | error |
| proceso incapaz de continuar | fatal |
| cancelación intencional | info o métrica; nunca error por defecto |

La severidad no debe convertirse en tag de alta cardinalidad sin motivo operativo.

## Mapping por sink

- Sink de soporte: detalle técnico corto, estable, sin copy público raw; solo si hay integración real + acción de soporte.
- Logs: mensaje detallado y contexto estructurado, acotado y searchable en sink real; usar route template, no URL completa.
- Métricas: categorías finitas; IDs solo en logs correlacionados.

Si sink no existe, marcar `No aplica`; no crear una integración ficticia.
