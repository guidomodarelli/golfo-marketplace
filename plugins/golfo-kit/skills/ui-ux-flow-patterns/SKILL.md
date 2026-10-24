---
name: ui-ux-flow-patterns
description: 'UI/UX por flujo: qué componente usar y qué mostrar en cada estado (loading y skeletons, vacío, con datos, error, parcial, sin permiso), cuándo usar toast, banner, inline o diálogo, confirmar o deshacer, validación previa con error junto al campo, limpieza de errores viejos (stale errors), pending, reintento y recuperación de operaciones async, feedback de reporte a soporte y copy de cada estado. Usar siempre, sin pedido explícito, al crear o modificar código visible o interactivo en cualquier stack: pantallas, rediseños, pasos de wizard, listas, tablas, formularios, búsquedas, uploads, códigos SMS u OTP, confirmaciones, acciones destructivas, copy, toasts o avisos, aunque el pedido solo diga mejorar la UX o hable de un solo botón. En un proyecto Next.js con App Router, cargarla junto con nextjs-route-ui-boundaries: esta decide qué muestra cada estado; aquella, boundaries y qué es server o cliente. No en código sin interfaz.'
license: MIT
metadata:
  version: "1.5.0"
  author: "Guido Modarelli"
  category: "frontend"
  tags: "ux, ui, empty-state, loading, error-state, toast, feedback, components, flows"
  command: "/ui-ux-flow-patterns"
---

# UI/UX por flujo: componentes, estados y feedback

Una pantalla no tiene un solo diseño: tiene uno por **estado**. La versión "con datos" es la que todos dibujan; las que hacen que un producto se sienta cuidado (Linear, Stripe, GitHub, Gmail, GOV.UK) son las otras: la primera carga, la lista vacía de un usuario nuevo, la búsqueda sin resultados, el error que no borra lo que el usuario escribió, el guardado que confirma sin interrumpir. Esta skill obliga a diseñar todas esas versiones antes de dar una UI por terminada y a elegir el componente y el canal de feedback que corresponden a cada una.

## Invocación automática

Usar esta skill por iniciativa propia cada vez que se crea o modifica código que el usuario ve o con el que interactúa (páginas, componentes, listas, tablas, formularios, diálogos, acciones), aunque el pedido solo hable de "agregar un botón" o "mostrar los pagos".

Disparadores concretos: "mejorá la UX/UI de…", "rediseñá la pantalla…", "pulí este paso", un paso nuevo o cambiado de un wizard, una confirmación o una acción destructiva, copy visible, feedback con toasts, banners o avisos, estados de carga, vacío o error. Cargarla **antes de diseñar**, no al revisar: los estados y el canal de feedback cambian qué componentes se eligen.

**Complementaria de `nextjs-route-ui-boundaries`.** Si el proyecto usa Next.js con App Router (`next` en `package.json` y `app/` o `src/app/`), cargar también esa skill en el mismo cambio, aunque solo se toquen contenedores cliente o componentes bajo `components/`: esta decide **qué muestra** cada estado; aquella, **dónde** van los boundaries y qué parte renderiza el server.

Elegir el modo según el alcance:

