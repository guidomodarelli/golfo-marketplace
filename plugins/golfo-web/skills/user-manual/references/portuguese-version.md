# Portuguese version

Read this only when the user asked for a Portuguese version in Step 0. The markup, the language
script and the switch behavior are in DESIGN.md ("Selector de idioma"); this file covers how to
translate and how to verify.

## Format: one Spanish manual plus a translation table

The manual is written and captured **once, in Spanish**. The Portuguese version is only the JSON in
`<script type="application/json" id="heritage-translations">`:

```json
{"pt": {"htmlLang": "pt-BR", "title": "Manual do usuário — …",
  "document": {"Cómo agregar colaboradores": "Como adicionar colaboradores"},
  "captures": {"Ingresar manualmente": "Digite manualmente"},
  "captureTemplates": {}}}
```

- **Keys are whole texts**: the text between two tags, without its edge spaces, exactly as written
  (with entities decoded), or the whole value of `aria-label`, `title`, `alt`, `placeholder`,
  `data-tooltip`, `data-target` or `data-target-text`. A sentence split by inline markup
  (`Tocá <strong>Confirmar</strong> para…`) gives one key per piece.
- **One translation per key.** The same Spanish text always becomes the same Portuguese text in its
  part of the table. If a piece needs two translations in two places, reword or regroup the markup so
  the texts differ.
- `document` holds the manual's texts; `captures` holds the app texts inside the captures; they are
  separate because the same word can be prose in one and an app label in the other (`Facility` in
  the glossary, "Instalação" in the app).
- `captureTemplates` is the exception: the full Portuguese HTML of a capture whose structure changes
  in pt-BR (the app shows other elements, not just other words). Leave it empty otherwise.
- Never duplicate the markup or the captures: no `<template>`, no `<name>--pt` frames.

## Translating, updating or adding a language: edit the table, do not capture again

Portuguese captures come from the Spanish ones plus the `captures` table, so a new or updated
translation never needs the app running or new captures:

- **First Portuguese version:** write both tables from the catalogs (below), with the manual already
  finished in Spanish.
- **The Spanish text changed:** update the affected keys. `check-manual.mjs` warns about keys that no
  longer match any text ("translation never used"), which is how a stale translation shows up.
- **Another language:** add its table next to `pt`, its option to the switch and its `UI_TEXT` entry
  in the navigation script.
- Capture again only when a screen changed in the app, or for a `captureTemplates` exception.

## Source of truth: the app's own catalogs

**Never translate an app text yourself.** Every text the app shows (labels, buttons, messages, the
quotes in the manual and every text of the `captures` table) takes its Portuguese from the repo's
translations: the `msgstr` of `pt-BR/messages.po` (or the pt-BR `messages.json`) for that `msgid`. If
the catalog does not have it, the app shows it in Spanish, and so does the manual. Only the manual's
own prose, which no catalog has, is written in Portuguese by hand, and it names every app concept
with the catalog's word (`atribuir`, `remover`, `padrão`…), never a synonym.

Read both locales from the branch you document, for example:

```bash
git show origin/develop:i18n/es-AR/messages.po
git show origin/develop:i18n/pt-BR/messages.po
git show origin/develop:app/translations/pt-BR/messages.json
```

- Build the Spanish → Portuguese map by **msgid**: the msgid is the Spanish source text. The es-AR
  catalog can be stale (a string missing there is shown as its msgid), so never require it in es-AR.
- Read plurals too: `msgid_plural` with `msgstr[0]` / `msgstr[1]`. In the pt-BR `messages.json` a
  plural entry is `[msgid_plural, msgstr[0], msgstr[1]]`: the singular translation is index 1, never
  index 0 (`"Pendiente": ["Pendientes", "Pendente", "Pendentes"]`).
