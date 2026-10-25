## What This Repository Is

A multi-provider marketplace of skills and plugins for AI agents. No application code — only skill definitions (SKILL.md), reference docs, eval configs, and installer scripts. Supports multiple providers: **Claude Code**, **Codex** and **Hermes** (through the portable Agent Plugins v1 package).

- `plugins/` — Production-ready plugins for marketplace distribution. Each plugin has provider spec directories (`.claude-plugin/`, `.codex-plugin/`), a portable root `plugin.json` (Hermes) + `skills/` directory.
- `skills/` — Standalone skills for prototyping. Same internal structure, lighter packaging.
- `skill-eval-runner/` — Central eval runner. Skills only need `evals/eval-config.json`; the runner handles execution, assertions, and reporting. Provider-agnostic.
- `.claude-plugin/marketplace.json` — Claude Code plugin registry. Register plugins here for Claude Code.
- `.agents/plugins/marketplace.json` — Codex plugin registry. Register plugins here for Codex.

For local development, skills symlink into each provider's own skills folder (`~/.claude/skills/` for Claude Code, `~/.codex/skills/` for Codex) — see **Local Testing**.

## Mandatory Rules

1. **Use `/skill-creator`** for all skill creation, modification, validation, and description optimization. Never create skills manually from scratch. Exception: work that `/skill-optimizer` performs on its target during its own run (the audit and validation of Phase 1 and the edits of Phase 6) does not go back through `/skill-creator`, so rules 1 and 4 cannot trigger each other in a loop.
2. **Every skill must have `evals/eval-config.json`** (test cases + assertions). Use the central `run-evals` CLI to execute them — no per-skill `run-evals.sh` needed. Use `/skill-creator` to generate evals. (Legacy skills may use `evals/evals.json` — prefer `eval-config.json` for new work.)
3. **All names in kebab-case** — plugins, skills, directories, commands. Names should convey expertise (e.g., `api-docs-expert` not `api-doc-guidelines`).
4. **Run `/skill-optimizer` after every skill creation or modification.** Once `/skill-creator` finishes creating or changing a skill (its `SKILL.md`, references, scripts or evals), run `/skill-optimizer` on that skill with `mode=audit` before reporting the work as done, and include its status and findings in the report. Escalate to `mode=quick` or `mode=full` only if the audit finds a measurable problem and the user agrees. Exceptions: edits made by `/skill-optimizer` itself (it must not invoke itself recursively) and changes limited to metadata such as the `version` field.
5. **Every `SKILL.md` follows the [Agent Skills specification](https://agentskills.io/specification)**, the format that Claude Code, Codex and Hermes read. Frontmatter constraints:
   - `name` (required): 1-64 characters, lowercase letters, digits and hyphens only, no leading, trailing or consecutive hyphens, and equal to the skill directory name.
   - `description` (required): 1-1024 characters, non-empty, saying what the skill does and when to use it. Quote it when it contains `: `, or the YAML frontmatter fails to parse.
   - Optional fields: `license`, `compatibility` (at most 500 characters), `metadata` (string keys to string values, so lists such as `tags` are written as a comma-separated string) and `allowed-tools` (experimental).

   Portable runtimes such as Hermes silently drop a skill whose `name` or `description` breaks these limits. `pnpm validate-portable-plugins` enforces `name` and `description` in CI; the other constraints are checked in review. If the specification changes, it wins over this summary.

## Conventions

- **SKILL.md frontmatter**: `name`, `description` (include trigger keywords), `license`, `metadata` (version, author, category, tags, command), within the limits of rule 5. The `description` field drives skill activation — make it count.
- **Branch naming**: `feature/<plugin-or-skill-name>`
- **Commit format**: `feat(marketplace): add <name>` or `feat(skills): add <name>`
- **Reference files are loaded on-demand** — skills declare them but only load when the relevant command executes.
- **Skills EXECUTE actions** — they write files, run installations, produce reports. They don't just show instructions.
- **Start in `skills/`, promote to `plugins/`** when production-ready.

## Plugin Structure

A plugin root (`plugins/<name>/`) contains provider-specific spec directories alongside the shared `skills/` directory:

```
plugins/<name>/
  .claude-plugin/plugin.json    ← Claude Code plugin spec (required for Claude)
  .codex-plugin/plugin.json     ← Codex plugin spec (required for Codex)
  plugin.json                   ← Agent Plugins v1 portable manifest (required for Hermes)
  skills/                       ← Shared skill implementations
  references/                   ← Docs shared by several skills (optional)
  tools/                        ← Executable tooling shared by several skills (optional), e.g. golfo-kit `tools/skill-coverage`
```

**Portable** `plugin.json` (Agent Plugins v1, installed by Hermes with `hermes plugins install guidomodarelli/golfo-marketplace#plugins/<name>`) may only contain the spec fields (`$schema`, `name`, `version`, `description`, `author`, `homepage`, `repository`, `license`, `keywords`, `extensions`); `$schema` must be `https://agent-plugins.org/schemas/1.0.0/plugin.schema.json`, `name` must equal the plugin directory and `version` must match `.claude-plugin/plugin.json`. Portable runtimes silently drop any skill whose frontmatter `name` differs from its directory or whose `description` is empty or longer than 1024 characters. `pnpm validate-portable-plugins` (`scripts/validate-portable-plugins.js`, run in CI) enforces all of this; run it after changing a manifest or a skill frontmatter.

**Claude** `.claude-plugin/plugin.json` optional fields:
```json
{
  "agents": "./agents/run.md",
  "mcpServers": "./.mcp.json",
  "hooks": "./hooks/hooks.json"
}
```

**Codex** `.codex-plugin/plugin.json` requires the following minimum schema (a manifest missing any of these fields fails to load):

```json
{
  "name": "<kebab-case>",
  "version": "<must match .claude-plugin/plugin.json>",
  "description": "...",
  "author": { "name": "...", "email": "", "url": "" },
  "keywords": ["..."],
  "skills": "./skills/",
  "interface": {
    "displayName": "Human-readable name",
    "shortDescription": "One-line description",
    "category": "Productivity",
    "capabilities": ["Read", "Write", "Bash"]
  }
}
```

Critical points (see `plugins/golfo-kit/.codex-plugin/plugin.json` as the canonical reference):

- **`version` is mandatory** and must match the sibling `.claude-plugin/plugin.json`. This applies even when the plugin is being added to Codex for the first time while already existing on the Claude side — the "shared version" rule trumps "new plugins start at 1.0.0".
- **`skills: "./skills/"`** is required so Codex's loader resolves the skill directory. Without it, the plugin loads but no skills appear.
- **`interface.capabilities`** is required, not optional. Declare it accurately based on what the skill does: `Read` for file reads, `Write` for file writes, `Bash` for shell-outs. Don't copy blindly from another plugin.
- **`author.email` and `author.url`** must be present even as empty strings — match the structure of existing plugins.

Codex plugins **cannot** include: `commands`, `hooks`, or `agents`.

## Multi-Provider Support

### Universal vs Provider-Specific Plugins

**Universal plugin** (same implementation works for all providers):
```
plugins/<name>/
  .claude-plugin/plugin.json
  .codex-plugin/plugin.json
  skills/
```
Both registries reference `"source": "./plugins/<name>"`.

**Provider-specific plugin** (different implementation per provider, optional):
```
plugins/<name>/
  claude/                     ← Claude-specific implementation
    .claude-plugin/plugin.json
    skills/
  codex/                      ← Codex-specific implementation
    .codex-plugin/plugin.json
    skills/
```
Each registry references its provider's subdirectory path.

### Marketplace Registration Rules

- A plugin is only installed for a provider if it appears in that provider's `marketplace.json`.
- **Never add a `version` field to plugin entries in `marketplace.json`** — version lives in each plugin manifest.
- Plugins must be registered in at least one `marketplace.json`.
- Codex plugin entries in `marketplace.json` must not include `commands`, `hooks`, or `agents`.

### Subcommands pattern (multi-provider, no duplication)

When a plugin needs multiple discrete actions (e.g. `/myplugin setup`, `/myplugin list`, `/myplugin sync`) and you want it to work in **both** Claude Code and Codex, use the **hybrid subcommands pattern**.

**The problem**:
- Codex cannot use the `commands/` directory — only `skills/` is read.
- Claude Code can use `commands/<name>.md` to enable the nicer `/plugin:name` slash syntax.
- Duplicating subcommand bodies across both is a maintenance trap.

**The pattern**: keep the lógica in **one place** inside the skill, and have Claude's `commands/` be thin wrappers that defer to it.

```
plugins/<name>/
├── .claude-plugin/plugin.json
├── .codex-plugin/plugin.json
├── commands/                              ← Only Claude reads this
│   ├── setup.md          ← 3-line wrapper: defers to subcommands/setup.md
│   ├── list.md
│   └── ...
└── skills/<name>/
    ├── SKILL.md          ← Dispatcher: parses argument, reads subcommands/<arg>.md
    ├── subcommands/      ← SINGLE SOURCE OF TRUTH (read by both providers)
    │   ├── setup.md
    │   ├── list.md
    │   └── ...
    └── knowledge/        ← Shared reference files (read on-demand by subcommands)
```

**Skill dispatcher** (`skills/<name>/SKILL.md`) — at activation, parse the first token after the skill name and read the matching `subcommands/<token>.md`. Without a token, show the help table. This is what makes the plugin work in Codex: the skill is the entry point, the dispatcher routes to subcommand files.

**Claude command wrappers** (`commands/<name>.md`) — keep them to ~3 lines, e.g.:
```markdown
---
description: <same as skill table>
argument-hint: <if applicable>
---

Leé y seguí literalmente las instrucciones de `${CLAUDE_PLUGIN_ROOT}/skills/<plugin>/subcommands/<name>.md`, aplicándolas a `$ARGUMENTS`.
```

**Invocation matrix**:

| Provider | User types | What loads |
|----------|-----------|------------|
| Claude Code | `/myplugin:setup` | `commands/setup.md` → reads `subcommands/setup.md` |
| Claude Code | `/myplugin setup` | Skill activates → dispatcher reads `subcommands/setup.md` |
| Codex | `/myplugin setup` | Skill activates → dispatcher reads `subcommands/setup.md` |

## Local Testing

Run the canonical shell test commands documented in [`README.md` → “Correr tests shell localmente”](README.md#-correr-tests-shell-localmente). During a task, run only the suites that cover the change, following “Qué suite correr según el cambio” in the README; the full suite runs in CI (`.github/workflows/tests.yml`) on every pull request.

```bash
# One-time setup: install the eval runner (provider-agnostic)
cd skill-eval-runner && ./install.sh

# Install a skill locally (symlink — edits are live, just restart your agent).
# Point it at the skills folder of whichever provider(s) you run:
SKILL_SRC="$PWD/plugins/<plugin-name>/skills/<skill-name>"
ln -sfn "$SKILL_SRC" ~/.claude/skills/<skill-name>   # Claude Code
ln -sfn "$SKILL_SRC" ~/.codex/skills/<skill-name>    # Codex

# Run evals for a specific skill (JSONL by default)
run-evals plugins/<plugin-name>/skills/<skill-name>

# Run evals for all skills (JSONL by default)
run-evals --all

# Optional human-readable colored report
run-evals plugins/<plugin-name>/skills/<skill-name> --pretty

# Optional provider override (default: auto-detect Codex or Claude)
run-evals plugins/<plugin-name>/skills/<skill-name> --provider codex

# Optional persistent provider override
export GOLFO_MARKETPLACE_EVAL_PROVIDER=codex
```

## Bumping a plugin version

`pnpm cv` is a short alias of `pnpm create-version` and accepts the same arguments.

```bash
# Interactive: pick a plugin from a numbered menu
pnpm create-version

# Target a plugin directly by name
pnpm create-version <plugin-name>

# Preview without writing, committing or pushing (shorthand: -n)
pnpm create-version --dry-run

# Skip the version prompt
pnpm create-version <plugin-name> --bump minor
pnpm create-version --set 2.0.0

# Show usage (shorthand: -h)
pnpm create-version --help
```

Updates the `version` field in **every** plugin manifest (`.claude-plugin/plugin.json`, `.codex-plugin/plugin.json` and, when present, the portable root `plugin.json`) so they stay in sync. Detects changed plugin paths under `plugins/` from the current branch diff against the first available remote base (`origin/develop`, `origin/master`, or `origin/main`) plus working-tree changes and any commit made under a plugin after the last commit that changed its version (so a plugin merged into the default branch without a bump is still detected there), and auto-selects the plugin when exactly one changed, even when other files outside `plugins/` are modified. When the repository has a single plugin, it is selected without showing the menu. Changed plugins whose manifest version already differs from the merge-base with that remote base (bumped in branch commits or in the working tree) are reported as already bumped, excluded from auto-selection, and marked as `✔ bumped` in the menu, so with several changed plugins the one still pending is auto-selected. Offers a semver bump (`patch`/`minor`/`major`) or a custom exact version, and aborts if the manifests are not already on the same version. After the version is selected, commits **only** the updated `plugin.json` manifests with a descriptive message (other staged, unstaged or untracked changes are left untouched), then pushes the branch automatically (`git push -u origin HEAD` when no upstream exists). It never force-pushes and also pushes default branches (`develop`, `master`, `main`); if the push fails, the local commit is kept and the script exits with an error. `--dry-run` (`-n`) runs the same prompts and prints the planned manifest updates, commit and push without changing anything. `--bump <patch|minor|major>` or `--set <version>` (mutually exclusive) skip the version prompt; `--help` (`-h`) prints usage. Implemented in `scripts/create-version.js` (zero external deps).

Pull requests must bump every plugin they change: the `Version bump` job (`.github/workflows/version-bump.yml`) runs `pnpm check-version-bump <base>` (`scripts/check-version-bump.js`) and fails when files under `plugins/<plugin>/` changed (except inside `tests/` or `evals/` directories) and the plugin version did not go up against the merge base, or when the Claude, Codex and portable manifests disagree. Run `pnpm create-version` before opening the pull request. Both scripts, and `scripts/validate-portable-plugins.js`, share `scripts/lib/plugin-manifests.js`.

## Single source of truth

- Toda pieza de información (procedimiento, roster, config, catálogo de IDs, formato, criterio) debe vivir en **un solo archivo** bien organizado con secciones claras.
- El resto de archivos que necesiten esa información deben **referenciar** el archivo + sección, nunca copiar el contenido.
- Antes de escribir un bloque de texto en un subcommand o regla, verificar si ya existe en otro archivo de `knowledge/`. Si existe, referenciar. Si no existe y es reutilizable, crearlo en `knowledge/` y referenciar.
- Cuando se detecte información duplicada entre archivos, consolidarla en el archivo más apropiado y reemplazar las copias por referencias.

## Uso de subagentes

- No crear subagentes salvo pedido explícito del usuario.
- Para búsquedas, reviews y análisis multiarchivo, trabajar directamente en la sesión principal.

## Centralización recursiva de instrucciones

`AGENTS.md` es fuente canónica para instrucciones de agente. Regla aplica a cada `CLAUDE.md` del proyecto, tanto en raíz como en subdirectorios.

Para cada `CLAUDE.md`, usar únicamente `AGENTS.md` hermano ubicado en mismo directorio. Nunca sustituirlo por `AGENTS.md` de raíz, directorio padre u otro nivel.

Cuando usuario solicite agregar, modificar o eliminar contenido de cualquier `CLAUDE.md`:

1. Identificar directorio exacto de `CLAUDE.md` solicitado.
2. Resolver `AGENTS.md` hermano en ese directorio.
3. Aplicar cambio en `AGENTS.md`.
4. No editar directamente `CLAUDE.md`.
5. Evitar instrucciones duplicadas o contradictorias entre ambos archivos.

La referencia `@AGENTS.md` se resuelve relativa al directorio que contiene `CLAUDE.md`.

### Normalización por directorio

- Si existe solo `AGENTS.md`, crear `CLAUDE.md`. En raíz, incluir `@AGENTS.md` más instrucción de centralización; en subdirectorios, incluir únicamente `@AGENTS.md`.
- Si existe solo `CLAUDE.md`, crear `AGENTS.md` hermano, mover allí contenido de `CLAUDE.md` y omitir únicamente primera línea cuando sea exactamente `@AGENTS.md`; después reemplazar `CLAUDE.md` por proxy correspondiente a su ubicación.
- Si ambos existen y `CLAUDE.md` ya está normalizado, no modificarlo.
- Si `CLAUDE.md` contiene instrucciones adicionales ausentes en `AGENTS.md`, migrarlas a `AGENTS.md` sin perder contenido y normalizar `CLAUDE.md`.
- Si ambos archivos son contradictorios, no sobrescribir automáticamente; informar paths exactos y solicitar resolución explícita.

Aplicar búsqueda recursiva cuando se solicite normalizar proyecto completo. Preservar contenido antes de migrarlo. No seguir ni sobrescribir symlinks automáticamente; tratar symlinks, directorios, archivos ilegibles y conflictos como resolución manual. Reportar archivos creados, migrados, normalizados, omitidos y conflictos.
