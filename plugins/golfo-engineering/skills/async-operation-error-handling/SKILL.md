---
name: async-operation-error-handling
description: Diseña, implementa y revisa manejo de errores para operaciones asíncronas distribuidas en cualquier dominio y stack —batch/chunks, mutations parciales, jobs, polling, reanudación, retries, estados terminales, cancelación y fallos upstream— atravesando service/adapter, API/BFF, client y UI o worker. Usar siempre cuando una operación pueda aceptar solo parte del trabajo, crear runs/jobs, terminar con resultados mixtos, fallar después de una respuesta parcial, reintentarse o necesitar preservar progreso; también cuando se deba evitar duplicación, clasificar upstream, sanitizar DTOs o traducir errores a copy localizado. Aplicar incluso si la solicitud menciona solo timeout, partial success, polling, retry, chunk failure, terminal status o error mapping.
license: MIT
metadata:
  version: "1.1.0"
  author: "Guido Modarelli"
  category: "error-handling"
  tags: "errors, async, batch, retries, polling, partial-success"
  command: "/async-operation-error-handling"
  plugin-dependencies: "golfo-frontend"
---

# Async Operation Error Handling

## Objetivo

Construir contratos de error que permitan recuperar una operación asíncrona sin perder progreso ni repetir mutaciones confirmadas. La skill es agnóstica al dominio: nombres como `run`, `job`, `batch`, `chunk`, `item` y `operation` describen roles, no APIs concretas. El patrón cubre tanto un backend único como una cadena producer → service/adapter → API/BFF → client → UI/worker.

Preservar comportamiento público válido —status, códigos, resultados, retry, copy y side effects— salvo cambio explícito. Separar siempre:

- semántica de dominio;
- clasificación técnica/upstream;
- mapping de transporte;
- diagnóstico interno;
- feedback de usuario.

Leer [`references/error-flow.md`](references/error-flow.md) para decisiones por boundary y [`references/testing-matrix.md`](references/testing-matrix.md) para cobertura.

## Cuándo aplicar

Activar este workflow cuando exista una o más señales:

- una petición se divide en chunks, ventanas, lotes o workers;
- algunas partes se aceptan y otras fallan;
- la respuesta crea identificadores para trabajo posterior;
- el estado se consulta por polling o webhook y puede quedar unresolved;
- un timeout no permite saber si la mutación ocurrió;
- el usuario puede reintentar, reanudar o cancelar;
- hay resultados terminales con éxito y fallas por item;
- un error upstream necesita clasificación segura antes de llegar a browser/UI;
- el flujo cruza server/client, SSR, BFF, job runner o más de un servicio.

No activarla para un error síncrono local sin progreso parcial, polling, retry ni boundary distribuido, salvo que el cambio también requiera el contrato tipado general de `typed-errors-refactor`.

## Preflight obligatorio

1. Resolver lenguaje, runtime, framework, test runner, branch/base y comandos del repositorio.
2. Leer instrucciones del repositorio, skills complementarias y contratos existentes antes de editar.
3. Dibujar flujo real y localizar productores, adapters, routes/handlers, serializers, clients, UI/workers, logs, métricas y catálogos.
4. Inventariar estados, códigos, status, shapes, identificadores de progreso, límites de concurrencia, deadline, backoff, cancelación y consumers.
5. Capturar baseline de tests focales y comportamiento público cuando sea posible.
6. Separar errores de inicio de operación, errores de progreso/polling y errores por item. No mezclar sus contratos solo porque comparten un mensaje.

No inventar una jerarquía de clases, `Result` ni retry automático. Reusar guards, factories, errores y barrels existentes cuando expresen el mismo boundary.

## Regla canónica de payloads

Leer y aplicar `~/.agents/rules/payload-validation-boundaries.md`. Esa rule es fuente única: prohíbe revalidar payloads backend/upstream, permite narrowing estructural mínimo para control flow y exige validar inputs y DTOs públicos del middleend. No duplicar ni contradecir sus detalles aquí.

## Contrato estable

Definir códigos de máquina allowlisted y no traducibles para cada semántica relevante. Como mínimo, evaluar:

- input inválido, autorización, conflicto y regla de negocio;
- rechazo upstream (incluidos 4xx), rate limit, timeout de transporte y unavailable;
- respuesta upstream inválida o incompleta;
- operación parcial, polling incompleto, deadline excedido y cancelación;
- estado terminal con fallas por item.

El contrato interno puede conservar `cause: unknown` y metadata segura; el contrato público no debe incluir `cause`, `stack`, `response` raw, request, headers, cookies, tokens, secretos, payload completo ni PII.

