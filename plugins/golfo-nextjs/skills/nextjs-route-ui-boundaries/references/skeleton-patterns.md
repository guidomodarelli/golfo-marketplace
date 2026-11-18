# Skeletons para loading.tsx y Suspense

Un skeleton es una versión del contenido final sin datos: misma grilla, mismos tamaños, placeholders donde va el texto o la imagen. Comunica qué va a aparecer y evita que el layout salte cuando llegan los datos.

## Antes y después

Antes (anti-patrón):

```tsx
export default function Loading() {
  return <p>Cargando...</p>;
}
```

Después:

```tsx
import { MembersPageSkeleton } from "@/components/members/members-page-skeleton";

export default function Loading() {
  return <MembersPageSkeleton />;
}
```

```tsx
// members-page-skeleton: mismo contenedor y grilla que la página real
export function MembersPageSkeleton() {
  return (
    <section className={styles.MembersPage} aria-busy="true">
      <span className={styles.visuallyHidden}>Cargando miembros</span>
      <h1 className={styles.MembersPage__title}>Miembros</h1>   {/* lo que ya se sabe, sin placeholder */}
      <div className={styles.MembersPage__toolbar} aria-hidden="true">
        <Skeleton className={styles.MembersPage__searchPlaceholder} />
        <Skeleton className={styles.MembersPage__buttonPlaceholder} />
      </div>
      <ul className={styles.MembersPage__list} aria-hidden="true">
        {MEMBER_ROW_PLACEHOLDERS.map((placeholderKey) => (
          <li key={placeholderKey} className={styles.MembersPage__row}>
            <Skeleton className={styles.MembersPage__avatarPlaceholder} />
            <Skeleton className={styles.MembersPage__namePlaceholder} />
          </li>
        ))}
      </ul>
    </section>
  );
}
```

Adaptar nombres de clases, primitivo `Skeleton` y forma de estilos a las convenciones del proyecto.

## Reglas

1. **Misma forma que el contenido.** Reusar las clases de layout de la página (contenedor, grid, gaps). Si la página tiene 3 columnas de cards, el skeleton también.
2. **Alturas reales.** Cada placeholder con la altura del elemento final (línea de texto, avatar, fila de tabla). Una cantidad de filas parecida a la típica (o al tamaño de página de la paginación).
3. **Mostrar lo conocido.** Títulos de sección, breadcrumbs estáticos, labels de filtros, tabs y botones que no dependen de datos se renderizan reales (deshabilitados si su acción depende de los datos).
4. **Un skeleton por boundary.** El de `loading.tsx` cubre la página; cada `<Suspense>` interno tiene el skeleton de su bloque. Si la página usa ambos, el skeleton de `loading.tsx` se compone de los skeletons de bloque para que no diverjan.
5. **Accesible.** Contenedor con `aria-busy="true"` y un texto oculto visualmente que diga qué se carga; placeholders con `aria-hidden="true"`. Si la región es `aria-live`, no anunciar cada placeholder.
6. **Motion contenido.** Shimmer o pulse sutil, desactivado con `@media (prefers-reduced-motion: reduce)`. Respetar los tokens de motion del proyecto.
7. **Sin layout shift.** Medir antes/después (CLS en Lighthouse o el overlay de Layout Shift en DevTools): el reemplazo skeleton → contenido no debería mover nada que no sea el placeholder mismo.
8. **No para respuestas instantáneas.** Si el bloque tarda menos que un frame en promedio, un skeleton genera parpadeo. Preferir cachear o renderizar directo.
9. **Ubicación.** El skeleton de una pantalla vive junto a sus componentes (no dentro de `app/`), así lo reutilizan `loading.tsx`, `<Suspense>` y los tests.
10. **Reutilización.** Construirlo con el primitivo de skeleton del design system del proyecto. Extraer el skeleton de cada pantalla a un componente propio cuando lo usan `loading.tsx` y un `<Suspense>` de la misma página, para que no diverjan. Segmentos hijos con la misma forma reexportan el skeleton del padre (`export { default } from "../loading";`) en vez de duplicarlo.

## Spinners y texto: cuándo sí

- Acciones del usuario dentro de una pantalla ya cargada (botón "Guardar" en estado pendiente): spinner o estado `loading` del botón, no skeleton.
- Operaciones sin forma conocida (exportar un archivo, procesar un pago): indicador de progreso con texto.
- Nunca como fallback de un segmento de ruta.

## Tests

- Render del componente skeleton: expone el estado ocupado (`aria-busy`) y el texto accesible de carga.
- La página con datos no muestra el skeleton.
- Si el proyecto tiene e2e, una navegación con datos lentos muestra el skeleton del segmento destino mientras el sidebar sigue visible.
