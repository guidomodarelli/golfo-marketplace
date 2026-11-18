---
name: widget-ui-proposals
description: "Show UI/UX proposals, variants and previews as interactive visual widgets instead of — or before — writing code, and let the user pick-and-apply options to build the final solution. Renders with Claude's mcp__visualize__show_widget, Codex's bundled visualize plugin (HTML fragment + variant carousel), or, in Hermes and other agents with a shell, a static preview (HTML rendered to PNG, choice via clarify). Use when the user wants to try several variants/options/alternatives for an interface, compare design or UX approaches, see how a change would look before applying it, or iterate by choosing improvements. Triggers (es/en): 'probar variantes', 'varias propuestas', 'mostrame opciones', 'opciones de UI/UX', 'alternativas de diseño', 'cómo quedaría', 'mostrame cómo queda', 'preview del cambio', 'mejorar la interfaz', 'rediseñá esto', 'qué mejorarías', 'mostrame un widget', 'try several variants', 'show me options/proposals', 'compare UI options', 'how would it look'."
license: MIT
metadata:
  version: "1.3.0"
  author: "Guido Modarelli"
  category: "frontend"
  tags: "ui, ux, design, widgets, previews, proposals"
  command: "/widget-ui-proposals"
---

# Widget-driven UI/UX proposals & previews

Use Claude visual widgets to **show** interface work before/while coding it, so the user
decides from something they can see — not a wall of prose. Two recurring shapes:

1. **Proposals / variants** — a grid of option cards the user can apply one-by-one.
2. **Preview** — a mockup of how a requested change would look (final result).

