# Matriz de testing de observabilidad

| Caso | Aserciones mínimas |
|---|---|
| Error relevante | se emite evento en boundary dueño con operación, etapa, código, outcome y dependencia |
| Rethrow entre capas | no duplica evento equivalente ni pierde correlación |
| Sink de soporte integrado | usa código/team allowlisted y detalle searchable; falla del sink no rompe respuesta |
| Repo sin sink de soporte | no intenta usar un sink inexistente; conserva log/métrica segura |
| Grafana/Loki disponible | log estructurado, route template, status, IDs correlacionables y mensaje truncado |
| Otro sink de logs | aplica mismo contrato sin asumir Grafana |
| Métrica | counter/histogram con tags finitos; no IDs ni mensajes libres |
| Severidad | input/partial/cancelación no se clasifican como fatal; dependencia fallida sí usa nivel acorde |
| Burst | métricas no se pierden; logs repetidos se deduplican o rate-limitan con conteo |
| Correlación | request/trace/correlation/operation/run IDs se diferencian y propagan correctamente |
| Sink failure | sink de soporte/logger/StatsD fallan de forma aislada, sin cambiar HTTP, retry o estado de negocio |
| Sanitización | no aparecen request, response, headers, token, password, cookie, stack, cause, PII ni payload raw |
| Log injection | controles y saltos de línea se escapan o eliminan; límite de longitud se respeta |
| Público vs diagnóstico | UI no recibe el mensaje detallado del log/sink de soporte |

## Casos negativos obligatorios

Usar errores sintéticos con `response`, `headers`, `authorization`, cookies, tokens, passwords, `stack`, `cause`, PII, URL con query sensible y payload grande. Afirmar ausencia en cada sink y DTO público.

Probar también:

- IDs inválidos, demasiado largos o con caracteres de control;
- status fuera de 100–599;
- contadores negativos o no enteros;
- tags dinámicos como `userId`, `runId`, `requestId` y mensaje raw;
- fallo simultáneo del sink de diagnóstico y del logger;
- cancelación intencional sin evento de soporte ni error visible.

Validar comportamiento observable y contratos públicos. No probar imports, texto fuente ni implementación interna del logger.
