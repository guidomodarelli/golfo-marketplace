---
name: create-issue
description: >
  Generates a structured issue description from the user's verbal explanation of what they
  want to build. No code, no diff, no PR exists yet — this is a planning artifact.
  Use when the user asks to "create an issue", "write the issue", "armar la issue",
  "crear la issue", "documentar lo que voy a hacer", or similar, before any implementation.
license: MIT
metadata:
  version: "1.0.0"
  author: "Guido Modarelli"
  category: "spec-driven-development"
  tags: "issue, planning, acceptance-criteria, tasks"
  command: "/create-issue"
---

# Create Issue

Generate a filled issue description from the user's explanation of planned work.

> Reads the repo to ground the issue in real component names and conventions.
> Does not require a diff or an existing PR — this is a planning artifact.
> If they haven't described the work yet, ask one question: "¿Qué querés construir?"
> Then fill every section from their answer.

---

## Step 1 — Understand the codebase context

Read the repo to ground the issue in real names and structure. Run in parallel:

List source files — prefer `fd`/`rg`, fall back to `find`/`grep`:

```bash
# with fd
fd --max-depth 4 --type f --exclude node_modules --exclude .git \
   --exclude dist --exclude build --exclude coverage --exclude .next \
   --exclude __pycache__ --exclude vendor --exclude target | head -80

# fallback (no fd)
find . -maxdepth 4 -type f \
  | grep -vE "(node_modules|\.git|dist|build|coverage|\.next|__pycache__|\.mypy_cache|vendor|target)" \
  | head -80
```

Detect the project type from what's present (e.g. `package.json`, `go.mod`, `Cargo.toml`,
`pyproject.toml`, `pom.xml`, `Gemfile`, etc.) and read the relevant manifest for
dependency and tech context.

Then, based on what the user described, locate relevant files — prefer `rg`, fall back to `grep`:

```bash
# with rg
rg --files-with-matches "<keyword>" --glob "!node_modules" --glob "!dist"

# fallback (no rg)
grep -rl "<keyword>" . --exclude-dir={node_modules,dist,build,.git,vendor,target}
```

- Read only the files directly relevant to the planned change — not the entire repo.
- Use real file names, exports, and existing patterns to inform the technical description.

If the codebase gives you concrete component names, file paths, or conventions, use them
in the issue. If the area is brand new with no existing code, say so.

---

## Filling rules

### Title
Short imperative phrase in English describing the planned change.
Format: `[type]: <description>`.
Types: `feat`, `fix`, `refactor`, `chore`, `docs`.
Example: `feat: add corporate information accordion to user detail sidebar`

### Problem (¿Qué problema resuelve?)
The business or technical need driving the work.
Infer from what the user described: is it a bug? a missing feature? a UX gap? a tech debt item?

### Solution (¿Cuál es la solución propuesta?)
The proposed implementation approach: which components, services, or areas will be touched and how.
Write in future tense since no code exists yet.

### Change type checkbox
Mark with `x` only the one that matches the planned work:
- Bug → 🐛 Bug Fix
- New functionality → ✨ New Feature
- Breaks existing behavior → 💥 Breaking Change
- Only docs → 📄 Documentation
- Restructuring without behavior change → 🧹 Refactor
- Dependencies, CI, config → ⚙️ Chore

### Acceptance criteria
Infer concrete, observable conditions that define when the work is done.
Write them as "Given / When / Then" bullets or plain "El sistema debe..." statements.
Base them on the described behavior — not on any existing code.

### Tareas
Break the planned work into concrete, checkable units derived from the solution and the
codebase context. Each task should map to a real component, file, or area when possible.

### Impacted areas (inferred by the agent, not the user)
From the codebase analysis in Step 1, **you** determine which areas the planned change will
touch — do not wait for the user to enumerate them. Cross-reference the described work against
the real code and list the concrete artifacts that will be created or modified, grouped by kind:

- **UI / Components** — views, components, templates, styles affected.
- **Lógica / Servicios** — business logic, services, hooks, controllers, use cases.
- **Módulos / Estructura** — new modules, folders, shared utilities, config.
- **Datos / Modelos** — schemas, models, migrations, types.

Name real files and symbols when the codebase reveals them. Omit any sub-group with nothing to list.

### API changes section
Determine this **yourself** by inspecting the code (route definitions, controllers, OpenAPI/
AsyncAPI specs, fetch/REST client calls). Identify endpoints that the planned change will add,
modify, or remove. Do not rely on the user to mention them.
Omit the entire section only if, after inspecting the code, there is genuinely no API surface
involved (e.g. a pure styling change).

---

## Output

Print a single fenced Markdown block. Nothing before or after it.

```markdown
# <Title>

## 📝 Descripción

**¿Qué problema resuelve?**
<Problem: bug, feature gap, UX issue, or tech debt being addressed>

**¿Cuál es la solución propuesta?**
<Proposed approach: components, services, or areas to be modified and how>

---

## 🚀 Tipo de Cambio

- [ ] 🐛 **Bug Fix** (un cambio no disruptivo que soluciona un problema)
- [ ] ✨ **New Feature** (un cambio no disruptivo que agrega funcionalidad)
- [ ] 💥 **Breaking Change** (un cambio que podría causar que la funcionalidad existente no opere como se esperaba)
- [ ] 📄 **Documentation** (si el cambio es exclusivamente sobre documentación)
- [ ] 🧹 **Refactor** (una reestructuración de código que no arregla un bug ni agrega una funcionalidad)
- [ ] ⚙️ **Chore** (actualización de dependencias, configuración de CI/CD, etc.)

---

## ✅ Criterios de Aceptación

- <Observable condition inferred from the described feature>
- <…>

---

## 🧩 Áreas Impactadas

**UI / Componentes**
- `<real file/component>`: <what changes>

**Lógica / Servicios**
- `<real file/service>`: <what changes>

**Módulos / Estructura**
- `<real module/folder>`: <what changes>

**Datos / Modelos**
- `<real schema/model>`: <what changes>

---

## 🔄 Cambios en la API (si aplica)

- **Agregados:**
  - `METHOD /path`: <description>
- **Modificados:**
  - `METHOD /path`: <what will change>
- **Eliminados:**
  - `METHOD /path`: <reason>

---

## 📋 Tareas

- [ ] <Concrete work unit inferred from the planned change>
- [ ] <…>
- [ ] Agregar/actualizar tests (si aplica).
- [ ] Actualizar documentación (si aplica).
```

Drop any "Áreas Impactadas" sub-group with nothing to list. Omit the "Cambios en la API"
section entirely only if your code inspection found no API surface involved.
