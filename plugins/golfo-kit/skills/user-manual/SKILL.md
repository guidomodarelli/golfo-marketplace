---
name: user-manual
description: >
  Genera o actualiza un manual de usuario .html autocontenido (nunca .htm) para una feature o flow, o un
  menú de manuales (una réplica del menú de la app que enlaza cada card con su manual),
  escrito como user story para lectores no técnicos, a partir del diff de una branch o del código actual. Usa
  el design system Heritage Spec del DESIGN.md de la skill. Documenta las reglas de visibilidad
  de UI según permisos, roles y contexto del usuario. Los mockups son capturas reales de la app
  (con cualquier design system) en el dispositivo donde se usa el flow, con mocks temporales para cada
  variante de pantalla y datos sanitizados; los manuales se pueden publicar en un document viewer embebido. Usar cuando se pida documentar
  los cambios de una branch, crear o actualizar un manual de usuario o explicar un flow a usuarios no técnicos.
metadata:
  tags: "context-optimized-v1.20.1"
  author: "Guido Modarelli"
  version: "2.6.0"
---

# User Manual Generator

Produce a `.html` file (never `.htm`) written as a user story manual for non-technical readers,
either from the diff of a branch vs a base (default `develop`) or, when updating an existing
manual, from what the current code does. The visual system is Heritage Spec — read it in full from:

```
DESIGN.md   # in this skill's folder, next to SKILL.md
```

Read that file **before** writing a single line of HTML. Every color, font, spacing, and
component token must come from it.

Helpers live in `scripts/` (see "Helpers" at the end). Use them instead of rewriting the same code.

---

## Agent compatibility

Every question in this skill (device, languages, repo location, glossary terms) uses the question tool that is actually present in the session, per [`agent-capabilities.md`](../../references/agent-capabilities.md): `AskUserQuestion` in Claude Code, `clarify` in Hermes (up to 4 `choices` per question), `request_user_input` only when Codex is in Plan mode. With none of them, or when `clarify` returns `undelivered`, `timed_out` or `cancelled`, ask the same question in chat with numbered options and **stop** until the user answers; never pick a default device, language or repo on their behalf. Report the fallback under `Limitaciones del agente` in the final message.

The real-app captures ([references/real-app-mockups.md](references/real-app-mockups.md)) need a browser where you can **evaluate JavaScript in the app's page**; they clone DOM and CSS, so they do not depend on pixel screenshots. Each agent's browsers, how to recognise them and which ones are the user's own are listed only in row «Navegador real del usuario y capturas» of `agent-capabilities.md`. Pick from that row by what the screen needs:

- **The screen needs the user's session** (an internal app with sign-in): use a browser that row accepts as the user's own and that can evaluate page scripts.
- **A local dev server or test credentials the project provides**: any browser of that row that evaluates page scripts is enough, headless and app-embedded ones included, because nothing is published as an image.

Evaluate the snippet in the tab you opened or claimed, and close only the tabs you opened. A tool that only drives the desktop (`computer_use`) cannot evaluate page scripts, so it does not replace this tool. If no browser can evaluate scripts in the app, or the one available keeps failing to start, fall back to hand-drawn mockups as described in Step 4 and report it under `Limitaciones del agente`.

## Step 0 — Ask the device and the languages

Before reading code or opening the app, ask the user with the question tool of the agent (see
"Agent compatibility" above; with none, ask in chat and wait):

> ¿Este flujo se usa principalmente en celular, en escritorio o en ambos?

| Answer | Captures | Prose |
|---|---|---|
| Celular | Every screen at **375 px** (`fixedWidth`), inside `.mockup.mockup--mobile` | "Tocá", handheld wording; no desktop section |
| Escritorio | Every screen in a window **≥ 1280 px**. Captures stay **responsive** (see below) | "Hacé click" |
| Ambos | Desktop captures for every screen + 375 px captures where the layout differs | Both, with "Experiencia en celular" |

Desktop captures are always responsive: the capture snippet turns the app's width media queries
into container queries and `vw` into container units, and the runtime lays each frame out at
`min(capture width, reader width)`. A reader on a phone sees the app's mobile layout of that same
screen, as the app itself would show it. Nothing else is needed for that.

**Languages — ask, never decide.** In the same round of questions, ask:

> ¿Querés incluir también una versión en portugués? (Si no, el manual queda solo en español.)

Only if the answer is yes, ask a second question:

> ¿Traduzco también las capturas al portugués (la app en pt-BR), o quedan en español?

| Answers | Result |
|---|---|
| No portuguese (default) | Spanish only. **No language switch** and no translation table. |
| Portuguese, captures in Spanish | The Spanish manual plus the `document` translation table and the switch ("Selector de idioma" in DESIGN.md); the captures stay in Spanish (empty `captures` table). |
| Portuguese, captures in Portuguese | Same, plus the `captures` table, which translates the Spanish captures to the app's pt-BR texts in place: no second set of captures. |

