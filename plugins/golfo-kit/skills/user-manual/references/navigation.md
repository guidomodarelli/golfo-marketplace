# Navigation of a manual

Read from `SKILL.md`, Step 4, before writing or reviewing the navigation of a manual. The components and their scripts are defined in DESIGN.md; this file says when to use them and how to verify them.

TOC, section map, section pill, "Inicio" button, copy-link buttons and keyboard shortcuts come from
DESIGN.md ("Índice (TOC)", "Mapa de secciones", "Píldora de sección", "Copiar enlace a una sección",
"Atajos de teclado", "Botón Inicio") and the boilerplate. When to use them:

- **TOC in every linear manual**, right after `</header>`, even with fewer than 5 sections. One entry
  per numbered section and, before the first section of each `part-header`, a non-link `toc-label`.
  Regenerate it after any edit that adds, removes, renames or renumbers a section. A staged manual
  has no top TOC: its pill sheet already lists every section, hidden stages included, and a second
  index would compete with the stage menu.
- **Stages, when chosen:** start from `assets/staged-reading/template.html` (its opening comment is the
  markup contract) and, once the manual is written on the boilerplate, run
  `node scripts/build-manual.mjs <manual.html>` to embed the staged CSS and script (run it
  again after updating them). The script reuses the boilerplate navigation instead of adding its own,
  so keep the boilerplate's navigation script current. Each stage opens with its objective and a
  reading estimate the script computes (200 words per minute) and closes with three key concepts and
  «Qué sigue». When a stage gathers several topics, group its sections in **chapters**
  (`div.stage-chapter`, at least two sections each); chapters order a stage, they do not hide parts
  of it. The script adds the active stage's outline to the menu, the reading progress, previous / next
  stage buttons in each recap and stage / chapter labels in the index sheet: do not write them by hand.
- **"Inicio" button always**, with the navigation script just before `</body>`.
- **Section map always**: never write its ticks by hand. Start each section with a paragraph that
  works as a one-line summary, because the map preview shows it. The map hides below 1024 px.
- **Section pill and TOC sheet always**: visible at every width and from the first screen (at the top
  it shows the document title), the only shortcut below 1024 px. The map, the sheet and the pill
  start with the document title, which leads back to the start. The header needs `id="top"` and a
  `.doc-title`, as in the boilerplate.
- **The URL follows the reader:** jumps and "Copiar enlace" write `#<slug>` (the start clears it), also in
  the address bar of an embedding viewer, so a reload lands on the same section.
- **Keyboard shortcuts** come with the script and are listed at the foot of the map preview:
  `⌥`/`Alt` + `↑` `↓` previous / next section, `⌥`/`Alt` + `I` table of contents, `Escape` closes
  previews. Nothing to add per manual; verify them.
- **Share URL** when the manual is published inside an iframe viewer: add
  `<meta name="heritage:share-url" content="<public document URL>">`, the URL readers open in the
  viewer; `<share URL>#<slug>` opens the manual at that section. When the viewer has its own link
  format (`/d/<doc_id>/view?href=<slug>` around an iframe `/d/<doc_id>/raw`), embed its adapter with
  `node scripts/build-manual.mjs <manual.html> --viewer document` (linear manuals too). It only
  updates the viewer's address bar after checking same origin and same document; otherwise
  navigation stays inside the manual and the limitation is logged, so never report the external URL
  as synchronized without checking it in the published viewer.

Verify on a **fresh load** and in the destination viewer: TOC links land with the section 16 px
below the top (16 px below the language switch when it covers the text column) about 2 s later; the button brings `scrollY` to `0`; at ≥ 1024 px a map tick magnifies
its neighbours and its preview shows number, title and first paragraph; at 375 px the pill opens the
sheet and its links land; `Alt`+`↓` moves to the next section; opening a copied section link
(`<share URL>#add-collaborators`) in a new tab, and reloading it, lands on that section in the viewer. Scroll with `behavior: 'instant'`
before screenshots. A browser tab in the background does not run `requestAnimationFrame` nor
dispatch scroll events: if "current section" checks fail in automation, check
`document.visibilityState` before blaming the script.