Metadata pública o loggable debe tener allowlist por código: identificadores de job/run ya aprobados, contadores, nombres de campos validados, status mapeado y correlation ID permitido. Limitar longitud y tipo. No aceptar `Record<string, unknown>` raw como DTO.

No usar `error.message` como discriminante estable. Si existe mensaje upstream, tratarlo como diagnóstico; usarlo como heurística solo después de status/código estructurado y solo cuando no contradiga una clasificación más específica.

## Clasificación y precedencia

Aplicar precedencia explícita, documentada y testeada:

1. Error de contrato/respuesta inválida reconocido por adapter.
2. Código o razón estable emitido por dominio/upstream.
3. Status HTTP estructurado, con prioridad a reglas de negocio conocidas.
4. Código de transporte (`ETIMEDOUT`, `ECONNABORTED` u homólogo).
5. Heurística de mensaje, únicamente como último recurso.
6. Fallback `dependency-unavailable`/`unexpected` seguro.

Un status 4xx no debe convertirse en timeout porque su mensaje contiene `timeout`. Un 4xx upstream atribuible a validación o rechazo contractual debe clasificarse según el código o razón estable definido por el adapter, nunca como `dependency-unavailable`/timeout ni como motivo para retry automático por recuperación del servicio. Cuando el adapter traduzca status upstream a razones estables, hacer ese mapping explícito (por ejemplo, rechazo de validación, autorización upstream y rate limit como códigos distintos) y documentarlo y testearlo en el repositorio; no existe una relación universal entre status HTTP y código de dominio. Timeouts de transporte y dependencia unavailable deben conservar clasificaciones separadas. No usar status upstream como autorización local ni copiarlo automáticamente al público: el boundary final decide el status según reglas del repositorio.

## Escrituras parciales e idempotencia

Para mutaciones chunked o fan-out:

- limitar capacidad y concurrencia; usar reservation/queue/backpressure existente;
- reunir resultados con el mecanismo del runtime que preserve fulfilled y rejected sin perder orden ni índice;
- conservar solo identificadores y estados seguros de partes aceptadas;
- incluir contadores accepted/rejected solo si son consistentes y útiles;
- conservar resultados de preflight, immediate y partial sin sobrescribir outcomes válidos;
- preservar `cause` únicamente en servidor/log controlado;
- no repetir chunks o jobs cuya mutación ya tenga outcome confirmado; si el contrato permite retry por item, construir una nueva operación solo con fallas terminales o unidades unresolved elegibles, usando identidad estable;
- deduplicar IDs y validar que no existan duplicados en la respuesta combinada;
- no informar éxito global cuando hubo fallas parciales;
- emitir métricas solo para outcomes agregables y accionables, nunca por cada error, item, ID o rethrow.

Un error parcial debe distinguir “no sabemos si inició” de “inició y tenemos runs aceptados”. `accepted=0` con `rejected>0` representa rechazo total, no progreso parcial ni indisponibilidad; no debe prometer retry por recuperación del servicio. `accepted>0` con `rejected>0` representa partial success y exige conservar runs/IDs aceptados, contadores consistentes y retry solo para unidades elegibles. El primer caso exige reconciliación segura antes de repetir la mutación.

## Polling, terminalidad y cancelación

Consumir cada respuesta backend/upstream según el contrato del adapter sin validarla ni revalidarla como input. Para el DTO público emitido por el middleend, aplicar validación de contrato en el client/consumer antes de usarlo. Definir explícitamente:

- estados de progreso y si el avance es medible (contadores, etapas): sin avance informado por el upstream, el contrato no deriva porcentajes ni tiempos restantes;
- estados terminales, incluidos terminal con fallas por item;
- condiciones de DTO público del middleend inválido o fallo de contrato upstream ya observado por el adapter;
- deadline global y límites de polling;
- backoff/intervalo acotado;
- runs completados y runs unresolved;
- estrategia de reanudación sin crear otro job;
- cancelación intencional y cleanup.

Cuando varios runs se consultan, conservar resultados completados aunque otro falle. Una respuesta terminal no debe seguirse indefinidamente solo porque contiene `failed`. Un timeout de polling no prueba que la mutación no ocurrió: exponer estado indeterminado y permitir consultar/reanudar, no duplicar.

Propagar `AbortSignal` cuando exista. Remover listeners y cancelar timers/controllers en éxito, error y teardown. Abort/cancelación intencional no debe mostrar toast, ErrorUX ni actualizar estado stale.

## Boundary API/BFF

Normalizar `unknown` en una sola capa por operación y proyectar DTOs nuevos mediante allowlist. Mapear:

`upstream/transport → domain code → public HTTP status + safe DTO + diagnostic context`.