Never add Portuguese, the switch or translated captures on your own, also when updating a manual:
an existing manual keeps its languages unless the user asks to change them. When there is a
Portuguese version, read `references/portuguese-version.md` before translating. The manual is written
and captured once, in Spanish; the Portuguese version is a translation table, so translating it again,
updating it or adding a language means editing that table, never running the app or capturing again.
App texts are never translated by hand: they come from the repo's `pt-BR/messages.po` (and its pt-BR
`messages.json`), and `check-manual.mjs` checks the table against those catalogs. The reference says which texts
stay in Spanish (strings the app does not translate), how quotes, pins and captures are translated,
and how to verify both languages. `check-manual.mjs` runs with `--translations-pt`. The manual always
opens in Spanish; the reader's choice is never stored.

---

## Step 1 — Gather context

**Find the repository first.** The folder where the user keeps their work repositories lives in the
`WORK_REPOS_DIR` variable of their shell. Read it from the environment, or from the export in their
shell startup file when the agent's shell did not load it:

```bash
echo "${WORK_REPOS_DIR:-}"; grep -h '^export WORK_REPOS_DIR=' ~/.zshrc ~/.bashrc 2>/dev/null | tail -1
```

- **Not defined:** ask the user, with the question tool, where they keep their work repositories. Then
  write it to their shell startup file (`~/.zshrc` for zsh, `~/.bashrc` for bash): replace the existing
  `export WORK_REPOS_DIR=` line, or append one. Tell the user it was saved and that new terminals pick it up.
- **Defined but the repo is not there** (or the user said it moved): ask again and update the same line.
- Never assume a personal layout or tool (`~/ghq`, `~/code`, `~/Projects`): only the current directory
  and `WORK_REPOS_DIR` are searched. Look there for the app's repo (`git remote -v` matching the app
  name), including the sibling repos of the same team.

When the repo is not there, **never guess and never search the whole disk at length: ask**, with the
question tool of the session (see "Agent compatibility"), offering:

| Option | What you do |
|---|---|
| It is at a local path | The user writes the path; check it is the right repo (`git remote -v`). |
| Clone it from GitHub | Ask for the repo URL and `git clone` it inside `$WORK_REPOS_DIR` (no need to ask where). Full clone that stays after the task, for future updates. |
| Temporary ephemeral clone | For a one-off manual, without leaving the repo on disk: `git clone --depth 50 --branch develop <url> /tmp/<name>` (depth enough to reach the recorded commit; deepen with `git fetch --deepen` if `source-trace.py diff` cannot find it). Delete it at the end. |

