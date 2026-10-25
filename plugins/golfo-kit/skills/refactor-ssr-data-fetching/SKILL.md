---
name: refactor-ssr-data-fetching
description: Prioriza acceso a backend/upstream desde server-side en aplicaciones React SSR y dirige requests posteriores a interacción mediante middle-end/BFF same-origin. Usar al implementar, modificar, revisar o depurar loaders, hooks server, getServerSideProps, Server Actions, route handlers BFF, caché server, llamadas upstream, filtros, búsquedas, paginación, polling, refetches o mutations, incluso si pedido solo dice “agregar llamada API”. No usar para CSR puro sin boundary server/BFF ni para estados loading/error sin decisión de arquitectura de red.
license: MIT
metadata:
  version: "1.0.0"
  author: "Guido Modarelli"
  category: "frontend"
  tags: "react, ssr, bff, data-fetching, security"
  command: "/refactor-ssr-data-fetching"
---

# React SSR y BFF Data Fetching

## Invariante de routing

Elegir primera ruta viable de esta jerarquía:

```text
Primer render:
request → SSR hook/loader → server-only service → upstream client
        → DTO mínimo browser-safe → props serializadas

Después de interacción:
browser → /api/... relativo same-origin → auth + validation + authz + ownership
        → server-only service → upstream client → DTO mínimo browser-safe

Excepción:
browser → upstream
        solo cuando todas condiciones de excepción están probadas y documentadas
```

Dato disponible durante request y necesario para HTML inicial pertenece a SSR. Dato solicitado después por búsqueda, filtro, paginación, polling, refetch o mutation puede iniciarse en browser, pero debe atravesar middle-end/BFF antes de upstream.

Leer [patterns.md](references/patterns.md) para seleccionar ruta o implementar patrón en stack SSR desconocido. Leer [server-cache-and-concurrency.md](references/server-cache-and-concurrency.md) al tocar estado de módulo, caché server (`React.cache()`, LRU), I/O estático o el orden de `await` dentro de un route handler BFF.

## Workflow

1. **Mapear boundaries.** Localizar SSR hook/loader/controller, props serializadas, routes BFF, server services, upstream clients y browser services/hooks.
2. **Inventariar operaciones.** Separar datasets iniciales, datos on-demand, frescura periódica y mutations.
3. **Clasificar disponibilidad.** Determinar si dato existe durante request, depende de interacción posterior o requiere actualización continua.
4. **Elegir ruta única.** Aplicar jerarquía SSR → BFF → upstream directo excepcional.
5. **Diseñar DTO público.** Permitir solo campos necesarios para render o interacción.
6. **Proteger boundary server.** Aplicar authentication, schema validation, authorization y ownership antes de consultar o mutar, en cada entrada server invocable desde browser: route BFF y Server Action (`"use server"`).
7. **Aislar estado por request.** Mantener datos de request, sesión o usuario en argumentos, contexto del framework o caché por request; nunca en variables mutables de módulo.
8. **Verificar comportamiento.** Probar cada frontera e inspeccionar network del browser sin exponer headers, cookies ni tokens.

## Reglas SSR-first

Usar SSR cuando dato:

- está disponible en request inicial;
- determina contenido visible, permisos, routing, configuración o opciones iniciales;
- requiere identidad, cookies, scopes, headers internos o composición de upstreams;
- evita loading/flicker y request duplicado después de hydration.

Orden recomendado:

1. validar `query`, `params` y datos derivados de request;
2. resolver authentication y authorization;
3. instanciar service server-only con request context;
4. consultar upstream mediante client server-only;
5. transformar respuesta a DTO browser-safe;
6. guardar DTO en `res.locals` o mecanismo equivalente;
7. mantener `getServerSideProps` o loader final como adaptador de props.

Hook/loader SSR debe llamar service directamente. No hacer loopback HTTP contra propia route `/api`:

```text
Incorrecto: SSR hook → http://localhost/.../api → mismo proceso → upstream
Correcto:   SSR hook → server-only service → upstream client
```

Loopback agrega latencia, serialización, timeouts y semántica de auth innecesarios.

### Errores SSR

- Tratar como fatal dato sin el cual una página autorizada no puede renderizar contrato válido.
- Degradar dato opcional de forma explícita, preservando resultados independientes.
- Loggear operación y metadata segura; no loggear error raw si puede contener headers, sesión, tokens o PII.
- Entregar mensaje/flag público controlado, nunca stack o detalle upstream.

## Reglas para requests iniciados en browser

Búsquedas, filtros aplicados, paginación posterior, polling, refetches y mutations pueden comenzar en cliente. Mantener ruta:

```text
browser service/hook
  → URL relativa same-origin /api/...
  → BFF route
  → server-only service
  → upstream client
```

BFF debe:

- autenticar request;
- validar `query`, `params` y `body` antes de leerlos;
- autorizar capacidad exacta;
- verificar ownership/tenant/facility/entity contra identidad confiable;
- imponer límites, defaults y transiciones de negocio server-side;
- transformar nombres y contratos entre browser y upstream;
- devolver DTO mínimo y errores seguros.

### Server Actions son endpoints públicos

Una función `"use server"` queda expuesta como endpoint POST invocable directamente, sin pasar por la página, el layout ni el middleware que la montó. Tratarla como route BFF: dentro de la propia action, validar schema del input (`unknown` hasta parsear), autenticar, autorizar la capacidad exacta y verificar ownership antes de mutar. Guard de página, botón oculto o middleware no la protegen. Devolver DTO mínimo y error seguro, igual que BFF.

