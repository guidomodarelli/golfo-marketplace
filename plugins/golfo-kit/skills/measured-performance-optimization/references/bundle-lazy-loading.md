# Bundle y lazy loading

Barrels, paths analizables y carga condicional adaptan reglas `bundle-*` de vercel-labs/agent-skills `react-best-practices` (MIT, Vercel).

El objetivo es que la ruta inicial descargue y ejecute solo lo que necesita para el primer render útil.

## Detectar

- Analizar el bundle con la herramienta del bundler (ver [measurement-tools.md](measurement-tools.md#alternativas-sin-mcp)) y ubicar los chunks más pesados de la ruta inicial.
- Coverage de Chrome DevTools: porcentaje de JS descargado y no ejecutado.
- Dependencias pesadas importadas enteras (librerías de fechas, íconos, charts, editores, `lodash` completo) o importadas en un módulo compartido por todas las rutas.
- **Barrel files**: imports desde el `index` de una librería o de una carpeta propia que reexporta cientos de módulos (`import { Check } from 'lucide-react'`, `@mui/material`, `react-icons`, `components/index.ts`). Señales: arranque de dev y cold start lentos, muchos módulos en el análisis del bundle o en el trace de server para una ruta que usa pocos.
- **`import()` con path no analizable**: `import(variable)` o paths armados con strings hacen que el bundler incluya todo lo que podría coincidir (o avise que no puede analizarlo); lo mismo con `path.join(process.cwd(), variable)` en server, que ensancha el file tracing de Next.js.

## Corregir

- Code splitting por ruta (el router del framework suele hacerlo; verificar que no se rompa por un import compartido).
- Lazy loading de componentes que no están en el primer viewport o que aparecen tras una interacción: `React.lazy` + `Suspense`, `next/dynamic`, `import()` dinámico al abrir un modal, tab o editor.
- **Barrels**: en Next.js, sumar la librería a `optimizePackageImports` en `next.config` (conserva los imports nombrados y sus tipos; varias librerías comunes ya vienen incluidas por defecto, verificar la lista de la versión instalada); fuera de Next.js, imports directos al subpath (`@mui/material/Button`) si la librería publica tipos para ese path. En barrels propios, importar desde el archivo del módulo.
- **Paths analizables**: reemplazar `import(variable)` por un mapa explícito de loaders (`{ invoices: () => import('./invoices-panel') }`) y paths de filesystem literales por rama. Cargar módulos o datos grandes solo cuando la feature se activa (al abrir, habilitar o navegar), con skeleton mientras llegan y manejo de error del import.
- Importar solo lo necesario (imports nombrados de paquetes ESM como `import { debounce } from 'lodash-es'`, íconos individuales) y reemplazar dependencias pesadas por alternativas livianas o APIs nativas (`Intl`, `fetch`, `structuredClone`).
- Prefetch del chunk diferido en hover o idle cuando el usuario probablemente lo vaya a necesitar, para no mover la espera a la interacción.
- Revisar que el lazy loading no empeore LCP: el contenido del primer viewport no se carga diferido.

## Métricas antes/después

- KB de JS inicial (comprimido y sin comprimir) de la ruta.
- Cantidad de módulos cargados por la ruta y tiempo de arranque en frío (dev boot o cold start del server) cuando el problema era un barrel.
- Cantidad y tamaño de chunks de la ruta inicial.
- TBT/INP y LCP en el mismo throttling.
