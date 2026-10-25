---
name: pr-description-template
description: "Provides the standard PR title and concise description template (change type, manual validation, screenshots of UI changes uploaded from the running app, optional API changes, reviewer notes) plus a traceability-only mode that preserves existing PR content. MANDATORY: load it before running any `gh pr create` or `gh pr edit --body`/`--body-file`, in any repository, including PRs the agent opens on its own initiative as one step of a larger task (publishing or releasing a library, shipping a fix to another repo, a review or auto-fix loop) where nobody said 'PR'. Never write a PR body by hand. Also use for /feature-branch-pr, 'crear PR', 'abrir pull request', 'subir cambios y crear PR', or any request to fill or restructure a pull request body."
allowed-tools: Bash(gh:*) Bash(git:*) Bash(bash:*) Bash(jq:*)
license: MIT
metadata:
  version: "1.3.1"
  author: "Guido Modarelli"
  category: "git-workflow"
  tags: "pull-request, template, description, screenshots"
  command: "/pr-description-template"
---

# PR Description Template

Use this skill any time a pull request body has to be written or filled. It defines the canonical title + description so every PR looks consistent.

## Strict scope

Run only the actions needed to compose, apply, or verify the title and body of the requested PR.

- Read the diff only as evidence to write the description; do not treat it as an implicit review request.
- Do not start a code review, security audit, dependency audit, performance review, or any other analysis unless explicitly asked.
- Do not run tests, builds, linters, scanners, or repository validations unless explicitly asked. Exception: launching the app only to capture the screenshots of [UI screenshots](#ui-screenshots), and stopping it once the captures are done.
- Do not invoke skills, agents, or workflows unrelated to PR composition unless explicitly asked or directly delegated by the calling flow. If a higher-priority rule forces an invocation, limit it to deciding applicability; do not expand scope.
- Do not modify code, dependencies, or configuration.
- Do not create or update Jira, labels, review comments, approvals, merge, or PR state.
- Allowed writes: create the PR when the calling flow asks for it, edit only the title/body of the explicitly requested PR, and upload its screenshots to the `pr-assets` branch with [scripts/upload-pr-image.sh](scripts/upload-pr-image.sh).
- In `traceability-only` mode, the only allowed write is the delegated body-only backlink; do not re-template the PR.
- Skip any action that is not a direct requirement of the requested description.
- Exception: after a successful `gh pr create`, hand the new PR to [`codex-autofix-loop`](../codex-autofix-loop/SKILL.md) as described in its «Arranque automático al abrir un PR» section, without asking. That loop owns the later fixes and the merge; this skill does not run them.

## Direct application

- When the user invokes `/pr-description-template` or names this skill, treat the request as an order to apply the change directly to the PR; do not answer with a draft to copy by hand.
- Locate the PR with `gh pr view --json number,title,body,url,headRefName,baseRefName`. For an existing PR, apply the change with `gh pr edit <number-or-url> --body-file <temp-file>` and add `--title` only for a full composition. For a new PR, use `gh pr create --body-file <temp-file>` when the calling flow asked to create it.
- Verify every write with `gh pr view --json title,body,url` before reporting the result.
- Do not print the title, body, template, or full generated content in chat. Report only the operation, affected PR, URL, and verification. If the operation fails or no PR applies, report the concrete blocker without pasting an alternative body.
- Return title/body content only when the user explicitly asks for a draft, preview, or content without direct application.

Triggers (explicit or implicit):
- the user runs `/feature-branch-pr` (the [feature-branch-pr](../feature-branch-pr/SKILL.md) skill must use this template for the PR body)
- the user asks to "crear PR", "abrir pull request", "subir cambios y crear PR", "branch + commit + push + PR"
- any flow that ends in `gh pr create` / editing a PR body and needs a title + description
- the agent decides by itself to open a PR as an intermediate step of another task: publishing or releasing a package ("publicá X"), landing a change in a sibling repository, a release flow that requires changes to go through `main` via PR, or an automated fix loop. The user never says "PR" in these cases, and they are the ones most often missed.

Hard gate: before typing `gh pr create` or `gh pr edit ... --body`/`--body-file`, this skill must already be loaded in the current turn. If it is not, stop, load it, and compose the body from the template. A hand-written body ("Qué cambia", "Validación", free-form sections) is a defect even when its content is accurate; if one was already published, re-apply the template to that PR with `gh pr edit` right away.

## Modes

### Full composition

Use for new PRs or when the user explicitly asks to fill or restructure the complete title/body. Apply the template below from the actual diff.

### Traceability-only patch

Use when another skill updates an existing PR only to add or normalize traceability metadata.

- Do not regenerate the template or edit the PR title.
- Do not add or recompute the initial file-count metadata line.
- Do not modify **Tipo de Cambio**, **Pruebas Manuales**, **Cambios en la API**, **Notas para el Revisor**, or unrelated ticket links.
- A canonical Jira backlink may be inserted as the first content under `## 📝 Descripción`; this is not the removed top-level **Referencia** metadata block.
- Conservar cuerpo existente y modificar únicamente enlace de trazabilidad solicitado. Releer cuerpo
  antes de escribir, preservar cambios concurrentes y evitar enlaces duplicados.
- Read `title`, `body`, and `url`; edit only through `gh pr edit <url> --body-file <temp-file>` without `--title`.
- Re-read the PR and verify title identity plus protected body content after the patch.

### Initial file-count metadata

Apply only during `full composition`, before writing the body. Count files from the actual PR comparison range (`base...head`), never from the whole repository, a line-count statistic, or unrelated working-tree changes.

Run [scripts/count-reviewable-files.sh](scripts/count-reviewable-files.sh) from this skill directory. It counts reviewable product code only (JavaScript and TypeScript files a reviewer must read to judge behavior) and excludes dot directories and dotfiles, root `config/` and `settings/`, tests, mocks, fixtures, snapshots, e2e, stories, `.d.ts` declarations, and tooling configuration.

- New PR: `bash <skill-dir>/scripts/count-reviewable-files.sh "<base-ref>...<head-ref>"`.
- Existing PR: fetch the PR head into a named ref, which also works for PRs from forks and counts only pushed commits, then pass that range:

  ```bash
  git fetch origin "<baseRefName>" "+refs/pull/<number>/head:refs/remotes/origin/pr/<number>"
  bash <skill-dir>/scripts/count-reviewable-files.sh "origin/<baseRefName>...origin/pr/<number>"
  git update-ref -d "refs/remotes/origin/pr/<number>"
  ```

- A caller that already resolved the range may pipe its exact `git diff --name-only` output into the script instead of passing a range.
- Do not diff against `FETCH_HEAD` (with two refspecs it points to the base, so the range is empty) and do not use `gh pr view --json files` (it returns at most 100 files).
- If the range cannot be determined or the fetch fails, stop and report the concrete blocker instead of inventing or estimating a number.

Place exactly one line, `<div align="right"><sup>📄 Archivos de código modificados: N</sup></div>`, as the first body content, followed by one blank line and `## 📝 Descripción`. Replace `N` with the script output; never leave placeholder text. Do not add this line in `traceability-only`.

## Agent compatibility

Screenshots need the **user's own browser** (their real Chrome with its sessions, fonts and extensions), not a headless or app-embedded one. Which tool drives it depends on the agent; [Capture browser](#capture-browser) lists the accepted ones, checked by capability per [`agent-capabilities.md`](../../references/agent-capabilities.md) (row «Navegador real del usuario y capturas»). When none of them is available, skip the capture, keep the rest of the body, and state under the reviewer notes that captures were skipped and which browsers were checked. Title, template and traceability-only mode work the same in every agent.

## UI screenshots

Apply only during `full composition`. When the diff changes what a user sees (components, markup, styles, visible copy, layout, theming, icons or animations) and you know how to launch the app, add a screenshot of the change to the body. Skip this section for changes with no visible effect (backend, tests, tooling, docs, agent instructions).

1. **Find out how to launch the app** before capturing, from the first source that applies: a dev server that is already running for this checkout; a project skill that launches the app (for example `run`); the launch and local-verification instructions in `AGENTS.md`, `CLAUDE.md` or `README.md`; `.claude/launch.json`; the `dev`/`start` scripts in `package.json`. Follow the project's own rules (required URL, proxy, port, environment). If none of them tells you how, or the app does not start, skip the capture.
2. **Always capture the real app.** Reach the changed screen on the running app in the user's own browser (see [Capture browser](#capture-browser)), which has their sessions, fonts and extensions as they really use the app. Do not use a built-in browser pane, an app-embedded browser or a headless browser for published captures. If no accepted browser is connected, ask the user to connect one instead of switching to a non-accepted browser. Never capture a harness, a static HTML page, a mock page or a component rendered outside the app: it misses global styles, fonts, icons and the real components, and misleads the reviewer. If the screen needs a sign-in, use only a session that is already open or test credentials the project provides for local development; never type real credentials. If the screen cannot be reached in the real app, skip the capture.
3. **Capture what a reviewer needs to judge the change**: always a before and an after (before from the base branch, or from the running app with the change temporarily undone, then restored), so the reviewer sees the difference at a glance. Crop both to the affected area, not the full page, and give each pair the same viewport, crop box and scroll position, so the only thing that differs is the change. Leave enough surrounding context to judge it (for example the neighbouring border the spacing is measured against). Capture each theme or viewport the change targets (for example dark and light, mobile and desktop) as its own pair.
4. **Check every image before uploading**, by viewing it:
   - It looks like the app the user sees: fonts, icons, colors and component styles loaded. Wait for `document.fonts.ready` and for the page to settle (no loaders, skeletons or entrance animations mid-flight) before capturing.
   - It shows the change the PR describes, and the before/after pair differs only in that change, visibly: if the two look the same at a glance, crop tighter or capture a state where the change shows.
   - It shows only test or sample data: never personal data, emails, tokens, internal URLs or anything secret. The image is published with the repository.
   If an image fails any check, capture it again or skip it.
5. **Stop every server you started** as soon as the last image passes the checks, before uploading, so it does not keep consuming CPU, memory or ports. This includes any server started for the base branch to capture the before image. Stop it through the same tool that launched it (`preview_stop`, `stop_terminal_tab`, `TaskStop`, or killing the process tree whose PID you recorded) and confirm the port no longer responds. Never stop a server that was already running before this skill started it: it belongs to the user. Apply the same cleanup when the capture is skipped or fails after the app was launched.
6. **Upload** with `bash <skill-dir>/scripts/upload-pr-image.sh <owner/repo> <head-branch> <image>...`. It stores the files in the repository's orphan `pr-assets` branch through the GitHub API, under a folder named after the head branch, without touching the local checkout, and prints the URL of each file, one per line. Use the head branch name, so the links exist before the PR does. Name each file by what it shows (`before-dark.png`, `after-dark.png`).
7. **Place the images** in the **Capturas** table of the template: one row per pair, the first cell names what the row shows (theme, viewport or state), and the **Antes** and **Después** columns hold the images side by side with the same `width`, so the reviewer compares them directly. Put each URL the script prints in `<img src="<url>" alt="<antes|después> <row>" width="<same width>">`; keep the width at most 400 so two fit side by side. Add one sentence above the table saying what to look at. Delete the section when no image applies.

### Capture browser

Which browsers count as the user's own, how to recognise each one and which are never accepted lives only in row «Navegador real del usuario y capturas» of [`agent-capabilities.md`](../../references/agent-capabilities.md). Use the first accepted one whose tools are actually in the session; a browser that row rejects (headless, app-embedded, throwaway profile) may check that a page loads, never produce the image the reviewer sees. What this skill adds for published captures:

- Open a **new** tab for the captures and close only the tabs you opened; never navigate or close the user's own tabs.
- A tool that drives the real desktop (for example Hermes `computer_use`) moves the user's mouse and keyboard: tell the user before starting and capture only if they agree. Crop the desktop screenshot to the page area.

When the change affects the UI but no image could be captured from the real app, delete **Capturas** and add one line to **Notas para el Revisor** with the concrete reason (`Sin captura: <motivo>`). Do not block the PR on a screenshot.

## Full-composition rules

- Fill every section from the actual diff; never leave `*italic placeholders*`. Delete optional sections (**Capturas**, **Cambios en la API**, **Notas para el Revisor**) when they do not apply.
- The template contains only content that is published. Do not add instructions, hints, or blockquotes for the author to the body.
- Start the body with the file-count line, then one blank line and **Descripción**. The PR title already carries the change summary, so do not repeat it as a body heading.
- Do not add a compact **Tipo** metadata block above **Descripción**. In **Tipo de Cambio**, mark exactly one primary category with `[x]` and leave every other category unmarked with `[ ]`.
- Include ordinary ticket or issue links naturally in **Descripción** or **Notas para el Revisor**; do not create a fixed metadata block.
- When fully composing an existing PR, preserve every canonical `🎫 Jira: [...]` backlink already present. Extract backlinks before replacing the body and reinsert each once as first content under `## 📝 Descripción`; never drop established traceability.
- New or legacy backlink normalization follows traceability-only mode; full composition preserves known canonical backlinks but does not invent Jira associations.
- In **Cambios en la API**, keep only the operation groups that apply (**Agregados**, **Modificados**, **Eliminados / Deprecados**) and delete unused lines.
- **Pruebas Manuales** is mandatory. List reproducible steps a reviewer can follow. When the change has no behavior a reviewer can exercise (only documentation, agent instructions, or tooling), replace the environment and steps with one line: `No aplica: <motivo>`. Do not state which validations you personally ran; mention automated coverage inside **Descripción** only when it adds relevant context.
- **Notas para el Revisor** holds relevant technical decisions (trade-offs, discarded alternatives, constraints) and where to focus the review. Delete it when there is nothing relevant.
- Body text is in Spanish; keep code, paths, endpoints, branch and identifier names in English.
- Never mention `@codex` in the body, neither `@codex review` nor `@codex fix`: Codex reads a mention in the PR body as a task request and answers asking to create an environment instead of reviewing. [`codex-autofix-loop`](../codex-autofix-loop/SKILL.md) requests the review with a separate comment. To talk about Codex in the body, name it without the `@`.
- Apply the complete PR body directly with `gh`, unless the user explicitly asks for a draft only.
- For an existing PR under full composition, locate it with `gh pr view --json number,title,body,url,headRefName,baseRefName`, write the filled template to a temp file, and run `gh pr edit <number-or-url> --title "<title>" --body-file <temp-file>`.
- For a new PR, pass the body to `gh pr create` via `--body-file` rather than a fragile inline `--body` string.
- After `gh pr edit` or `gh pr create`, verify the result with `gh pr view --json title,body,url`.

## Title

Single line, descriptive, English-friendly subject. Example: `Add user status sidebar element to detail views`. Use it only as the PR title; do not repeat it inside the body.

## Body template

```markdown
<div align="right"><sup>📄 Archivos de código modificados: N</sup></div>

## 📝 Descripción

### ❓ ¿Qué problema resuelve?
*Contexto del problema de negocio o técnico. ¿Por qué es necesario este cambio?*

### 💡 ¿Cuál fue la solución?
*Resumen técnico de la implementación. Componentes, servicios y archivos clave modificados.*

## 🚀 Tipo de Cambio

- [ ] 🐛 **Bug Fix** — corrige comportamiento defectuoso
- [ ] ✨ **New Feature** — agrega funcionalidad nueva
- [ ] 💥 **Breaking Change** — modifica un contrato o comportamiento incompatible
- [ ] ⚡ **Performance** — mejora tiempos, uso de recursos o escalabilidad
- [ ] 🧹 **Refactor** — reestructura código sin cambiar comportamiento
- [ ] 🧪 **Tests** — agrega o mejora cobertura sin cambiar producción
- [ ] 📄 **Documentation** — actualiza documentación sin cambiar código funcional
- [ ] 🏗️ **Build** — modifica compilación, empaquetado o herramientas de build
- [ ] 👷 **CI/CD** — modifica pipelines, checks o automatización de entrega
- [ ] ⬆️ **Dependencies** — actualiza, agrega o elimina dependencias
- [ ] ⚙️ **Chore** — mantenimiento sin impacto funcional directo
- [ ] ↩️ **Revert** — revierte un cambio anterior

## 🖐️ Pruebas Manuales

**🌐 Entorno:** `<URL / ambiente, si aplica>`

1. `<Acción a realizar>` → `<Resultado esperado>`
2. `<Acción a realizar>` → `<Resultado esperado>`

## 📸 Capturas *(si aplica)*

*Qué mirar:* `<la diferencia que el revisor tiene que ver>`

| | Antes | Después |
| --- | --- | --- |
| `<tema / viewport>` | <img src="https://github.com/<owner>/<repo>/blob/pr-assets/<head-branch>/before-dark.png?raw=true" alt="Antes <tema / viewport>" width="380"> | <img src="https://github.com/<owner>/<repo>/blob/pr-assets/<head-branch>/after-dark.png?raw=true" alt="Después <tema / viewport>" width="380"> |

## 🔄 Cambios en la API *(si aplica)*

- ➕ **Agregados:** `POST /api/v1/...`
- ✏️ **Modificados:** `PUT /api/v1/.../{id}`
- ➖ **Eliminados / Deprecados:** `GET /api/v1/...`

## 👀 Notas para el Revisor *(si aplica)*

*Decisiones técnicas relevantes (trade-offs, alternativas descartadas, restricciones) y dónde enfocar la revisión.*
```
