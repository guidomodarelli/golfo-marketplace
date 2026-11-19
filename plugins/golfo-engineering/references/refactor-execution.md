# Ejecución compartida de refactors

Leer este archivo antes de refactorizar con `refactor-modularize-code`.

## Alcance y métricas

1. Inspeccionar archivo, callers, tests y convenciones cercanas. Medir líneas de archivo principal y líneas totales del feature antes de editar.
2. Identificar responsabilidades, dependencias y contratos públicos. Elegir una sola frontera cohesionada por fase.
3. Para archivos de aproximadamente 800+ líneas, acordar fases con usuario antes de extraer. Reportar ambas métricas tras cada fase: archivo principal y total del feature. No presentar reducción local como reducción total.

## Orden de extracción

1. Tipos compartidos hacia módulo neutral.
2. Constantes puras y vocabulario estable.
3. Helpers puros por responsabilidad.
4. Componentes, hooks o servicios.

Mantener código feature-local salvo reutilización real. Reexportar símbolos públicos movidos desde módulo original cuando existan importers externos.

## Estado y contratos React

- Mantener estado junto al componente o hook que posee ciclo de vida correspondiente.
- Cuando una extracción necesita coordinar reset, foco o invalidación entre parent e hijo, usar props explícitas y semánticas, por ejemplo `searchResetKey` u `onSearchFocusChange`.
- No cambiar orden de side effects, estados loading/error/disabled, accesibilidad, cache keys ni contratos API.
- Preferir tests de comportamiento en frontera pública. Agregar test directo de módulo extraído solo cuando integración existente no cubra comportamiento propio.

## Validación por fase

Después de cada extracción:

1. Ejecutar typecheck, lint y tests focales.
2. Medir ambas métricas.
3. Releer flujo principal y confirmar que quedó más claro, con menos responsabilidades mezcladas.
4. Verificar imports, exports y ausencia de ciclos.

Detener fases posteriores cuando frontera siguiente agregue más plumbing que claridad. Documentar trabajo diferido.
