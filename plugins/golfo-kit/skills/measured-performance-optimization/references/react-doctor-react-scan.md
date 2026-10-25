# react-doctor y react-scan vía golfo-lint

En proyectos que dependen de `react`, esta skill usa dos herramientas y las dos entran **solo a través de golfo-lint** (`@golfo/lint`, [github.com/guidomodarelli/golfo-lint](https://github.com/guidomodarelli/golfo-lint)):

- **react-doctor** como chequeo estático y gate de CI, con `golfo-lint react`.
- **react-scan** para contar re-renders en desarrollo, con `golfo-lint react-scan`.

**Excepción acotada.** golfo-kit no impone librerías: primero usa lo que el proyecto ya tiene, después lo nativo del framework, y recién entonces propone una librería nueva como decisión explícita. golfo-lint es una excepción decidida por el usuario: si el proyecto React no lo tiene, esta skill lo instala. La excepción cubre solo `@golfo/lint` y lo que él instala y configura; no habilita instalar react-doctor o react-scan por fuera de golfo-lint (otra versión, otros flags, telemetría) ni ninguna otra librería.

## 1. Asegurar golfo-lint

1. Buscar `@golfo/lint` en `devDependencies` del `package.json` de la app (en un monorepo, el del workspace que se mide). Detectar el package manager por el lockfile.
2. Si falta, leer la versión publicada en ese momento: `npm view @golfo/lint version`. Instalarla exacta, nunca `latest` ni un rango:
   - pnpm: `pnpm add -D --save-exact @golfo/lint@<versión>`
   - npm: `npm install -D --save-exact @golfo/lint@<versión>`
   - yarn: `yarn add -D --exact @golfo/lint@<versión>`
3. Sumar los peers con la versión exacta que pide la sección «Instalación» del README de **esa** versión (`npm view @golfo/lint@<versión> readme`): `react-doctor` (hoy `react-doctor@0.9.18`) y `eslint`. Con pnpm 12, la misma sección pide aprobar `unrs-resolver` en `allowBuilds` de `pnpm-workspace.yaml`.
4. **Si `npm view` responde 404 (`E404`)**, `@golfo/lint` todavía no está publicado: esta parte cierra **bloqueada** con el motivo «falta publicar `@golfo/lint` en npm». No instalar desde git (`github:guidomodarelli/golfo-lint`, un tarball o un clon), no instalar ni correr react-doctor o react-scan directo (`npx react-doctor`, `npx react-scan`) como reemplazo. El resto del flujo sigue con las herramientas de [Renders innecesarios → Detectar](unnecessary-renders.md#detectar) y el bloqueo va a **Sin medir** y **Limitaciones del agente**. Cualquier otro error de instalación (red, registry, auth) se reporta literal, con el mismo criterio de no buscar otro camino.

## 2. react-doctor: `golfo-lint react`

- Correrlo con el binario local: `pnpm exec golfo-lint react` (`npx --no-install golfo-lint react` con npm). Sin argumentos analiza la carpeta actual.
- No correr react-doctor a mano ni pasarle flags: golfo-lint ya lo ejecuta con `--blocking warning --no-respect-inline-disables --no-telemetry --no-supply-chain` y con las reglas de diseño visual apagadas. Llamarlo directo pierde eso y manda telemetría y la lista de dependencias a servicios externos.
- Códigos de salida: `0` pasó o no aplica; `2` análisis desconocido; `3` no pudo ejecutar la herramienta (si dice que falta react-doctor, instalarlo exacto según el paso 1.3); cualquier otro distinto de cero, hallazgos.
- Los hallazgos son **señales del paso 4**, no mediciones: uno de rendimiento se prioriza y se confirma midiendo; uno de estado y efectos se corrige con [state-and-effects.md](../../react-render-performance-patterns/references/state-and-effects.md) de `react-render-performance-patterns`. No se silencian: los `eslint-disable` en línea no tienen efecto, y apagar una regla en `doctor.config.ts` es una decisión explícita del usuario.

### Gate de CI

1. Buscar el CI del proyecto (`.github/workflows/*.yml` u otro).
2. Si ya corre `golfo-lint all`, react-doctor está cubierto (`all` ejecuta todos los análisis que aplican al proyecto): confirmarlo en el reporte y no agregar nada.
3. Si no, sumar un paso `pnpm exec golfo-lint react` (o el equivalente del package manager) en el job de lint o tests, después de instalar dependencias.
4. Si el proyecto no tiene CI, no crearlo en silencio: proponerlo en **Próximos pasos** como decisión explícita.

## 3. react-scan: `golfo-lint react-scan` (solo desarrollo)

- `pnpm exec golfo-lint react-scan` es el camino por defecto: instala `react-scan` con versión exacta como devDependency si falta y escribe en el entry de la app el import del helper `@golfo/lint/react-scan`, que activa react-scan solo en desarrollo con un import dinámico del paquete local, sin CDN. Detecta Next.js App Router, Pages Router y Vite.
- Si el comando no detecta el framework, la alternativa manual es importar ese mismo helper `@golfo/lint/react-scan` en el entry de la app, con `react-scan` como devDependency en la versión exacta que instala golfo-lint.
- Si responde con código `2` (análisis desconocido), la versión instalada de golfo-lint no trae el comando: actualizarla a la publicada con el paso 1.2. Si la publicada tampoco lo trae, react-scan queda bloqueado y los renders se cuentan con React DevTools Profiler.
- **Nunca** `npx react-scan init` (carga el script desde unpkg sin versión y ofrece instalar `react-doctor@latest`), un `<script src="https://unpkg.com/react-scan...">`, ni una integración escrita a mano que no sea el import del helper: golfo-lint es la única vía. react-scan **nunca** corre en CI ni en un build de producción.
- Antes de cerrar, correr el build de producción del proyecto y confirmar que react-scan no quedó en el output (`grep -rl react-scan .next/static` o `dist/`). Si aparece, es un defecto: no se entrega así.

### Medir con react-scan

- Sirve para **contar re-renders** y ver qué componentes re-renderizan en una interacción: levantar el dev server, repetir la misma interacción con los mismos datos antes y después del cambio con la automatización de navegador de la sesión y leer los conteos del componente objetivo en react-scan.
- Los **tiempos** (INP, duración del commit, long tasks) siguen saliendo del build de producción del [paso 3](../SKILL.md#3-medir-la-línea-base): React de desarrollo es más lento y no sirve para medir latencia.

## Métricas antes/después

- Renders del componente objetivo por interacción, con `golfo-lint react-scan (dev)` como herramienta en la tabla del paso 7.
- Hallazgos de `golfo-lint react` antes y después, por regla.
