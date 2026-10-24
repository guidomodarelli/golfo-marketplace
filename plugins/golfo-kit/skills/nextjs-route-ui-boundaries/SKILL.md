---
name: nextjs-route-ui-boundaries
description: 'Next.js App Router: decide loading.tsx con skeleton, error.tsx, layouts compartidos, Suspense, server vs client (sidebar, header, tablas, contenedores) y las APIs de Next.js que conviene usar. Usar siempre, sin pedido explícito, al crear o modificar cualquier código de un proyecto Next.js con App Router: archivos de app/ (page, layout, route), contenedores y componentes cliente que monta una ruta (app/**, components/**), hooks, formularios, server actions o next.config, aunque el cambio no toque page.tsx, loading.tsx ni error.tsx y el pedido solo diga mejorar la UI/UX, rediseñar una pantalla o agregar un botón. En un cambio de UI, cargarla junto con ui-ux-flow-patterns: esta decide boundaries y qué es server o cliente; aquella, qué muestra cada estado. No en Pages Router ni en repos sin Next.js.'
license: MIT
metadata:
  version: "1.3.0"
  author: "Guido Modarelli"
  category: "frontend"
  tags: "nextjs, app-router, loading, error-boundary, layout, suspense, skeleton, server-components"
  command: "/nextjs-route-ui-boundaries"
---

# Next.js: boundaries de UI por ruta

Esta skill decide **qué archivo especial o boundary corresponde a cada segmento** del árbol `app/` y **qué parte de cada pantalla se renderiza en server**. El objetivo es que cada navegación muestre algo útil al instante (shell + skeleton), que un error quede contenido en la porción más chica posible y que el JavaScript enviado al browser sea solo el de las piezas interactivas.

## Invocación automática en cada cambio de Next.js

Usar esta skill por iniciativa propia cada vez que se crea o modifica código de un proyecto Next.js con App Router, aunque el pedido no hable de rutas ni de loading: un componente nuevo puede ser la razón de que una página entera pase a `"use client"`, un `await` nuevo en un layout puede congelar todas las navegaciones, y es mucho más barato decidir el boundary al escribir el código que descubrirlo después.

Disparadores concretos, aunque el diff no toque `page.tsx`, `loading.tsx` ni `error.tsx`:

- Un contenedor o componente cliente que monta una ruta (`app/**/<algo>-container.tsx`, `components/**`), sus hooks o sus estilos.
- Un rediseño o "mejorá la UI/UX de la pantalla X": la pantalla vive en un segmento de `app/`, así que el reparto server/cliente y los estados de carga del segmento entran en el alcance.
- Un formulario, una server action, un route handler, un `fetch` nuevo o un cambio de `next.config.*`.

Que el cambio parezca "solo de componentes" no la deja afuera: esos componentes son los que deciden dónde cae `"use client"` y qué espera la ruta.

**Complementaria de `ui-ux-flow-patterns`.** En cualquier cambio de UI dentro de un proyecto Next.js, cargar las dos antes de diseñar: esta decide **dónde** van los boundaries y qué renderiza el server; `ui-ux-flow-patterns` decide **qué muestra** cada estado y qué feedback recibe el usuario. Cargar una no reemplaza a la otra.

Detectar el proyecto: `next` en `package.json` y un directorio `app/` (o `src/app/`). Con solo `pages/`, la skill no aplica.

Elegir el modo según el alcance del cambio:

- **Modo liviano** (cambio puntual: un componente, una página, un fix, estilos o copy dentro de una ruta). No re-auditar todo el árbol. Revisar solo los segmentos que el cambio toca contra este checklist y corregir en el mismo trabajo lo que el cambio introduzca:
  1. ¿El cambio agrega `"use client"`? Que quede en la hoja interactiva, no en la página, el layout o el contenedor (sección 3).
  2. ¿Agrega un `await`, `cookies()`, `headers()`, `params` o `searchParams`? Que haya un `loading.tsx` en ese segmento o un `<Suspense>` con skeleton alrededor, y que no viva en un `layout.tsx` sin su propio `<Suspense>` (sección 2).
  3. ¿Agrega I/O que puede fallar? Que un `error.tsx` por debajo del layout o un `catchError` lo contenga sin tumbar la chrome.
  4. ¿Agrega un estado de carga? Skeleton con la forma del contenido, no texto ni spinner (sección 4).
  5. ¿Hay una API de Next.js que resuelva mejor lo que el cambio hace a mano? Por ejemplo `useEffect` + `fetch` para datos iniciales, `<a>` en lugar de `Link`, `<img>` sin tamaño, `router.push` para un formulario de búsqueda, `try/catch` alrededor de `notFound()`. Consultar [nextjs-apis.md](references/nextjs-apis.md).
  
  Si nada del checklist aplica, seguir con la tarea sin reportar nada extra. Si algo aplica, sumar una línea por hallazgo al reporte de la tarea.
