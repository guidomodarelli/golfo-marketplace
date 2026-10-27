# Pins, before / after and glossary

Read from `SKILL.md`, Step 4, when a section has numbered pins on a capture, a before / after comparison or glossary terms.

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
