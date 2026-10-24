---
name: optimistic-action-mutations
description: 'Optimistic UI y ciclo de vida de acciones. INVOCAR SIEMPRE, sin pedido explícito, al crear, modificar, corregir o refactorizar cualquier flujo de UI o su lógica en cualquier stack (pantallas, formularios, botones, handlers, hooks, caché, consultas/refetch y endpoints que alimentan esa UI), aunque no pidan optimismo. Revisar estado inicial, carga, GET/POST/PATCH/DELETE, envío, guardado, toggle, selección, reintento, reenvío de SMS/OTP, reset, cancelar, deshacer, éxito, error, timeout, offline, duplicación, concurrencia, rollback y reconciliación. Decidir entre actualización optimista, estado pending y confirmación por servidor; no anticipar éxito en pagos, autenticación, permisos ni acciones irreversibles. Registrar siempre la cobertura por subflujo con skill-coverage (crear registro y unidad si faltan) y complementar ui-ux-flow-patterns. No en tareas sin UI ni flujo de usuario.'
license: MIT
metadata:
  version: "1.2.0"
  author: "Guido Modarelli"
  category: "frontend"
  tags: "optimistic-ui, mutations, concurrency, rollback, reconciliation, react, nextjs, tanstack-query"
  command: "/optimistic-action-mutations"
---

# Ciclo de vida de acciones y optimistic UI

Cada acción de una UI tiene un ciclo de vida: el usuario la dispara, la UI responde, el servidor decide y la UI se reconcilia con esa decisión. Esta skill revisa ese ciclo en cada operación que un cambio toca y elige, para cada una, cuánto puede adelantarse la UI sin mentir: actualizar ya y reconciliar (optimistic), mostrar que se está procesando sin afirmar el resultado (pending-first) o esperar la respuesta del servidor (server-confirmed). No convierte todo en optimistic: se asegura de que ninguna acción relevante quede sin evaluar.

## Invocación automática

La descripción pide cargarla en cada cambio de un flujo de UI. Es una instrucción al agente, no una garantía: el runtime decide qué skills carga y ningún texto lo vuelve determinístico. Por eso esta sección define qué hacer una vez cargada, para que el costo sea proporcional al cambio.

