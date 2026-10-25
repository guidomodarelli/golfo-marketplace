# Renders innecesarios

El criterio para decidir si un re-render es un problema vive en la sección [«Diagnose before optimizing»](../../react-render-performance-patterns/SKILL.md#diagnose-before-optimizing) de la skill `react-render-performance-patterns`. Esta referencia agrega solo las herramientas de medición, las causas frecuentes y las métricas propias de esta skill.

## Detectar

- React DevTools Profiler: grabar la interacción lenta y buscar commits largos y componentes que se renderizan sin que cambien sus props visibles ("Why did this render?").
- `<Profiler onRender>` temporal alrededor del árbol sospechoso: registra la duración y la cantidad de commits de la interacción sin depender de la extensión; quitarlo después de medir. React desactiva el Profiler en producción, así que sobre un build de producción exige el build de profiling (`react-dom/profiling`, p. ej. `next build --profile`) usado igual en antes y después; si no, usar el performance trace de DevTools sobre el build normal.
- Chrome DevTools MCP: performance trace de la interacción; long tasks atribuidas a scripting de React indican render caro.
- Causas frecuentes propias de esta skill: estado en un nivel demasiado alto y contexts que cambian de valor en cada render. Las props inline que rompen `React.memo` y los `setState` con valores iguales se diagnostican con [Pattern 4](../../react-render-performance-patterns/SKILL.md#pattern-4--stabilize-identities-with-usecallback-and-reactmemo) y [Pattern 5](../../react-render-performance-patterns/SKILL.md#pattern-5--guard-against-no-op-state-updates) de `react-render-performance-patterns`. Una lista o tabla que renderiza todas sus filas es un problema de tamaño del DOM: se diagnostica y corrige con [Listas y DOM grande](large-lists-dom.md).

## Corregir

Aplicar los patrones de la skill `react-render-performance-patterns` en el orden de ataque que define su sección [«Diagnose before optimizing»](../../react-render-performance-patterns/SKILL.md#diagnose-before-optimizing). Además, considerar:

- Bajar el estado al componente que lo usa o partir un context grande en varios.
- Si el commit es caro porque la lista monta cientos de filas, virtualizarla según [Listas y DOM grande → Corregir](large-lists-dom.md#corregir).

## Métricas antes/después

- Cantidad de commits y duración del commit en el Profiler para la misma interacción.
- INP o duración de la long task de la interacción.
- Cantidad de renders del componente objetivo.