**Always document an up-to-date `develop`** (or the repo's base branch when it has no `develop`):
`git fetch origin develop` and read and run `origin/develop`, from a detached worktree or the
ephemeral clone, never from whatever branch the user's checkout is on and never pulling into it. The
exception is a manual of a branch diff the user asked for (below).

**Compare against the recorded commit, then record the new one.** Before reading code for an existing
manual, run `python3 scripts/source-trace.py diff <manual.html> --repo <repo>`: it fetches and compares
the commit recorded in the manual (its `heritage:source-*` metas, or, in older manuals, the commit the
`doc-footer` links to) with `origin/develop`, so you update only what changed since then. With no
recorded commit (no metas and no footer link), read the whole flow. Either way, when the manual is done,
`source-trace.py record --ref origin/develop` stores the documented commit in the metas and the footer
(Step 5), so the next update starts from it.

**New manual from a branch.** Run in parallel:

```bash
git log develop..HEAD --oneline
git diff develop..HEAD --stat
git diff develop..HEAD -- <key files>
```

**Updating an existing manual, or documenting a flow as it is today.** The source of truth is the
code of the base branch, not the old manual:

- **Start from the recorded source** ("Compare against the recorded commit" above; add `--patch` for
  the full diff). It lists the commits and files of the documented paths changed since the recorded
  commit (the whole repository when only the footer commit exists); "No changes" means the content is
  still current (only design or capture updates remain). Then read the whole flow anyway for new paths
  the old list did not cover. Manuals that record no commit are read from scratch. The commit is the same one the `doc-footer` links to ("Código: <base> @
  <commit>"); the diff reads it from the metas. After the update, run `source-trace.py record` again
  (Step 5) so the metas and the footer move to the commit you documented. With a Portuguese version,
  every Spanish text you change needs its entry in the translation table updated too
  (`check-manual.mjs` warns about entries that no longer match).

- If the user asks to ignore the current branch, or it has unrelated changes, read the base with
  `git show origin/<base>:<path>` and run the app from a **detached worktree** of the base
  (`git worktree add --detach /tmp/<name> origin/<base>`), never touching the user's checkout. Remove
  it at the end (`git worktree remove --force`).
- Read the whole flow: routes and server hooks (redirects, guards, error views), page components,
  modals, client and server validations, API error mapping, limits/constants, and the **translation
  files**. Quote visible texts from the translations of the reader's locale.
- For every error key the UI can show, check it has a translation. Keys without one appear raw on
  screen (`site_unmatch`): document them as they appear and report them as product bugs.
- Strings that exist only in translation files but no longer in code are obsolete: remove them from
  the manual.
- Compare the old manual section by section and list what is wrong, missing or obsolete before
  rewriting. Never mark sections as new or updated (see "No change markers").

From the code, extract:

- **UI surfaces** — pages, components, sections, panels, drawers, modals, snackbars, empty states.
- **Permission flags** — every `canXxx`, `userCanXxx`, `isXxx` boolean and authorization middleware.
- **Role / context conditions** — division checks, user type checks, attribute presence guards.
- **Data fields** — attributes, props, API keys surfaced in the UI.
- **Limits and formats** — maximum counts, accepted input formats, timers (inactivity, polling).
- **Mobile vs desktop differences** — responsive branches, FAB stacks, drawers.
- **i18n strings** — labels visible to the end user.
- **Entry points** — how the reader gets to the flow (see below).

**Find how the reader enters the flow.** Search the code, never guess:

- Grep the flow's route across the repo (`'/reports'`, `buildPath('…')`, `href=`, `navigate(`,
  `router.push`) to find home/hub pages, cards, menus, tabs or buttons that link to it, and follow
  redirects (index pages that send to a sub-route).
- Look for menu or navigation configuration in the repo (sidebar items, nav JSON, `setPageSettings`
  navigation, menu registries).
- For each entry found, record its visible label (from the translations), the route of the screen
  it lives on, and its visibility gates (permission flags, feature flags): an entry can be visible
  to everyone while the flow itself checks a permission, or the other way around.
- The outer menu often lives **outside the repo** (portal navigation, a microfrontend in another
  repo, a configuration service). Document only the part confirmed in the code, starting at the
  first screen that lives in the repo, and say in the report that the outer path could not be
  verified. Do not describe menus you did not see in code; if the user knows the outer path, they
  can provide it.

---

## Step 2 — Map visibility rules

Build a complete visibility matrix before writing prose. For each UI element answer:

| Element | Who sees it | Extra condition |
|---|---|---|
| … | `permissionFlag` or "Everyone" | any additional guard |

- If an element is gated by **multiple AND conditions**, list them all.
- If a value is filtered out when empty/null/placeholder (`not apply`, `n/a`, etc.), note it.
- If visibility differs between desktop and mobile, call it out.
- If a button is **always rendered but conditionally disabled**, separate visibility from
  enabled state — they are different rows or a split cell.

---

## Step 3 — Structure the document

Right after the doc header goes the **table of contents** (`Contenido`) in a linear manual, and the
page always ends with the floating **Inicio** button, the **section map** and the **section pill**.
See "Navigation (always)" in Step 4.

**Reading mode: linear or by stages.** Linear is the default and fits most manuals. Group the
sections into **stages** (DESIGN.md, "Lectura por etapas") only when a long manual overwhelms when
read top to bottom (many sections that serve different learning goals) and the user agrees; never
for short documents. Stages only change what is shown at a time: the standard order below, the slugs
and the sections themselves stay the same, and the pill sheet replaces the top TOC as the complete
index (a staged manual has no `nav.toc`; `check-manual.mjs` rejects one).

**Audience, always, confirmed by the user.** Before writing, deduce the roles that use or take part
in the flow:

- from the repo's own documentation: `README`, `docs/`, specs and SDD files (`PROJECT.md`,
  functional specs, actor tables), any `.md`, and JSDoc / Javadoc / TSDoc of the pages and services;
- from the code: permission and role checks (Step 2), position and role values, and who acts on each
  screen (who operates the tool, who only shows a QR or approves).

Then **always confirm them with the user** with the question tool, even when the docs and the code
agree: show the roles you propose, where each comes from (file or check) and what each does in the
flow, and let the user pick or rename them. When updating a manual, confirm its current audience the
same way. With the confirmed roles:

