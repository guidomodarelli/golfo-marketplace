---
name: parallel-pr-hygiene
description: "Higiene de PRs cuando varias ramas, sesiones o agentes trabajan a la vez en el mismo repo: revisar qué está en vuelo antes de empezar (PRs abiertos, worktrees, últimos commits de main), trabajar en un worktree nuevo desde origin/main, evitar choques de versión al subir manifests (package.json, plugin.json), resolver conflictos de rebase que son solo de versión, limpiar worktrees de PRs mergeados y cerrar el pedido enviado (commit, push, PR y loop de review), salvo en equipos de trabajo con ~/.work. Usar siempre al abrir, rebasear o mergear un PR en un repo con otras sesiones activas, cuando el PR sube una versión, cuando un rebase choca en un manifest o cuando quedan worktrees de PRs ya mergeados."
license: MIT
metadata:
  version: "1.0.0"
  author: "Guido Modarelli"
  category: "git-workflow"
  tags: "pull-request, worktree, versioning, rebase, parallel-sessions, merge"
  command: "/parallel-pr-hygiene"
---

# Higiene de PRs en paralelo

Reglas genéricas para repos donde varias sesiones de agentes abren PRs a la vez. Las reglas propias de un repo (qué archivos llevan versión, qué validadores corren) viven en su `AGENTS.md` o en su skill de mantenimiento.

## Antes de empezar

- Listar lo que está en vuelo: `gh pr list --state open`, `git worktree list` y `git log --oneline -5 origin/main`. Otra sesión puede ser dueña de una rama o un PR del mismo tema; si un PR abierto toca los mismos archivos, avisar al usuario antes de duplicar trabajo.
- Trabajar en un worktree nuevo desde `origin/main`, nunca en el checkout principal: puede estar en la rama de otra sesión.

## Versionado

- Leer la versión de `origin/main` justo antes de subirla a mano (`git show origin/main:<manifest>`): en repos con mucho tráfico otra rama puede haberla subido minutos antes. Los checks de versión comparan contra la base del merge.
- Dos ramas que suben la versión a la vez: darle a cada una una versión distinta (por ejemplo minor en una, patch en la otra). La que mergea segunda rebasea y vuelve a subir por encima de `main`.
- Un conflicto de rebase que es solo de versión se resuelve quedándose con la más alta (durante un rebase, `--theirs` es tu commit) y volviendo a correr el check de versión. Esos checks suelen mirar commits, no el working tree: correrlos después de commitear.

## Loop de Codex

- Las reglas del loop de Codex (cómo se pide la review, qué no escribir en el cuerpo del PR) viven en este plugin (`golfo-github`): `codex-autofix-loop` y `pr-description-template`.
- Un PR mergeado deja su worktree en una rama borrada, y no puede pasar a `main` si el checkout principal la tiene. Si el worktree ya no se usa, confirmar que `git status` está limpio (los estados locales gitignored, como `.codex-autofix/`, no cuentan) y borrarlo con `git worktree remove` + `git branch -D <rama>`: `gh pr merge --delete-branch` corrido desde ese worktree borra la rama remota pero no la local. Si se va a reusar, estacionarlo con `git switch --detach origin/main`.

## Cierre

- Un pedido de cambio termina enviado sin que el usuario lo pida: commit solo de los archivos propios, push, PR (o push al PR abierto de esa rama) y loop de Codex lanzado. Excepción: si existe `~/.work` en la máquina (`test -e ~/.work`; en PowerShell `Test-Path ~/.work`), es un equipo de trabajo: no commitear, pushear ni abrir PR por iniciativa propia; dejar los cambios sin commitear y listarlos en el reporte, salvo que el usuario lo pida explícitamente. Verificar con `gh pr view N --json state,mergeCommit` antes de reportar que algo se mergeó.
