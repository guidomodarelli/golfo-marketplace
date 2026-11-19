---
name: feature-branch-pr
description: "Ship current branch changes end-to-end: create a feature/* branch (only if currently on a default branch), commit when needed, push, open a PR, and report a summary table. Use when the user asks to commit & push current changes and open a PR, 'subir los cambios y crear PR', 'branch + commit + push + PR', or to close out work-in-progress into a pull request."
allowed-tools: Bash(git:*) Bash(gh:*)
license: MIT
metadata:
  version: "1.1.0"
  author: "Guido Modarelli"
  category: "git-workflow"
  tags: "git, branch, commit, push, pull-request"
  command: "/feature-branch-pr"
---

# Feature Branch + Commit + Push + PR

Take the current uncommitted changes and ship them as a pull request in one closeout flow, then return a summary table.

## Alcance estricto

Ejecutar únicamente cierre solicitado: inspeccionar estado, crear/reutilizar branch, stage, commit, push, crear PR y verificar resultado.

- No iniciar code review, security audit, dependency audit, performance review ni análisis adicional salvo pedido explícito.
- No ejecutar tests, builds, linters o scanners adicionales. Hooks Git obligatorios pueden ejecutarse como parte de commit; no lanzar validaciones aparte.
- No invocar skills, agentes o workflows ajenos al flujo, excepto `pr-description-template` y, tras crear el PR, `codex-autofix-loop` (ver paso 6). Si una regla de mayor prioridad obliga una invocación, limitarla a determinar aplicabilidad; no expandir alcance.
- No modificar código, dependencias o configuración para corregir problemas descubiertos durante cierre.
- Si hook, commit, push o creación PR falla por contenido del repositorio, detener y reportar blocker; no aplicar fixes automáticos.
- No crear ni actualizar Jira, review comments, approvals, merge, labels ni estado del PR. Los fixes y el merge posteriores son del loop de Codex, no de esta skill.
- Writes permitidos: branch local, index Git, commit, push y creación/title/body del PR solicitado.
- Si una acción no es requisito directo para cierre pedido, omitirla.

Use when:
- the user asks to commit & push the current changes and open a PR
- "subir cambios y crear PR", "branch + commit + push + PR", closeout of WIP
- the working tree has changes that should become a pull request

## Contract

- Run only when the user explicitly asks to commit/push/PR. This skill performs outward-facing, hard-to-reverse actions (push + PR).
- **Branch rule (mandatory):** create a new `feature/<slug>` branch **only if** the current branch is a default branch (`develop`, `main`, or `master`). If the current branch is already anything else, **reuse it** — never branch off a branch.
- Never commit on `develop`/`main`/`master`. If on a default branch, you must create the feature branch first.
- Keep every technical name (branch, commit subject, PR title/body) in **English**. The summary table shown to the user is in **Spanish**.
- Do not force-push, do not skip hooks (`--no-verify`), do not bypass signing.
- End commit messages with the co-author/attribution trailer that the runtime provides for this session (e.g. the `Co-Authored-By:` line from the system instructions). Do not hardcode a model name: models change and a stale trailer misattributes the commit. If the runtime provides no trailer, omit it.
- If `gh` is unavailable or unauthenticated, stop before the PR step and report the push result plus the exact blocker.

## Steps

### 1. Inspect state and resolve PR base

Select first available remote base in this mandatory order:

```bash
BASE_REF=''
for candidate in origin/develop origin/master origin/main; do
  if git show-ref --verify --quiet "refs/remotes/$candidate"; then
    BASE_REF="$candidate"
    break
  fi
done

if [ -z "$BASE_REF" ]; then
  echo "No supported remote PR base found" >&2
  exit 1
fi

BASE_BRANCH="${BASE_REF#origin/}"
git rev-parse --abbrev-ref HEAD
git status --porcelain
git diff --stat "$BASE_REF"...HEAD
```

- If no remote ref exists in `origin/develop`, `origin/master`, or `origin/main`, stop and report that no supported PR base was found.
- Capture current branch name, selected `BASE_REF`, and `BASE_BRANCH` for later steps.
- Branch has changes to ship when working tree is dirty **or** `git diff --quiet "$BASE_REF"...HEAD` returns non-zero.
- If working tree is clean and branch has no diff against selected base, report nothing to ship and stop.
- A clean working tree with commits ahead of selected base is valid: skip commit step, continue with push and PR creation.

### 2. Check if a PR already exists for this branch

If the current branch is NOT a default branch, check whether a PR is already open:

```bash
gh pr view --json url --jq .url 2>/dev/null
```