- **Modo completo** (pedido explícito sobre rutas, loading, errores, layouts o rendimiento de navegación; ruta o sección nueva; reestructura de `app/`). Seguir los pasos 0 a 5 completos.

No cambiar boundaries de rutas que el cambio no toca: si se detectan problemas fuera del alcance, listarlos como sugerencia al final en vez de corregirlos.

## Cobertura incremental

Obligatorio en cada ejecución, haya o no registro: seguí el [protocolo de cobertura](../../references/skill-coverage.md#protocolo-de-una-skill) con `--skill nextjs-route-ui-boundaries` en cada unidad funcional que toque el trabajo: `affected` (y la creación de la unidad si falta) y `check` antes de decidir, `begin`, `evidence` y `record` al cerrar. Si el repositorio no tiene `.golfo/skill-coverage/` o ninguna unidad cubre el código tocado, creálos en el paso 1 del protocolo antes de `check` (`init`; `discover --scope <carpeta> --write` en páginas del App Router o `add-unit --id --kind --module --subflow --entry <path:symbol>` para el resto; después ajustá límites, nombres e ids): proponer `discover` no alcanza. Si no se puede registrar (sin `node`, sin el CLI, falla de `add-unit` o de `record`), terminá el trabajo de la skill pero cerrá **incompleto** con el motivo concreto y qué falta para registrar ([cierre incompleto](../../references/skill-coverage.md#cierre-incompleto-o-bloqueado)), nunca como completo ni como simple limitación. Crear la unidad es parte de la skill; inventar cobertura o evidencia, nunca. El registro decide **cuánto** volver a revisar, nunca **si** cargar la skill: los disparadores de arriba mandan siempre. Para una ruta sin unidad, `discover --scope <carpeta de la ruta> --write` es el punto de partida; la unidad incluye la ruta en `routes` para que el motor sume su contexto.

- **Qué incluye la unidad para esta skill.** Además de su código, el motor suma lo que envuelve sus rutas: layouts y templates ancestros, `loading`/`error`/`not-found`/`forbidden`/`unauthorized` heredados, `default` de los slots paralelos, `global-error`, `next.config.*` y `middleware`/`proxy` ([detalle](../../references/skill-coverage.md#políticas-por-skill)). Por eso `affected --paths app/(platform)/layout.tsx --skill nextjs-route-ui-boundaries` lista todas las rutas bajo ese layout, y un handler aislado de una ruta no invalida las demás. Si `check` no ve una dependencia que sí decide un boundary (una ruta interceptada, una URL llamada por `fetch`), declarala en `dependsOn` de la unidad.
- **Decisión de `check` → modo.** `skip`: la cobertura verificada respalda el resto de la unidad, pero lo que vos agregás o tocás se revisa igual con el checklist del modo liviano. `incremental`: solo el alcance que lista `check` (cada parte con su foco: directiva `"use client"`, `await` nuevo en el render, archivo de ruta movido, layout compartido, skeleton) más su contexto necesario. `full`: los pasos 0 a 5 sobre toda la unidad. Una ruta nueva, una reestructura de `app/` o un pedido de auditoría completa usan `check --force-full` y modo completo aunque la cobertura esté vigente.
- **Modo de `begin`** igual al que usaste: `lightweight` (modo liviano sobre una unidad ya verificada), `incremental` (el alcance de `check`) o `full` (modo completo).
- **Evidencia** después de `begin`, solo de lo que realmente hiciste:
  - `review` con los segmentos y decisiones revisados (tabla del paso 2 o checklist del modo liviano).
  - `command` con `--exec` del build, lint o typecheck: tiene que correrlo el CLI; un comando declarado no acredita.
  - `browser` con lo recorrido en el dev server (navegación entre hermanas con la chrome fija, skeleton del segmento destino, error contenido y `retry`, shell server-rendered) o `test` con `--exec` de los tests que ejercen esos estados. El modo liviano pide `review` + (`command` o `test`).
  - Sin navegador o sin poder correr el build, registrá la falta con `--limitation`: el resultado queda `partial` (o `blocked` si nada se pudo verificar), que es lo que corresponde. No describas navegaciones ni builds que no ocurrieron.
- **Registros independientes.** La cobertura de `ui-ux-flow-patterns`, `optimistic-action-mutations` o `measured-performance-optimization` sobre la misma unidad no acredita esta skill ni la reemplaza: cada una registra la suya. Las mediciones de rendimiento son de `measured-performance-optimization`; esta skill no las exige.

## 0. Verificar la versión antes de escribir código

Las convenciones cambian entre versiones de Next.js (por ejemplo, `error.tsx` recibe `retry` además de `reset` desde 16.x, y con Cache Components un layout que lee datos runtime exige su propio `<Suspense>`). Antes de proponer código:

1. Leer la versión de `next` en `package.json` y si `next.config.*` activa `cacheComponents` o `partialPrefetching`.
2. Si existe `node_modules/next/dist/docs/`, leer ahí `loading.md`, `error.md`, `layout.md` y, si aplica, `instant-navigation.md` de esa versión. La doc instalada manda sobre lo que recuerdes.
3. Leer las instrucciones del proyecto (`AGENTS.md`, `CLAUDE.md`, `DESIGN.md`, convenciones de `docs/`): librería de componentes, primitivo de skeleton existente, estilos (CSS Modules, SCSS, Tailwind) y copy (idioma de los textos visibles). Reutilizar lo que ya exista antes de crear algo nuevo.

Ver [version-notes.md](references/version-notes.md) para las diferencias que más afectan estas decisiones y [nextjs-apis.md](references/nextjs-apis.md) para el catálogo de APIs (archivos especiales, prefetch e instant navigation, hooks de navegación, `notFound`/`forbidden`/`catchError`, Cache Components, invalidación, metadata, componentes optimizados y configuración) con el caso en que cada una aporta valor. Proponer una API solo cuando resuelve un problema concreto del código analizado, y avisar si es experimental y requiere un flag.

## 1. Mapear el árbol de rutas

Listar `app/` con sus archivos especiales y armar una tabla por segmento:

```text
segmento | layout | template | loading | error | not-found | page | ¿qué datos espera? | ¿qué UI comparte con hermanos?
```

Marcar en cada `page.tsx` y `layout.tsx`: `await` de datos, lectura de `params` / `searchParams` / `cookies()` / `headers()`, `"use client"` en el archivo raíz y componentes cliente grandes.

## 2. Decidir cada archivo especial

Leer [decision-rules.md](references/decision-rules.md) antes de decidir: es la fuente única de los criterios. Para cada segmento del mapa, recorrer en este orden:

1. Jerarquía de render y qué cubre cada boundary: [introducción de decision-rules.md](references/decision-rules.md#reglas-de-decisión-por-archivo-especial).
2. Chrome compartida: [layout.tsx compartido](references/decision-rules.md#layouttsx-compartido).
3. Espera de datos: [loading.tsx](references/decision-rules.md#loadingtsx) y [Suspense granular](references/decision-rules.md#suspense-granular).
4. Fallos: [error.tsx](references/decision-rules.md#errortsx), incluidos `global-error.tsx` y los error boundaries de componente.
5. Recursos inexistentes o sin permiso: [not-found.tsx, forbidden, unauthorized](references/decision-rules.md#not-foundtsx-forbidden-unauthorized).
6. Remontaje por navegación: [template.tsx](references/decision-rules.md#templatetsx).
7. Regiones independientes de una misma URL: [Parallel e intercepting routes](references/decision-rules.md#parallel-e-intercepting-routes).

Registrar cada decisión en la tabla del reporte y reportar los [anti-patrones](references/decision-rules.md#anti-patrones-a-reportar) que aparezcan en los segmentos analizados.

## 3. Decidir qué renderiza el server

Por defecto todo es Server Component y solo baja a cliente **la hoja interactiva**, nunca el contenedor entero. Leer [server-client-split.md](references/server-client-split.md) y, para cada elemento de la pantalla, aplicar el reparto, las preguntas y el catálogo (sidebar, header, tablas, filtros, formularios, gráficos y demás), con sus [patrones de composición](references/server-client-split.md#patrones-de-composición), y registrar cada cambio en la tabla "Server vs cliente" del reporte.

## 4. Skeletons en vez de texto plano

Un `loading.tsx` o un fallback de `<Suspense>` que devuelve texto ("Cargando...") o un spinner centrado se reemplaza por un skeleton con la **forma final** del segmento. Antes de escribirlo, leer las [reglas de skeleton-patterns.md](references/skeleton-patterns.md#reglas) y cumplir cada una en el código entregado (forma, alturas, contenido conocido, accesibilidad, motion con `prefers-reduced-motion`, ubicación y reutilización); usar spinners o texto solo en los [casos que esa referencia admite](references/skeleton-patterns.md#spinners-y-texto-cuándo-sí).

## 5. Aplicar y verificar

1. Presentar primero la tabla de decisiones por segmento (qué se agrega, mueve o elimina y por qué) y después aplicar los cambios en el código.
2. Respetar las convenciones del proyecto: estructura de componentes, estilos, idioma del copy visible y librería de UI.
3. Verificar:
   - `typecheck`, lint y build (un `error.tsx` sin `"use client"` o un layout que lee `searchParams` fallan acá o en runtime).
   - Navegar entre rutas hermanas en el dev server: el shell y el sidebar quedan fijos y aparece el skeleton del segmento destino, no una pantalla congelada.
   - Forzar un error en una página (throw temporal o toggle de boundary en React DevTools) y comprobar que el sidebar sigue usable y que `retry` recupera.
   - Recargar en una ruta con datos lentos: el HTML inicial ya trae el shell server-rendered (ver código fuente o desactivar JS).
   - Revisar el bundle o las islas `"use client"`: el sidebar no debería aparecer entero como componente cliente.
4. Actualizar o agregar tests de comportamiento que cubran los estados nuevos (render del skeleton, fallback de error con acción de reintentar, `notFound`), siguiendo la estrategia de testing del proyecto.
5. Cerrar con `record` por cada unidad tocada (creándola antes si faltaba) y sumar al reporte una línea por unidad: decisión de `check`, resultado registrado y pendientes; si no se pudo registrar, el cierre es incompleto con su motivo.

## Formato del reporte

```markdown
## Árbol analizado
<tabla por segmento del paso 1>

## Decisiones
| Segmento | Cambio | Motivo |

## Server vs cliente
| Elemento | Antes | Después | Motivo |

## Verificación
<comandos y comprobaciones ejecutadas, con resultado>

## Cobertura
<siempre: por unidad (creada en esta ejecución o existente), decisión de `check`, resultado de `record` y pendientes; si no se pudo registrar, `incompleta` con el motivo y qué falta>
```

## Límites con otras skills

- `refactor-ssr-data-fetching`: desde dónde se piden los datos (SSR, BFF o upstream) y qué DTO cruza al browser.
- `prevent-ssr-hydration-mismatches`: que el HTML de server y el primer render cliente coincidan (por ejemplo, el estado colapsado del sidebar leído de cookie y no de `localStorage`).
- `ui-ux-flow-patterns`: complementaria en todo cambio de UI; decide qué muestra cada estado (vacío, error, confirmación, toasts) y el feedback de cada acción. Cargar las dos juntas.
- `optimistic-action-mutations`: complementaria en todo cambio de UI; decide la clase, la concurrencia, el rollback y la reconciliación de cada acción que monta la ruta.
- `async-operation-error-handling`: errores de mutations y validaciones dentro de una pantalla, no de la ruta.
- `measured-performance-optimization`: medir el impacto (LCP, CLS, bundle) cuando el pedido es de rendimiento.
- `mobile-first-responsive-layout`: el comportamiento responsive del sidebar y la chrome.
