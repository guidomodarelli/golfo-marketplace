# user-manual

## Paleta de DESIGN.md

`DESIGN.md` de esta skill es la fuente única del design system Heritage Spec, también para otros repos que lo consulten.

Si se modifica la paleta o los tokens de motion de `DESIGN.md` (front matter o `:root` del boilerplate), ejecutar `bash scripts/check-design-tokens.sh` desde esta carpeta y sus tests `bun run test:shell` (incluye `tests/check-design-tokens.bats`).

## Navegación y lectura por etapas

Si se modifica el script de navegación del boilerplate de `DESIGN.md`, `assets/staged-reading/`, `assets/viewer-adapters/`, `scripts/check-manual.mjs`, `scripts/check-rendered.js` o `scripts/embed-staged-reading.mjs`, correr `pnpm run test:user-manual` desde la raíz del repo, con Playwright disponible para la suite de navegador (ver el README raíz).
