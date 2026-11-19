# user-manual

## Paleta de DESIGN.md

`DESIGN.md` de esta skill es la fuente única del design system Heritage Spec, también para otros repos que lo consulten.

Si se modifica la paleta o los tokens de motion de `DESIGN.md` (front matter) o el `:root` de `assets/boilerplate/base.css`, ejecutar `bash scripts/check-design-tokens.sh` desde esta carpeta y su suite `tests/check-design-tokens.bats`. Si se tocan breakpoints, espaciados o medidas de layout (tokens `breakpoints`, `spacing`, `layout` o el CSS de `assets/`), ejecutar `node scripts/check-layout-tokens.mjs`.

## Navegación y lectura por etapas

Si se modifica `assets/boilerplate/`, `assets/staged-reading/`, `assets/viewer-adapters/`, `scripts/check-manual.mjs`, `scripts/check-rendered.js`, `scripts/check-layout-tokens.mjs` o `scripts/build-manual.mjs`, correr `pnpm run test:user-manual` desde la raíz del repo, con Playwright disponible para la suite de navegador (ver el README raíz).