- **Library and platform texts** are not in the app catalog: take them from their own source, never
  from your translation. For example the error page of a UI or framework package ("Ir à página principal", in its
  bundle under `node_modules/<package>/dist/`) or relative dates, which come from
  `Intl.RelativeTimeFormat` (`new Intl.RelativeTimeFormat('pt-BR', { style: 'long' }).format(-1,
  'minute')` → "há 1 minuto"). Put each verified pair in a small JSON file
  (`{"Ir a la página principal": "Ir à página principal"}`) and pass it to `check-manual.mjs` as one
  more `--translations-pt`. Pass that library file **first**: when a library text has the same msgid as
  an app string (a design system's pagination «Siguiente» → «Seguinte», app catalog «Siguiente» → «Próximo»), the
  first file wins.

## What stays in Spanish (or English)

The Portuguese version shows what a pt-BR operator really sees. Before translating any app text,
check in the source that it is translated:

- **Strings passed to `gettext` through a ternary or a variable**
  (`gettext(count === 1 ? '{0} operador seleccionado' : '{0} operadores seleccionados', …)`). The
  extractor does not pick them up, they are missing from pt-BR, and the app shows them in Spanish. The
  capture and the quote in the text stay in Spanish.
- **Texts hardcoded in the server** (for example an English `errorTitle`): same in every language.
- **Texts from another platform** (Training in App tours, platform "No autorizado" pages): they are
  not in the catalog and cannot be verified, so quote them verbatim.
- **Example data** (names, facilities, codes, process names) and values the operator types.

## Captures

The `captures` table translates the app texts of every capture: text nodes plus `placeholder`,
`aria-label`, `title` and `alt` (never `<style>` or `<script>`). List every app text of the captures,
look each one up in the catalogs, and report the ones left untranslated to review them against the
list above.

- **Sentences split by inline markup:** a catalog key like
  `!Perfecto! Los {1}{0} colaboradores{2} escaneados te seran asignados` renders as
  `…Los <b>3 colaboradores</b> escaneados…`. Translate the whole paragraph with its markup, not node
  by node.
- **Labels built as `{prefix}: {data}`** (pending-change tags, `Agregar: Inventory • Cycle Count`):
  translate only the prefix. When the value is itself a translated label (a status built with
  `getStatusLabel(i18n)`, a filter tag «Estado: Habilitado» → «Estado: Ativo»), the app translates both
  parts: write both translated in the `captures` table (`check-manual.mjs` accepts either form). In the
  prose, quote a tag whose value the app does not translate («Rol: ADMIN»), since a prose quote has a
  single expected form.
- **Placeholders:** catalog keys with `{0}` match texts with values ("Podés buscar hasta 100 IDs…").
  Use that matching only on capture texts and quotes, never on prose.

## Text

- The Portuguese text is the `document` table over the same markup: same sections, same captures.
- **Quotes are app texts.** «…» and “…” always quote an app string; in Portuguese they hold the exact
  pt-BR catalog string, with its values filled in, never a paraphrase. A truncated quote («Este
  usuario está inactivo…») becomes the first sentence of the pt-BR string plus "…". Values the operator
  types (`prueba`, `sin motivo`) go in `<em>`, not in quotes: `check-manual.mjs` checks every quote
  against the catalogs.
- **Only exact catalog matches in prose.** Matching `{0}` keys against prose mixes languages
  ("Quitar de la lista…" → "Remover de la lista…"). Translate prose yourself.
- **Pins:** a `data-target` that names an app text (`button[aria-label="Quitar Ada Lovelace"]`) and a
  `data-target-text` need a `document` entry that points at the Portuguese capture's text
  (`button[aria-label="Remover Ada Lovelace"]`).
- **Header:** `Público:` instead of `Audiencia:`; `title` follows the Spanish title format
  ("Gestão de operadores e contingência · Manual do usuário"). The capture runtime names frames
  "Captura de tela:" by itself when `<html lang>` is pt-BR.
- Glossary terms keep the word the reader sees in the app (`facility`), so `a.term` still resolves.

## Verify

1. `check-manual.mjs` with `--translations` (es-AR) and `--translations-pt` (pt-BR, plus the
   library pairs): 0 errors in both languages. For Spanish it also accepts the pt-BR msgids. It also
   checks the table against the catalogs: an entry whose Spanish is an app text and whose Portuguese
   is not that text's `msgstr` is an error, and a capture text the catalogs do not have is a warning
   (keep it in Spanish, or add its verified library source). A text that fits several catalog strings
   with different translations (`¡Hola {0}!` → `Olá {0}!` and `¡Hola {0} {1}!` → `¡Olá {0} {1}!`) is a
   warning: read in the source which `gettext` the screen calls and use that msgstr.
   No "translation never used" warnings.
2. `__umCheckRendered` in both languages, at desktop width and at 390 px: once loading `?lang=pt`, and
   once after switching in place from Spanish (pins must follow the translated captures).
3. A round trip es → pt → es leaves the text, the attributes and the captures exactly as before.
4. In the destination viewer: the manual opens in Spanish; the switch changes language in the same
   document (no navigation, a few tens of ms) and keeps the reading position: the block that was at
   the top of the screen (paragraph, step, row, capture) stays at the same distance from the top
   (±2 px), also mid-section and after the captures re-render; the viewer's address bar keeps `#<slug>`.

When measuring in the shared browser, the user may be using it too: a language change you did not
trigger is a click of theirs. Measure inside an iframe you create. If the emulated viewport is wider than the real window, fixed elements
look cut at the edge; compare `innerWidth` with `outerWidth` before reporting an overflow.