Always render the visual with the `mcp__visualize__show_widget` tool (or, in Codex, with
the mechanism of [Codex mode](#codex-mode); elsewhere, with [Static preview mode](#static-preview-mode)). Explanatory text, recommendations and
trade-offs go in the chat response, **never inside the widget**.

## Agent compatibility

Pick the render mode by capability before step 1, not by agent name (see [`agent-capabilities.md`](../../references/agent-capabilities.md), row «Widgets visuales»):

1. **Claude mode** — the session tool list (including deferred tools) has `mcp__visualize__show_widget`: follow the [Workflow](#workflow) as written.
2. **Codex mode** — no `show_widget`, Codex's bundled `visualize` skill is available (it is listed or loadable as a skill, or `visualize@openai-bundled` is enabled in `$CODEX_HOME/config.toml`), **and** the session runs in a frontend that renders it: the Codex desktop app, recognisable because its app tools (`codex_app`, for example `automation_update` or `create_thread`) are in the session. Follow [Codex mode](#codex-mode). In the Codex CLI or `codex exec` (no app tools, or `CODEX_CI=1`) the `visualize{…}` reference stays plain text, so go to the next mode instead.
3. **Static preview mode** — neither of the above, but the session can run shell commands, a headless browser binary is available to render HTML to an image (`chrome`/`chromium`/`msedge` with `--headless=new --screenshot`, or the agent's own browser tool with a screenshot helper, such as Hermes `browser_exec` + `capture_screenshot()`), and the user can see an image (inline in a messaging gateway, an image-capable chat, or a file path they open): follow [Static preview mode](#static-preview-mode). Typical in Hermes and in headless Claude Code sessions.
4. **None** — no render path at all: do not simulate a widget (no fake widget markup in chat, no claim that a widget was shown, no HTML presented as if it were rendered). Stop before step 1 and tell the user, under `Limitaciones del agente`, which render paths were checked (`show_widget`, Codex `visualize`, headless browser binary, browser screenshot tool) and that visual proposals need any of them. Only if the user then explicitly asks for proposals without visuals, list them as plain text; that is a different deliverable, so say so.

If a render path fails at runtime (the image is not produced, or the user says the visual did not show up), drop to the next mode instead of retrying the same one in a loop, and report it.

### Codex mode

Codex has no widget tool: its `visualize` plugin renders an HTML fragment that the agent writes to a file and references from the final answer. Load the `visualize` skill and read it **in full** (`SKILL.md` and its `tweak.md`) before authoring; its contract (file location, fragment rules, CDN allowlist, no `fetch`/XHR, < 1 MB, unique root ID, silent work, never announcing the widget or implementation details) overrides the Claude-specific rules of [Widget design rules](#widget-design-rules-from-the-visualize-design-system) and step 1. This skill keeps the propose → pick → apply loop and maps its pieces like this:

| Claude mode | Codex mode |
|---|---|
| `mcp__visualize__read_me` once (step 1) | Read the `visualize` skill in full |
| `show_widget` call | Write `<title>.html` (fragment, no `<html>/<head>/<body>`) in a writable task directory and put `visualize{"path":"<absolute-path>/<title>.html"}` on its own line in the final answer (`"mode":"wide"` only for full-screen app mockups) |
| Grid of option cards (2a) | A `.viz-carousel` with one direct child per option (`data-variant="<Name>"`, all but the first `hidden`); the runtime adds navigation and picker |
| `sendPrompt('Implementá: …')` on "Aplicar ↗" | `await window.openai.sendFollowUpMessage({ prompt: 'Implementá: …', title })` on an "Aplicar" button inside each variant |
| Interactive filters/toggles | Local interactions in the fragment; design knobs with the `Tweak` helper from `tweak.md` |

Two consequences of that contract: carousel navigation does **not** tell the model which variant the user looked at, so the choice reaches you only through an "Aplicar" click or the user naming the option in chat; and the visible text of the answer only describes what the visual helps decide (ranked recommendation and how options combine), without mentioning widgets, HTML or files.

### Static preview mode

The user sees a rendered **image** of the proposals and chooses with a question instead of clicking inside the chat. Same propose → pick → apply loop, mapped like this:

| Claude mode | Static preview mode |
|---|---|
| `mcp__visualize__read_me` (step 1) | Not needed; follow [Widget design rules](#widget-design-rules-from-the-visualize-design-system) with literal colors instead of host CSS variables (light theme, system fonts, Tabler icons only if the CDN loads, otherwise none) |
| `show_widget` call | Write a self-contained HTML **document** (`<!doctype html>`, inline CSS, no network needed) to a temp or task directory, then render it to PNG: `<browser> --headless=new --disable-gpu --hide-scrollbars --window-size=<W>,<H> --screenshot=<abs>.png file:///<abs>.html` (use a throwaway `--user-data-dir` so it never touches the user's profile), or the agent's browser screenshot helper. Headless is fine here: this is a mockup of proposals, not a capture of the user's app |
| Grid of option cards (2a) | The same grid in one image, each card labelled with a short visible ID (`A`, `B`, `C`…) and its title, so the user can name it |
| "Aplicar ↗" → `sendPrompt` | `clarify` (Hermes; ≤ 4 `choices` per question, `multi_select=true` because options compose) or, without it or when it returns `undelivered`/`timed_out`/`cancelled`, numbered options in chat and **stop** until the user answers. Inside the HTML, each "Aplicar" button copies its `Implementá: …` instruction to the clipboard, for users who open the file |
| Interactive filters/toggles | Render each meaningful state as its own image (at most 3) instead of a live toggle |

Before showing it, **look at the PNG** (vision tool or image viewer): it must not be blank, cropped or unstyled; fix and re-render otherwise. Deliver it so it is visible: in a messaging gateway (Hermes on Telegram/Slack/Discord) mention the PNG's absolute path outside code blocks so the gateway uploads it; in a CLI, give the absolute paths of the PNG and the HTML. Then give the ranked recommendation in chat as usual.

Report the loss under `Limitaciones del agente`: the preview is static (no in-chat clicks or live toggles), and the choice comes back through `clarify` or a chat answer. Nothing else changes: options stay distinct and composable, and only the picked ones are implemented.

## When to use

- The user asks for **several** variants/proposals/options/alternatives for UI or UX.
- The user asks to improve / redesign an interface and the solution space is open.
- The user asks "cómo quedaría / mostrame cómo queda / preview" of a change before applying it.
- You're about to make a non-trivial visual change and a preview would de-risk it.

Do NOT use it for: backend-only logic, a trivial one-line style tweak the user already
specified exactly, or when the user explicitly asked you to just write the code.

## Workflow

### 1. Before the first widget
Call `mcp__visualize__read_me` once per conversation (pick modules `mockup` / `interactive` /
`data_viz` as fit), then build the widget. A brief one-line update on what you're doing is
fine; the widget itself is what the user needs to see, so keep the focus there.

### 2a. Proposals / variants mode
When the user wants to explore options, render **one widget** with a responsive grid of
option cards. Each card:

- A short title + 1–2 line description of the approach and its trade-off (in **Spanish** —
  the user works in Spanish).
- An apt Tabler outline icon.
- An **"Aplicar ↗"** button that calls `sendPrompt('Implementá: <concrete instruction>')`
  so a click sends the message that triggers implementation. The instruction must be
  self-contained (it will be read cold).
- Mark 1–2 cards "Recomendada" with a subtle badge + `border: 2px solid var(--color-border-info)`.

Options must be **distinct and composable** — the user may apply several. After the widget,
in the chat give your ranked recommendation and how they combine.

### 2b. Preview mode
When the user asks for a specific change (or you're proposing one), render a widget that
**mockups the final result** with realistic sample data, matching the real component's
structure (layout, labels, states). Use it to confirm direction before editing code.

### 3. Apply-and-iterate loop
- The user clicks an "Aplicar" button or names the option(s) they want.
- Implement that change in the real code following project conventions (architecture,
  SCSS/components, tests, gates).
- When useful, show an **updated preview widget** of the new state and offer the next batch
  of options. Repeat until the user is satisfied.
- The user can keep adding options across turns — treat the widgets as the running menu and
  the code as the accumulating final solution.

### 4. After implementing
Run the project's quality gates for the changed files (lint, typecheck, relevant tests) and
report status. Keep widget copy and chat questions/recommendations in **Spanish**.

## Widget design rules (from the visualize design system)

- Flat and native: no gradients, drop shadows, blur or neon. Use the host CSS variables
  (`--color-*`, `--border-radius-*`, `--font-*`) so it adapts to light/dark.
- Sentence case, two font weights (400/500), no font-size below 11px, Tabler **outline**
  icons only (`<i class="ti ti-...">`).
- The widget contains **only** the visual. Titles, explanations and trade-offs go in your
  chat response.
- `sendPrompt(text)` for any action that should continue the conversation (apply an option,
  drill into one). Append `↗` to such buttons.
- For interactive option widgets, make filters/toggles work in JS so the user can feel the
  interaction; round every displayed number.
- Scale effort to the ask: a few options for "show me some ideas"; a larger, clearly-ranked
  set for "what would you improve / be thorough".

## Anti-patterns

- Don't dump the proposals as a long prose list when the user asked to "see" options — show
  the widget.
- Don't put paragraphs of explanation inside the widget.
- Don't invent that you can't preview something visual — a mockup widget is almost always
  possible with sample data.
- Don't apply changes the user didn't pick; the widget proposes, the user disposes.
