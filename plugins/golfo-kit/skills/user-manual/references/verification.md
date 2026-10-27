# Step 5 — Verify alignment

Read from `SKILL.md`, Step 5, before reporting a manual as done: the commands to run, what each one reports and what to cross-check against the code by hand.

**Record the source** the manual was written from, so the next update can start from a diff:

```bash
python3 scripts/source-trace.py record <manual.html> --repo <repo> --ref origin/<base> \
  --files <every file or directory read: pages, components, hooks, API routes, validations, constants, translations>
```

It writes the `heritage:source-repo|ref|commit|files|commit-url` metas into the `<head>` and, at the
end of the document, a `doc-footer` "Para el equipo técnico · Código: <base> @ <commit>" linked to the
commit on GitHub (only maintainers need it, so it stays out of the header; new tab; inside an
iframe viewer the host must allow links to the repository's GitHub organization). Prefer directories over single files where the
flow lives in one, so files added later are covered.

The `doc-meta` carries only what tells the reader something: `Fecha`, audience, device and
`Capturas`. No `Estado` (a published manual is always the current one), no app version (the package
version means nothing to the reader) and no `Código` (it lives in the `doc-footer`).

**Run the checks** and fix everything they report before publishing:

```bash
node scripts/check-manual.mjs <manual.html> \
  --translations <app>/i18n/<locale>/messages.po --translations <app>/app/translations/<locale>/messages.json \
  --forbidden "<every real value seen while capturing, comma-separated>"
```

It fails on: TOC links or titles that do not match the sections (in a staged manual: a top TOC, or
stages that are not intro → contiguous sections → recap with three key concepts, chapters with fewer
than two sections or sections before a stage's first chapter, or the staged
script and styles missing), missing navigation pieces, glossary
links without `<dt>`, pins on captures without `data-target`, a section with two pins of the same
number or with steps/references whose pin is not in that section, hosts in `mockup-url`, any change
marker, missing source metas, unexpected hosts or environment markers (`:8443`, `localhost`, …),
secrets (hidden inputs, CSRF, session ids), real values, and any text quoted between «…» that does
not exist in the app's translations (obsolete or misquoted strings). It warns when a mockup has no
`figcap`, the share URL is missing, the embedded navigation, staged or viewer script differs from its
source (an outdated copy: replace it with the current one), or the share URL is a document viewer
one (`/d/<doc_id>/view`) without its adapter.

Then serve the manual, inject `scripts/check-rendered.js` and run `await __umCheckRendered()` at
1280 px and at 390 px (inside an iframe viewer: `__umCheckRendered(iframe.contentWindow)`). It must return
`ok: true`: every capture rendered, none cut, every anchored pin next to its element, inside the
capture and within 24 px of what the reader sees in it (a pin on a wide cell fails: anchor it to the
icon, text or button inside). Also look at each pin: it must read as pointing at its element.
In a staged manual its `stages` list must be empty: shown sections match the chosen stage, print
shows everything and restores the stage, no horizontal scroll, menu and map off the content, pill in
the bottom left corner. Check also, in the published viewer, the items of DESIGN.md "Validación de la
variante por etapas" that a local page cannot prove (viewer URL, copy, reload, Back/Forward).

Cross-check against the code what the scripts cannot see:

- Every permission flag the code checks appears in **Permisos y prerrequisitos**, with its exact
  identifier and everything it enables, and no other section repeats what a permission enables.
- Every visible label, notice and error text appears in the prose or a table, and every one of them
  exists in the code (no obsolete strings).
- Every conditional render, redirect and guard maps to a rule in the doc.
- Every limit, format and timer matches the constant in the code.
- No fabricated behavior — only what the code actually does, confirmed on the running app.

Fix the HTML before reporting done.
