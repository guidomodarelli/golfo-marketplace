---
name: semantic-html-a11y
description: Enforces semantic HTML and accessibility in frontend markup, such as native elements for actions, labels, roles, aria attributes, keyboard support, focus management, and accessible names. Use when creating or updating React or HTML components, forms, menus, dialogs, toggles, or any custom interactive control.
license: MIT
metadata:
  version: "1.0.0"
  author: "Guido Modarelli"
  category: "frontend"
  tags: "accessibility, a11y, semantic-html, aria, keyboard, focus"
  command: "/semantic-html-a11y"
  plugin-dependencies: "golfo-engineering"
---

# Semantic HTML and Accessibility

## Quick start

Use the most semantic native element for each interaction, and add roles, `aria-*` attributes, and keyboard handling only when native semantics cannot express the behavior. Every interactive control needs an accessible name and must work with the keyboard.

## Core workflow

1. Choose the most semantic native element for each interaction (`button` for actions, `a` for navigation, `input` + `label` for fields, `form` for submission).
2. Give every interactive control an accessible name: visible text, an associated `label`, or `aria-label`/`aria-labelledby` when there is no visible text.
3. Add `aria-*` attributes or roles only when native semantics are not enough, for example `aria-expanded`, `aria-controls`, `aria-describedby`, or `aria-live`.
4. Make custom controls keyboard-operable: focusable, activatable with Enter/Space, and with the expected arrow-key behavior for menus, tabs, and listboxes.
5. Manage focus on dynamic UI: move focus into dialogs, trap it while they are open, and return it to the trigger when they close.
6. Associate errors and helper text with their fields through `aria-describedby`, and announce async status changes through a live region.

## Guidelines

- **Native first**: never attach click handlers to a `div` or `span` for actions; a native `button` brings focus, keyboard support, and role for free.
- **Links versus buttons**: `a` with `href` navigates; `button` performs actions. Do not swap them for styling.
- **Headings and landmarks**: keep a logical heading order and use `main`, `nav`, `header`, `footer`, and `section` with an accessible name when it helps navigation.
- **Images**: give meaningful images an `alt` that conveys their purpose; use `alt=""` for decorative ones.
- **Do not over-ARIA**: a wrong or redundant role is worse than none. Do not add `role="button"` to a `button`.
- **Visible focus**: never remove focus outlines without an equivalent visible style.
- **Text through the project's i18n**: accessible names and messages follow the same translation flow as visible copy.

## Patterns

### Semantic action

```jsx
<button type="button" onClick={handleSearch}>
  {searchLabel}
</button>
```

### Accessible disclosure

```jsx
<button
  type="button"
  aria-expanded={isFiltersOpen}
  aria-controls="filters-panel"
  onClick={toggleFilters}
>
  {filtersLabel}
</button>
<section id="filters-panel" hidden={!isFiltersOpen}>…</section>
```

### Field with error

```jsx
<label htmlFor="email">{emailLabel}</label>
<input
  id="email"
  type="email"
  aria-invalid={Boolean(emailError)}
  aria-describedby={emailError ? 'email-error' : undefined}
/>
{emailError && <p id="email-error">{emailError}</p>}
```

## Quick checklist

- Native semantic elements are used for actions, navigation, and fields.
- Every interactive control has an accessible name.
- Roles and `aria-*` appear only where native semantics fall short, and they are correct.
- Custom controls work with the keyboard.
- Focus is managed in dialogs and dynamic content, and it stays visible.
- Errors, helper text, and async status are announced to assistive technology.

## Out of scope

Component structure, modularization, constants, and duplication belong to `refactor-modularize-code`, `constants-refactor`, and `simplify-code`.
