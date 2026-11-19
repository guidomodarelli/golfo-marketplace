# Probes en dispositivo real y medición local

## Servir un probe por LAN

- IP de la PC: `ipconfig` (adaptador WiFi). El teléfono tiene que estar en la misma red.
- **Harness de librería con Vite** (p. ej. `tests/browser/vite.config.ts`): crear `tests/browser/zz-<probe>.html` +
  `.tsx` que importen el barrel público, y servir con
  `node node_modules/vite/bin/vite.js --config tests/browser/vite.config.ts --host 0.0.0.0 --port <p> --strictPort`.
  En background, lanzalo con `pty=true`: sin TTY Vite sale enseguida. El `dist/` que usa es el último build:
  correr `pnpm build` (o el test que buildea) después de tocar el código fuente.
- **App Next real** (preferido para reproducir el contexto): ruta temporal dentro del route group del layout real
  (p. ej. `app/(platform)/zz-<probe>/page.tsx`, pública si el layout admite anónimos), reutilizando el
  `styles.module.scss` de la pantalla afectada y renderizando el componente con su estado inicial desde el
  servidor (SSR). Agregar la IP LAN a `allowedDevOrigins` en `next.config` (si no, el JS de dev no carga desde
  el teléfono y no hidrata) y levantar `next dev -H 0.0.0.0 -p <p>`. Revertir ambos al terminar.
- Variantes por override CSS en la misma página: envolver cada variante en
  `<span data-variant="X" style="display:contents">` y un `<style>` con
  `[data-variant="B"] [data-slot=...]{prop:valor!important}`. Rotular en la página qué es cada una.

## Playwright local (sin el navegador del usuario)

- Script `.mjs` copiado temporalmente a la raíz del repo (para resolver `@playwright/test`), borrado al final.
- Sesión: si el proyecto tiene sign-in de desarrollo por env (ver `pr-description-template`, paso 2 de capturas),
  iniciar sesión con `context.request.post("/api/auth/sign-in/email", { data, headers: { origin } })`.
  Las credenciales van solo al env del proceso de `next dev` (archivo en el scratch con modo 600, contraseña
  aleatoria que nunca se imprime), con el email de un usuario existente de la base sandbox leído por SQL.
  - Entrá como líder o como alguien sin suscripción paga: al abrir páginas de la tribu, la reconciliación de
    suscripciones corre contra el mock del proveedor de pagos y puede cancelar la suscripción y sacar de la tribu
    al integrante en la sandbox. Si pasó, ofrecé restaurarlo o resetear la sandbox (`pnpm db:sandbox -- --reset`).
  - Si faltan migraciones en la sandbox, las páginas fallan con funciones SQL inexistentes: aplicalas con
    `pnpm db:sandbox` antes de medir.
  - Al terminar, borrá el archivo de env y, en la sandbox, la cuenta `credential` y las sesiones que creó el login.
- Previews para el usuario: antes/después recortados con PIL, avatar difuminado (`GaussianBlur`), unidos en una sola
  imagen con rótulos y enviados por `MEDIA:`; para el PR, separá las dos mitades y subilas con el script de
  `pr-description-template` (en Windows, `TMPDIR` apuntando a una ruta nativa del scratch).
- Medir: `getBoundingClientRect()` del contenedor y del primer contenido visible; imprimir JSON por viewport
  (desktop 1366 y mobile 390).
- **Skeletons de `loading.tsx`**: navegar del lado cliente con `window.next.router.push(href)` (sin `??` con un
  fallback: `push` devuelve `undefined` y dispara el fallback, que recarga la página) y demorar solo las respuestas
  RSC con `page.route("**/*", …)` cuando `request.headers()["rsc"] === "1"`; así CSS/JS cargan y el skeleton
  aparece estilado. El throttling de red global deja el skeleton sin estilos.
- Antes/después de un cambio de CSS sin otro checkout: `git checkout origin/main -- <archivos>` pisa el árbol de
  trabajo sin guardarlo, así que el fix tiene que estar a salvo antes. Con el fix commiteado (`git status --short
  <archivos>` vacío): `git checkout origin/main -- <archivos>`, medir y `git checkout HEAD -- <archivos>`. Con el fix
  sin commitear: `git stash push -- <archivos>`, `git checkout origin/main -- <archivos>`, medir,
  `git checkout HEAD -- <archivos>` y `git stash pop`. Si eso no aplica limpio, medí el antes en un worktree de
  `origin/main` (`git worktree add --detach <dir> origin/main`).