- **Modo liviano** (cambio puntual: un botón, una columna, un campo, copy). Revisar solo lo que el cambio toca con este checklist y corregir en el mismo trabajo lo que el cambio introduzca:
  1. Si el cambio **trae datos**: ¿tiene estado de carga con la forma del contenido (un [skeleton](references/state-matrix.md#skeleton) si el layout se conoce y la espera supera ~300 ms; nunca en recargas ni acciones), estado vacío y estado de error con reintento? ([state-matrix.md](references/state-matrix.md))
  2. Si el cambio **ejecuta una acción**: ¿el control muestra pending sin cambiar de ancho, evita el doble envío y el resultado llega por el canal correcto, con la duración, el cierre y la salida de su [ficha](references/feedback-channels.md#ficha-por-canal)? ¿Timeout, error, cancelación y resultado incierto tienen salida, sin reintentar a ciegas una mutación no idempotente? ([operaciones asíncronas](references/state-matrix.md#operaciones-asíncronas))
  3. Si la acción **destruye o es irreversible**: ¿se eligió entre deshacer y confirmar según [la regla](references/feedback-channels.md#confirmar-o-deshacer)? Si el proyecto confirma con una casilla junto al botón, aplicar la [confirmación inline](references/feedback-channels.md#confirmación-inline): etiqueta con recurso e impacto, consentimiento que se desmarca al cambiar de selección y aviso fijo si afecta al recurso en uso.
  4. Si el cambio **valida input o muestra errores**: ¿la acción se bloquea antes del request, el error queda junto al campo y el error viejo se limpia al cambiar de recurso o reintentar? Si lo que falla es una condición del proceso (código vencido, límite, sesión) y no el valor, ¿se muestra en el paso con su acción de salida en lugar de bloquear el campo? ([validation-feedback.md](references/validation-feedback.md))
  5. ¿El feedback nuevo es accesible (live region, foco, no solo color)? ([accesibilidad](references/feedback-channels.md#accesibilidad-del-feedback))

  Aplicar lo que salga del checklist directamente en el código. No producir la matriz de estados ni las tablas del [formato del reporte](#formato-del-reporte), que son del modo completo: un cambio puntual se entrega con el formato que pidió el usuario. Si nada aplica, seguir sin reportar nada extra; si algo aplica, sumar una línea por hallazgo al cierre de la tarea. Sumar siempre una línea por unidad con el resultado registrado, o el cierre incompleto con su motivo si no se pudo registrar.
- **Modo completo** (pantalla o flujo nuevo, rediseño, pedido explícito sobre UX, estados o feedback). Seguir los pasos 0 a 5.

No rediseñar pantallas que el cambio no toca: los problemas fuera del alcance se listan como sugerencia al final.

## Cobertura incremental

Obligatorio en cada ejecución, haya o no registro: seguí el [protocolo de cobertura](../../references/skill-coverage.md#protocolo-de-una-skill) con `--skill ui-ux-flow-patterns` en cada unidad funcional que toque el trabajo: `affected` (y la creación de la unidad si falta) y `check` antes de diseñar, `begin`, `evidence` y `record` al cerrar. Si el repositorio no tiene `.golfo/skill-coverage/` o ninguna unidad cubre el código tocado, creálos en el paso 1 del protocolo antes de `check` (`init`; `discover --scope <carpeta> --write` en páginas del App Router o `add-unit --id --kind --module --subflow --entry <path:symbol>` para el resto; después ajustá límites, nombres e ids): proponer `discover` no alcanza. Si no se puede registrar (sin `node`, sin el CLI, falla de `add-unit` o de `record`), terminá el trabajo de la skill pero cerrá **incompleto** con el motivo concreto y qué falta para registrar ([cierre incompleto](../../references/skill-coverage.md#cierre-incompleto-o-bloqueado)), nunca como completo ni como simple limitación. Crear la unidad es parte de la skill; inventar cobertura o evidencia, nunca. El registro sirve para no volver a revisar lo que ya está cubierto, no para dejar de cargar la skill: los disparadores de arriba siguen mandando.

- **La decisión acota la revisión, nunca tu cambio.** `skip` dice que el resto de la unidad ya está verificado; lo que vos agregás o tocás se revisa igual, con el modo que corresponda. `incremental` limita la revisión al alcance que lista `check` más su contexto necesario: los estados de la región que contiene lo cambiado, su feedback, errores, validación y accesibilidad, sin recorrer toda la página. `full` (sin cobertura previa o cambio de gran parte de la unidad) es el modo completo sobre toda la unidad.
- **Modo de `begin`** igual al que usaste: `lightweight` para un cambio puntual sobre una unidad ya verificada, `incremental` para el alcance de `check`, `full` para el modo completo. Un pedido de auditoría completa o un rediseño usa `check --force-full` y modo completo, aunque la cobertura esté vigente.
- **Evidencia** después de `begin`: `review` con lo que revisaste (checklist del modo liviano o matriz de estados), `test` con `--exec` de los tests de comportamiento que corriste y `browser` con los estados que recorriste y con qué herramienta. Sin navegador, registrá la falta como `--limitation`: el resultado queda `partial`, que es lo que corresponde.
- `nextjs-route-ui-boundaries` se sigue cargando junto con esta skill en Next.js con App Router; el registro de esta skill no cubre sus decisiones.

## 0. Leer el sistema de diseño del proyecto

Antes de proponer componentes, leer `DESIGN.md`, `AGENTS.md`/`CLAUDE.md` y las convenciones de `docs/` si existen, y ubicar la librería de componentes que el proyecto ya usa (por ejemplo su `EmptyState`, `Skeleton`, `toast`, `Alert`/`Banner`, `Dialog`). Reusar esos primitivos y su API; los nombres de esta skill (toast, banner, empty state) son **roles**, no componentes a crear. Respetar el idioma del copy visible y las reglas de motion y estilos del proyecto. Si el proyecto ya define cuándo usar cada tipo de toast u otro canal, esa regla manda sobre esta skill.

## 1. Identificar el tipo de flujo

Clasificar la pantalla o acción en uno o más tipos de [flow-catalog.md](references/flow-catalog.md) (colección/lista/tabla, búsqueda, detalle, formulario de creación/edición, guardado y autosave, edición concurrente, wizard u onboarding, acción destructiva, upload, importación y exportación, dashboard, settings, permisos y límites del plan, autenticación y verificación por código, pago, inbox/notificaciones, chat/tiempo real). Su [índice de escenarios](references/flow-catalog.md#escenarios-de-feedback-y-recuperación) enlaza cada caso con la sección que define su canal, duración, control y salida. Cada tipo trae sus componentes típicos, sus estados críticos, los errores comunes y referencias de productos que lo resuelven bien. Leer solo las secciones de los tipos que aplican.

## 2. Armar la matriz de estados

Para cada región que trae datos o ejecuta acciones, completar la matriz con los estados de [state-matrix.md](references/state-matrix.md#estados): carga inicial, recarga o refetch, vacío (primera vez, sin resultados por filtro o búsqueda, vaciado por el usuario, sin permiso), con datos (incluido uno solo y muchísimos), parcial, error (total, parcial, de acción), offline o desactualizado. Por cada estado decidir **qué se ve**, **qué puede hacer el usuario** y **cómo sale de ese estado**. Un estado sin salida (un error sin reintento, un vacío sin acción, un control deshabilitado sin motivo) es un callejón y se corrige. Cada acción async recorre además el [ciclo de vida de operaciones](references/state-matrix.md#operaciones-asíncronas) (`idle`, `pending`, `success`, `error` y, si aplican, `cancelled`, `partial_success` o resultado incierto).

## 3. Elegir el canal de feedback de cada evento

Para cada evento (acción completada, fallo, validación, cambio de estado en segundo plano, aviso persistente) elegir el canal con la [tabla de decisión](references/feedback-channels.md#tabla-de-decisión): inline junto al control, mensaje de formulario, banner, toast, diálogo, badge, página completa o el propio cambio de la UI. La pregunta guía es **dónde está mirando el usuario y cuánto necesita actuar**: lo que requiere acción no se va solo, y lo que solo confirma no interrumpe. No todo éxito o error va en toast. Con el canal elegido, su [ficha](references/feedback-channels.md#ficha-por-canal) fija ubicación, duración, cierre manual, acción de recuperación, controles habilitados, qué limpiar y cómo se anuncia. Decidir también confirmar o deshacer para cada acción destructiva. Para validación previa, errores viejos y feedback de reporte a soporte, aplicar [validation-feedback.md](references/validation-feedback.md).

## 4. Escribir el copy de cada estado

Cada estado vacío, error y confirmación responde: **qué pasó**, **por qué** (si ayuda) y **qué hacer ahora**, con una acción concreta. Seguir las [reglas de copy](references/state-matrix.md#copy-de-los-estados): verbos específicos en botones ("Guardar cambios", no "Aceptar"), errores sin culpa ni jerga técnica, sin exponer detalles internos, en el idioma del producto.

## 5. Aplicar y verificar

1. Presentar primero la matriz de estados y el canal elegido por evento; después implementar.
2. Verificar cada estado de verdad, no solo el feliz: simular la red lenta (throttling o un delay temporal), una respuesta vacía, un error del servidor, un timeout, una respuesta tardía que llega después de cambiar de contexto y un doble clic en cada acción. Si hay dev server, recorrer los estados en el browser con el teclado y con el lector de pantalla o las herramientas de accesibilidad disponibles.
3. Agregar o actualizar tests de comportamiento para los estados nuevos (render del vacío con su acción, error con reintento que recupera, botón en pending que no envía dos veces), siguiendo la estrategia de testing del proyecto.

## Compatibilidad entre agentes

El recorrido de estados del paso 5 usa el navegador que exista en la sesión, según la fila «Verificar en un navegador» de [`agent-capabilities.md`](../../references/agent-capabilities.md): buscá la herramienta concreta en la sesión o en `PATH`, no te guíes por el nombre del agente.

- Claude in Chrome o un MCP de navegador conectado: recorrer cada estado con clics y teclado.
- Codex: plugin `chrome@openai-bundled` (`tab.playwright.getByRole(...).click()` por estado y `tab.dev.logs` para errores); en la app de escritorio también sirve el navegador in-app para localhost.
- Hermes: `browser_exec` para localhost sin login; si no arranca dos veces seguidas, pasar a Playwright por terminal. `computer_use` solo si la pantalla necesita la sesión del usuario, avisando antes y con su consentimiento.
- Cualquier agente con shell: Playwright con el Chrome instalado ([comando](../../references/agent-capabilities.md#verificación-en-navegador-por-terminal)), sin sesión del usuario.

Un navegador headless confirma qué se ve y qué se puede hacer en cada estado, pero no reemplaza el lector de pantalla: si no hubo uno, decilo en **Verificación**. Si ningún mecanismo estuvo disponible o algo quedó sin recorrer, sumá **Limitaciones del agente** al cierre con lo omitido y cómo verificarlo.

## Formato del reporte

Solo en modo completo:

```markdown
## Flujo
<tipo(s) de flujo y regiones de la pantalla>

## Matriz de estados
| Región | Estado | Qué se ve | Acción disponible | Cómo sale |

## Feedback por evento
| Evento | Canal | Motivo |

## Verificación
<estados recorridos, con qué navegador o herramienta, tests y comprobaciones ejecutadas, con resultado>

## Cobertura
<siempre: por unidad (creada en esta ejecución o existente), decisión de `check`, resultado de `record` y pendientes; si no se pudo registrar, `incompleta` con el motivo y qué falta>

## Limitaciones del agente
<solo si faltó una herramienta: qué se omitió, qué se evaluó y cómo verificarlo>
```

## Límites con otras skills

- `nextjs-route-ui-boundaries`: en Next.js, **dónde** van `loading.tsx`, `error.tsx` y los `<Suspense>` y qué parte renderiza el server; esta skill decide **qué muestran**. En un proyecto Next.js con App Router, cargar las dos juntas.
- `optimistic-action-mutations`: complementaria en todo cambio de UI; decide si cada acción es optimistic, pending-first o confirmada por el servidor, y su concurrencia, rollback y reconciliación. Esta skill decide qué ve el usuario en cada uno de esos estados.
- `async-operation-error-handling`: errores de jobs, batches, polling y éxito parcial a través de las capas (service, API, client); esta skill decide qué ve y puede hacer el usuario en cada estado de la operación.
- `semantic-html-a11y`: semántica, roles y foco de los controles.
- `mobile-first-responsive-layout`: cómo se adapta cada estado a pantallas chicas.
- `widget-ui-proposals`: mostrar variantes visuales de un estado antes de implementarlo.
