# Qué renderizar en server y qué en cliente

Principio: el server renderiza la estructura y los datos; el cliente agrega solo la interactividad que necesita el browser. Cuando un elemento mezcla ambas cosas, se parte: contenedor en server, hoja interactiva en cliente.

Reparto por defecto:

```text
Server: estructura, datos, permisos, links, listas, textos, íconos, markup estático
Cliente: estado efímero, handlers, hooks de browser (usePathname para resaltar el link activo,
         useState para colapsar, refs, media queries, drag & drop)
```

Preguntas para cada elemento:

1. ¿Necesita estado, handlers, refs, efectos o APIs del browser? Si no, es server.
2. Si sí, ¿qué parte mínima lo necesita? Esa parte es la isla cliente; el resto sigue en server y se pasa como `children` o props serializables.
3. ¿El primer HTML tiene que salir ya en su estado final (colapsado, tema, tab activa)? Leer ese estado en server (cookie, segmento de la URL) para evitar saltos y mismatches de hidratación.

## Catálogo

| Elemento | Server | Isla cliente | Notas |
|---|---|---|---|
| Sidebar / nav principal | `<aside>`, items filtrados por permisos, `<Link>`, íconos, badges con conteos, todo dentro del `layout.tsx` | Resaltado del link activo (`usePathname`) como isla que envuelve o recibe los items, o un `NavLink` cliente por item; botón colapsar que alterna y persiste la cookie; drawer en mobile | Estado colapsado en cookie leída en server para que el primer HTML salga con el ancho correcto, sin salto. Items que dependen de datos runtime (usuario, membresías) dentro de `<Suspense>` con skeleton del sidebar, para que el resto del layout no bloquee la navegación. |
| Header / topbar | Logo, título de la sección, nombre y avatar del usuario | Menú de usuario (dropdown), toggle de tema, buscador con atajo de teclado, campana de notificaciones en vivo | El dropdown recibe el contenido ya renderizado como `children`. |
| Breadcrumbs | Derivados de la ruta y de los datos del recurso (nombre de la tribu, del curso) | Solo si se truncan dinámicamente según el ancho | Generarlos en la página o con `generateMetadata`/datos del segmento, no en el layout si dependen de `params`. |
| Tabs de sección | Lista de tabs como `<Link>` | Indicador de tab activa (`useSelectedLayoutSegment`) | Las tabs viven en el layout de la sección. |
| Footer | Todo | — | |
| Títulos, textos, contenido editorial, Markdown | Todo | — | Parsear Markdown en server para no enviar el parser al browser. |
| Listas, tablas, cards de datos | Filas y celdas con datos | Ordenamiento o selección en cliente si no se resuelve por URL, checkboxes de selección múltiple, menú de acciones por fila | Paginación, filtros y orden preferentemente en la URL (`searchParams` leídos en la página) para que el server renderice el resultado. |
| Filtros y buscador | Valores iniciales desde `searchParams` | Inputs controlados que actualizan la URL (debounce) | El cliente usa `useSearchParams` dentro de `<Suspense>`. |
| Formularios | Estructura, labels, valores iniciales, Server Action | Validación inmediata, estado pendiente (`useFormStatus`/`useActionState`), campos dependientes | Un formulario simple con Server Action funciona sin JS. |
| Modales y drawers | Contenido del modal | Apertura/cierre, focus trap | Para detalles navegables, intercepting routes. |
| Gráficos | Datos agregados, título, leyenda estática | El chart (librerías de canvas/SVG interactivo) | Cargarlo con `dynamic()` si es pesado y con skeleton del tamaño final. |
| Mapas, editores ricos, reproductores | Contenedor con tamaño fijo y fallback | El widget | `dynamic(..., { ssr: false })` solo si la librería no soporta SSR, con placeholder del mismo tamaño. |
| Toasts / notificaciones | — | Toaster montado una vez en el layout raíz | |
| Estado vacío y errores de datos | Todo | Acción de reintentar | |
| Banners de permisos o estado de cuenta | Todo, calculado con la sesión en server | Botón de descartar | Nunca decidir permisos solo en cliente. |
| Avatares e imágenes | `next/image` con tamaño declarado | — | Evita CLS. |
| Contadores en vivo, presencia, chat | Valor inicial | Suscripción (polling, websocket) | El valor inicial sale en el HTML; la isla solo actualiza. |

