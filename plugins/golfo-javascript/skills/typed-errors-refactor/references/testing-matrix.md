# Matriz de testing

Los tests deben verificar comportamiento observable y contratos públicos, no imports, strings internos ni la forma exacta del archivo fuente.

| Caso | Test recomendado | Aserciones mínimas |
|---|---|---|
| Éxito | Unit/integration | resultado y side effects esperados |
| Código/status | Contract/adapter/route | código estable y mapping correcto |
| `unknown` throw | Unit normalizer | string, `null`, objeto y `Error` no rompen |
| `cause` | Unit contract | identidad interna preservada, ausencia pública |
| Metadata | Contract | allowlist positiva y campos sensibles ausentes |
| Upstream malformed | Service/adapter | `upstream-invalid`, fallback y no raw response |
| API sanitization | Route/BFF | DTO sin stack/cause/secrets/PII |
| Logs | Logger spy/sink fake | contexto seguro, sin request/response raw |
| Retry/fallback | Service behavior | retryable, cantidad, status y fallback |
| Cancelación | Async behavior | cleanup, sin toast/error visible, sin estado stale |
| SSR/loader | Server/loader test | props controladas y HTML sin diagnóstico |
| Error Boundary | Render test | captura render, fallback seguro |
| Consumers legacy | Regression/compatibility | alias/códigos y copy preservados durante bridge |
| UI | Component/mapper | loading/error/empty/copy por código |

## Reglas de diseño

- Usar Arrange/Act/Assert o Given/When/Then.
- Agregar tests con el cambio, priorizando boundaries, permisos, integraciones, payloads inválidos y fallbacks.
- Mockear solo dependencias externas o side effects en su propio borde. No mockear SDK interno/plataforma si integración real es posible.
- No agregar `isTest`, exports artificiales o ramas sin comportamiento de producto.
- No debilitar una aserción para hacer pasar una implementación incorrecta.
- Ejecutar primero tests focales y luego suite completa/build del repositorio.

## Casos negativos de sanitización

Usar objetos upstream realistas que contengan campos sensibles y comprobar explícitamente que no aparecen:

- `authorization`, cookies, tokens y passwords;
- `stack`, `cause`, request/response raw;
- PII completa, payloads o URLs con secretos;
- detalles internos no allowlisted.

Conservar únicamente campos públicos acordados como `code`, status mapeado, request ID permitido, field name validado o contadores.

## Async y cancelación

Cubrir:

1. request exitoso;
2. error real que produce feedback/fallback;
3. abort antes de iniciar;
4. abort durante request o timer;
5. respuesta stale posterior a cleanup;
6. retry/fallback cuando corresponda.

El test debe demostrar que cancelación no se presenta como error de usuario y que listeners/timers se limpian.

## SSR y Error Boundary

Separar tests de:

- loader/SSR que captura fallos async y devuelve props seguras;
- serializer que evita stack/cause en HTML;
- Error Boundary que captura solo render/lifecycle;
- componente que maneja error de API mediante estado explícito.

No asumir que un Error Boundary cubre errores de effects, handlers, callbacks async o server-side.
