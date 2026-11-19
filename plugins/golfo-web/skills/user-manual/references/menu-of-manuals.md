# Menu of manuals

Read this only when the user asks for a menu of manuals.

When the user asks for a page that gathers the manuals of a tool ("el menú de la herramienta, con un
link al manual de cada sección"), build a **menu of manuals** (DESIGN.md, "Menú de manuales"),
not a manual:

- **Always a replica of the app's real menu, captured with `app-frame`** — never a grid of cards
  drawn by hand. Find the menu in the code (Step 1, "Find how the reader enters the flow"), capture it
  with **every card visible** (a user with all the permissions, or mocks that grant them) at the
  device the user chose, with the greeting's name replaced by a synthetic one.
- One `a.menu-link` per card, anchored with `data-target` + `data-target-text` (the card's text):
  - with a manual: `href` to the manual's public URL (the viewer's share URL), plus `#<slug>` when the card opens
    one part of a manual (a card covered by another tool's manual);
  - without a manual: `aria-disabled="true"` and no `href` (the script turns its icon gray and translucent; the texts stay as in the app).
  Ask the user which manuals exist and where they live when it is not clear.
- `<meta name="heritage:kind" content="menu">`; header with `Fecha` and `Capturas` (no audience); no
  TOC, section map, pill or "Inicio" button; `figcap` saying each user sees only the cards their
  permissions enable; a short legend (what a card opens, what a card with a gray icon means); the
  "Navegación entre documentos" script; source metas and footer from `source-trace.py record`.
- Languages as in Step 0 (ask). The cards' texts come from the catalogs like any capture text.
- **Each linked manual gets "← Ir al menú"** (`a.menu-back`, fixed top-left, first child of
  `<body>`, `data-document-link`, `href` = the menu's public URL; the arrow `←` in an `aria-hidden`
  span, never `‹` or `<`) and the "Navegación entre documentos" script; with Portuguese, its text in
  the `document` table (`Ir al menú` → `Ir ao menu`). When the menu is a
  new viewer document the user uploads, ask for its URL before republishing the manuals.
- `check-manual.mjs` checks a menu in its own mode (capture present, every link anchored, `href` xor
  `aria-disabled`, `aria-label`); `__umCheckRendered` and the cover check (every `menu-link` box equals
  its card's box) must pass at 1280 px and 390 px in every language. Inside an iframe viewer, verify that a card
  opens its manual in the whole page with the language kept, and that "Ir al menú" comes back.