- **Activación.** Cualquier creación, modificación, corrección o refactor de un flujo de UI o de la lógica que lo alimenta (handler, hook, caché, query, route handler, server action, contrato de API que una pantalla consume), aunque el pedido no mencione optimismo. Que el cambio "solo agregue un botón" no la deja afuera: ese botón es una operación nueva con su propio ciclo de vida.
- **Evaluación.** Listar las operaciones que el cambio agrega o toca (lecturas, mutaciones, operaciones prolongadas) y las transiciones afectadas. Solo esas: una pantalla que el cambio no toca no se vuelve a auditar.
- **Aplicación.** Clasificar cada operación ([decisión](references/optimistic-decision.md)) y aplicar el patrón que corresponde con las primitivas que el proyecto ya tiene ([primitivas](references/framework-primitives.md)). El optimismo se implementa solo donde la clasificación lo permite.
- **No aplicabilidad.** Si el cambio no agrega ni modifica operaciones (copy, estilos, layout, un componente de presentación sin datos ni acciones), terminar con una línea que lo justifique («sin operaciones nuevas ni modificadas: no aplica») y seguir. Un cambio que solo toca lecturas (GET, búsqueda, refetch, paginación) no es «no aplica»: el optimismo no corresponde, pero antes de cerrar se revisan los checks de lectura del [catálogo](references/action-catalog.md#lectura-y-obtención-de-datos) (estado de carga, respuestas fuera de orden o de parámetros viejos, cancelación, conservar los datos previos) y se cierra con la línea «solo lecturas: sin optimismo; checks de lectura revisados». No agregar estado, abstracciones ni tests para cumplir con la skill.

Un cambio mínimo produce una evaluación mínima. **No en**: jobs, migraciones, scripts CLI, workers o endpoints sin ninguna pantalla que los consuma, ni documentación sin código.

**Complementaria de `ui-ux-flow-patterns`** (y de `nextjs-route-ui-boundaries` en Next.js con App Router). Las tres se cargan juntas en un cambio de UI y no se reemplazan: esta decide la intención, la concurrencia, la mutación, el rollback y la reconciliación; `ui-ux-flow-patterns` decide qué ve el usuario en cada estado y por qué canal; `nextjs-route-ui-boundaries`, los boundaries y el reparto server/client.

## Modos

- **Modo liviano** (cambio puntual: un botón, un handler, un campo, un endpoint). Para cada operación que el cambio toca, responder en el mismo trabajo:
  1. ¿Qué tipo de operación es y qué clase le corresponde (optimistic, pending-first o server-confirmed)? Una lectura no lleva clase: se revisa con los checks de lectura del catálogo. ([catálogo](references/action-catalog.md), [decisión](references/optimistic-decision.md))
  2. ¿Se protege del doble disparo y de la respuesta vieja que pisa un estado nuevo? ([concurrencia](references/concurrency-reconciliation.md))
  3. ¿Qué pasa ante error, timeout y resultado desconocido? ¿Hay rollback al baseline confirmado sin destruir otras operaciones? ¿Hay salida para el usuario?
  4. ¿Qué se limpia al cambiar de ruta, de entidad o al desmontar?

  Corregir lo que el cambio introduce y sumar una línea por hallazgo al cierre. Si nada aplica, no reportar nada extra.
- **Modo completo** (flujo o pantalla nueva, rediseño, pedido explícito sobre optimismo, concurrencia o reconciliación). Seguir los pasos 1 a 6.

## Cobertura incremental

Obligatorio en cada ejecución, haya o no registro: seguí el [protocolo de cobertura](../../references/skill-coverage.md#protocolo-de-una-skill) con `--skill optimistic-action-mutations` en cada unidad funcional que toque el trabajo, incluido su paso 1 cuando falta el registro o la unidad (crearlos es parte de la skill; proponer `discover` no alcanza) y el [cierre incompleto](../../references/skill-coverage.md#cierre-incompleto-o-bloqueado) cuando no se puede registrar. Nunca inventar cobertura ni evidencia. El registro decide **cuánto** trabajo repetir, nunca **si** cargar la skill: la activación de arriba manda siempre.

- **Decisión de `check`.** `skip`: la cobertura verificada sigue vigente para el resto de la unidad, pero lo que vos agregás o tocás se evalúa igual. `incremental`: solo el alcance que lista `check` (cada parte con su foco: handler, render, contrato del servidor, configuración de tiempos) más su contexto necesario. `full`: el inventario completo de operaciones de la unidad. Un pedido de auditoría completa usa `check --force-full`.
- **Modo de `begin`** igual al que usaste: `lightweight`, `incremental` o `full`.
- **Evidencia** después de `begin`: `review` con las operaciones evaluadas y su clase, y `test` con `--exec` de los tests de comportamiento que corriste (rollback, respuesta vieja, doble disparo). Sin tests ejecutables, registrá la falta con `--limitation` y el resultado queda `partial`. No hay evidencia que inventar: solo lo que se ejecutó o revisó en la sesión.
- **No aplica.** Si la unidad no tiene operaciones (ni lecturas ni mutaciones), registrá `record --result not-applicable --summary "<motivo>"`, nunca `applicable: false` en la unidad ([por qué](../../references/skill-coverage.md#políticas-por-skill)): el registro se reevalúa cuando se agrega una operación. Una unidad de solo lecturas no es `not-applicable`: registrá `review` con los checks de lectura revisados y `test` con los tests que corriste (o la falta con `--limitation`), como cualquier otra unidad.
- **Unidad nueva.** Una operación sin unidad se registra creando la unidad del subflujo que la contiene (por ejemplo, `add-unit --kind ui-flow --entry <componente>:<Componente>/<handler>`), no salteando el registro.

## 1. Inventariar las operaciones

Listar las operaciones de la unidad o del cambio con el [catálogo de acciones](references/action-catalog.md): lecturas (carga inicial, GET dependiente de parámetros, refetch, invalidación, paginación, búsqueda), mutaciones (POST, PUT/PATCH, DELETE, guardado y autosave, toggle, selección, reordenamiento, masivas, envío de mensajes, reenvío de códigos, reset, cancelar, deshacer) y operaciones prolongadas (uploads, jobs, polling, resultados parciales). Por cada una anotar qué dispara el usuario, qué endpoint o acción del servidor ejecuta y qué estado de la UI depende de ella.

## 2. Clasificar cada operación

Con la [tabla de decisión](references/optimistic-decision.md) clasificar cada mutación como **optimistic**, **pending-first** o **server-confirmed** según reversibilidad, efectos secundarios, permisos, probabilidad de fallo, costo del rollback, idempotencia y consistencia entre clientes. Pagos, autenticación, envíos reales de SMS o email, permisos, eliminaciones irreversibles y procesos externos no compensables nunca muestran un éxito antes de que el servidor lo confirme. Las lecturas no se clasifican así: se revisan sus estados de carga y su protección contra respuestas fuera de orden.

## 3. Recorrer la máquina de estados de cada interacción

Para cada operación afectada, revisar las transiciones de la [máquina de estados por interacción](references/interaction-state-machine.md): qué ve el usuario, qué sigue habilitado, qué datos se conservan, qué es verdad confirmada, cómo se recupera y cómo se impide que una respuesta vieja pise un estado nuevo. Los nombres de los estados se adaptan al framework; no hace falta una máquina formal ni una dependencia nueva para una acción trivial. Qué mensaje y qué canal recibe cada estado lo decide `ui-ux-flow-patterns`.

## 4. Proteger concurrencia y reconciliación

Aplicar los patrones de [concurrencia y reconciliación](references/concurrency-reconciliation.md): baseline confirmado separado de la intención optimista, intenciones pendientes por entidad y operación, secuencias o versiones para descartar respuestas viejas, deduplicación y protección del doble envío, claves de idempotencia, conflictos, ids temporales, invalidación dirigida, rollback que no destruye otras operaciones confirmadas, limpieza al desmontar o navegar y recuperación tras reconexión.

Reglas que no se negocian:

- **Timeout no es fallo.** Si la respuesta se perdió, la operación pudo ejecutarse en el servidor. Resolver primero el resultado (consulta de estado, id de operación o clave de idempotencia) antes de repetir una mutación con efectos secundarios.
- **Abortar no es deshacer.** Cancelar el request del cliente no revierte una escritura que ya llegó al servidor.
- **Una UI rápida no justifica un éxito falso.** Si la clase es pending-first o server-confirmed, el resultado de negocio se muestra recién con la confirmación.
- Sin reintentos automáticos ilimitados ni una política universal de debounce: cada operación decide según su semántica.
- Ningún estado deja al usuario trabado sin una salida.

## 5. Implementar con las primitivas del proyecto

Reusar lo que el proyecto ya tiene: `useOptimistic` y Actions de React, `onMutate`/rollback/`cancelQueries`/invalidación de TanStack Query, `mutate` de SWR, la caché y las server actions del framework real ([primitivas](references/framework-primitives.md)). No instalar librerías nuevas ni construir un gestor de estado propio si las primitivas existentes alcanzan. El contrato del servidor devuelve lo mínimo para reconciliar y es seguro ante reintentos y concurrencia ([contrato del servidor](references/concurrency-reconciliation.md#contrato-del-servidor)).

## 6. Verificar con tests de comportamiento

Cubrir con tests lo que la clasificación promete, siguiendo la estrategia de testing del proyecto ([checklist](references/concurrency-reconciliation.md#checklist-de-tests)): feedback inmediato o pending según la clase, última intención con clicks rápidos, rollback al baseline, respuesta vieja descartada, doble envío sin efectos duplicados, resultado desconocido que consulta antes de repetir y limpieza al desmontar. No mockear las librerías de UI o de plataforma para probarlo: probar el comportamiento observable en el borde del componente o del caso de uso.

## Compatibilidad entre agentes

La skill solo necesita leer y editar código y correr los tests del proyecto, igual en Claude Code, Codex y Hermes. El registro de cobertura obligatorio necesita `node` en `PATH` y el CLI de `skill-coverage` instalado junto al plugin (fila «Registrar cobertura de skills» de [`agent-capabilities.md`](../../references/agent-capabilities.md)); sin ellos la skill termina su trabajo pero cierra **incompleta**, con el motivo y qué falta para registrar. Si hace falta recorrer estados en un navegador, usar el mecanismo de la fila «Verificar en un navegador» del mismo archivo.

## Formato del reporte

En modo liviano, una línea por operación tocada: `<operación> → <clase>: <decisión o hallazgo>`, o la línea de no aplicabilidad o de solo lecturas. En modo completo:

```markdown
## Operaciones
| Operación | Tipo | Clase | Motivo |

## Transiciones y concurrencia
<por operación: estados revisados, protección contra respuestas viejas y doble disparo, rollback y reconciliación>

## Verificación
<tests ejecutados y resultado>

## Cobertura
<siempre: por unidad (creada en esta ejecución o existente), decisión de `check`, resultado de `record` y pendientes; si no se pudo registrar, `incompleta` con el motivo y qué falta>

## Limitaciones del agente
<solo si faltó una herramienta: qué se omitió y cómo verificarlo>
```

## Límites con otras skills

- `ui-ux-flow-patterns`: qué ve el usuario en cada estado, canales de feedback, copy y accesibilidad del feedback.
- `nextjs-route-ui-boundaries`: boundaries de ruta y reparto server/client en Next.js.
- `async-operation-error-handling`: jobs, batches, polling, éxito parcial, reintentos distribuidos y contratos de operación entre capas.
- `error-observability-diagnostics`: logs, correlación y diagnóstico de errores. La cobertura de `skill-coverage` registra qué revisó una skill; no es observabilidad de producción.