- **PR exists** → this is a successive commit scenario. **Do NOT commit or push automatically.** Report working-tree state, branch diff against `BASE_REF`, and existing PR URL, then **stop**. User owns commit/push lifecycle after initial PR creation.
- **No PR exists** → continue with the full flow below.

### 3. Decide the branch

Default branches: `develop`, `main`, `master`.

- **Current branch IS a default branch** → create a new one. Derive a short, descriptive English slug from the change:

  ```bash
  git switch -c "feature/<slug>"
  ```

  `branchAction = "created"`.

- **Current branch is NOT a default branch** → reuse it. Do **not** create or rename anything.

  `branchAction = "reused"`.

Slug rules: lowercase, hyphen-separated, English, no spaces, no ticket-noise. Example: `feature/link-preapproval-checkout`.

### 4. Commit

- If working tree is clean and branch diff against `BASE_REF` exists, do not create empty commit; record `commitAction = "existing"` and continue.
- If working tree is dirty, stage everything and commit with a clear Conventional-Commit-style English subject plus a short body describing the change.

```bash
git add -A
git commit -m "$(cat <<'EOF'
<type>: <concise english subject>

<short english body: what changed and why>

<co-author trailer provided by the runtime, if any>
EOF
)"
```

On Windows PowerShell, use a single-quoted here-string (`@' ... '@`) for the message instead of the bash heredoc.

If a pre-commit hook fails, stop and report the blocker with the hook output — do not fix it automatically and do not bypass it (`--no-verify`).

### 5. Push

Push and set upstream on first push of the branch:

```bash
git push -u origin HEAD
```

Capture the push result and the remote tracking ref.

### 6. Open the PR

Check tooling first:

```bash
gh auth status
```

If `gh` is missing or unauthenticated, skip this step and record the blocker. Otherwise:

**Build the title and body in full-composition mode with the [pr-description-template](../pr-description-template/SKILL.md) skill** — fill every applicable section from the diff, remove optional sections that add no context, then write the body to a temp file and pass it with `--body-file`:

```bash
gh pr create --title "<english subject>" --body-file <tmp-body.md> --base "$BASE_BRANCH" --head <feature-branch>
```

- Base = `BASE_BRANCH`, selected from remote refs in this order: `origin/develop` → `origin/master` → `origin/main`. Use `--base "$BASE_BRANCH"`; do not replace this fallback with GitHub's default-branch metadata.
- Title in English; body follows the `pr-description-template` (Spanish prose, English code/identifiers).
- Mark exactly one primary change type, include reproducible manual steps, and keep only applicable HTTP contract changes.
- Mention automated coverage inside **Descripción** only when it adds reviewer context.
- Do not add a **Referencia** metadata block, Jira workflow rules, or invoke a ticket-tracker skill automatically.
- A later Jira association uses traceability-only mode and must not regenerate title or body.
- End the PR body with:

  ```
  🤖 Generated with [Claude Code](https://claude.com/claude-code)
  ```

- Capture the returned PR URL.
- Right after the PR is created, launch the Codex auto-fix loop for it without asking, following the «Arranque automático al abrir un PR» section of [codex-autofix-loop](../codex-autofix-loop/SKILL.md) (it also lists when not to launch it).

### 7. Report the summary table (Spanish)

Always close with a Markdown table summarizing the run:

| Paso | Resultado |
| --- | --- |
| Rama | `feature/<slug>` (creada \| reutilizada) |
| Base | `<BASE_BRANCH>` (seleccionada por fallback remoto) |
| Commit | `<short-hash>` — `<subject>` |
| Push | OK → `origin/<feature-branch>` |
| PR | `<pr-url>` (o motivo si no se creó) |
| Loop Codex | Lanzado (tope `<R>` rondas) \| No lanzado — `<motivo>` |

If any step was skipped or failed, show its real status in the table (e.g. `PR | No creado — gh no autenticado`) instead of reporting success.

## Edge cases

- **Clean tree:** if branch has no diff against selected `BASE_REF`, report nothing to ship and stop; if branch has commits ahead of selected base, skip commit and continue with push/PR.
- **Detached HEAD:** treat as non-default → create `feature/<slug>` so the work is not orphaned, then proceed.
- **PR already open for the branch (successive commits):** do NOT commit or push. Report working-tree state, branch diff against `BASE_REF`, and existing PR URL, then stop. User decides when and how to commit/push subsequent changes.
- **Push rejected (non-fast-forward):** do not force-push. Report the rejection and ask the user how to proceed.
- **No `origin` remote:** stop before base resolution and report missing remote; do not commit, push, or create PR.
