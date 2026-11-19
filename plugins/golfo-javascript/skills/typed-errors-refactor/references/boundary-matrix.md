# Matriz de boundaries

Usar la matriz para decidir dónde normalizar, qué conservar y qué devolver.

| Boundary | Clasificación | Normalización | Salida permitida | Prohibido |
|---|---|---|---|---|
| Input/validation | `invalid-input` | Schema/validator aprobado | `code`, campos allowlisted, status del transporte | payload raw, copy como discriminante |
| Domain | Código de negocio | Error type/factory/union | resultado seguro y metadata mínima | dependencia, query, headers |
| Upstream adapter | `dependency-unavailable` / `upstream-invalid` | Adapter específico | código estable, retryability y diagnóstico interno | body, response, stack, headers, cause raw |
| Persistence | `storage-failure` | Error técnico estable | correlation ID permitido | query, credenciales, datos completos |
| Service | Domain/dependency mapping | Normalizer central | contrato interno explícito | error tercero sin normalizar |
| API/BFF | Transport mapping | Serializer allowlisted | DTO público, status y ErrorUX seguro | `cause`, stack, response, PII |
| Logs/telemetry | Diagnóstico | Redaction y truncado | operación, route template, status, IDs estables, request ID | request/response completa, token, cookies |
| Browser client | Client contract | Guard y normalizer | `code`, estado seguro, retry/cancelación | upstream raw, URL/headers sensibles |
| UI | Presentación | Mapper por código | copy localizado, fallback accionable | `error.message` raw, stack, PII |
| Async/cancelación | Cancelación intencional | `AbortError`/equivalente explícito | cleanup y estado neutral | toast/error screen por abort |
| SSR/loader | Error de carga | `try/catch` server-side | props/DTO controlados | stack/cause en HTML |
| Error Boundary | Render síncrono | Fallback de render | UI fallback y logging seguro | usarlo para API, effects, handlers o SSR |

## Reglas de mapping

Una causa técnica puede mapearse distinto según boundary. Un timeout upstream puede ser `dependency-unavailable` para service, `503` para API y un fallback/retry para UI. Una respuesta upstream inválida puede ser `upstream-invalid` aunque transporte use `502`.

HTTP status es responsabilidad de transporte. No usar `status === 400` como única semántica en dominio si existe un código estable. No confiar en status recibido desde upstream para autorizar, ocultar validación o decidir ownership.

## Sanitización

Crear una proyección segura en cada salida, con allowlist independiente:

```ts
const publicError = {
	code: publicCode,
	message: publicMessage,
	...(requestId ? { requestId } : {}),
};
```

Excluir `cause`, `stack`, `response`, `request`, headers, cookies, tokens, passwords, CSRF, payloads y PII. Para logs, usar campos estructurados permitidos por el logger del proyecto y representar valores no-`Error` sin imprimirlos completos.

## SSR y React

- SSR/loader debe capturar errores de requests, devolver props controladas y evitar serializar datos de diagnóstico.
- Error Boundary solo cubre render/lifecycle de descendientes.
- Effects, event handlers, Promises y requests requieren estado explícito y normalizer.
- Hydration no debe silenciarse con `suppressHydrationWarning` para esconder un error de datos; corregir la fuente o controlar el DTO inicial.