- the `doc-meta` carries `Audiencia: <rol> / <rol>` (`Público:` in Portuguese);
- the **Audiencia** section (`<section class="section" data-section="audience">`, right after
  **¿Para qué sirve?**) is the only place that describes them: a table `Rol | Qué hace en el flujo |
  Qué necesita`, one row per role, with short lists in the cells; "Qué necesita" names a permission
  or a condition in plain words and points to "Permisos y prerrequisitos" (or says "Ningún
  permiso"). ¿Para qué sirve? does not list the roles, and no other section keeps its own actors or
  roles table;
- the prose addresses the role that operates the tool, and calls the others by their role name.

**Standard order, the same in every manual** (a branch diff or a whole flow, new or updated). Each
standard section has a fixed slug as its id and in `data-section`, so `#faq` or `#permissions` mean
the same in any manual and `check-manual.mjs` can check the order:

| # | Section | Slug (`id` and `data-section`) | When |
|---|---|---|---|
| — | **Contenido** (TOC, not numbered) | — | always |
| 01 | **¿Para qué sirve?** | `purpose` | always |
| 02 | **Audiencia** | `audience` | always, confirmed by the user |
| 03 | **Permisos y prerrequisitos** | `permissions` | always |
| 04 | **¿Cómo se accede?** | `access` | always |
| 05 | **Flujo general del proceso** | `happy-path` | always |
| … | **Particularidades** of the flow: one section per screen, surface or variant (the initial configuration, each step) | own slugs | as needed |
| … | **Flujos no felices** | `unhappy-paths` | when the flow can stop or fail; always after the happy path and every particularity |
| … | **Límites y valores** | `limits` | when there are maximums, minimums, formats or codes to look up |
| … | **Mensajes y situaciones frecuentes** | `messages` | when the flow shows messages |
| … | **Buenas prácticas y recomendaciones** | `good-practices` | when there is advice worth giving |
| … | **Preguntas frecuentes** | `faq` | when there are real questions |
| … | **¿A quién escalar?** | `escalation` | when the user gives the channel |
| last | **Glosario** | `glossary` | only with the terms the user confirmed |

- **¿Para qué sirve?** — what the tool or flow is for and what the manual helps to do, in a few
  sentences (no roles: they go in Audiencia). For a branch diff, add what changed and why in one
  paragraph, with a before / after `compare` of the main screen when a before capture exists.
- **Permisos y prerrequisitos** — everything the reader needs before starting, only what really
  stops or changes the flow (a permission, a configuration, an account state, the device). Two parts:
  - **Permisos**: the **only place** that lists the permissions, one row per permission with its exact
    identifier in `<code>`, who usually has it, what it enables (every screen, action and element it
    gates, from the matrix of Step 2) and what happens without it. A table of elements only for what a
    permission gates (an entry card, a screen, a button, an option); behavior that depends on data or
    state belongs to its screen's section. Permission identifiers only, never the front end's internal
    names (`canEditReports`). The rest of the manual names a permission in plain words and links
    here. When the flow checks no permission, one sentence says so.
  - **Prerrequisitos**: the other conditions, with who must meet each and what happens when it is not
    met. Leave out anything that does not change what the reader sees or can do.
- **¿Cómo se accede?** — the main menu or screen that holds the entry, deduced from the code (Step 1):
  a real capture, its route in the `mockup-url`, an anchored pin on the card/item/button, its exact
  label, who sees it and what happens without access. When the entry is a card of a menu, capture the
  menu with **every card** (the same capture in every manual of that menu) and keep only this manual's
  card in color: `data-mute=".<card>"` + `data-mute-except=".<card>:nth-of-type(N)"` on the `app-frame`
  (the runtime grays the other cards' icons); the entry is a `steps` item ("Tocá «…»" / "Hacé click en
  «…»") tied to the pin, and how to go back is a sentence after it. When the outer menu lives outside the repo,
  start at the first screen that is in it, without inventing the steps before it. When the entry
  cannot be deduced from the code, **ask the user** how readers get there; never skip the section.
- **Flujo general del proceso** — the happy path end to end: an overview of every screen in order,
  then the `steps` linked to `hotspot` pins on each capture, and how the reader knows it ended well.
  Step-by-step guides live here and in the particularities, never as separate "Guía paso a paso"
  sections.
- **Particularidades** — each screen, surface or variant in detail (all its states), with its steps and
  pins, starting with the initial configuration. Mobile-specific behavior goes here when Step 0 was
  "Ambos".
- **Flujos no felices** — the paths that stop or fail (error screens, no access, invalid
  configuration, a failed confirmation, an empty result): what the reader sees (capture), why and how
  to go on. **Never before the initial configuration, the general flow or the happy path**: the reader
  learns how it works first, then how it fails, so the section goes after the last particularity and
  before the closing sections. Each message is explained once, in **Mensajes y situaciones
  frecuentes** (the reference catalog: message, cause, what to do); the unhappy paths link to it
  instead of repeating it.
- **Buenas prácticas y recomendaciones** — one block per role of the Audiencia (who operates the tool,
  who takes part), so advice for different roles does not split into two near-identical sections.
- **¿A quién escalar?** — when to escalate and through which channel. The channel never comes from
  the code: **ask the user** for it; without an answer, leave the section out.
- **Glosario** — technical terms and business-specific language (`facility`, `site`, an account ID, a
  role or process name) defined in plain words. **Which terms go in is the user's decision**
  ("Glossary terms — ask" in Step 4); with no confirmed terms there is no glossary: no section, no
  TOC entry and no `a.term` links.

Optional sections that have nothing to say are left out; the others keep their relative order.
Updating an existing manual means moving its content into this order (merging sections that say the
same, such as "Objetivo" and "Qué es…" into ¿Para qué sirve?), not keeping a different one.

Adjust sections when there is little to say — skip sections that have nothing to say.

---

## Step 4 — Write the HTML

### Output file

Write the file to `user-guides/<feature-slug>.html` under the project root (e.g.
`user-guides/user-detail-sidebar.html`). Ask the user if the slug is unclear. Ensure
`user-guides/.gitignore` exists and contains exactly `*`; create or overwrite it otherwise. When the
manual only lives in its destination (for example a document in a hosted viewer being updated), work in `/tmp`.

### HTML skeleton (copy from DESIGN.md boilerplate exactly)

- Encoding `UTF-8`; viewport `width=device-width, initial-scale=1.0`.
- Google Fonts via `<link>` + `preconnect`: `DM Sans` (400/500/600) + `DM Mono` (400/500).
- All CSS inline in `<style>`. Colors only through the `:root` variables. The one exception is the
  real-app capture payload injected by `scripts/embed-app-frames.mjs`.
- Semantic markup: `<header class="doc-header">` + `<h1 class="doc-title">`, one
  `<section class="section" aria-labelledby="<slug>">` per numbered section with
  `<h2 class="section-title" id="<slug>">`.
- **Section ids are fixed slugs**, never `sNN` and never the title: short kebab-case English words
  that say what the section is about (`prerequisites`, `add-collaborators`, `permissions`,
  `glossary`), unique in the manual and the same in every language. Choose it when the section is
  created and never change it: renumbering, inserting sections in between or retitling leave it as
  it is, so a copied link keeps opening the same section. Ids of deleted sections are not reused.
- Keep the `beforeprint` script. Max width `860px`, centered.

### Components to use (from DESIGN.md)

| Need | Component |
|---|---|
| Document header | `doc-header` + `doc-label` + `doc-title` + `doc-sub` + `doc-meta` |
| Table of contents (**linear manuals**) | `nav.toc` + `toc-label` + `toc-num`, right after the header |
| Reading by stages (**long manuals, when agreed**) | `div.stage-intro` + sections with `data-stage` + `aside.stage-recap`, from `assets/staged-reading/template.html` |
| Section map (**always**) | empty `nav.section-rail`, next to the "Inicio" button |
| Section pill + TOC sheet (**always**) | `button.section-pill` + `dialog.toc-sheet` |
| Numbered section | `section` + `section-num` + `section-title` |
| Major divider | `part-header` + `part-header-label` + `part-header-title` |
| Info / warn / ok / error note | `callout` `.c-info` / `.c-warn` / `.c-ok` / `.c-red`, starting with a `<strong>` keyword |
| Comparison table | `.table-wrap` > `table` + `th scope="col"` + `td` with `badge` pills for status |
| Permission / status pill | `.badge` `.b-green` / `.b-amber` / `.b-red` / `.b-gray` |
| Process walkthrough | `ol.steps` > `step-item` + `step-circle` + `step-label` + `step-desc` |
| UI preview | `mockup` + `mockup-bar` (`mockup-dots` + `mockup-url`) + `app-frame` or `mockup-body`, then `div.figcap` |
| Mobile capture | `.mockup.mockup--mobile` (375 px captures, centered) |
| Concrete scenario | `example-box` + `example-label` |
| Value transition (`US$ 15 → US$ 20`) | `flow` + `pill-stale` / `pill-neutral` / `pill-success` |
| Reference block (rules, errors, checklist) | `details.acc` + `summary` (+ `acc-num`) + `acc-body` |
| Numbered pins on a capture, tied to steps | `div.hotspot-stage` + `span.hotspot[data-target]`; `data-hotspot` on `step-item` and `span.hotspot-ref` |
| Before / after of one screen | `div.compare` |
| Domain term with its definition | `a.term` → `dl.glossary` (`dt` + `dd`) |
| Inline identifier | `<code>` |

Copy the markup from the "Snippets de componentes" block in DESIGN.md; class names are a contract.

### No change markers

Never mark sections as new or updated: no `data-change`, no "Nuevo" / "Actualizado" badges, no
"Novedades: N secciones" in the `doc-meta`. An updated manual reads as the complete, current
document; its history lives in the destination (the viewer's versions).

### Navigation (always)

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
  `node scripts/embed-staged-reading.mjs <manual.html>` to embed the staged CSS and script (run it
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
  `node scripts/embed-staged-reading.mjs <manual.html> --viewer document` (linear manuals too). It only
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

### Glossary terms — ask

When the prose is written, list the candidate terms (technical words and business language the text
uses: codes, roles, process and place names, identifiers) and ask the user which ones go in the
glossary, with the question tool (`multiSelect`; at most four options per question, so split the
candidates into several questions or list them in chat when there are more). Show each candidate
with the one-line definition you would write. Then:

- the glossary holds exactly the confirmed terms, in the order the reader meets them;
- only those terms get `a.term` links; unconfirmed ones stay plain text;
- a link goes only in the manual's own prose: never inside an app text (a label, a button, a screen
  or modal name such as «Solicitar acceso», even when it is not in bold or quoted), a heading, a
  caption or a mockup bar;
- no confirmed term: no glossary section at all (an empty glossary is never shown);
- when updating a manual, keep its confirmed terms and ask only about new candidates.

### Pins, before / after and glossary

- **Pins, as many as make sense — always.** A manual is a practical guide: every element the text
  tells the reader to look at, tap, fill or read on a capture gets a pin, not only the ones in a
  `steps` list. On each capture, pin every button, field, tab, filter, badge, message or value the
  prose names, and put the matching `hotspot-ref` where the prose names it ("Tocá «Confirmar» (2)").
  When a section describes a screen element by element, turn that description into a short `steps`
  list or a list of references, so each pin has its text. Only skip a pin when it would point at
  nothing the reader acts on or reads (decoration, layout). Before closing a manual, walk every
  capture and ask "what does the text ask the reader to find here?"; each answer needs a pin.
- **Steps before their capture:** an `ol.steps` linked to a capture always goes **before** that
  `.mockup` and its `figcap`, never after (DESIGN.md, "Puntos sobre capturas").
- **Pins in reading order:** number the pins of each capture top to bottom and, on the same row, left to
  right; across several captures of a section the numbering continues. Steps and references take the same
  numbers, so steps are written in that order; an action that must come before one placed higher goes in a
  separate steps list. Inline references are mentioned in that same order inside each paragraph, list or
  table ("(5) … (6) … (7)"); when a sentence names the elements in another order, rewrite it following the
  capture. `check-rendered.js` reports captures out of order (`order`) and `check-manual.mjs` reports
  references out of order in the text.
- **Inline references before their capture, too:** the paragraph, list or table holding `hotspot-ref`s
  goes right before the capture with those pins: steps → text with references → capture → figcap. A list
  that names pins of several consecutive captures is split, one list before each capture. `check-manual.mjs`
  reports references that come after their capture.
- **Pins on steps:** on the capture of every screen with a `steps` walkthrough, one pin per step that
  touches a visible element, same number as the step. On real captures **always anchor the pin**:
  `data-target="<selector inside the capture>"` plus `data-target-text="<exact text>"` when the
  selector matches several elements. The capture runtime places it 14 px left of the element after
  every fit and resize, so it never drifts. Keep `--x`/`--y` as the initial position. Then check, at
  1280 px and 390 px, that every pin sits next to its element. Up to 6 pins per capture: when a
  screen needs more, split the text in two groups and repeat the capture for the second one.
- **Anchor to a compact element** (icon, button, input, a short label), never to a full-width cell or
  row: the pin sits 14 px left of the element, so on a cell that starts at the frame's edge it ends up
  cut or outside the capture. For repeated elements without own text, use a structural selector
  (`.card:first-of-type .card__icon`).
- The runtime places the pin next to what the reader **sees** of the target: its text and media, or
  the whole box when it has a visible background or border (a button, a chip, a message). So a
  centered title or a transparent link works as a target. When a row starts with a badge or an icon,
  anchor to that first item (the pin would otherwise sit on top of it), and to the whole message box
  rather than its title (the icon inside would be covered).
- When there is no room on the left (the target starts at the capture's edge) the runtime puts the pin
  on the right, or just inside a full-width button. When the target is glued to text on its left (a
  "+2" right after a value), add `data-side="right"`. Switches and checkboxes: anchor to the control
  (the switch element with its text), not to its label, or the pin covers the toggle.
- **Pins live with their steps, one per number per section.** A section never shows two pins with
  the same number, and never pins a capture for steps written in another section. When a step
  happens on a screen already shown elsewhere (the main screen in its own section, the steps in
  "Cómo agregar…"), repeat that capture (same `data-cap`, no extra payload) inside the step's
  section with its pin, and leave the original without pins. Write "en esta pantalla", never
  "marcado en la sección NN". The navigation script links them both ways, always scrolling: tapping a
  step or a reference centers its pin, and tapping the pin centers its step's circle; the destination
  then pulses 3 times under a short blur spotlight so the reader sees what it points to (a pin's "back" bubble leaves with the last beat). Check both directions in the browser, in
  a section with pins on several captures: after the jump, only the destination stays highlighted.
  The script also signals that the circles can be tapped (a small hand on each step circle that keeps
  tapping while the pointer is on the step, a "back" bubble on each pin shown on hover and on arrival, hover growth, a tooltip with the action and,
  under the first capture with pins of each section, «Hacé click en un número para ir a su paso.»
  with a mouse or «Tocá un número para ir a su paso.» on touch screens, chosen by the pointer), so
  never write that hint by hand.
- **Before / after:** only when both captures have the same width and framing. Give each
  `app-frame` its own `aria-label`. Otherwise show two separate mockups.
- **Glossary:** link only the first use of each term per section; every `a.term` points to an
  existing `<dt>`; plain-word definitions.

### Mockups

**Default: capture the real app, every screen and every variant.** Follow
`references/real-app-mockups.md` in full before capturing. In short:

- Run the app locally with the project's mock layer and create **temporary synthetic mocks for
  every state of every screen** the manual shows: success, each validation error, each blocking
  modal, each non-blocking notice, empty and loading states, limits, creation errors, result
  screens with successes and failures, polling that ends in error, invalid configuration pages.
  Delete them all at the end.
- Intercept every upstream the flow touches **before** navigating: a missing fixture proxies to the
  real upstream, which for a confirmation creates real data.
- Capture at the device from Step 0 with `scripts/frame-driver.js` (iframe at 375 px or ≥ 1280 px),
  export with `__umExport(…, { endpoint })` to `scripts/capture-bridge.py`, embed with
  `scripts/embed-app-frames.mjs`.
- In shared environments (production, sandbox, staging) navigate read-only and never confirm.

**Fallback: hand-drawn mockups** (`mockup-body`) only when the app cannot be reached, no browser can evaluate scripts in it (see "Agent compatibility"), a gate blocks
it, or its stylesheets are cross-origin and blocked; say so in the report.

Use real label strings and example data, never real people or IDs. The `mockup-url` shows only the
route or the dialog title, never a scheme, host or port, and prose never names an environment host.
Every mockup is followed by a `figcap` describing the screen, with "(datos de ejemplo)" when it shows
data. List enum values in a table with code and display name.

### Downloads

The user pre-authorizes every download this workflow needs; prefer the local bridge over browser
downloads. Before the first one, read `references/downloads.md`.

### Section references

Every mention of another section is a link named after it, never a bare number: `<a href="#permissions">sección
Permisos y prerrequisitos</a>`, or `secciones <a href="#a">A</a> y <a href="#b">B</a>`. Portuguese uses `seção`
and the translated title. No quotes around the title (quotes are for app texts). A link inside a step with a pin
goes to the section, not to the pin (DESIGN.md, "Referencias a secciones"); `check-manual.mjs` reports any
"sección NN" left without a link.

### Writing tone

- Address the reader as **the operator**. Mobile flows: "tocá"; desktop: "hacé click".
- No code, no jargon. Refer to UI elements by their visible labels. Exceptions in `<code>`: permission
  flags in the permissions table, configuration values support needs (position codes, facility
  types) in tables, and error keys the app shows untranslated.
- Quote visible texts exactly as the app shows them, typos included, and say so in the caption when
  they look wrong.
- Short paragraphs, one idea each. `<strong>` for emphasis, never colors.

---

## Step 5 — Verify alignment

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

---

## Menu of manuals

When the user asks for a page that gathers the manuals of a tool ("el menú de la herramienta, con un
link al manual de cada sección"), build a **menu of manuals**, not a manual: read
`references/menu-of-manuals.md` in full first.

---

## Step 6 — Publish (when the destination is a document viewer)

When the manual lives in a hosted document viewer, start from its current published version (not an
old local copy), remove anything the viewer injected into the downloaded HTML, re-run
`check-manual.mjs` on the exact file to publish, publish it with the viewer's own mechanism and
verify in the viewer after a cache-busting reload. Publishing a new version of a document the user
pointed to is authorized by the request; any other document needs confirmation.

---

## Helpers

| Script | Where it runs | What it does |
|---|---|---|
| `scripts/capture-snippet.js` | App page / iframe | `__umCap`, `__umCheck`, `__umExport` (download or `endpoint`), `__umClear`. Converts width media queries to container queries, `vw` to `cqw`, resolves `vh`; drops hidden inputs and environment hosts |
| `scripts/frame-driver.js` | App page | `__umFrame({ width, height, snippetUrl })`: drives a same-origin iframe at the device width, reloads the snippet per navigation, fills React inputs, finds buttons/modals, captures with `fixedWidth` on mobile |
| `scripts/capture-bridge.py` | Terminal | Serves files with CORS for one origin and stores POSTed JSON exports (127.0.0.1 only) |
| `scripts/embed-app-frames.mjs` | Terminal | Embeds captures into the manual (lazy shadow-root frames, fit, fixed-layer containment, responsive layout, anchored pins) |
| `scripts/check-manual.mjs` | Terminal | Static checks of the final HTML (structure, navigation, pins, hosts, secrets, real values, quoted texts vs translations, change markers, source metas, outdated navigation script) |
| `scripts/check-rendered.js` | Manual page / viewer tab | `__umCheckRendered(view)`: captures rendered, fit, anchored pin distance; staged contract (`stages`) |
| `scripts/embed-staged-reading.mjs` | Terminal | Embeds `assets/staged-reading/` CSS + script and, with `--viewer document`, `assets/viewer-adapters/document-viewer-adapter.js`; `--example <out>` builds the template on the boilerplate |
| `scripts/source-trace.py` | Terminal | `record` writes the source metas and "Código:" line; `diff` lists what changed in the documented paths since then |

Write one-off scripts (migrations, fixture generators) in the moment for the manual at hand; do not
add them to `scripts/`.

---

## Output checklist

- [ ] Step 0 asked: captures and prose match the device the flow is used on.
- [ ] Every `steps` list linked to a capture comes before the capture, not after.
- [ ] Every inline reference (`hotspot-ref`) sits right before the capture with its pin, never after.
- [ ] Pins of every capture are numbered top to bottom, left to right (`__umCheckRendered` `order` is empty).
- [ ] Inline references are mentioned in ascending order inside each paragraph, list and table.
- [ ] Never two accordions open at once in the whole document, also when a jump opens one.
- [ ] Glossary terms show one superscript per mention (added by the navigation script); each one opens its mention (and its closed accordion) with 3 beats and the spotlight, and a term opens its definition the same way.
- [ ] Every mention of another section is a link with its title, never a bare number; clicking it inside a step goes to the section, not to the pin.
- [ ] Step 0 asked about Portuguese (and, if yes, about translating the captures); a Spanish-only
      manual has no language switch.
- [ ] With Portuguese: every quote («…» or “…») is the exact app string of its language, texts the
      app does not translate stay in Spanish, pin selectors point at the pt capture texts, and
      `__umCheckRendered` passes with `?lang=pt` at desktop and 390 px.
- [ ] Quotes only hold app texts; values the operator types go in `<em>`.
- [ ] Audience confirmed by the user (proposed from the repo's docs and code): `Audiencia:` in the
      `doc-meta` and an **Audiencia** section right after ¿Para qué sirve?, the only place that describes the roles.
- [ ] Repo found locally or provided by the user (local path, clone from GitHub inside `$WORK_REPOS_DIR`, or ephemeral clone, asked with the question tool); the manual documents an up-to-date `origin/develop`, compared first with the recorded commit (`source-trace.py diff`).
- [ ] `source-trace.py record` ran: source metas in the `<head>` and "Código: <base> @ <commit>" in
      the `doc-footer`, linked to the commit on GitHub.
- [ ] `check-manual.mjs` exits 0 with the app's translations and the real values seen, and its
      warnings were resolved or explained in the report.
- [ ] `__umCheckRendered()` returns `ok: true` at 1280 px and 390 px, locally and in the destination.
- [ ] File is `.html`, under `user-guides/` (or `/tmp` for destination-only manuals), with
      `user-guides/.gitignore` = `*` when written in a repo.
- [ ] All CSS inline; colors, fonts and radii from DESIGN.md; passes its "Checklist de conformidad".
- [ ] Linear: TOC right after the header, one working link per section, titles identical to the
      `<h2>`, part labels before each `part-header` group. Staged: no top TOC, stage assets embedded
      and `stages` empty in `__umCheckRendered()`.
- [ ] Section map, section pill + sheet and "Inicio" button present and working on a fresh load,
      also inside the destination viewer; shortcuts verified.
- [ ] `heritage:share-url` set when the manual is published inside an iframe viewer.
- [ ] No change markers: no `data-change`, "Nuevo", "Actualizado" or "Novedades".
- [ ] **¿Cómo se accede?** present: from the code (entry screen captured with an anchored pin on the
      entry, exact label, visibility gates) or, when the code does not show it, as the user explained;
      the outer path not in the repo is not invented.
- [ ] Every screen of the flow is captured with **all its variants**, from temporary synthetic mocks.
- [ ] Mobile flows: every capture at 375 px inside `.mockup--mobile`. Desktop flows: captures at
      ≥ 1280 px that reflow at 390 px.
- [ ] Every pin is anchored (`data-target`) and sits next to its element at 1280 px and 390 px.
- [ ] Each section has at most one pin per number, in the same section as its steps and references.
- [ ] Every element the text names on a capture has a pin and a reference (as many pins as make sense).
- [ ] Every mockup has a `figcap`; every frame has `role="img"` and an `aria-label` starting with
      "Captura de pantalla:"; the header shows "Capturas: YYYY-MM-DD".
- [ ] The fit check in `references/real-app-mockups.md` returns `[]` and every frame was compared
      against the live screen.
- [ ] `grep` over the final manual finds no real value seen during capture (names, usernames, user and
      account IDs), no token/CSRF, and no environment host (`https?://` in mockup bars or prose,
      `:8443`, `localhost`, internal domains).
- [ ] Every `compare` uses captures with the same width and framing; every `a.term` resolves.
- [ ] Sections in the standard order of Step 3 with their slugs (`check-manual.mjs` checks it);
      **Permisos y prerrequisitos** is the only list of permissions and keeps only conditions that
      change the flow; **Glosario** is last and holds only the terms the user confirmed, or does not
      exist when none was confirmed; **¿A quién escalar?** only with the channel the user gave.
- [ ] Visibility matrix complete; texts, limits and formats verified against code and translations;
      untranslated keys reported.
- [ ] Temporary fixtures, worktrees, local servers, logs with request headers and exports deleted.
- [ ] Tone is non-technical throughout.
- [ ] Menu of manuals (when asked): replica of the real menu captured with `app-frame`, every card
      covered by its `menu-link` at 1280 px and 390 px in every language, cards without manual with their icon gray,
      and every linked manual has "← Ir al menú" with the menu's URL.