## Patrones de composición

Isla cliente que recibe contenido de server:

```tsx
// layout.tsx (Server Component)
<SidebarShell defaultCollapsed={collapsedFromCookie}>
  <SidebarNav items={itemsAllowedForUser} />
</SidebarShell>

// sidebar-shell.tsx ("use client"): solo maneja el estado colapsado
// sidebar-nav.tsx (server): renderiza los <Link>; un NavLink cliente resalta el activo
```

- No importar un Server Component desde un archivo `"use client"`: pasarlo como `children` o prop.
- Las props que cruzan a cliente deben ser serializables y mínimas (sin entidades completas, tokens ni datos que el cliente no usa).
- `"use client"` en el archivo más profundo posible: marcar un layout o una página entera como cliente arrastra a todos sus imports al bundle.

## Datos en Server Components

Fuente de esta sección: reglas `server-parallel-*` y `server-dedup-props` de vercel-labs/agent-skills `react-best-practices` (MIT, Vercel), adaptadas. Son patrones de performance: aplicarlos cuando el árbol tiene lecturas lentas e independientes o el payload RSC pesa (medición en `measured-performance-optimization` → [ssr-ttfb-streaming.md](../../measured-performance-optimization/references/ssr-ttfb-streaming.md)).

**Fetch en paralelo por composición.** Un Server Component que hace `await` antes de devolver su JSX retrasa a todos los hijos que renderiza: sus lecturas recién arrancan después. Si cada región necesita datos propios e independientes, que cada una sea un Server Component async hermano que pide lo suyo, y que el padre solo componga, sin `await`.

```tsx
// Incorrecto: TeamRoster recién empieza a pedir cuando terminó getTeamHeader.
export default async function TeamPage({ params }) {
  const { teamId } = await params;
  const header = await getTeamHeader(teamId);
  return (<><TeamHeader data={header} /><TeamRoster teamId={teamId} /></>);
}

// Correcto: hermanos que piden en paralelo; cada uno con su <Suspense> si conviene streamearlo.
export default async function TeamPage({ params }) {
  const { teamId } = await params;
  return (<><TeamHeader teamId={teamId} /><TeamRoster teamId={teamId} /></>);
}
```

- Si el padre necesita varios datos a la vez, arrancar las promesas juntas (`Promise.all`) en vez de awaits seriales.
- En listas con lectura anidada por ítem, encadenar la dependencia dentro de cada ítem (`ids.map((id) => getTeam(id).then((team) => getLead(team.leadId)))`) para que un ítem lento no frene al resto.
- Dónde poner el `<Suspense>` de cada región: [Suspense granular](decision-rules.md#suspense-granular). Deduplicar la misma lectura entre hermanos (`React.cache()`) y orden de `await` dentro de handlers: `refactor-ssr-data-fetching` → [server-cache-and-concurrency.md](../../refactor-ssr-data-fetching/references/server-cache-and-concurrency.md).

**No serializar lo mismo dos veces.** El payload RSC deduplica por referencia, no por valor: pasar `members` y además `members.toSorted(...)`, `members.filter(...)` o `{ ...member }` a un componente cliente manda los datos dos veces. Pasar la colección una vez y derivar en el cliente (orden, filtro, subconjunto), salvo que la derivación sea cara o el cliente no necesite el original; en ese caso mandar solo lo derivado. Medir el tamaño del payload antes y después según [ssr-ttfb-streaming.md](../../measured-performance-optimization/references/ssr-ttfb-streaming.md#métricas-antesdespués).

## Señales de que algo está mal ubicado

- Un componente cliente que hace `fetch` en `useEffect` para datos que existían al hacer el request.
- Un layout o página con `"use client"` en la primera línea.
- Props enormes serializadas hacia un componente cliente que solo usa dos campos.
- Estado visual inicial (colapsado, tab, tema) leído de `localStorage`: produce salto o mismatch de hidratación. Moverlo a cookie o a la URL.
- Un `page.tsx` o `layout.tsx` async que awaitea varias lecturas independientes en serie antes de renderizar hijos que podrían pedirlas solos.
- El mismo arreglo pasado a un componente cliente en dos props (original y ordenado o filtrado en server).