Usar 4xx para causas atribuibles a input, autorización, recurso o estado de dominio; reservar 5xx para fallas inesperadas o de dependencia no atribuibles al caller, conforme a reglas del repositorio. ErrorUX/diagnóstico debe ser tolerante: si falla su generación, conservar respuesta segura y loggear el fallo sin reemplazarlo por raw error.

Logs estructurados deben incluir operación, etapa, código, status, conteos y IDs estables mínimos. Nunca registrar request/response completos, credenciales, cookies, tokens, PII completa o `cause` sin sanitizar.

## Client, UI y copy

El client debe:

- validar shapes y allowlists del DTO público del middleend; nunca validar ni revalidar respuestas backend/upstream;
- normalizar solo campos seguros, sin transportar response raw;
- separar error de inicio, polling, partial result y item failure;
- conservar partial result y unresolved runs en el error typed/client contract;
- ofrecer resume para trabajo unresolved y retry solo para fallas terminales o unidades unresolved explícitamente elegibles según contrato;
- exponer al consumer el estado del reintento y los límites de la política como datos: intento actual, máximo de intentos y deadline o próximo intento, tomados de la misma constante o configuración que ejecuta el retry, nunca copiados en otra capa ni en el copy. Si la política no define un máximo o un deadline, el contrato lo omite (o lo manda `null`) para que la UI no invente uno. Si el retry corre dentro de un request síncrono, el consumer no puede verlo: exponerlo exige un recurso consultable (job con estado, polling o stream). Qué muestra la UI de esos datos es de `ui-ux-flow-patterns` (`references/system-status.md`);
- mapear copy por código/razón estable, no por mensaje upstream;
- para rechazos upstream 4xx, orientar a corregir causa/datos y no sugerir espera por recuperación ni retry automático;
- usar i18n para todo copy visible y mantener catálogos fuente según convención del repositorio;
- tratar unknown/malformed response con fallback accionable.

La UI debe mostrar diferencia entre éxito parcial, resultado terminal con fallas, estado indeterminado y error recuperable. No cerrar o limpiar progreso aceptado al mostrar error. No presentar cancelación como fallo.

## Tests de comportamiento

Agregar o actualizar tests en cada boundary afectado. Priorizar contratos observables e integración real del validador/transporte disponible; no mockear librerías internas o de plataforma sin imposibilidad técnica documentada.

Cubrir como mínimo:

- cada clasificación y precedencia status/código sobre mensaje;
- status 4xx con texto que menciona timeout;
- rechazo total (`accepted=0`, `rejected>0`) y partial success (`accepted>0`, `rejected>0`) sin perder progreso ni inventar runs;
- respuesta upstream inválida y campos sensibles ausentes en DTO/log;
- cero, todos y algunos chunks aceptados;
- resultados preflight/immediate/partial combinados sin duplicados;
- run terminal exitoso, terminal con fallas por item, payload inválido y unresolved;
- deadline/timeout sin afirmar que mutation no ocurrió;
- retry/resume solo de unidades unresolved o fallas terminales elegibles, sin crear duplicados;
- abort antes/durante polling y cleanup de timers/listeners;
- intento y máximo expuestos iguales a los de la política que ejecuta el retry, y ausentes cuando la política no los define;
- UI loading, partial, terminal failure, fallback y copy localizado;
- unknown throw (`null`, string, objeto, `Error`) sin crash ni exposición raw.

No testear strings internos del archivo fuente, imports, compilación artificial ni snapshots como única evidencia. No debilitar aserciones para acomodar implementación incorrecta.

## Orden de implementación

1. Caracterizar contratos actuales y agregar códigos/tipos solo donde exista consumer.
2. Implementar clasificación y normalización en producer/adapter/service.
3. Implementar serialización/mapping API y logging seguro.
4. Migrar client, polling, partial/resume y cancelación.
5. Migrar UI/worker y copy i18n.
6. Agregar tests por boundary; retirar comparaciones por mensaje y bridges solo cuando no queden consumers.
7. Ejecutar tests focales, typecheck, lint, build/runtime disponibles y diff check.

Tras cada edición significativa, verificar que el objetivo se cumplió y que no cambió status, retry, side effects o copy salvo decisión explícita.

## Formato de salida

Usar en español, salvo identificadores, paths, comandos y términos técnicos:

```markdown
## Alcance y baseline
## Flujo y boundaries
## Clasificación y contrato
## Partial success, polling e idempotencia
## Mapping, sanitización y UI
## Plan/cambios aplicados
## Tests y validación
## Riesgos, compatibilidad y pendientes
```

Ser explícito sobre estados no verificables, validaciones omitidas, decisiones de retry y cualquier cambio observable.