```ts
'use server';
export async function archiveOrder(rawInput: unknown) {
  const { orderId } = archiveOrderSchema.parse(rawInput);
  const identity = await requireAuthenticatedIdentity();
  await requireCapability(identity, 'orders:archive');
  await requireOrderOwnership(identity, orderId);
  return toBrowserSafeDTO(await new OrderService(identity).archive(orderId));
}
```

Upstream client debe concentrar host, scope, cookies, request-derived headers, timeout y retries. Nada de esto pertenece al bundle browser.

Client service debe usar baseURL relativa. No importar server service desde componente React ni reconstruir headers internos en cliente.

Para entry point único, deduplicación, estados loading/error y cancelación de races en async `useEffect`, aplicar `react-data-fetching-best-practices`.

## Excepción browser → upstream directo

Aceptar acceso directo solo si **todas** condiciones se cumplen:

- endpoint público y anónimo;
- no usa cookies, tokens, scopes, secrets ni credenciales;
- no depende de authz, ownership, tenant o identidad;
- no devuelve PII ni datos internos;
- CORS está soportado explícitamente por owner del endpoint;
- BFF no necesita filtrar, transformar, agregar ni ocultar campos;
- no se pierde observabilidad, rate policy o control requerido;
- existe restricción concreta que vuelve BFF difícil de implementar o imposible, no mera preferencia por ahorrar salto.

Si una condición falla, usar BFF.

Documentar excepción junto a implementación:

- endpoint y owner;
- restricción que impide BFF;
- clasificación de datos/campos expuestos;
- evidencia de CORS;
- evaluación de credenciales, PII, authz y ownership;
- transformaciones u observabilidad perdidas;
- mitigaciones;
- evento/fecha que obliga a reconsiderar decisión.

## Seguridad y minimización

- No serializar cookies, session IDs, CSRF values, tokens, scopes, authorization headers, secrets ni configuración interna.
- No pasar respuesta upstream completa al browser; construir DTO explícito.
- No incluir PII innecesaria.
- No confiar en botón oculto o ID enviado por browser como authorization.
- No configurar CORS como atajo para evitar BFF.
- No usar `dangerouslySetInnerHTML` para mostrar datos remotos.
- No guardar usuario, sesión, tenant ni respuesta de un request en `let`/objetos mutables de módulo: renders y handlers concurrentes comparten proceso y un usuario puede recibir datos de otro. Detalle y excepciones permitidas en [server-cache-and-concurrency.md](references/server-cache-and-concurrency.md#estado-de-módulo).
- No compartir caché entre requests para datos personalizados o dependientes de permisos.
- Mantener logs sanitizados y respuestas públicas sin detalles técnicos.

## Testing

Probar cada frontera afectada:

1. **SSR hook/loader:** validation/auth antes de service, llamada directa sin loopback, degradación/fallo esperado.
2. **Props adapter:** lee `res.locals`/equivalente y aplica defaults seguros sin volver a consultar.
3. **BFF route y Server Action:** authentication, schema, authorization, ownership, status y error seguro; invocar la action directamente (sin la página) con identidad ajena o sin sesión y verificar rechazo.
4. **Concurrencia server:** dos requests solapados de usuarios distintos no comparten datos de request.
5. **Server service/client:** mapping upstream, límites, scopes/headers exclusivamente server-side.
6. **Browser service:** URL relativa `/api`, params correctos y ausencia de host upstream.
7. **UI:** comportamiento visible para loading/error/data sin testear implementación textual.
8. **Runtime:** snapshot, requests XHR/fetch y consola; no inspeccionar headers completos.

Si datos SSR hidratan React, aplicar `prevent-ssr-hydration-mismatches`. Para evidencia runtime, usar la herramienta de verificación del proyecto o automatización de browser cuando esté disponible.

## Scope boundaries

- `react-data-fetching-best-practices`: entry point, deduplicación, mapping a props, feedback loading/error y cancelación de races en efectos async.
- `prevent-ssr-hydration-mismatches`: igualdad entre HTML SSR y primer render cliente.
- Skills o convenciones propias del framework del proyecto: mecánica concreta de service → API route → browser hook, API de schema validation, formato de logging estructurado y validación runtime.
- `review-security`: auditoría AppSec exhaustiva.

Esta skill decide **dónde** ocurre acceso upstream y **qué datos** pueden cruzar boundary server/browser.

## Checklist final

- Datos necesarios para primer render se obtienen server-side.
- SSR llama service directo, sin loopback HTTP a propia API.
- Requests posteriores desde browser usan BFF relativo same-origin.
- Hosts, scopes, cookies, headers y secrets quedan server-only.
- Input se valida antes de acceso.
- Authentication, authorization y ownership se revalidan server-side, también dentro de cada Server Action.
- Ningún dato de request/usuario vive en estado mutable de módulo; caché entre requests solo para datos no personalizados y con invalidación.
- Route handlers BFF arrancan lecturas independientes antes de awaitearlas y no awaitean trabajo que una rama de early return descarta.
- Browser recibe DTO mínimo, no response upstream completa.
- Errores y logs no exponen detalles sensibles.
- Acceso browser→upstream, si existe, satisface y documenta todas condiciones.
- Tests cubren SSR, BFF, service/client, browser service y runtime.
- Skill vecina correcta cubre hydration, abort, fetching genérico y APIs específicas del framework.
